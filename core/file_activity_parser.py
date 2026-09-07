import os
import platform
from pathlib import Path

from .artifact_utils import (
    classify_device,
    decode_registry_binary,
    extract_device_id,
    extract_drive_letter,
    extract_serial_from_device_id,
    extract_volume_guid,
    file_mtime_utc,
    short_text,
    strings_from_binary,
)

try:
    import winreg
except ImportError:
    winreg = None

try:
    from Registry import Registry
except ImportError:
    Registry = None

RECENTDOCS_PATH = r"Software\Microsoft\Windows\CurrentVersion\Explorer\RecentDocs"
SHELLBAGS_PATHS = [
    r"Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\BagMRU",
    r"Software\Microsoft\Windows\Shell\BagMRU",
]


def default_live_lnk_dirs():
    userprofile = os.environ.get("USERPROFILE")
    appdata = os.environ.get("APPDATA")
    if not userprofile:
        return []
    dirs = [Path(userprofile) / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Recent"]
    if appdata:
        dirs.append(Path(appdata) / "Microsoft" / "Windows" / "Recent")
    return [str(p) for p in dirs if p.exists()]


def default_live_jump_dirs():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return []
    base = Path(appdata) / "Microsoft" / "Windows" / "Recent"
    return [str(base / "AutomaticDestinations"), str(base / "CustomDestinations")]


def read_binary(path, limit_bytes=4 * 1024 * 1024):
    with Path(path).open("rb") as f:
        return f.read(limit_bytes)


def interesting_strings(path):
    try:
        data = read_binary(path)
    except Exception:
        return []
    strings = strings_from_binary(data, min_len=4, limit=120)
    keep = []
    for item in strings:
        upper = item.upper()
        if any(x in upper for x in ["USBSTOR", "VID_", "PID_", "VOLUME{", ":\\", "\\DEVICE\\HARDDISKVOLUME", "REMOVABLE", "PORTABLE"]):
            keep.append(item)
    return keep[:40]


def artifact_from_file(path, artifact_type):
    strings = interesting_strings(path)
    joined = " ".join(strings)
    device_id = extract_device_id(joined)
    item = {
        "event_kind": "file_activity",
        "artifact_type": artifact_type,
        "artifact_source": f"File:{path}",
        "file_path": str(path),
        "timestamp_utc": file_mtime_utc(path),
        "action": "file_activity_artifact",
        "action_text": f"{artifact_type} file artifact",
        "device_instance_id": device_id,
        "serial": extract_serial_from_device_id(device_id),
        "drive_letter": extract_drive_letter(joined),
        "volume_guid": extract_volume_guid(joined),
        "friendly_name": Path(path).name,
        "target_candidates": strings,
        "message_short": short_text(" | ".join(strings), 360) or "File artifact was found, but no readable USB-related strings were extracted.",
    }
    item["device_class"] = classify_device(item)
    return item


def scan_files(directories, suffixes, artifact_type, limit=5000):
    results = []
    count = 0
    for directory in directories or []:
        root = Path(directory)
        if not root.exists():
            results.append({"error": f"Directory was not found: {directory}"})
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in suffixes:
                continue
            results.append(artifact_from_file(path, artifact_type))
            count += 1
            if count >= limit:
                return results
    return results


def enum_live_subkeys(key):
    try:
        count = winreg.QueryInfoKey(key)[0]
    except OSError:
        return
    for idx in range(count):
        try:
            yield winreg.EnumKey(key, idx)
        except OSError:
            continue


def enum_live_values(key):
    try:
        count = winreg.QueryInfoKey(key)[1]
    except OSError:
        return
    for idx in range(count):
        try:
            yield winreg.EnumValue(key, idx)
        except OSError:
            continue


def live_key_last_write_utc(key):
    try:
        from .registry_parser import key_last_write_utc
        return key_last_write_utc(key)
    except Exception:
        return None


def live_recentdocs():
    if winreg is None or platform.system().lower() != "windows":
        return []
    results = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RECENTDOCS_PATH) as base:
            results += parse_live_recentdocs_key(base, fr"HKCU\{RECENTDOCS_PATH}")
            for sub in enum_live_subkeys(base):
                try:
                    with winreg.OpenKey(base, sub) as subkey:
                        results += parse_live_recentdocs_key(subkey, fr"HKCU\{RECENTDOCS_PATH}\{sub}")
                except OSError:
                    continue
    except OSError:
        pass
    return results


def parse_live_recentdocs_key(key, source_prefix):
    items = []
    for name, data, reg_type in enum_live_values(key):
        if str(name).upper().startswith("MRU"):
            continue
        decoded = decode_registry_binary(data)
        item = recentdocs_item(source_prefix, name, decoded, live_key_last_write_utc(key), None, None)
        items.append(item)
    return items


def live_shellbags():
    if winreg is None or platform.system().lower() != "windows":
        return []
    results = []
    for path in SHELLBAGS_PATHS:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as base:
                results += walk_live_shellbag(base, fr"HKCU\{path}", 0, 1200)
        except OSError:
            continue
    return results


def walk_live_shellbag(key, source_prefix, depth, limit):
    if depth > 8 or limit <= 0:
        return []
    results = []
    for name, data, reg_type in enum_live_values(key):
        decoded = decode_registry_binary(data)
        if decoded and len(decoded) >= 3:
            results.append(shellbag_item(source_prefix, name, decoded, live_key_last_write_utc(key), None, None))
            if len(results) >= limit:
                return results
    for sub in enum_live_subkeys(key):
        try:
            with winreg.OpenKey(key, sub) as child:
                results += walk_live_shellbag(child, source_prefix + "\\" + sub, depth + 1, limit - len(results))
                if len(results) >= limit:
                    return results
        except OSError:
            continue
    return results


