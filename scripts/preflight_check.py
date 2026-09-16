import os
import sys
import time
import shutil
import zipfile
from pathlib import Path

# Ensure UTF-8 console output on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.paths import (
    DATASET_A_DIR,
    DATASET_B_DIR,
    OUTPUTS_DIR,
    REPORTS_DIR,
    DATA_CACHE_DIR,
)
from src.io_utils import (
    get_canonical_session_id,
    load_session_events,
    load_gt_manifest,
    load_gt_events,
)
from src.ground_truth import extract_gt_intervals


def check_python_environment():
    print("=" * 70)
    print("1. PYTHON & DEPENDENCY ENVIRONMENT CHECK")
    print("=" * 70)
    print(f"Python Executable: {sys.executable}")
    print(f"Python Version   : {sys.version.split()[0]}")
    
    required_packages = [
        "numpy",
        "pandas",
        "sklearn",
        "joblib",
        "matplotlib",
        "tqdm",
    ]
    all_ok = True
    for pkg in required_packages:
        try:
            mod = __import__(pkg)
            version = getattr(mod, "__version__", "installed")
            print(f"  [OK] {pkg:<15} version: {version}")
        except ImportError as e:
            print(f"  [FAIL] {pkg:<15} ERROR: {e}")
            all_ok = False
            
    return all_ok


def check_disk_and_directories():
    print("\n" + "=" * 70)
    print("2. STORAGE & DIRECTORY PERMISSIONS CHECK")
    print("=" * 70)
    total, used, free = shutil.disk_usage(PROJECT_ROOT)
    free_gb = free / (1024 ** 3)
    total_gb = total / (1024 ** 3)
    print(f"Project Root     : {PROJECT_ROOT}")
    print(f"Disk Free Space  : {free_gb:.2f} GB / {total_gb:.2f} GB total")
    if free_gb < 5:
        print("  [WARN] Low disk space (< 5 GB). Avoid extracting full screenshot zips.")
    else:
        print("  [OK] Ample disk space available.")

    for d in [OUTPUTS_DIR, REPORTS_DIR, DATA_CACHE_DIR]:
        test_file = d / ".write_test"
        try:
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            print(f"  [OK] Directory writable: {d.name}/")
        except Exception as e:
            print(f"  [FAIL] Directory write error {d.name}/: {e}")


def check_datasets():
    print("\n" + "=" * 70)
    print("3. DATASET REPOSITORY AUDIT")
    print("=" * 70)
    
    # Dataset A
    print(f"Dataset A Location: {DATASET_A_DIR}")
    if not DATASET_A_DIR.exists():
        print("  [FAIL] Dataset A directory does not exist!")
        return False
    a_zips = sorted(list(DATASET_A_DIR.glob("*.zip")))
    a_dirs = sorted([p for p in DATASET_A_DIR.glob("ses_*") if p.is_dir()])
    a_items = a_zips if a_zips else a_dirs
    print(f"  Found {len(a_items)} session items in Dataset A (zips={len(a_zips)}, dirs={len(a_dirs)})")
    
    # Dataset B
    print(f"\nDataset B Location: {DATASET_B_DIR}")
    if not DATASET_B_DIR.exists():
        print("  [FAIL] Dataset B directory does not exist!")
        return False
    b_zips = sorted(list(DATASET_B_DIR.glob("*.zip")))
    b_dirs = sorted([p for p in DATASET_B_DIR.glob("ses_*") if p.is_dir()])
    b_items = b_zips if b_zips else b_dirs
    print(f"  Found {len(b_items)} session items in Dataset B (zips={len(b_zips)}, dirs={len(b_dirs)})")
    
    return len(a_items) > 0 and len(b_items) > 0


def run_sampling_test():
    print("\n" + "=" * 70)
    print("4. STREAMING I/O & GROUND TRUTH SAMPLING TEST")
    print("=" * 70)
    
    a_zips = sorted(list(DATASET_A_DIR.glob("*.zip")))
    if a_zips:
        sample_a = a_zips[0]
        sid_a = get_canonical_session_id(sample_a)
        print(f"Sampling Dataset A: {sample_a.name}")
        print(f"  Canonical ID  : {sid_a}")
        
        t0 = time.time()
        evts_a = load_session_events(sample_a)
        t_load = time.time() - t0
        print(f"  Events Loaded : {len(evts_a):,} events in {t_load:.2f}s ({len(evts_a)/max(0.01, t_load):,.0f} evts/sec)")
        
        gt_manifest = load_gt_manifest(sample_a)
        print(f"  GT Manifest   : {'Present' if gt_manifest else 'Missing'}")
        if gt_manifest:
            procs = gt_manifest.get("processes", [])
            print(f"    Processes in Manifest: {len(procs)}")
            
        gt_intervals = extract_gt_intervals(sample_a)
        print(f"  GT Intervals  : {len(gt_intervals)} execution intervals extracted")
        if gt_intervals:
            print(f"    First GT interval: {gt_intervals[0]}")

    b_zips = sorted(list(DATASET_B_DIR.glob("*.zip")))
    if b_zips:
        sample_b = b_zips[0]
        sid_b = get_canonical_session_id(sample_b)
        print(f"\nSampling Dataset B: {sample_b.name}")
        print(f"  Canonical ID  : {sid_b}")
        
        t0 = time.time()
        evts_b = load_session_events(sample_b)
        t_load = time.time() - t0
        print(f"  Events Loaded : {len(evts_b):,} events in {t_load:.2f}s ({len(evts_b)/max(0.01, t_load):,.0f} evts/sec)")
        if evts_b:
            print(f"    First Event : type={evts_b[0].get('event_type')}, layer={evts_b[0].get('layer')}, time={evts_b[0].get('timestamp_iso')}")
            print(f"    Last Event  : type={evts_b[-1].get('event_type')}, layer={evts_b[-1].get('layer')}, time={evts_b[-1].get('timestamp_iso')}")


def main():
    print("\nStarting Antigravity Pre-Flight Diagnostic Checks...")
    py_ok = check_python_environment()
    check_disk_and_directories()
    ds_ok = check_datasets()
    if ds_ok:
        run_sampling_test()
    print("\n" + "=" * 70)
    if py_ok and ds_ok:
        print(">>> ALL PRE-FLIGHT CHECKS PASSED SUCCESSFULLY! <<<")
    else:
        print(">>> PRE-FLIGHT CHECKS REPORTED ISSUES (SEE ABOVE) <<<")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
