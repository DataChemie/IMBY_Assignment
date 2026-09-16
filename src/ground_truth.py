from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from .io_utils import (
    load_gt_manifest,
    load_gt_events,
    get_canonical_session_id,
    parse_iso,
    to_iso,
    ts_ms,
)


def extract_gt_intervals(session_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Extract and normalize ground truth execution intervals for a session.
    
    Uses gt_manifest.json if present, falling back to gt.jsonl.
    Null end_ts is closed at the next execution start, or at session_end
    for the final execution.
    """
    p = Path(session_path)
    canonical_id = get_canonical_session_id(p)
    gm = load_gt_manifest(p)
    
    intervals: List[Dict[str, Any]] = []
    
    if gm:
        session_end = gm.get("session", {}).get("end_ts")
        raw_executions = []
        for proc in gm.get("processes", []):
            code = proc.get("code", "")
            family = proc.get("family_name", code)
            domain = proc.get("domain", "")
            for ex in proc.get("executions", []):
                item = dict(ex)
                item["family_name"] = family
                item["domain"] = domain
                item["code"] = code
                raw_executions.append(item)
                
        # Chronological sort by start_ts
        raw_executions.sort(key=lambda x: x.get("start_ts", "") or "")
        
        for i, ex in enumerate(raw_executions):
            start = ex.get("start_ts")
            end = ex.get("end_ts")
            if not end:
                if i + 1 < len(raw_executions):
                    end = raw_executions[i + 1].get("start_ts")
                else:
                    end = session_end
            if start and end and start < end:
                intervals.append({
                    "session_id": canonical_id,
                    "code": ex.get("code", ""),
                    "label": ex.get("code") or ex.get("family_name", "unknown"),
                    "family_name": ex.get("family_name", ""),
                    "domain": ex.get("domain", ""),
                    "variant": ex.get("variant", "std"),
                    "case_id": ex.get("case_id", ""),
                    "start": start,
                    "end": end,
                })
        return intervals

    # Fallback to gt.jsonl
    gt_rows = load_gt_events(p)
    if not gt_rows:
        return []
        
    cur_proc = None
    cur_start = None
    
    for row in gt_rows:
        event = row.get("event")
        ts = row.get("ts_utc") or row.get("timestamp_iso")
        if event == "process_started":
            if cur_proc and cur_start and ts and cur_start < ts:
                intervals.append({
                    "session_id": canonical_id,
                    "code": cur_proc.get("process_code", ""),
                    "label": cur_proc.get("process_code") or cur_proc.get("process_name", "unknown"),
                    "family_name": cur_proc.get("process_name", ""),
                    "domain": "",
                    "variant": cur_proc.get("process_variant", "std"),
                    "case_id": cur_proc.get("case_id", ""),
                    "start": cur_start,
                    "end": ts,
                })
            cur_proc = row
            cur_start = ts
        elif event in ("process_switched_out", "process_suspended", "session_ended"):
            if cur_proc and cur_start and ts and cur_start < ts:
                intervals.append({
                    "session_id": canonical_id,
                    "code": cur_proc.get("process_code", ""),
                    "label": cur_proc.get("process_code") or cur_proc.get("process_name", "unknown"),
                    "family_name": cur_proc.get("process_name", ""),
                    "domain": "",
                    "variant": cur_proc.get("process_variant", "std"),
                    "case_id": cur_proc.get("case_id", ""),
                    "start": cur_start,
                    "end": ts,
                })
            cur_proc = None
            cur_start = None

    return intervals


def label_events_with_gt(events: List[Dict[str, Any]], intervals: List[Dict[str, Any]]) -> List[str]:
    """Label each raw event with the ground-truth process code/label it falls into."""
    parsed_intervals = []
    for iv in intervals:
        s_dt = parse_iso(iv["start"])
        e_dt = parse_iso(iv["end"])
        if s_dt and e_dt:
            parsed_intervals.append((int(s_dt.timestamp() * 1000), int(e_dt.timestamp() * 1000), iv["label"]))
            
    labels = []
    for e in events:
        t = ts_ms(e)
        matched_label = "__outside__"
        for s_ms, e_ms, lbl in parsed_intervals:
            if s_ms <= t <= e_ms:
                matched_label = lbl
                break
        labels.append(matched_label)
    return labels
