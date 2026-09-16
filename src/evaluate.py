import argparse
import json
import numpy as np
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

from .io_utils import (
    load_session_events,
    parse_iso,
    read_jsonl,
    ts_ms,
    get_canonical_session_id,
)
from .ground_truth import extract_gt_intervals


def _label_at_ms(t_ms: int, intervals: List[Dict[str, Any]]) -> str:
    """Find the label of the active interval covering timestamp t_ms."""
    for x in intervals:
        s_ms = int(parse_iso(x["start"]).timestamp() * 1000)
        e_ms = int(parse_iso(x["end"]).timestamp() * 1000)
        if s_ms <= t_ms <= e_ms:
            return x.get("code") or x.get("label", "__outside__")
    return "__outside__"


def compute_event_level_metrics(
    events: List[Dict[str, Any]],
    gt_intervals: List[Dict[str, Any]],
    pred_segments: List[Dict[str, Any]],
) -> Dict[str, float]:
    """Compute token-level classification accuracy, precision, recall, and F1."""
    y_true: List[str] = []
    y_pred: List[str] = []
    
    for e in events:
        t = ts_ms(e)
        true_label = _label_at_ms(t, gt_intervals)
        if true_label != "__outside__":
            y_true.append(true_label)
            y_pred.append(_label_at_ms(t, pred_segments))
            
    if not y_true:
        return {}
        
    p, r, f, _ = precision_recall_fscore_support(
        y_true, y_pred, average="weighted", zero_division=0
    )
    return {
        "event_accuracy": float(accuracy_score(y_true, y_pred)),
        "weighted_precision": float(p),
        "weighted_recall": float(r),
        "weighted_f1": float(f),
    }


def compute_boundary_error(
    pred_segments: List[Dict[str, Any]],
    gt_intervals: List[Dict[str, Any]],
) -> Optional[float]:
    """Compute average error in seconds between predicted and ground truth boundaries."""
    ps = []
    for x in pred_segments:
        s_dt = parse_iso(x["start"])
        e_dt = parse_iso(x["end"])
        if s_dt and e_dt:
            ps.extend([s_dt.timestamp() * 1000, e_dt.timestamp() * 1000])

    gs = []
    for x in gt_intervals:
        s_dt = parse_iso(x["start"])
        e_dt = parse_iso(x["end"])
        if s_dt and e_dt:
            gs.extend([s_dt.timestamp() * 1000, e_dt.timestamp() * 1000])

    if not ps or not gs:
        return None

    unused = gs[:]
    errs = []
    for p in ps:
        j = min(range(len(unused)), key=lambda k: abs(unused[k] - p))
        errs.append(abs(unused[j] - p) / 1000.0)
        unused.pop(j)
        if not unused:
            break
            
    return float(np.mean(errs)) if errs else None


def interval_overlap_seconds(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    """Calculate the overlap duration in seconds between two intervals."""
    s_a = parse_iso(a["start"]).timestamp()
    e_a = parse_iso(a["end"]).timestamp()
    s_b = parse_iso(b["start"]).timestamp()
    e_b = parse_iso(b["end"]).timestamp()
    
    overlap = min(e_a, e_b) - max(s_a, s_b)
    return max(0.0, overlap)


def evaluate_session_predictions(
    session_path: Path,
    pred_segments: List[Dict[str, Any]],
    events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Evaluate predicted segments for a single session against ground truth."""
    gt_intervals = extract_gt_intervals(session_path)
    if events is None:
        events = load_session_events(session_path)
        
    canonical_id = get_canonical_session_id(session_path)
    m = compute_event_level_metrics(events, gt_intervals, pred_segments)
    b_err = compute_boundary_error(pred_segments, gt_intervals)
    
    # Overlap and segment match rate
    matched_gt = 0
    correct_label_gt = 0
    used_pred = set()
    
    for gt in gt_intervals:
        best_pred_idx = None
        best_overlap = 0.0
        for i, pred in enumerate(pred_segments):
            if i in used_pred:
                continue
            overlap = interval_overlap_seconds(gt, pred)
            if overlap > best_overlap:
                best_overlap = overlap
                best_pred_idx = i
                
        if best_pred_idx is not None and best_overlap > 0:
            used_pred.add(best_pred_idx)
            matched_gt += 1
            pred = pred_segments[best_pred_idx]
            if pred.get("label") == gt.get("label") or pred.get("label") == gt.get("code"):
                correct_label_gt += 1
                
    match_rate = (correct_label_gt / len(gt_intervals)) if gt_intervals else None
    
    return {
        "session_id": canonical_id,
        "gt_segments": len(gt_intervals),
        "pred_segments": len(pred_segments),
        "matched_gt_segments": matched_gt,
        "correctly_labeled_gt_matches": correct_label_gt,
        "segment_label_match_rate": match_rate,
        "boundary_mean_error_seconds": b_err,
        **m,
    }
