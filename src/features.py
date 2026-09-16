import re
from typing import Any, Dict, List, Optional
from .io_utils import parse_iso, ts_ms


def norm_text(x: Any) -> str:
    """Normalize arbitrary metadata/payload objects into a flat string."""
    if x is None:
        return ""
    if isinstance(x, (str, int, float, bool)):
        return str(x)
    if isinstance(x, list):
        return " ".join(norm_text(v) for v in x)
    if isinstance(x, dict):
        return " ".join(f"{k} {norm_text(v)}" for k, v in x.items())
    return str(x)


def get_active_app_info(evt: Dict[str, Any]) -> Dict[str, str]:
    """Extract active app name, process name, and window title from event."""
    context = evt.get("context") or {}
    active = context.get("active_app") or {}
    return {
        "app_name": (active.get("app_name") or "").strip(),
        "process_name": (active.get("process_name") or "").strip(),
        "window_title": (active.get("window_title") or "").strip(),
    }


def get_browser_tab_info(evt: Dict[str, Any]) -> Dict[str, str]:
    """Extract browser tab URL and title from event."""
    context = evt.get("context") or {}
    tab = context.get("active_browser_tab") or {}
    return {
        "url": (tab.get("url") or "").strip(),
        "title": (tab.get("title") or "").strip(),
    }


def extract_event_text(evt: Dict[str, Any]) -> str:
    """Extract descriptive text representation from an event for TF-IDF."""
    c = evt.get("context") or {}
    p = evt.get("payload") or {}
    parts = []

    evt_type = evt.get("event_type", "")
    layer = evt.get("layer", "")
    parts.append(f"event_type_{evt_type}")
    parts.append(f"layer_{layer}")

    app_info = get_active_app_info(evt)
    for k, v in app_info.items():
        if v:
            parts.append(f"{k}_{v}")

    tab_info = get_browser_tab_info(evt)
    for k, v in tab_info.items():
        if v:
            parts.append(f"browser_{k}_{v}")

    extracted = c.get("extracted_text")
    if extracted:
        parts.append(f"screen_text {norm_text(extracted)}")

    if evt_type == "keystroke":
        for k in ("key", "character", "target_field"):
            if p.get(k):
                parts.append(f"{k}_{p[k]}")
    elif evt_type == "browser_click":
        el = p.get("element") or {}
        parts.append(f"browser_element {norm_text(el)}")
    elif evt_type == "browser_form_input":
        parts.append(f"browser_form {norm_text(p)}")
    elif evt_type == "clipboard_change":
        for k in ("content_preview", "source_app", "target_app"):
            if p.get(k):
                parts.append(f"{k}_{p[k]}")
    elif evt_type == "app_switch":
        for k in ("new_app", "previous_app"):
            if p.get(k):
                parts.append(f"{k}_{p[k]}")
    elif evt_type == "browser_navigation":
        parts.append(f"navigation {norm_text(p)}")
    elif evt_type in ("window_title_change", "dialog_opened", "dialog_closed"):
        parts.append(f"window {norm_text(p)}")

    return " ".join(parts)


def compute_boundary_features(
    curr_evt: Dict[str, Any],
    prev_evt: Optional[Dict[str, Any]],
) -> Dict[str, float]:
    """Compute domain-agnostic transition features between consecutive events."""
    if prev_evt is None:
        return {
            "gap_seconds": 0.0,
            "is_app_switch": 0.0,
            "is_title_change": 0.0,
            "is_url_change": 0.0,
            "is_family_switch": 0.0,
            "long_gap_30s": 0.0,
            "long_gap_60s": 0.0,
        }

    t_curr = ts_ms(curr_evt)
    t_prev = ts_ms(prev_evt)
    gap_seconds = max(0.0, (t_curr - t_prev) / 1000.0)

    curr_app = get_active_app_info(curr_evt)
    prev_app = get_active_app_info(prev_evt)

    curr_tab = get_browser_tab_info(curr_evt)
    prev_tab = get_browser_tab_info(prev_evt)

    is_app_switch = 1.0 if curr_app["app_name"] != prev_app["app_name"] else 0.0
    is_title_change = 1.0 if curr_app["window_title"] != prev_app["window_title"] else 0.0
    is_url_change = 1.0 if (curr_tab["url"] and prev_tab["url"] and curr_tab["url"] != prev_tab["url"]) else 0.0

    def get_family(app: str) -> str:
        a = app.lower()
        if "edge" in a or "chrome" in a or "browser" in a:
            return "browser"
        if "excel" in a or "word" in a or "notepad" in a or "onenote" in a:
            return "office"
        return "other"

    curr_fam = get_family(curr_app["app_name"])
    prev_fam = get_family(prev_app["app_name"])
    is_family_switch = 1.0 if curr_fam != prev_fam else 0.0

    return {
        "gap_seconds": gap_seconds,
        "is_app_switch": is_app_switch,
        "is_title_change": is_title_change,
        "is_url_change": is_url_change,
        "is_family_switch": is_family_switch,
        "long_gap_30s": 1.0 if gap_seconds >= 30.0 else 0.0,
        "long_gap_60s": 1.0 if gap_seconds >= 60.0 else 0.0,
    }
