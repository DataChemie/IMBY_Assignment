import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Union

# Pattern to extract canonical session ID: ses_<date>-<time>-<machine>
SESSION_ID_PATTERN = re.compile(r"(ses_\d{8}-\d{6}-[A-Za-z0-9_-]+)")


def get_canonical_session_id(name_or_path: Union[str, Path]) -> str:
    """Extract canonical session ID from directory or zip filename.
    
    Example:
        ses_20260630-121953-LAPTOP-R36BQBTE-20260913T091815Z-1-001.zip
        -> ses_20260630-121953-LAPTOP-R36BQBTE
    """
    stem = Path(name_or_path).stem
    clean_id = re.sub(r"-\d{8}T\d{6}Z.*$", "", stem)
    return clean_id


def parse_iso(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO 8601 string to timezone-aware UTC datetime."""
    if not ts_str:
        return None
    cleaned = ts_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def to_iso(dt: Optional[datetime]) -> str:
    """Convert datetime to canonical ISO 8601 UTC string ending in 'Z'."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ts_ms(evt: Dict[str, Any]) -> int:
    """Extract epoch milliseconds timestamp from event dict."""
    if "timestamp_ms" in evt and evt["timestamp_ms"] is not None:
        return int(evt["timestamp_ms"])
    if "timestamp_iso" in evt and evt["timestamp_iso"]:
        dt = parse_iso(evt["timestamp_iso"])
        if dt:
            return int(dt.timestamp() * 1000)
    return 0


def read_jsonl(path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Read a JSONL file into a list of dictionaries."""
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                try:
                    rows.append(json.loads(stripped))
                except json.JSONDecodeError:
                    continue
    return rows


def write_jsonl(rows: List[Dict[str, Any]], path: Union[str, Path]) -> None:
    """Write list of dictionaries to a JSONL file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def stream_events_from_zip(zip_path: Union[str, Path]) -> Generator[Dict[str, Any], None, None]:
    """Stream raw events directly from a session zip without unzipping to disk."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        event_entries = sorted([name for name in zf.namelist() if name.endswith("events.jsonl")])
        for entry in event_entries:
            with zf.open(entry, "r") as ef:
                for line in ef:
                    stripped = line.decode("utf-8", "replace").strip()
                    if stripped:
                        try:
                            yield json.loads(stripped)
                        except json.JSONDecodeError:
                            continue


def load_session_events(path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Load and chronologically sort all events for a session (from zip or directory)."""
    p = Path(path)
    events: List[Dict[str, Any]] = []
    canonical_id = get_canonical_session_id(p)

    if p.is_file() and p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p, "r") as zf:
            event_entries = sorted([name for name in zf.namelist() if name.endswith("events.jsonl")])
            for entry in event_entries:
                content = zf.read(entry).decode("utf-8", "replace")
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped:
                        try:
                            evt = json.loads(stripped)
                            if "session_id" not in evt or not evt["session_id"]:
                                evt["session_id"] = canonical_id
                            events.append(evt)
                        except json.JSONDecodeError:
                            continue
    elif p.is_dir():
        for ep in sorted(p.glob("chunk_*/events.jsonl")):
            for evt in read_jsonl(ep):
                if "session_id" not in evt or not evt["session_id"]:
                    evt["session_id"] = canonical_id
                events.append(evt)

    events.sort(key=ts_ms)
    return events


def load_gt_manifest(path: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """Load gt_manifest.json from a session zip or directory if present."""
    p = Path(path)
    if p.is_file() and p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p, "r") as zf:
            manifest_entries = [n for n in zf.namelist() if n.endswith("gt_manifest.json")]
            if manifest_entries:
                try:
                    data = json.loads(zf.read(manifest_entries[0]).decode("utf-8", "replace"))
                    return data
                except Exception:
                    return None
    elif p.is_dir():
        target = p / "gt_manifest.json"
        if target.exists():
            try:
                return json.loads(target.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                return None
    return None


def load_gt_events(path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Load gt.jsonl from a session zip or directory if present."""
    p = Path(path)
    gt_rows: List[Dict[str, Any]] = []
    if p.is_file() and p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p, "r") as zf:
            gt_entries = [n for n in zf.namelist() if n.endswith("gt.jsonl")]
            if gt_entries:
                content = zf.read(gt_entries[0]).decode("utf-8", "replace")
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped:
                        try:
                            gt_rows.append(json.loads(stripped))
                        except json.JSONDecodeError:
                            continue
    elif p.is_dir():
        target = p / "gt.jsonl"
        if target.exists():
            return read_jsonl(target)
    return gt_rows


def load_session_manifests(path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Load chunk manifest.json files from a session zip or directory."""
    p = Path(path)
    manifests: List[Dict[str, Any]] = []
    if p.is_file() and p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p, "r") as zf:
            manifest_entries = sorted([n for n in zf.namelist() if n.endswith("manifest.json") and not n.endswith("gt_manifest.json")])
            for entry in manifest_entries:
                try:
                    data = json.loads(zf.read(entry).decode("utf-8", "replace"))
                    manifests.append(data)
                except Exception:
                    continue
    elif p.is_dir():
        for target in sorted(p.glob("chunk_*/manifest.json")):
            try:
                manifests.append(json.loads(target.read_text(encoding="utf-8", errors="replace")))
            except Exception:
                continue
    return manifests
