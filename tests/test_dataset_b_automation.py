from pathlib import Path

from automation.prototype import run_full_dataset_b_automation
from config.paths import SEGMENTS_JSONL_PATH


def test_dataset_b_full_automation_generates_summary():
    result = run_full_dataset_b_automation(segments_path=SEGMENTS_JSONL_PATH)

    assert result["batch_metadata"]["total_records_processed"] > 0
    assert result["batch_metadata"]["automated_records"] >= 0
    assert result["batch_metadata"]["flagged_for_review"] >= 0
    assert "detailed_results" in result
