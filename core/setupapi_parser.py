import re
from datetime import datetime
from pathlib import Path

from .artifact_utils import (
    classify_device,
    extract_device_id,
    file_mtime_utc,
    parse_device_id,
    short_text,
)

HEADER_RE = re.compile(r"^>>>\s+\[(?P<title>.+?)(?:\s+-\s+(?P<device>.+?))?\]\s*$")
START_RE = re.compile(r"^>>>\s+Section start\s+(?P<time>\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)")
END_RE = re.compile(r"^<<<\s+Section end\s+(?P<time>\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)")


def read_text_any(path):
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        for encoding in ("utf-16", "utf-16le", "utf-16be"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "utf-16le"):
        try:
            text = raw.decode(encoding)
            visible = sum(1 for ch in text[:5000] if ch.isprintable() or ch in "\r\n\t")
            ratio = visible / max(len(text[:5000]), 1)
            if ratio > 0.70:
                return text
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_setupapi_time(value):
    if not value:
        return None
    for fmt in ("%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).isoformat()
        except ValueError:
            pass
    return value


def normalize_section(section, path):
    text = "\n".join(section.get("lines") or [])
    device_id = section.get("device_id") or extract_device_id(text)
    device_info = parse_device_id(device_id)
    warnings = [line.strip() for line in section.get("lines", []) if line.strip().startswith("!")]
    errors = [line.strip() for line in section.get("lines", []) if line.strip().startswith("!!!")]
    item = {
        "event_kind": "setupapi",
        "artifact_type": "SETUPAPI_DEV_LOG",
        "artifact_source": f"SetupAPI:{Path(path).name}:section={section.get('index')}",
        "file_mtime_utc": file_mtime_utc(path),
        "timestamp_local": section.get("start_time"),
        "timestamp_utc": None,
        "action": "setupapi_section",
        "action_text": section.get("title") or "SetupAPI device installation section",
        "friendly_name": device_id or section.get("title") or "SetupAPI USB section",
        "device_instance_id": device_id,
        "message_short": short_text(text, 360),
        "setupapi_warnings_count": len(warnings),
        "setupapi_errors_count": len(errors),
        "setupapi_end_time_local": section.get("end_time"),
    }
    item.update({k: v for k, v in device_info.items() if v})
    item["device_class"] = classify_device(item)
    return item


def parse_setupapi_log(path):
    p = Path(path)
    if not p.exists():
        return [{"error": f"setupapi.dev.log file was not found: {path}"}]
    try:
        text = read_text_any(p)
    except Exception as exc:
        return [{"error": f"Could not read setupapi.dev.log {path}: {exc}"}]
    sections = []
    current = None
    index = 0
    for line in text.splitlines():
        header = HEADER_RE.match(line)
        if header:
            if current:
                sections.append(current)
            index += 1
            current = {
                "index": index,
                "title": header.group("title"),
                "device_id": extract_device_id(header.group("device") or ""),
                "start_time": None,
                "end_time": None,
                "lines": [line],
            }
            continue
        if current is None:
            continue
        current["lines"].append(line)
        start = START_RE.match(line)
        if start:
            current["start_time"] = parse_setupapi_time(start.group("time"))
        end = END_RE.match(line)
        if end:
            current["end_time"] = parse_setupapi_time(end.group("time"))
    if current:
        sections.append(current)
    items = []
    for section in sections:
        raw_text = "\n".join(section.get("lines") or [])
        if extract_device_id(raw_text) or "usb" in raw_text.lower() or "wpd" in raw_text.lower():
            items.append(normalize_section(section, p))
    return items


def get_setupapi_data(paths):
    results = []
    for path in paths or []:
        results += parse_setupapi_log(path)
    return results
