import sys
import json
import numpy as np
from pathlib import Path
from collections import Counter, defaultdict

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.paths import DATASET_A_DIR, REPORTS_DIR
from src.io_utils import load_session_events, parse_iso, ts_ms
from src.ground_truth import extract_gt_intervals


def analyze_gt_boundaries(num_sessions: int = 20):
    print("=" * 70)
    print("ANALYZING GROUND TRUTH BOUNDARY DYNAMICS (DATASET A)")
    print("=" * 70)
    
    a_zips = sorted(list(DATASET_A_DIR.glob("*.zip")))[:num_sessions]
    
    boundary_gap_seconds = []
    preceding_event_types = Counter()
    process_durations = defaultdict(list)
    boundary_app_switches = 0
    total_boundaries = 0
    
    for zp in a_zips:
        intervals = extract_gt_intervals(zp)
        events = load_session_events(zp)
        if not intervals or not events:
            continue
            
        evt_times = [ts_ms(e) for e in events]
        
        for iv in intervals:
            total_boundaries += 1
            start_ms = int(parse_iso(iv["start"]).timestamp() * 1000)
            end_ms = int(parse_iso(iv["end"]).timestamp() * 1000)
            dur_s = (end_ms - start_ms) / 1000.0
            process_durations[iv["label"]].append(dur_s)
            
            # Find closest event index to start_ms
            idx = min(range(len(evt_times)), key=lambda i: abs(evt_times[i] - start_ms))
            if idx > 0:
                prev_e = events[idx - 1]
                curr_e = events[idx]
                gap_s = (evt_times[idx] - evt_times[idx - 1]) / 1000.0
                boundary_gap_seconds.append(gap_s)
                preceding_event_types[curr_e.get("event_type")] += 1
                
                # Check if app switch occurred around boundary
                c_prev = prev_e.get("context") or {}
                a_prev = c_prev.get("active_app") or {}
                app_prev = (a_prev.get("app_name") or "")

                c_curr = curr_e.get("context") or {}
                a_curr = c_curr.get("active_app") or {}
                app_curr = (a_curr.get("app_name") or "")
                if app_prev != app_curr:
                    boundary_app_switches += 1

    print(f"Analyzed {total_boundaries} ground-truth boundaries across {len(a_zips)} sessions.")
    print(f"Boundaries with App Switch : {boundary_app_switches}/{total_boundaries} ({100 * boundary_app_switches / max(1, total_boundaries):.1f}%)")
    
    if boundary_gap_seconds:
        gaps = np.array(boundary_gap_seconds)
        print(f"\nInter-Event Gap at Boundary (seconds):")
        print(f"  Min   : {np.min(gaps):.2f}s")
        print(f"  Median: {np.median(gaps):.2f}s")
        print(f"  Mean  : {np.mean(gaps):.2f}s")
        print(f"  75th %: {np.percentile(gaps, 75):.2f}s")
        print(f"  90th %: {np.percentile(gaps, 90):.2f}s")
        print(f"  Max   : {np.max(gaps):.2f}s")

    print("\nEvent Types at Boundary Onset:")
    for etype, cnt in preceding_event_types.most_common(6):
        print(f"  {etype:<25}: {cnt:>4} ({100 * cnt / max(1, total_boundaries):.1f}%)")

    print("\nProcess Execution Durations (Median seconds):")
    for code, durs in sorted(process_durations.items(), key=lambda x: np.median(x[1])):
        print(f"  Process [{code}]: Median={np.median(durs):.1f}s | Mean={np.mean(durs):.1f}s | Min={np.min(durs):.1f}s | Max={np.max(durs):.1f}s | N={len(durs)}")


if __name__ == "__main__":
    analyze_gt_boundaries(25)
