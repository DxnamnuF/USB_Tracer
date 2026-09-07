import json
import platform
import re
import shutil
import subprocess
from pathlib import Path

from .artifact_utils import (
    classify_device,
    extract_device_id,
    extract_serial_from_device_id,
    extract_vid_pid,
    iso_utc,
    parse_device_descriptor,
    parse_device_id,
    short_text,
)

DEFAULT_CHANNELS = [
    "Microsoft-Windows-Kernel-PnP/Configuration",
    "System",
]

USB_HINTS = [
    "USBSTOR",
    "USB\\VID_",
    "VID_",
    "PID_",
    "Disk&Ven_",
    "WPDBUSENUM",
    "Portable Devices",
    "Mass Storage",
    "USB Mass Storage",
]

EVENT_ID_HINTS = {
    400: ("device_configured", "device configured"),
    410: ("device_started", "device started"),
    411: ("device_problem", "configuration or migration issue"),
    420: ("device_install_requested", "device installation requested"),
    430: ("device_install_finished", "device installation finished"),
    20001: ("driver_install", "driver installation"),
    20003: ("driver_install_finished", "driver installation finished"),
    219: ("driver_problem", "driver problem"),
    225: ("device_removal_blocked", "device removal blocked"),
}


def is_windows():
    return platform.system().lower() == "windows"


def find_powershell():
    return shutil.which("powershell") or shutil.which("pwsh")


def has_usb_hint(message):
    if not message:
        return False
    upper = str(message).upper()
    return any(hint.upper() in upper for hint in USB_HINTS)


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def guess_action(event_id, message):
    try:
        event_id = int(event_id)
    except (TypeError, ValueError):
        event_id = None
    if event_id in EVENT_ID_HINTS:
        code, title = EVENT_ID_HINTS[event_id]
        return code, title
    text = (message or "").lower()
    if "configured" in text:
        return "device_configured", "device configured"
    if "started" in text:
        return "device_started", "device started"
    if "not migrated" in text or "could not be migrated" in text:
        return "device_problem", "configuration or migration issue"
    if "requires further installation" in text:
        return "device_needs_installation", "further installation required"
    if "installed" in text:
        return "device_installed", "device installed"
    if "deleted" in text or "removed" in text:
        return "device_removed", "device removed or disconnected"
    return "usb_related_event", "USB or PnP event"


def powershell_json_script_live():
    return r'''
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$logName = $args[0]
$maxEvents = [int]$args[1]
$daysBack = [int]$args[2]
$filter = @{ LogName = $logName }
if ($daysBack -gt 0) {
    $filter.StartTime = (Get-Date).AddDays(-$daysBack)
}
Get-WinEvent -FilterHashtable $filter -MaxEvents $maxEvents |
    Select-Object `
        @{Name='TimeCreatedUtc'; Expression={$_.TimeCreated.ToUniversalTime().ToString('o')}},
        Id,
        ProviderName,
        LogName,
        LevelDisplayName,
        RecordId,
        MachineName,
        @{Name='Message'; Expression={$_.Message}} |
    ConvertTo-Json -Depth 4 -Compress
'''


def powershell_json_script_path():
    return r'''
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$path = $args[0]
$maxEvents = [int]$args[1]
Get-WinEvent -Path $path -MaxEvents $maxEvents |
    Select-Object `
        @{Name='TimeCreatedUtc'; Expression={$_.TimeCreated.ToUniversalTime().ToString('o')}},
        Id,
        ProviderName,
        LogName,
        LevelDisplayName,
        RecordId,
        MachineName,
        @{Name='Message'; Expression={$_.Message}} |
    ConvertTo-Json -Depth 4 -Compress
'''


def run_powershell(script, args, timeout=90):
    ps = find_powershell()
    if not ps:
        return None, "PowerShell was not found. Event Log parsing requires PowerShell."
    cmd = [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script] + [str(x) for x in args]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "PowerShell timeout. Reduce the date range or event limit."
    except OSError as exc:
        return None, f"Could not start PowerShell: {exc}"
    output = (completed.stdout or "").strip()
    if not output:
        err = (completed.stderr or "").strip()
        return [], err if err else None
    try:
        raw = json.loads(output)
    except json.JSONDecodeError:
        err = (completed.stderr or "").strip()
        return None, f"PowerShell returned non-JSON output. {err}"
    if isinstance(raw, dict):
        return [raw], None
    if isinstance(raw, list):
        return raw, None
    return [], None


