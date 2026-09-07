from datetime import datetime, timedelta, timezone

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
    import winreg
except ImportError:
    winreg = None

USBSTOR_PATH = r"SYSTEM\CurrentControlSet\Enum\USBSTOR"
USB_ENUM_PATH = r"SYSTEM\CurrentControlSet\Enum\USB"
SWD_WPDBUSENUM_PATH = r"SYSTEM\CurrentControlSet\Enum\SWD\WPDBUSENUM"
MOUNTED_DEVICES_PATH = r"SYSTEM\MountedDevices"
WPD_PATH = r"SOFTWARE\Microsoft\Windows Portable Devices\Devices"
MOUNTPOINTS2_PATH = r"Software\Microsoft\Windows\CurrentVersion\Explorer\MountPoints2"


def filetime_to_utc(value):
    if not value:
        return None
    try:
        dt = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=value / 10)
        return iso_utc(dt)
    except Exception:
        return None


def get_registry_value(key, value_name, default=None):
    try:
        return winreg.QueryValueEx(key, value_name)[0]
    except FileNotFoundError:
        return default
    except OSError:
        return default


def enum_subkeys(key):
    try:
        count = winreg.QueryInfoKey(key)[0]
    except OSError:
        return
    for i in range(count):
        try:
            yield winreg.EnumKey(key, i)
        except OSError:
            continue


def enum_values(key):
    try:
        count = winreg.QueryInfoKey(key)[1]
    except OSError:
        return
    for i in range(count):
        try:
            name, data, reg_type = winreg.EnumValue(key, i)
            yield name, data, reg_type
        except OSError:
            continue


def key_last_write_utc(key):
    try:
        return filetime_to_utc(winreg.QueryInfoKey(key)[2])
    except OSError:
        return None


def finalize_item(item):
    item["device_class"] = item.get("device_class") or classify_device(item)
    return item


def get_wpd_data():
    if winreg is None:
        return []
    devices = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, WPD_PATH) as base_key:
            base_last_write = key_last_write_utc(base_key)
            for device_id in enum_subkeys(base_key):
                try:
                    with winreg.OpenKey(base_key, device_id) as subkey:
                        friendly_name = get_registry_value(subkey, "FriendlyName")
                        device_desc = get_registry_value(subkey, "DeviceDesc")
                        label = get_registry_value(subkey, "Label")
                        source_id = extract_device_id(device_id)
                        item = {
                            "artifact_type": "WPD",
                            "artifact_source": fr"HKLM\{WPD_PATH}\{device_id}",
                            "device_id": device_id,
                            "device_id_upper": device_id.upper(),
                            "device_instance_id": source_id,
                            "serial": extract_serial_from_device_id(source_id),
                            "friendly_name": friendly_name or label or device_desc or "WPD device",
                            "last_write_utc": key_last_write_utc(subkey) or base_last_write,
                            "volume_guid": extract_volume_guid(device_id),
                            "message_short": "WPD stores a human-readable portable device record.",
                        }
                        devices.append(finalize_item(item))
                except OSError:
                    continue
    except OSError:
        pass
    return devices


def find_wpd_match(instance_str, wpd_devices):
    instance_upper = str(instance_str or "").upper()
    if not instance_upper:
        return None
    for item in wpd_devices:
        if instance_upper in item.get("device_id_upper", ""):
            return item
    return None


