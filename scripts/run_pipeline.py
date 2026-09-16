import argparse
import sys
import time
from pathlib import Path

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.paths import DATASET_A_DIR, DATASET_B_DIR, SEGMENTS_JSONL_PATH
from scripts.preflight_check import (
    check_python_environment,
    check_disk_and_directories,
    check_datasets,
)
from src.segmenter import segment_dataset_b
from src.process_miner import run_process_mining, print_roi_table
from scripts.test_prototype import test_prototype
from scripts.run_eval_a import evaluate_on_dataset_a


def run_full_pipeline(eval_a_sessions: int = 5):
    t_start = time.time()
    print("=" * 80)
    print("IMBESIDEYOU FDE EVALUATION: END-TO-END AUTOMATION & MINING PIPELINE")
    print("=" * 80)

    # 1. Pre-Flight Diagnostic Checks
    print("\n>>> PHASE 0: PRE-FLIGHT CHECKS <<<")
    if not (check_python_environment() and check_datasets()):
        print("Pre-flight checks failed. Aborting pipeline.")
        sys.exit(1)
    check_disk_and_directories()

    # 2. Step 1: Work Recovery & Segmentation on Dataset B
    print("\n>>> PHASE 1: WORK RECOVERY & SEGMENTATION (DATASET B) <<<")
    segments, seg_summary = segment_dataset_b(DATASET_B_DIR, SEGMENTS_JSONL_PATH)
    print(f"Generated {len(segments)} coherent work segments across {len(seg_summary['sessions'])} sessions.")
    print(f"Deliverable #1 saved: {SEGMENTS_JSONL_PATH}")

    # 2b. Evaluate Boundary Segmentation on Dataset A Ground Truth
    if eval_a_sessions > 0:
        print(f"\n>>> PHASE 1b: GROUND TRUTH VALIDATION (DATASET A: {eval_a_sessions} SESSIONS) <<<")
        evaluate_on_dataset_a(eval_a_sessions)

    # 3. Step 2: Process Mining & ROI Prioritization
    print("\n>>> PHASE 2: PROCESS MINING & ROI PRIORITIZATION <<<")
    roi_report = run_process_mining(SEGMENTS_JSONL_PATH)
    print_roi_table(roi_report)

    # 4. Step 3: Automation Prototype Execution & Testing
    print("\n>>> PHASE 3: AUTOMATION PROTOTYPE EXECUTION (TOP CANDIDATE) <<<")
    test_prototype()

    elapsed = time.time() - t_start
    print("\n" + "=" * 80)
    print(f">>> FULL PIPELINE COMPLETED SUCCESSFULLY IN {elapsed:.2f}s <<<")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run full ImBesideYou pipeline")
    parser.add_argument("--eval-a-sessions", type=int, default=5, help="Number of Dataset A sessions to evaluate against GT")
    args = parser.parse_args()

    run_full_pipeline(eval_a_sessions=args.eval_a_sessions)