def run_get_winevent(channel, days=30, max_events=2000):
    if not is_windows():
        return [{"error": "Live Event Log can be read only on Windows."}]
    raw, error = run_powershell(powershell_json_script_live(), [channel, max_events, days])
    if error and raw is None:
        return [{"error": f"Could not read channel {channel}: {error}"}]
    return raw or []


def run_get_winevent_path(path, max_events=2000):
    if not is_windows():
        return [{"error": "Offline EVTX parsing through Get-WinEvent can be run only on Windows."}]
    if not Path(path).exists():
        return [{"error": f"EVTX file was not found: {path}"}]
    raw, error = run_powershell(powershell_json_script_path(), [path, max_events])
    if error and raw is None:
        return [{"error": f"Could not read EVTX file {path}: {error}"}]
    return raw or []


def enrich_device_fields(item):
    device_id = item.get("device_instance_id")
    info = parse_device_id(device_id)
    item.update({k: v for k, v in info.items() if v and not item.get(k)})
    if not item.get("serial"):
        item["serial"] = extract_serial_from_device_id(device_id)
    vid, pid = extract_vid_pid(device_id or item.get("message") or "")
    if vid and not item.get("vid"):
        item["vid"] = vid
    if pid and not item.get("pid"):
        item["pid"] = pid
    if item.get("vendor_product"):
        desc = parse_device_descriptor(item.get("vendor_product"))
        for key, value in desc.items():
            if value and not item.get(key):
                item[key] = value
    item["device_class"] = classify_device(item)
    return item


def normalize_event(raw, source_name, source_path=None):
    message = raw.get("Message") or ""
    event_id = raw.get("Id")
    device_id = extract_device_id(message)
    action, action_text = guess_action(event_id, message)
    item = {
        "event_kind": "eventlog",
        "timestamp_utc": iso_utc(raw.get("TimeCreatedUtc")),
        "action": action,
        "action_text": action_text,
        "channel": raw.get("LogName") or source_name,
        "provider": raw.get("ProviderName"),
        "event_id": event_id,
        "level": raw.get("LevelDisplayName"),
        "record_id": raw.get("RecordId"),
        "machine_name": raw.get("MachineName"),
        "message": message,
        "message_short": short_text(message),
        "artifact_source": f"EventLog:{raw.get('LogName') or source_name}:RecordId={raw.get('RecordId')}",
        "device_instance_id": device_id,
    }
    if source_path:
        item["event_file"] = str(source_path)
        item["artifact_source"] = f"EVTX:{Path(source_path).name}:RecordId={raw.get('RecordId')}"
    return enrich_device_fields(item)


def filter_event(raw, keep_unmatched=False):
    message = raw.get("Message") or ""
    device_id = extract_device_id(message)
    return bool(device_id) or has_usb_hint(message) or keep_unmatched


def get_usb_eventlog_data(days=30, max_events=2000, channels=None, keep_unmatched=False):
    channels = channels or DEFAULT_CHANNELS
    results = []
    errors = []
    for channel in channels:
        raw_events = run_get_winevent(channel, days=days, max_events=max_events)
        if raw_events and isinstance(raw_events[0], dict) and "error" in raw_events[0]:
            errors.extend(raw_events)
            continue
        for raw in raw_events:
            if filter_event(raw, keep_unmatched=keep_unmatched):
                results.append(normalize_event(raw, channel))
    if results:
        return results
    if errors:
        return errors
    return []


def get_usb_evtx_data(evtx_paths, max_events=5000, keep_unmatched=False):
    results = []
    errors = []
    for path in evtx_paths or []:
        raw_events = run_get_winevent_path(path, max_events=max_events)
        if raw_events and isinstance(raw_events[0], dict) and "error" in raw_events[0]:
            errors.extend(raw_events)
            continue
        for raw in raw_events:
            if filter_event(raw, keep_unmatched=keep_unmatched):
                results.append(normalize_event(raw, Path(path).name, source_path=path))
    if results:
        return results + errors
    if errors:
        return errors
    return []
