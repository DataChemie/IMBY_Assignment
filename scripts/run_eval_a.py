import json
import sys
from pathlib import Path
from typing import List

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.paths import DATASET_A_DIR, OUTPUTS_DIR
from src.segmenter import TaskBoundarySegmenter
from src.io_utils import load_session_events, get_canonical_session_id, write_jsonl
from src.evaluate import evaluate_session_predictions


def evaluate_on_dataset_a(num_sessions: int = 15):
    print("=" * 70)
    print(f"EVALUATING SEGMENTATION ON DATASET A (SAMPLE: {num_sessions} SESSIONS)")
    print("=" * 70)

    segmenter = TaskBoundarySegmenter(min_duration_sec=10.0, max_idle_gap_sec=40.0)
    zips = sorted(list(DATASET_A_DIR.glob("*.zip")))[:num_sessions]

    all_preds = []
    session_results = []

    for zp in zips:
        sid = get_canonical_session_id(zp)
        events = load_session_events(zp)
        preds = segmenter.segment_session_events(events, session_id=sid)
        all_preds.extend(preds)

        res = evaluate_session_predictions(zp, preds, events=events)
        session_results.append(res)
        b_err_str = f"{res['boundary_mean_error_seconds']:.2f}s" if res['boundary_mean_error_seconds'] is not None else "N/A"
        print(f"  {sid:<36} | GT: {res['gt_segments']:>2} | Pred: {res['pred_segments']:>2} | Matched: {res['matched_gt_segments']:>2} | BoundaryErr: {b_err_str:>7}")

    valid_b_errs = [s["boundary_mean_error_seconds"] for s in session_results if s["boundary_mean_error_seconds"] is not None]
    mean_b_err = sum(valid_b_errs) / len(valid_b_errs) if valid_b_errs else 0.0

    total_gt = sum(s["gt_segments"] for s in session_results)
    total_matched = sum(s["matched_gt_segments"] for s in session_results)
    total_pred = sum(s["pred_segments"] for s in session_results)

    summary = {
        "sessions_evaluated": len(session_results),
        "total_gt_segments": total_gt,
        "total_pred_segments": total_pred,
        "total_matched_segments": total_matched,
        "gt_segment_recall": round(total_matched / max(1, total_gt), 3),
        "precision_approx": round(total_matched / max(1, total_pred), 3),
        "mean_boundary_error_seconds": round(mean_b_err, 2),
    }

    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY ON DATASET A:")
    print("=" * 70)
    print(f"  Total Ground Truth Segments: {total_gt}")
    print(f"  Total Predicted Segments   : {total_pred}")
    print(f"  Matched Segments           : {total_matched} ({summary['gt_segment_recall'] * 100:.1f}% GT recall)")
    print(f"  Mean Boundary Error        : {summary['mean_boundary_error_seconds']:.2f} seconds")
    print("=" * 70)

    eval_out = OUTPUTS_DIR / "dataset_a_evaluation.json"
    eval_out.write_text(json.dumps({"summary": summary, "per_session": session_results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved evaluation details to {eval_out}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    evaluate_on_dataset_a(n)
