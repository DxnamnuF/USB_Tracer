import os
import re
from datetime import datetime, timezone
from pathlib import Path



def iso_utc(value):
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def now_utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def short_text(value, limit=260):
    if value is None:
        return ""
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[:limit - 3] + "..."


def safe_upper(value):
    return str(value or "").upper()


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def decode_registry_binary(data):
    if data is None:
        return None
    if isinstance(data, str):
        return data
    if isinstance(data, (list, tuple)):
        return "; ".join(str(x) for x in data)
    if not isinstance(data, (bytes, bytearray)):
        return str(data)
    raw = bytes(data)
    candidates = []
    for encoding in ("utf-16le", "utf-8", "latin-1"):
        try:
            text = raw.decode(encoding, errors="ignore")
            text = text.replace("\x00", " ").strip()
            printable = " ".join("".join(ch if ch.isprintable() else " " for ch in text).split())
            if len(printable) >= 3:
                candidates.append(printable)
        except Exception:
            pass
    if candidates:
        candidates.sort(key=len, reverse=True)
        return candidates[0]
    return raw.hex()


def strings_from_binary(data, min_len=4, limit=60):
    if data is None:
        return []
    if isinstance(data, str):
        text = data
        found = re.findall(r"[ -~]{%d,}" % min_len, text)
        return found[:limit]
    raw = bytes(data)
    found = []
    ascii_hits = re.findall(rb"[ -~]{%d,}" % min_len, raw)
    for hit in ascii_hits:
        try:
            found.append(hit.decode("utf-8", errors="ignore"))
        except Exception:
            pass
    for encoding in ("utf-16le", "utf-16be"):
        try:
            text = raw.decode(encoding, errors="ignore")
            hits = re.findall(r"[^\x00\r\n\t]{%d,}" % min_len, text)
            for hit in hits:
                cleaned = " ".join(hit.split())
                if cleaned and any(ch.isalnum() for ch in cleaned):
                    found.append(cleaned)
        except Exception:
            pass
    unique = []
    seen = set()
    for item in found:
        cleaned = short_text(item, 300)
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            unique.append(cleaned)
        if len(unique) >= limit:
            break
    return unique