def open_offline_hive(path):
    if Registry is None:
        return None
    try:
        return Registry.Registry(path)
    except Exception:
        return None


def try_open(root, path):
    try:
        return root.open(path)
    except Exception:
        return None


def offline_key_ts(key):
    try:
        from .artifact_utils import iso_utc
        return iso_utc(key.timestamp())
    except Exception:
        return None


def recentdocs_item(source_prefix, name, decoded, timestamp, hive_path, user_label):
    device_id = extract_device_id(decoded)
    item = {
        "event_kind": "file_activity",
        "artifact_type": "RECENTDOCS",
        "artifact_source": f"{source_prefix}:{name}",
        "user_hive": str(hive_path) if hive_path else None,
        "user_label": user_label,
        "timestamp_utc": timestamp,
        "action": "recentdocs_entry",
        "action_text": "RecentDocs registry artifact",
        "friendly_name": decoded or name,
        "device_instance_id": device_id,
        "serial": extract_serial_from_device_id(device_id),
        "drive_letter": extract_drive_letter(decoded),
        "volume_guid": extract_volume_guid(decoded),
        "message_short": short_text(decoded, 360),
    }
    item["device_class"] = classify_device(item)
    return item


def shellbag_item(source_prefix, name, decoded, timestamp, hive_path, user_label):
    device_id = extract_device_id(decoded)
    item = {
        "event_kind": "file_activity",
        "artifact_type": "SHELLBAGS",
        "artifact_source": f"{source_prefix}:{name}",
        "user_hive": str(hive_path) if hive_path else None,
        "user_label": user_label,
        "timestamp_utc": timestamp,
        "action": "shellbags_entry",
        "action_text": "ShellBags registry artifact",
        "friendly_name": decoded or name,
        "device_instance_id": device_id,
        "serial": extract_serial_from_device_id(device_id),
        "drive_letter": extract_drive_letter(decoded),
        "volume_guid": extract_volume_guid(decoded),
        "message_short": short_text(decoded, 360),
    }
    item["device_class"] = classify_device(item)
    return item


def offline_recentdocs(ntuser_path):
    hive = open_offline_hive(ntuser_path)
    if not hive:
        return [{"error": f"Could not open NTUSER.DAT for RecentDocs: {ntuser_path}"}]
    base = try_open(hive, RECENTDOCS_PATH)
    if not base:
        return []
    results = []
    user_label = Path(ntuser_path).parent.name or Path(ntuser_path).name
    results += parse_offline_recentdocs_key(base, fr"NTUSER.DAT:{user_label}\{RECENTDOCS_PATH}", ntuser_path, user_label)
    for subkey in base.subkeys():
        results += parse_offline_recentdocs_key(subkey, fr"NTUSER.DAT:{user_label}\{RECENTDOCS_PATH}\{subkey.name()}", ntuser_path, user_label)
    return results


def parse_offline_recentdocs_key(key, source_prefix, ntuser_path, user_label):
    items = []
    for value in key.values():
        name = value.name()
        if str(name).upper().startswith("MRU"):
            continue
        decoded = decode_registry_binary(value.value())
        items.append(recentdocs_item(source_prefix, name, decoded, offline_key_ts(key), ntuser_path, user_label))
    return items


def offline_shellbags(ntuser_path, limit=1500):
    hive = open_offline_hive(ntuser_path)
    if not hive:
        return [{"error": f"Could not open NTUSER.DAT for ShellBags: {ntuser_path}"}]
    results = []
    user_label = Path(ntuser_path).parent.name or Path(ntuser_path).name
    for path in SHELLBAGS_PATHS:
        base = try_open(hive, path)
        if base:
            results += walk_offline_shellbag(base, fr"NTUSER.DAT:{user_label}\{path}", ntuser_path, user_label, 0, limit - len(results))
        if len(results) >= limit:
            break
    return results


def walk_offline_shellbag(key, source_prefix, ntuser_path, user_label, depth, limit):
    if depth > 8 or limit <= 0:
        return []
    results = []
    for value in key.values():
        decoded = decode_registry_binary(value.value())
        if decoded and len(decoded) >= 3:
            results.append(shellbag_item(source_prefix, value.name(), decoded, offline_key_ts(key), ntuser_path, user_label))
            if len(results) >= limit:
                return results
    for subkey in key.subkeys():
        results += walk_offline_shellbag(subkey, source_prefix + "\\" + subkey.name(), ntuser_path, user_label, depth + 1, limit - len(results))
        if len(results) >= limit:
            return results
    return results


def get_file_activity_data(lnk_dirs=None, jump_list_dirs=None, ntuser_hive_paths=None, include_live_user_registry=False, include_default_live_paths=False, limit=5000):
    results = []
    lnk_dirs = list(lnk_dirs or [])
    jump_list_dirs = list(jump_list_dirs or [])
    if include_default_live_paths:
        lnk_dirs += default_live_lnk_dirs()
        jump_list_dirs += default_live_jump_dirs()
    results += scan_files(lnk_dirs, {".lnk"}, "LNK_FILE", limit=limit)
    results += scan_files(jump_list_dirs, {".automaticdestinations-ms", ".customdestinations-ms"}, "JUMP_LIST", limit=limit)
    if include_live_user_registry:
        results += live_recentdocs()
        results += live_shellbags()
    for ntuser_path in ntuser_hive_paths or []:
        results += offline_recentdocs(ntuser_path)
        results += offline_shellbags(ntuser_path)
    return results
