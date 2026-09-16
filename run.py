import argparse
import sys
from pathlib import Path

# Ensure UTF-8 console output on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    parser = argparse.ArgumentParser(description="ImBesideYou FDE Project CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. Preflight
    subparsers.add_parser("preflight", help="Run environment and dataset diagnostic checks")

    # 2. EDA
    eda_p = subparsers.add_parser("eda", help="Run cross-dataset exploratory data analysis")
    eda_p.add_argument("--max-a", type=int, default=15, help="Number of Dataset A sessions to analyze")

    # 3. Segment Dataset B
    seg_p = subparsers.add_parser("segment", help="Run segmentation on Dataset B (Generate Deliverable 1: segments.jsonl)")
    seg_p.add_argument("--output", default=None, help="Custom output path for segments.jsonl")

    # 4. Evaluate on Dataset A
    eval_p = subparsers.add_parser("eval-a", help="Evaluate segmentation on Dataset A ground truth")
    eval_p.add_argument("--sessions", type=int, default=62, help="Number of Dataset A sessions to evaluate")

    # 5. Process Mining & ROI
    subparsers.add_parser("mine", help="Run process mining and ROI candidate ranking (Step 2)")

    # 6. Test Prototype
    subparsers.add_parser("prototype", help="Run and test Step 3 Automation Prototype")

    # 7. All
    all_p = subparsers.add_parser("all", help="Execute entire end-to-end pipeline sequentially")
    all_p.add_argument("--eval-a-sessions", type=int, default=62, help="Number of Dataset A sessions for GT evaluation")

    args = parser.parse_args()

    if args.command == "preflight":
        from scripts.preflight_check import main as preflight_main
        preflight_main()
    elif args.command == "eda":
        from scripts.run_eda import run_eda
        run_eda(max_a_sessions=args.max_a)
    elif args.command == "segment":
        from config.paths import DATASET_B_DIR, SEGMENTS_JSONL_PATH
        from src.segmenter import segment_dataset_b
        out_path = Path(args.output) if args.output else SEGMENTS_JSONL_PATH
        segment_dataset_b(DATASET_B_DIR, out_path)
    elif args.command == "eval-a":
        from scripts.run_eval_a import evaluate_on_dataset_a
        evaluate_on_dataset_a(num_sessions=args.sessions)
    elif args.command == "mine":
        from src.process_miner import run_process_mining, print_roi_table
        report = run_process_mining()
        print_roi_table(report)
    elif args.command == "prototype":
        from scripts.test_prototype import test_prototype
        test_prototype()
    elif args.command == "all":
        from scripts.run_pipeline import run_full_pipeline
        run_full_pipeline(eval_a_sessions=args.eval_a_sessions)


if __name__ == "__main__":
    main()