def get_usbstor_data():
    if winreg is None:
        return [{"error": "Live Registry parsing requires Windows. The winreg module is not available."}]
    results = []
    wpd_cache = get_wpd_data()
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, USBSTOR_PATH) as base_key:
            for device_str in enum_subkeys(base_key):
                device_info = parse_device_descriptor(device_str)
                try:
                    with winreg.OpenKey(base_key, device_str) as device_key:
                        for instance_str in enum_subkeys(device_key):
                            try:
                                with winreg.OpenKey(device_key, instance_str) as instance_key:
                                    friendly_name = get_registry_value(instance_key, "FriendlyName")
                                    friendly_source = "USBSTOR" if friendly_name else None
                                    wpd_match = find_wpd_match(instance_str, wpd_cache)
                                    if not friendly_name and wpd_match and wpd_match.get("friendly_name"):
                                        friendly_name = wpd_match["friendly_name"]
                                        friendly_source = "WPD"
                                    if not friendly_name:
                                        friendly_name = "Unknown USB storage device"
                                        friendly_source = "fallback"
                                    serial = instance_str
                                    item = {
                                        "artifact_type": "USBSTOR",
                                        "artifact_source": fr"HKLM\{USBSTOR_PATH}\{device_str}\{instance_str}",
                                        "device_instance_id": fr"USBSTOR\{device_str}\{instance_str}",
                                        "vendor_product": device_str,
                                        "device_type": device_info["device_type"],
                                        "vendor": device_info["vendor"],
                                        "product": device_info["product"],
                                        "revision": device_info["revision"],
                                        "serial": serial,
                                        "friendly_name": friendly_name,
                                        "friendly_name_source": friendly_source,
                                        "wpd_match": bool(wpd_match),
                                        "wpd_device_id": wpd_match["device_id"] if wpd_match else None,
                                        "is_generated": is_generated_serial(serial),
                                        "parent_id_prefix": get_registry_value(instance_key, "ParentIdPrefix"),
                                        "container_id": get_registry_value(instance_key, "ContainerID"),
                                        "class_guid": get_registry_value(instance_key, "ClassGUID"),
                                        "hardware_id": get_registry_value(instance_key, "HardwareID", []),
                                        "last_write_utc": key_last_write_utc(instance_key),
                                        "message_short": "Main USBSTOR artifact for a USB mass storage device.",
                                    }
                                    results.append(finalize_item(item))
                            except OSError:
                                continue
                except OSError:
                    continue
    except PermissionError as exc:
        return [{"error": f"USBSTOR access denied. Run the terminal as Administrator: {exc}"}]
    except OSError as exc:
        return [{"error": f"Could not open USBSTOR: {exc}"}]
    return results


def get_usb_enum_data():
    if winreg is None:
        return []
    results = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, USB_ENUM_PATH) as base_key:
            for device_id in enum_subkeys(base_key):
                vid, pid = extract_vid_pid(device_id)
                try:
                    with winreg.OpenKey(base_key, device_id) as device_key:
                        for instance in enum_subkeys(device_key):
                            try:
                                with winreg.OpenKey(device_key, instance) as instance_key:
                                    friendly = get_registry_value(instance_key, "FriendlyName")
                                    desc = get_registry_value(instance_key, "DeviceDesc")
                                    service = get_registry_value(instance_key, "Service")
                                    item = {
                                        "artifact_type": "USB_ENUM",
                                        "artifact_source": fr"HKLM\{USB_ENUM_PATH}\{device_id}\{instance}",
                                        "device_instance_id": fr"USB\{device_id}\{instance}",
                                        "friendly_name": friendly or desc or device_id,
                                        "serial": instance,
                                        "is_generated": is_generated_serial(instance),
                                        "vid": vid,
                                        "pid": pid,
                                        "service": service,
                                        "container_id": get_registry_value(instance_key, "ContainerID"),
                                        "class_guid": get_registry_value(instance_key, "ClassGUID"),
                                        "hardware_id": get_registry_value(instance_key, "HardwareID", []),
                                        "last_write_utc": key_last_write_utc(instance_key),
                                        "message_short": "Enum USB artifact with VID/PID and PnP instance data.",
                                    }
                                    results.append(finalize_item(item))
                            except OSError:
                                continue
                except OSError:
                    continue
    except OSError:
        pass
    return results


