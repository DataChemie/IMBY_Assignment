import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.paths import OUTPUTS_DIR, REPORTS_DIR, SEGMENTS_JSONL_PATH
from src.io_utils import parse_iso, read_jsonl


def run_process_mining(segments_path: Path = SEGMENTS_JSONL_PATH) -> Dict[str, Any]:
    """Mine process execution statistics from segments.jsonl and rank automation candidates."""
    segments = read_jsonl(segments_path)
    if not segments:
        raise ValueError(f"No segments found at {segments_path}")

    # Process metrics
    proc_stats = defaultdict(lambda: {
        "executions": 0,
        "total_seconds": 0.0,
        "durations": [],
        "sessions": set(),
    })

    for s in segments:
        label = s.get("label", "unknown")
        s_dt = parse_iso(s.get("start"))
        e_dt = parse_iso(s.get("end"))
        dur = (e_dt - s_dt).total_seconds() if s_dt and e_dt else 0.0

        proc_stats[label]["executions"] += 1
        proc_stats[label]["total_seconds"] += dur
        proc_stats[label]["durations"].append(dur)
        proc_stats[label]["sessions"].add(s.get("session_id"))

    # Total observed working time
    total_fleet_time = sum(p["total_seconds"] for p in proc_stats.values())

    # Candidate evaluation criteria:
    # 1. Volume & Time: total seconds, frequency
    # 2. Determinism Score (0.0 to 1.0): rule-based predictability
    # 3. Feasibility Score (1 to 5): 5 = high feasibility (clean tabular/form I/O)
    # 4. Complexity Penalty (1 to 5): 1 = low complexity, 5 = heavy branching/free-form text
    # 5. Risk Assessment (Low/Medium/High)

    domain_characteristics = {
        "hr_payroll_deduction_processing": {
            "name_jp": "給与備考・控除整備",
            "domain": "HR",
            "determinism": 0.90,
            "feasibility": 5,
            "complexity": 2,
            "risk": "Low",
            "rationale": "High volume (33% of logged time), structured tabular inputs, standard arithmetic rules for allowances/deductions. Direct REST/DOM form filling."
        },
        "hr_maternity_childcare_leave_review": {
            "name_jp": "育児・産休申請確認",
            "domain": "HR",
            "determinism": 0.75,
            "feasibility": 4,
            "complexity": 3,
            "risk": "Medium",
            "rationale": "Frequent, but requires date arithmetic and cross-referencing company leave eligibility policies."
        },
        "hr_onboarding_verification": {
            "name_jp": "入社照合・手当確認",
            "domain": "HR",
            "determinism": 0.80,
            "feasibility": 4,
            "complexity": 2,
            "risk": "Low-Medium",
            "rationale": "High time consumption, repetitive checklist verification against new-hire employee records."
        },
        "hr_social_insurance_correction": {
            "name_jp": "社保・年金補正対応",
            "domain": "HR",
            "determinism": 0.70,
            "feasibility": 3,
            "complexity": 4,
            "risk": "Medium",
            "rationale": "Government-mandated pension tiers require strict compliance; edge cases require human judgment."
        },
        "hr_resident_tax_notification": {
            "name_jp": "住民税通知確認",
            "domain": "HR",
            "determinism": 0.85,
            "feasibility": 4,
            "complexity": 2,
            "risk": "Low",
            "rationale": "Repetitive monthly municipal tax record updates, straightforward field matching."
        },
        "finance_expense_approval": {
            "name_jp": "経費精算承認",
            "domain": "Finance",
            "determinism": 0.85,
            "feasibility": 5,
            "complexity": 2,
            "risk": "Low",
            "rationale": "Structured claim validation, receipt amount matching, policy limit checking."
        },
        "ops_contract_cancellation_processing": {
            "name_jp": "契約解除手続き",
            "domain": "Operations",
            "determinism": 0.65,
            "feasibility": 3,
            "complexity": 3,
            "risk": "Medium-High",
            "rationale": "Short duration, irregular clauses, potential customer legal implications."
        },
        "ops_inventory_adjustment": {
            "name_jp": "在庫調整",
            "domain": "Operations",
            "determinism": 0.80,
            "feasibility": 4,
            "complexity": 2,
            "risk": "Low",
            "rationale": "Warehouse SKU counting and stock reconciliation."
        },
        "finance_accounting_management": {
            "name_jp": "財務会計全般",
            "domain": "Finance",
            "determinism": 0.60,
            "feasibility": 3,
            "complexity": 4,
            "risk": "Medium",
            "rationale": "Broad category, heterogeneous general ledger entries."
        },
        "finance_budget_variance_analysis": {
            "name_jp": "予算差異分析",
            "domain": "Finance",
            "determinism": 0.50,
            "feasibility": 3,
            "complexity": 4,
            "risk": "High",
            "rationale": "Analytical cognitive task, high variance, low repetition in Dataset B."
        },
    }

    ranked_candidates = []
    for label, stats in proc_stats.items():
        if label in ("internal_communication_noise", "general_backoffice_work", "support_document_task"):
            continue

        meta = domain_characteristics.get(label, {
            "name_jp": label,
            "domain": "Other",
            "determinism": 0.50,
            "feasibility": 3,
            "complexity": 3,
            "risk": "Medium",
            "rationale": "Uncataloged operational procedure."
        })

        durations = stats["durations"]
        mean_dur = sum(durations) / max(1, len(durations))
        time_share = (stats["total_seconds"] / max(1.0, total_fleet_time)) * 100

        # ROI Score Calculation:
        # (Total Seconds * Determinism * Feasibility) / (Complexity * 100)
        roi_score = (stats["total_seconds"] * meta["determinism"] * meta["feasibility"]) / (meta["complexity"] * 100.0)

        ranked_candidates.append({
            "label": label,
            "name_jp": meta["name_jp"],
            "domain": meta["domain"],
            "executions": stats["executions"],
            "sessions_involved": len(stats["sessions"]),
            "total_seconds": round(stats["total_seconds"], 1),
            "mean_duration_sec": round(mean_dur, 1),
            "time_share_pct": round(time_share, 1),
            "determinism": meta["determinism"],
            "feasibility_score": meta["feasibility"],
            "complexity_score": meta["complexity"],
            "risk_level": meta["risk"],
            "roi_score": round(roi_score, 2),
            "rationale": meta["rationale"],
        })

    # Sort by ROI Score descending
    ranked_candidates.sort(key=lambda x: -x["roi_score"])

    # Assign priority ranks
    for idx, c in enumerate(ranked_candidates, 1):
        c["priority_rank"] = idx

    output_report = {
        "total_sessions_analyzed": len(set(s["session_id"] for s in segments)),
        "total_segments": len(segments),
        "total_monitored_work_hours": round(total_fleet_time / 3600.0, 2),
        "ranked_automation_candidates": ranked_candidates,
    }

    out_file = REPORTS_DIR / "process_mining_roi.json"
    out_file.write_text(json.dumps(output_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved Process Mining & ROI Prioritization to {out_file}")

    return output_report


def print_roi_table(report: Dict[str, Any]):
    print("=" * 100)
    print("STEP 2: AUTOMATION CANDIDATES RANKED BY PROJECTED ROI")
    print("=" * 100)
    header = f"{'Rank':<5} | {'Process Label':<35} | {'Domain':<8} | {'Execs':<5} | {'Total Time':<10} | {'Time %':<7} | {'ROI Score':<9} | {'Risk':<8}"
    print(header)
    print("-" * 100)
    for c in report["ranked_automation_candidates"]:
        row = f"#{c['priority_rank']:<4} | {c['label']:<35} | {c['domain']:<8} | {c['executions']:<5} | {c['total_seconds']:>7.0f}s   | {c['time_share_pct']:>5.1f}% | {c['roi_score']:>9.1f} | {c['risk_level']:<8}"
        print(row)
    print("=" * 100)
    print(f"\nTop Candidate #1: {report['ranked_automation_candidates'][0]['label']}")
    print(f"  Rationale: {report['ranked_automation_candidates'][0]['rationale']}")


if __name__ == "__main__":
    report = run_process_mining()
    print_roi_table(report)
