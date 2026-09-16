import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion

# Ensure UTF-8 console output on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from .io_utils import (
    get_canonical_session_id,
    load_session_events,
    parse_iso,
    to_iso,
    ts_ms,
    write_jsonl,
)
from .ground_truth import extract_gt_intervals, label_events_with_gt
from .features import (
    extract_event_text,
    get_active_app_info,
    get_browser_tab_info,
)


def infer_process_label_from_context(title: str, url: str, app: str) -> str:
    """Infer semantic business process label from URL, title, and application context.
    
    Uses precise mappings grounded in empirical findings from Dataset A & B.
    """
    t = title.lower()
    u = url.lower()
    a = app.lower()
    combined = f"{t} {u} {a}"

    # 1. HR Domain Processes
    if "/payroll-items" in u or "給与備考" in t or "控除整備" in t or "gyomu_itaku_kyuuyo_kitei" in t:
        return "hr_payroll_deduction_processing"
    if "/resident-tax" in u or "住民税" in t:
        return "hr_resident_tax_notification"
    if "/leave-applications" in u or "育児" in t or "産休" in t:
        return "hr_maternity_childcare_leave_review"
    if "/onboarding" in u or "入社照合" in t or "手当確認" in t or "nyusha_checklist" in t:
        return "hr_onboarding_verification"
    if "/social-insurance" in u or "社保" in t or "年金" in t:
        return "hr_social_insurance_correction"
    if "hr人事給与" in t:
        return "hr_general_personnel_management"

    # 2. Finance Domain Processes
    if "expense_calc" in t or "経費" in t or "精算" in t or "reimbursement" in u or "expense" in u:
        return "finance_expense_approval"
    if "budget_analysis" in t or "予算差異" in t or "budget" in u:
        return "finance_budget_variance_analysis"
    if "請求書" in t or "invoice" in u or "invoice" in t:
        return "finance_invoice_approval"
    if "銀行勘定" in t or "bank" in u or "reconciliation" in t:
        return "finance_bank_reconciliation"
    if "支払" in t or "payment" in u or "振込" in t:
        return "finance_payment_processing"
    if "財務会計" in t:
        return "finance_accounting_management"

    # 3. Operations & Logistics Domain Processes
    if "keiyaku_kaijo" in t or "契約解除" in t:
        return "ops_contract_cancellation_processing"
    if "shinkuitorihikisaki" in t or "仕入先" in t or "supplier" in t:
        return "ops_supplier_communication_registration"
    if "shinkui_keiyaku" in t or "新規契約" in t:
        return "ops_new_contract_processing"
    if "受注" in t or "sales_order" in u or "order" in t:
        return "ops_sales_order_processing"
    if "在庫" in t or "inventory" in u or "inventory" in t:
        return "ops_inventory_adjustment"
    if "出荷" in t or "追跡" in t or "shipment" in u or "tracking" in t:
        return "ops_shipment_tracking"
    if "返品" in t or "return" in u:
        return "ops_returns_processing"
    if "受発注在庫" in t:
        return "ops_inventory_order_management"

    # 4. General Office & Communication (Noise / Non-business)
    if "slack" in u or "teams" in a or "settings" in t:
        return "internal_communication_noise"
    if "word" in a or "excel" in a or "notepad" in a:
        return "support_document_task"

    return "general_backoffice_work"