def get_swd_wpdbusenum_data():
    if winreg is None:
        return []
    results = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, SWD_WPDBUSENUM_PATH) as base_key:
            for device_id in enum_subkeys(base_key):
                try:
                    with winreg.OpenKey(base_key, device_id) as subkey:
                        source_id = extract_device_id(device_id)
                        friendly = get_registry_value(subkey, "FriendlyName") or get_registry_value(subkey, "DeviceDesc") or "WPD bus enumerated device"
                        item = {
                            "artifact_type": "SWD_WPDBUSENUM",
                            "artifact_source": fr"HKLM\{SWD_WPDBUSENUM_PATH}\{device_id}",
                            "device_id": device_id,
                            "device_instance_id": source_id or fr"SWD\WPDBUSENUM\{device_id}",
                            "friendly_name": friendly,
                            "serial": extract_serial_from_device_id(source_id),
                            "volume_guid": extract_volume_guid(device_id),
                            "container_id": get_registry_value(subkey, "ContainerID"),
                            "parent_id_prefix": get_registry_value(subkey, "ParentIdPrefix"),
                            "last_write_utc": key_last_write_utc(subkey),
                            "message_short": "SWD WPDBUSENUM links Portable Devices with USB/PnP records.",
                        }
                        results.append(finalize_item(item))
                except OSError:
                    continue
    except OSError:
        pass
    return results


def get_mounted_devices_data():
    if winreg is None:
        return []
    results = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, MOUNTED_DEVICES_PATH) as base_key:
            last_write = key_last_write_utc(base_key)
            for name, data, reg_type in enum_values(base_key):
                text = decode_registry_binary(data)
                device_id = extract_device_id(text)
                item = {
                    "artifact_type": "MOUNTED_DEVICES",
                    "artifact_source": fr"HKLM\{MOUNTED_DEVICES_PATH}:{name}",
                    "mount_name": name,
                    "drive_letter": extract_drive_letter(name),
                    "volume_guid": extract_volume_guid(name),
                    "device_instance_id": device_id,
                    "serial": extract_serial_from_device_id(device_id) or extract_serial_from_device_id(text),
                    "friendly_name": name,
                    "raw_target_text": text,
                    "last_write_utc": last_write,
                    "message_short": "MountedDevices can connect drive letters and Volume GUIDs with device identifiers.",
                }
                results.append(finalize_item(item))
    except OSError:
        pass
    return results


def get_mountpoints2_data():
    if winreg is None:
        return []
    results = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, MOUNTPOINTS2_PATH) as base_key:
            for mount_id in enum_subkeys(base_key):
                try:
                    with winreg.OpenKey(base_key, mount_id) as subkey:
                        device_id = extract_device_id(mount_id)
                        item = {
                            "artifact_type": "MOUNTPOINTS2",
                            "artifact_source": fr"HKCU\{MOUNTPOINTS2_PATH}\{mount_id}",
                            "mount_name": mount_id,
                            "drive_letter": extract_drive_letter(mount_id),
                            "volume_guid": extract_volume_guid(mount_id),
                            "device_instance_id": device_id,
                            "serial": extract_serial_from_device_id(device_id),
                            "friendly_name": mount_id,
                            "last_write_utc": key_last_write_utc(subkey),
                            "message_short": "MountPoints2 is a user-level artifact of storage access.",
                        }
                        results.append(finalize_item(item))
                except OSError:
                    continue
    except OSError:
        pass
    return results


def get_live_registry_artifacts(include_extended=True):
    base = get_usbstor_data()
    if base and isinstance(base[0], dict) and "error" in base[0]:
        return base
    if not include_extended:
        return base
    return base + get_usb_enum_data() + get_wpd_data() + get_swd_wpdbusenum_data() + get_mounted_devices_data() + get_mountpoints2_data()


if __name__ == "__main__":
    for entry in get_live_registry_artifacts():
        if "error" in entry:
            print(entry["error"])
        else:
            print(f"[{entry.get('artifact_type')}] {entry.get('friendly_name')} | {entry.get('serial')} | {entry.get('last_write_utc')}")
