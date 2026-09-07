from pathlib import Path

from .artifact_utils import (
    classify_device,
    decode_registry_binary,
    extract_device_id,
    extract_drive_letter,
    extract_serial_from_device_id,
    extract_vid_pid,
    extract_volume_guid,
    iso_utc,
    is_generated_serial,
    parse_device_descriptor,
)

try:
    from Registry import Registry
except ImportError:
    Registry = None


def open_hive(path):
    if not path:
        return None, {"error": "Hive path was not provided."}
    if Registry is None:
        return None, {"error": "Offline Registry parsing requires python-registry. Install it with: pip install python-registry"}
    try:
        return Registry.Registry(path), None
    except Exception as exc:
        return None, {"error": f"Could not open hive {path}: {exc}"}


def key_ts(key):
    try:
        return iso_utc(key.timestamp())
    except Exception:
        return None


def get_value(key, name, default=None):
    try:
        return key.value(name).value()
    except Exception:
        return default


def try_open(root, path):
    try:
        return root.open(path)
    except Exception:
        return None


def control_sets(system_hive):
    result = []
    try:
        select = system_hive.open("Select")
        current = int(select.value("Current").value())
        result.append(f"ControlSet{current:03d}")
    except Exception:
        pass
    try:
        root = system_hive.root()
        for subkey in root.subkeys():
            name = subkey.name()
            if name.upper().startswith("CONTROLSET") and name not in result:
                result.append(name)
    except Exception:
        pass
    return result or ["ControlSet001"]


def finalize_item(item):
    item["device_class"] = item.get("device_class") or classify_device(item)
    return item


def read_offline_wpd_data(software_hive_path):
    software, err = open_hive(software_hive_path)
    if err:
        return []
    base = try_open(software, r"Microsoft\Windows Portable Devices\Devices")
    if not base:
        return []
    items = []
    for subkey in base.subkeys():
        device_id = subkey.name()
        friendly = get_value(subkey, "FriendlyName") or get_value(subkey, "Label") or get_value(subkey, "DeviceDesc")
        source_id = extract_device_id(device_id)
        item = {
            "artifact_type": "WPD",
            "artifact_source": fr"SOFTWARE\Microsoft\Windows Portable Devices\Devices\{device_id}",
            "device_id": device_id,
            "device_id_upper": device_id.upper(),
            "device_instance_id": source_id,
            "serial": extract_serial_from_device_id(source_id),
            "friendly_name": friendly or "WPD device",
            "volume_guid": extract_volume_guid(device_id),
            "last_write_utc": key_ts(subkey),
            "message_short": "WPD artifact from an offline SOFTWARE hive.",
        }
        items.append(finalize_item(item))
    return items


def find_wpd_match(instance_str, wpd_items):
    upper = str(instance_str or "").upper()
    for item in wpd_items:
        if upper and upper in item.get("device_id_upper", ""):
            return item
    return None


def read_offline_usbstor(system_hive, system_hive_path, wpd_items):
    items = []
    for cs in control_sets(system_hive):
        base = try_open(system_hive, fr"{cs}\Enum\USBSTOR")
        if not base:
            continue
        for device_key in base.subkeys():
            device_str = device_key.name()
            device_info = parse_device_descriptor(device_str)
            for instance_key in device_key.subkeys():
                serial = instance_key.name()
                friendly = get_value(instance_key, "FriendlyName")
                source = "USBSTOR" if friendly else None
                wpd_match = find_wpd_match(serial, wpd_items)
                if not friendly and wpd_match:
                    friendly = wpd_match.get("friendly_name")
                    source = "WPD"
                if not friendly:
                    friendly = "Unknown USB storage device"
                    source = "fallback"
                item = {
                    "artifact_type": "USBSTOR",
                    "artifact_source": fr"SYSTEM\{cs}\Enum\USBSTOR\{device_str}\{serial}",
                    "device_instance_id": fr"USBSTOR\{device_str}\{serial}",
                    "vendor_product": device_str,
                    "device_type": device_info.get("device_type"),
                    "vendor": device_info.get("vendor"),
                    "product": device_info.get("product"),
                    "revision": device_info.get("revision"),
                    "serial": serial,
                    "friendly_name": friendly,
                    "friendly_name_source": source,
                    "wpd_match": bool(wpd_match),
                    "wpd_device_id": wpd_match.get("device_id") if wpd_match else None,
                    "is_generated": is_generated_serial(serial),
                    "parent_id_prefix": get_value(instance_key, "ParentIdPrefix"),
                    "container_id": get_value(instance_key, "ContainerID"),
                    "class_guid": get_value(instance_key, "ClassGUID"),
                    "hardware_id": get_value(instance_key, "HardwareID", []),
                    "control_set": cs,
                    "last_write_utc": key_ts(instance_key),
                    "message_short": "USBSTOR artifact from an offline SYSTEM hive.",
                }
                items.append(finalize_item(item))
    return items