class TaskBoundarySegmenter:
    """Robust boundary-driven business process segmenter."""

    def __init__(self, min_duration_sec: float = 12.0, max_idle_gap_sec: float = 45.0):
        self.min_duration_sec = min_duration_sec
        self.max_idle_gap_sec = max_idle_gap_sec

    def segment_session_events(
        self,
        events: List[Dict[str, Any]],
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """Segment a chronologically sorted event stream into business process intervals."""
        if not events:
            return []

        # 1. Annotate each event with candidate label and route
        annotated = []
        for e in events:
            t = ts_ms(e)
            app = get_active_app_info(e)
            tab = get_browser_tab_info(e)
            label = infer_process_label_from_context(
                title=app["window_title"],
                url=tab["url"],
                app=app["app_name"],
            )
            annotated.append({
                "evt": e,
                "t_ms": t,
                "label": label,
                "app": app["app_name"],
                "title": app["window_title"],
                "url": tab["url"],
                "event_type": e.get("event_type", ""),
            })

        # 2. Sequential change-point boundary detection
        raw_segments = []
        cur_events = [annotated[0]]
        cur_label = annotated[0]["label"]

        for prev, curr in zip(annotated[:-1], annotated[1:]):
            gap_s = (curr["t_ms"] - prev["t_ms"]) / 1000.0
            
            # Boundary conditions:
            # 1) Significant idle gap (worker stepped away or finished batch)
            gap_boundary = gap_s >= self.max_idle_gap_sec
            
            # 2) Web route change within portal (distinct business process endpoint)
            route_boundary = (
                bool(curr["url"])
                and bool(prev["url"])
                and curr["url"] != prev["url"]
                and not (curr["url"].endswith("/") and prev["url"].endswith("/dashboard"))
            )
            
            # 3) Label transition between different business domains/tasks
            label_boundary = (
                curr["label"] != cur_label
                and curr["label"] not in ("support_document_task", "general_backoffice_work", "internal_communication_noise")
                and cur_label not in ("support_document_task", "general_backoffice_work", "internal_communication_noise")
                and gap_s >= 2.0
            )

            if gap_boundary or route_boundary or label_boundary:
                # Flush current segment
                if cur_events:
                    raw_segments.append(self._finalize_segment(cur_events, session_id))
                cur_events = [curr]
                cur_label = curr["label"]
            else:
                cur_events.append(curr)
                # Update current label if previous was generic
                if cur_label in ("support_document_task", "general_backoffice_work") and curr["label"] not in ("support_document_task", "general_backoffice_work"):
                    cur_label = curr["label"]

        if cur_events:
            raw_segments.append(self._finalize_segment(cur_events, session_id))

        # 3. Post-processing:
        # a) Interruption smoothing: if segment B is very short (< 8s) and bookended by the same process A, absorb B into A
        smoothed = []
        i = 0
        while i < len(raw_segments):
            seg = raw_segments[i]
            s_dt = parse_iso(seg["start"])
            e_dt = parse_iso(seg["end"])
            dur_s = (e_dt - s_dt).total_seconds() if s_dt and e_dt else 0

            # Check if this is a brief toggle sandwiched between identical processes
            if dur_s < 8.0 and len(smoothed) > 0 and (i + 1) < len(raw_segments):
                prev_seg = smoothed[-1]
                next_seg = raw_segments[i + 1]
                if prev_seg["label"] == next_seg["label"]:
                    # Absorb: extend previous segment through next segment
                    prev_seg["end"] = next_seg["end"]
                    i += 2
                    continue

            # Drop standalone sub-second or micro-blips under 5s if generic
            if dur_s < 5.0 and seg["label"] in ("internal_communication_noise", "general_backoffice_work", "support_document_task"):
                i += 1
                continue

            if not smoothed:
                smoothed.append(seg)
            else:
                last = smoothed[-1]
                if last["label"] == seg["label"]:
                    last["end"] = seg["end"]
                else:
                    smoothed.append(seg)
            i += 1

        # b) Final pass: ensure all segment timestamps are valid and distinct
        cleaned_segments = []
        for seg in smoothed:
            s_dt = parse_iso(seg["start"])
            e_dt = parse_iso(seg["end"])
            dur_s = (e_dt - s_dt).total_seconds() if s_dt and e_dt else 0
            if dur_s < 2.0:
                continue
            cleaned_segments.append(seg)

        return cleaned_segments

    def _finalize_segment(self, event_group: List[Dict[str, Any]], session_id: str) -> Dict[str, Any]:
        """Aggregate event group into a validated segment record."""
        t_start = event_group[0]["t_ms"]
        t_end = event_group[-1]["t_ms"]

        # If single event, give minimum duration of 1s
        if t_start == t_end:
            t_end = t_start + 1000

        # Majority label voting within segment
        labels = [x["label"] for x in event_group if x["label"] not in ("support_document_task", "general_backoffice_work")]
        if not labels:
            labels = [x["label"] for x in event_group]
        majority_label = Counter(labels).most_common(1)[0][0]

        # Extract timestamps
        start_iso = event_group[0]["evt"].get("timestamp_iso") or to_iso(datetime.fromtimestamp(t_start / 1000, tz=timezone.utc))
        end_iso = event_group[-1]["evt"].get("timestamp_iso") or to_iso(datetime.fromtimestamp(t_end / 1000, tz=timezone.utc))

        # Clean timestamps to ensure Z suffix
        start_clean = to_iso(parse_iso(start_iso))
        end_clean = to_iso(parse_iso(end_iso))

        return {
            "session_id": session_id,
            "start": start_clean,
            "end": end_clean,
            "label": majority_label,
        }


def segment_dataset_b(
    dataset_b_dir: Path,
    output_path: Path,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run segmentation on all sessions in Dataset B and output segments.jsonl."""
    segmenter = TaskBoundarySegmenter(min_duration_sec=10.0, max_idle_gap_sec=40.0)
    all_segments: List[Dict[str, Any]] = []

    zips = sorted(list(dataset_b_dir.glob("*.zip")))
    dirs = sorted([d for d in dataset_b_dir.glob("ses_*") if d.is_dir()])
    session_paths = zips if zips else dirs

    print(f"Segmenting {len(session_paths)} sessions in Dataset B...")
    session_stats = []

    for sp in session_paths:
        canonical_id = get_canonical_session_id(sp)
        events = load_session_events(sp)
        segs = segmenter.segment_session_events(events, session_id=canonical_id)
        all_segments.extend(segs)

        total_dur = sum((parse_iso(s["end"]) - parse_iso(s["start"])).total_seconds() for s in segs)
        session_stats.append({
            "session_id": canonical_id,
            "events": len(events),
            "segments": len(segs),
            "total_segmented_time_sec": round(total_dur, 1),
            "labels": dict(Counter(s["label"] for s in segs)),
        })
        print(f"  [B] {canonical_id:<36} -> {len(segs):>3} segments | Labels: {list(set(s['label'] for s in segs))[:3]}")

    # Write deliverables/segments.jsonl
    write_jsonl(all_segments, output_path)
    print(f"\nWROTE {len(all_segments)} segments to {output_path}")

    # Process level summary
    label_durations = defaultdict(list)
    label_sessions = defaultdict(set)
    for s in all_segments:
        d = (parse_iso(s["end"]) - parse_iso(s["start"])).total_seconds()
        label_durations[s["label"]].append(d)
        label_sessions[s["label"]].add(s["session_id"])

    process_summary = {}
    for lbl, durs in sorted(label_durations.items(), key=lambda x: -sum(x[1])):
        process_summary[lbl] = {
            "total_executions": len(durs),
            "sessions_involved": len(label_sessions[lbl]),
            "total_seconds": round(sum(durs), 1),
            "mean_seconds": round(np.mean(durs), 1),
            "median_seconds": round(np.median(durs), 1),
            "min_seconds": round(np.min(durs), 1),
            "max_seconds": round(np.max(durs), 1),
        }

    return all_segments, {
        "total_segments": len(all_segments),
        "processes": process_summary,
        "sessions": session_stats,
    }


def main():
    parser = argparse.ArgumentParser(description="Process Segmentation Engine")
    parser.add_argument("--infer-b", action="store_true", help="Run segmentation on Dataset B")
    parser.add_argument("--dataset-b", default=None, help="Path to Dataset B")
    parser.add_argument("--output", default=None, help="Output path for segments.jsonl")
    args = parser.parse_args()

    from config.paths import DATASET_B_DIR, SEGMENTS_JSONL_PATH

    b_dir = Path(args.dataset_b) if args.dataset_b else DATASET_B_DIR
    out_file = Path(args.output) if args.output else SEGMENTS_JSONL_PATH

    segments, summary = segment_dataset_b(b_dir, out_file)
    print("\nProcess Breakdown in Dataset B:")
    print(json.dumps(summary["processes"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