def extract_vid_pid(text):
    match = re.search(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", str(text or ""), re.IGNORECASE)
    if not match:
        return None, None
    return match.group(1).upper(), match.group(2).upper()


def normalize_usb_path(text):
    if not text:
        return None
    value = str(text).strip().strip(".,;:()[]{}<>\"'")
    value = value.replace("#", "\\")
    value = value.replace("_??_", "\\??\\")
    value = re.sub(r"\\{2,}", r"\\", value)
    value = re.sub(r"\\+$", "", value)
    return value


def extract_device_id(text):
    if not text:
        return None
    value = str(text)
    patterns = [
        r"USBSTOR[\\#][^\s\r\n\"']+",
        r"USB[\\#]VID_[0-9A-F]{4}&PID_[0-9A-F]{4}[^\s\r\n\"']*",
        r"SWD[\\#]WPDBUSENUM[^\s\r\n\"']*",
        r"WPDBUSENUMROOT[\\#]UMB[\\#][^\s\r\n\"']+",
        r"SCSI[\\#]Disk[^\s\r\n\"']*",
    ]
    for pattern in patterns:
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            return normalize_usb_path(match.group(0))
    return None


def extract_all_device_ids(text):
    if not text:
        return []
    value = str(text)
    patterns = [
        r"USBSTOR[\\#][^\s\r\n\"']+",
        r"USB[\\#]VID_[0-9A-F]{4}&PID_[0-9A-F]{4}[^\s\r\n\"']*",
        r"SWD[\\#]WPDBUSENUM[^\s\r\n\"']*",
        r"WPDBUSENUMROOT[\\#]UMB[\\#][^\s\r\n\"']+",
        r"SCSI[\\#]Disk[^\s\r\n\"']*",
    ]
    items = []
    seen = set()
    for pattern in patterns:
        for match in re.finditer(pattern, value, re.IGNORECASE):
            device_id = normalize_usb_path(match.group(0))
            key = safe_upper(device_id)
            if device_id and key not in seen:
                seen.add(key)
                items.append(device_id)
    return items


def extract_serial_from_device_id(text):
    device_id = normalize_usb_path(text)
    if not device_id:
        return None
    parts = device_id.split("\\")
    if len(parts) >= 3:
        serial = parts[-1]
        return serial.strip("&") or None
    return None


def is_generated_serial(serial):
    return bool(serial) and len(str(serial)) > 1 and str(serial)[1] == "&"


def clean_descriptor_part(text):
    if not text:
        return None
    return str(text).replace("_", " ").strip() or None


def parse_device_descriptor(device_str):
    parsed = {
        "device_type": None,
        "vendor": None,
        "product": None,
        "revision": None,
    }
    if not device_str:
        return parsed
    parts = str(device_str).split("&")
    if parts:
        parsed["device_type"] = clean_descriptor_part(parts[0])
    prefixes = {
        "VEN_": "vendor",
        "PROD_": "product",
        "REV_": "revision",
    }
    for part in parts[1:]:
        upper = part.upper()
        for prefix, field in prefixes.items():
            if upper.startswith(prefix):
                parsed[field] = clean_descriptor_part(part[len(prefix):])
                break
    return parsed


def parse_device_id(device_id):
    normalized = normalize_usb_path(device_id)
    info = {
        "device_instance_id": normalized,
        "vendor_product": None,
        "serial": None,
        "is_generated": None,
        "device_type": None,
        "vendor": None,
        "product": None,
        "revision": None,
        "vid": None,
        "pid": None,
    }
    if not normalized:
        return info
    parts = normalized.split("\\")
    if len(parts) >= 3 and parts[0].upper() == "USBSTOR":
        info["vendor_product"] = parts[1]
        info["serial"] = parts[2]
        info["is_generated"] = is_generated_serial(parts[2])
        info.update(parse_device_descriptor(parts[1]))
    elif len(parts) >= 3:
        info["serial"] = parts[-1]
        info["is_generated"] = is_generated_serial(parts[-1])
    vid, pid = extract_vid_pid(normalized)
    if vid and pid:
        info["vid"] = vid
        info["pid"] = pid
    return info


def extract_drive_letter(text):
    value = str(text or "")
    match = re.search(r"\\DosDevices\\([A-Z]):", value, re.IGNORECASE)
    if match:
        return f"{match.group(1).upper()}:"
    match = re.search(r"\b([A-Z]):\\", value, re.IGNORECASE)
    if match:
        return f"{match.group(1).upper()}:"
    match = re.fullmatch(r"([A-Z]):", value.strip(), re.IGNORECASE)
    if match:
        return f"{match.group(1).upper()}:"
    return None


def extract_volume_guid(text):
    value = str(text or "")
    match = re.search(r"Volume\{([0-9A-Fa-f\-]{20,})\}", value, re.IGNORECASE)
    if match:
        return "Volume{" + match.group(1).lower() + "}"
    match = re.search(r"\{([0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12})\}", value)
    if match:
        return "Volume{" + match.group(1).lower() + "}"
    return None


def classify_device(item):
    text = " ".join(str(item.get(k) or "") for k in [
        "artifact_type", "friendly_name", "device_instance_id", "vendor_product", "device_type", "service", "class_guid", "hardware_id", "message_short"
    ]).lower()
    if "usbstor" in text or "mass storage" in text or "disk&ven" in text or "usb device" in text and "disk" in text:
        return "mass_storage"
    if "iphone" in text or "android" in text or "portable device" in text or "wpdbusenum" in text:
        return "mobile_or_portable_device"
    if "camera" in text or "imaging" in text or "webcam" in text:
        return "camera"
    if "keyboard" in text or "mouse" in text or "hid" in text or "input device" in text:
        return "input_device"
    if "bluetooth" in text:
        return "bluetooth_adapter"
    if "root hub" in text or "usb hub" in text or "usbhub" in text:
        return "usb_hub"
    if "printer" in text or "brother" in text or "print" in text:
        return "printer"
    if "fingerprint" in text or "biometric" in text:
        return "biometric_device"
    if "descriptor request failed" in text or "unknown usb device" in text:
        return "unknown_or_failed_usb_device"
    if item.get("artifact_type") in {"LNK_FILE", "JUMP_LIST", "RECENTDOCS", "SHELLBAGS"}:
        return "file_activity_artifact"
    return "unknown"


def file_size(path):
    try:
        return os.path.getsize(path)
    except Exception:
        return None


def file_mtime_utc(path):
    try:
        return iso_utc(datetime.fromtimestamp(os.path.getmtime(path), timezone.utc))
    except Exception:
        return None
