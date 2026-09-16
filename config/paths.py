import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# Project root: C:\Users\User\Documents\ImBesideYouAssignment
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Provided data directories on user's system
DATASET_A_DIR = Path(os.getenv("DATASET_A"))
DATASET_B_DIR = Path(os.getenv("DATASET_B"))

# Project directories
SRC_DIR = PROJECT_ROOT / "src"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
REPORTS_DIR = PROJECT_ROOT / "reports"
AUTOMATION_DIR = PROJECT_ROOT / "automation"
DATA_CACHE_DIR = PROJECT_ROOT / "data_cache"

# Target deliverables
SEGMENTS_JSONL_PATH = OUTPUTS_DIR / "segments.jsonl"
FINAL_REPORT_PATH = REPORTS_DIR / "final_report.md"
WORK_LOG_PATH = REPORTS_DIR / "work_log.md"

# Ensure output and report directories exist
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
AUTOMATION_DIR.mkdir(parents=True, exist_ok=True)
DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