def read_offline_usb_enum(system_hive, system_hive_path):
    items = []
    for cs in control_sets(system_hive):
        base = try_open(system_hive, fr"{cs}\Enum\USB")
        if not base:
            continue
        for dev_key in base.subkeys():
            device_id = dev_key.name()
            vid, pid = extract_vid_pid(device_id)
            for instance_key in dev_key.subkeys():
                instance = instance_key.name()
                friendly = get_value(instance_key, "FriendlyName") or get_value(instance_key, "DeviceDesc") or device_id
                item = {
                    "artifact_type": "USB_ENUM",
                    "artifact_source": fr"SYSTEM\{cs}\Enum\USB\{device_id}\{instance}",
                    "device_instance_id": fr"USB\{device_id}\{instance}",
                    "friendly_name": friendly,
                    "serial": instance,
                    "is_generated": is_generated_serial(instance),
                    "vid": vid,
                    "pid": pid,
                    "service": get_value(instance_key, "Service"),
                    "container_id": get_value(instance_key, "ContainerID"),
                    "class_guid": get_value(instance_key, "ClassGUID"),
                    "hardware_id": get_value(instance_key, "HardwareID", []),
                    "control_set": cs,
                    "last_write_utc": key_ts(instance_key),
                    "message_short": "Enum USB artifact from an offline SYSTEM hive.",
                }
                items.append(finalize_item(item))
    return items


def read_offline_swd_wpdbusenum(system_hive, system_hive_path):
    items = []
    for cs in control_sets(system_hive):
        base = try_open(system_hive, fr"{cs}\Enum\SWD\WPDBUSENUM")
        if not base:
            continue
        for subkey in base.subkeys():
            device_id = subkey.name()
            source_id = extract_device_id(device_id)
            friendly = get_value(subkey, "FriendlyName") or get_value(subkey, "DeviceDesc") or "WPD bus enumerated device"
            item = {
                "artifact_type": "SWD_WPDBUSENUM",
                "artifact_source": fr"SYSTEM\{cs}\Enum\SWD\WPDBUSENUM\{device_id}",
                "device_id": device_id,
                "device_instance_id": source_id or fr"SWD\WPDBUSENUM\{device_id}",
                "friendly_name": friendly,
                "serial": extract_serial_from_device_id(source_id),
                "volume_guid": extract_volume_guid(device_id),
                "container_id": get_value(subkey, "ContainerID"),
                "parent_id_prefix": get_value(subkey, "ParentIdPrefix"),
                "control_set": cs,
                "last_write_utc": key_ts(subkey),
                "message_short": "SWD WPDBUSENUM artifact from an offline SYSTEM hive.",
            }
            items.append(finalize_item(item))
    return items


def read_offline_mounted_devices(system_hive, system_hive_path):
    base = try_open(system_hive, "MountedDevices")
    if not base:
        return []
    items = []
    for value in base.values():
        name = value.name()
        text = decode_registry_binary(value.value())
        device_id = extract_device_id(text)
        item = {
            "artifact_type": "MOUNTED_DEVICES",
            "artifact_source": fr"SYSTEM\MountedDevices:{name}",
            "mount_name": name,
            "drive_letter": extract_drive_letter(name),
            "volume_guid": extract_volume_guid(name),
            "device_instance_id": device_id,
            "serial": extract_serial_from_device_id(device_id) or extract_serial_from_device_id(text),
            "friendly_name": name,
            "raw_target_text": text,
            "last_write_utc": key_ts(base),
            "message_short": "MountedDevices artifact from an offline SYSTEM hive.",
        }
        items.append(finalize_item(item))
    return items


def read_offline_mountpoints2(ntuser_hive_path):
    ntuser, err = open_hive(ntuser_hive_path)
    if err:
        return [err]
    base = try_open(ntuser, r"Software\Microsoft\Windows\CurrentVersion\Explorer\MountPoints2")
    if not base:
        return []
    items = []
    user_label = Path(ntuser_hive_path).parent.name or Path(ntuser_hive_path).name
    for subkey in base.subkeys():
        mount_id = subkey.name()
        device_id = extract_device_id(mount_id)
        item = {
            "artifact_type": "MOUNTPOINTS2",
            "artifact_source": fr"NTUSER.DAT:{user_label}\Software\Microsoft\Windows\CurrentVersion\Explorer\MountPoints2\{mount_id}",
            "user_hive": str(ntuser_hive_path),
            "user_label": user_label,
            "mount_name": mount_id,
            "drive_letter": extract_drive_letter(mount_id),
            "volume_guid": extract_volume_guid(mount_id),
            "device_instance_id": device_id,
            "serial": extract_serial_from_device_id(device_id),
            "friendly_name": mount_id,
            "last_write_utc": key_ts(subkey),
            "message_short": "User MountPoints2 artifact from an offline NTUSER.DAT hive.",
        }
        items.append(finalize_item(item))
    return items


def get_offline_registry_artifacts(system_hive_path=None, software_hive_path=None, ntuser_hive_paths=None, include_extended=True):
    items = []
    errors = []
    ntuser_hive_paths = [p for p in (ntuser_hive_paths or []) if p]
    wpd_items = read_offline_wpd_data(software_hive_path) if software_hive_path else []
    if system_hive_path:
        system_hive, err = open_hive(system_hive_path)
        if err:
            errors.append(err)
        else:
            items += read_offline_usbstor(system_hive, system_hive_path, wpd_items)
            if include_extended:
                items += read_offline_usb_enum(system_hive, system_hive_path)
                items += read_offline_swd_wpdbusenum(system_hive, system_hive_path)
                items += read_offline_mounted_devices(system_hive, system_hive_path)
    elif not ntuser_hive_paths and not software_hive_path:
        errors.append({"error": "Offline Registry parsing requires at least one hive path."})
    if include_extended:
        items += wpd_items
        for ntuser_path in ntuser_hive_paths:
            items += read_offline_mountpoints2(ntuser_path)
    return items + errors
