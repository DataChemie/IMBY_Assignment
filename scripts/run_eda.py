import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

# Ensure UTF-8 console output on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.paths import DATASET_A_DIR, DATASET_B_DIR, REPORTS_DIR
from src.io_utils import (
    load_session_events,
    load_gt_manifest,
    get_canonical_session_id,
    ts_ms,
)
from src.features import get_active_app_info, get_browser_tab_info


def analyze_session_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze event sequence for a single session."""
    stats = {
        "event_count": len(events),
        "event_types": Counter(),
        "layers": Counter(),
        "apps": Counter(),
        "window_titles": Counter(),
        "browser_urls": Counter(),
        "shortcuts": Counter(),
        "gaps_ms": [],
    }
    
    prev_t = None
    for evt in events:
        etype = evt.get("event_type", "unknown")
        layer = evt.get("layer", "unknown")
        stats["event_types"][etype] += 1
        stats["layers"][layer] += 1
        
        app_info = get_active_app_info(evt)
        if app_info["app_name"]:
            stats["apps"][app_info["app_name"]] += 1
        if app_info["window_title"]:
            stats["window_titles"][app_info["window_title"]] += 1
            
        tab_info = get_browser_tab_info(evt)
        if tab_info["url"]:
            stats["browser_urls"][tab_info["url"]] += 1
            
        # Shortcuts
        if etype == "shortcut":
            p = evt.get("payload") or {}
            key = p.get("shortcut") or p.get("key") or ""
            if key:
                stats["shortcuts"][key] += 1
                
        # Inter-event gaps
        t = ts_ms(evt)
        if prev_t is not None and t >= prev_t:
            gap = t - prev_t
            if gap < 600000: # filter gaps > 10 min
                stats["gaps_ms"].append(gap)
        prev_t = t
        
    return stats


def run_eda(max_a_sessions: int = 15):
    print("=" * 70)
    print("STARTING EXPLORATORY DATA ANALYSIS (EDA)")
    print("=" * 70)
    
    b_zips = sorted(list(DATASET_B_DIR.glob("*.zip")))
    a_zips = sorted(list(DATASET_A_DIR.glob("*.zip")))[:max_a_sessions]
    
    print(f"Analyzing {len(a_zips)} Dataset A sessions and {len(b_zips)} Dataset B sessions...")
    
    eda_results = {
        "dataset_a": {"sessions": len(a_zips), "total_events": 0, "apps": Counter(), "window_titles": Counter(), "urls": Counter(), "event_types": Counter(), "shortcuts": Counter()},
        "dataset_b": {"sessions": len(b_zips), "total_events": 0, "apps": Counter(), "window_titles": Counter(), "urls": Counter(), "event_types": Counter(), "shortcuts": Counter(), "session_summaries": []},
    }
    
    # Process Dataset B (All 15 sessions)
    print("\n--- Processing Dataset B (Production Data) ---")
    t0 = time.time()
    for zp in b_zips:
        sid = get_canonical_session_id(zp)
        evts = load_session_events(zp)
        res = analyze_session_events(evts)
        eda_results["dataset_b"]["total_events"] += len(evts)
        eda_results["dataset_b"]["apps"].update(res["apps"])
        eda_results["dataset_b"]["window_titles"].update(res["window_titles"])
        eda_results["dataset_b"]["urls"].update(res["browser_urls"])
        eda_results["dataset_b"]["event_types"].update(res["event_types"])
        eda_results["dataset_b"]["shortcuts"].update(res["shortcuts"])
        
        duration_sec = (ts_ms(evts[-1]) - ts_ms(evts[0])) / 1000.0 if len(evts) > 1 else 0
        eda_results["dataset_b"]["session_summaries"].append({
            "session_id": sid,
            "events": len(evts),
            "duration_sec": round(duration_sec, 1),
            "top_apps": [k for k, _ in res["apps"].most_common(3)],
            "top_titles": [k for k, _ in res["window_titles"].most_common(3)],
        })
        print(f"  [B] {sid:<38} | {len(evts):>5} evts | {duration_sec:>6.1f}s | Apps: {', '.join(res['apps'].keys())[:40]}")

    # Process sample of Dataset A
    print(f"\n--- Processing Dataset A ({len(a_zips)} sessions sample) ---")
    for zp in a_zips:
        sid = get_canonical_session_id(zp)
        evts = load_session_events(zp)
        res = analyze_session_events(evts)
        eda_results["dataset_a"]["total_events"] += len(evts)
        eda_results["dataset_a"]["apps"].update(res["apps"])
        eda_results["dataset_a"]["window_titles"].update(res["window_titles"])
        eda_results["dataset_a"]["urls"].update(res["browser_urls"])
        eda_results["dataset_a"]["event_types"].update(res["event_types"])
        eda_results["dataset_a"]["shortcuts"].update(res["shortcuts"])

    print(f"\nCompleted in {time.time() - t0:.2f}s")
    
    # Save structured summary
    summary_path = REPORTS_DIR / "eda_summary.json"
    serializable = {
        "dataset_a": {
            "sessions_analyzed": len(a_zips),
            "total_events": eda_results["dataset_a"]["total_events"],
            "top_apps": eda_results["dataset_a"]["apps"].most_common(10),
            "top_titles": eda_results["dataset_a"]["window_titles"].most_common(15),
            "top_urls": eda_results["dataset_a"]["urls"].most_common(10),
            "event_types": eda_results["dataset_a"]["event_types"].most_common(10),
            "top_shortcuts": eda_results["dataset_a"]["shortcuts"].most_common(10),
        },
        "dataset_b": {
            "sessions_analyzed": len(b_zips),
            "total_events": eda_results["dataset_b"]["total_events"],
            "top_apps": eda_results["dataset_b"]["apps"].most_common(10),
            "top_titles": eda_results["dataset_b"]["window_titles"].most_common(15),
            "top_urls": eda_results["dataset_b"]["urls"].most_common(10),
            "event_types": eda_results["dataset_b"]["event_types"].most_common(10),
            "top_shortcuts": eda_results["dataset_b"]["shortcuts"].most_common(10),
            "sessions": eda_results["dataset_b"]["session_summaries"],
        }
    }
    summary_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved EDA report to {summary_path}")

    # Print Key Comparative Insights
    print("\n" + "=" * 70)
    print("KEY COMPARATIVE EDA FINDINGS (DATASET A vs DATASET B)")
    print("=" * 70)
    print("Top Applications in Dataset A:")
    for app, count in eda_results["dataset_a"]["apps"].most_common(5):
        print(f"  {app:<30}: {count:>6} events")
        
    print("\nTop Applications in Dataset B:")
    for app, count in eda_results["dataset_b"]["apps"].most_common(5):
        print(f"  {app:<30}: {count:>6} events")
        
    print("\nTop Window Titles in Dataset B:")
    for title, count in eda_results["dataset_b"]["window_titles"].most_common(10):
        print(f"  {title:<45}: {count:>5} events")

    print("\nTop Visited Web Routes in Dataset B:")
    for url, count in eda_results["dataset_b"]["urls"].most_common(8):
        print(f"  {url:<45}: {count:>5} events")
        
    print("\nTop Keyboard Shortcuts in Dataset B:")
    for sc, count in eda_results["dataset_b"]["shortcuts"].most_common(5):
        print(f"  {sc:<30}: {count:>5} times")
    print("=" * 70)


if __name__ == "__main__":
    run_eda()
