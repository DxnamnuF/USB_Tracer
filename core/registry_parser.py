from datetime import datetime, timedelta, timezone

try:
    import winreg
except ImportError:
    winreg = None

USBSTOR_PATH = r"SYSTEM\CurrentControlSet\Enum\USBSTOR"
WPD_PATH = r"SOFTWARE\Microsoft\Windows Portable Devices\Devices"


def is_generated_serial(serial: str) -> bool:
    """Винда ставит & вторым символом, если серийник выдумала сама"""
    return len(serial) > 1 and serial[1] == "&"


def filetime_to_utc(value):
    """FILETIME из реестра переводим в нормальную дату"""
    if not value:
        return None
    try:
        dt = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=value / 10)
        return dt.isoformat().replace("+00:00", "Z")
    except Exception:
        return None


def get_registry_value(key, value_name, default=None):
    """Берём значение, если его нет — ругаемся"""
    try:
        return winreg.QueryValueEx(key, value_name)[0]
    except FileNotFoundError:
        return default
    except OSError:
        return default


def enum_subkeys(key):
    """С писок подпапок в ключе реестра"""
    count = winreg.QueryInfoKey(key)[0]
    for i in range(count):
        try:
            yield winreg.EnumKey(key, i)
        except OSError:
            continue


def key_last_write_utc(key):
    """Это время последнего изменения ключа, а не время подключения :( """
    try:
        return filetime_to_utc(winreg.QueryInfoKey(key)[2])
    except OSError:
        return None


def clean_descriptor_part(text):
    if not text:
        return None
    return text.replace("_", " ").strip() or None


def parse_device_descriptor(device_str: str) -> dict:
    """Парсим строку вида Disk&Ven_...&Prod_...&Rev_..."""
    parsed = {
        "device_type": None,
        "vendor": None,
        "product": None,
        "revision": None,
    }

    parts = device_str.split("&")
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


def get_wpd_data():
    """Читаем WPD, там лежит нормальное имя"""
    if winreg is None:
        return []

    devices = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, WPD_PATH) as base_key:
            for device_id in enum_subkeys(base_key):
                try:
                    with winreg.OpenKey(base_key, device_id) as subkey:
                        friendly_name = get_registry_value(subkey, "FriendlyName")
                        device_desc = get_registry_value(subkey, "DeviceDesc")
                        label = get_registry_value(subkey, "Label")
                        devices.append({
                            "device_id": device_id,
                            "device_id_upper": device_id.upper(),
                            "friendly_name": friendly_name or label or device_desc,
                        })
                except OSError:
                    continue
    except OSError:
        pass

    return devices


def find_wpd_match(instance_str: str, wpd_devices: list):
    """Ищем WPD-запись, где внутри есть серийник из USBSTOR"""
    instance_upper = instance_str.upper()
    for item in wpd_devices:
        if instance_upper in item["device_id_upper"]:
            return item
    return None


def get_usbstor_data():
    """Главная функция. USBSTOR + немного WPD"""
    if winreg is None:
        return [{
            "error": "Czy naprawde jeseś teraz na windowsie?"
        }]

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
                                        friendly_name = "Unknown :("
                                        friendly_source = "fallback"

                                    results.append({
                                        "artifact_source": fr"HKLM\{USBSTOR_PATH}\{device_str}\{instance_str}",
                                        "vendor_product": device_str,
                                        "device_type": device_info["device_type"],
                                        "vendor": device_info["vendor"],
                                        "product": device_info["product"],
                                        "revision": device_info["revision"],
                                        "serial": instance_str,
                                        "friendly_name": friendly_name,
                                        "friendly_name_source": friendly_source,
                                        "wpd_match": bool(wpd_match),
                                        "wpd_device_id": wpd_match["device_id"] if wpd_match else None,
                                        "is_generated": is_generated_serial(instance_str),
                                        "parent_id_prefix": get_registry_value(instance_key, "ParentIdPrefix", "sirotka"),
                                        "container_id": get_registry_value(instance_key, "ContainerID"),
                                        "class_guid": get_registry_value(instance_key, "ClassGUID"),
                                        "hardware_id": get_registry_value(instance_key, "HardwareID", []),
                                        "last_write_utc": key_last_write_utc(instance_key),
                                    })
                            except OSError:
                                continue
                except OSError:
                    continue
    except PermissionError as e:
        return [{"error": f"Spróbuj admina, nie masz dostępu do USBSTOR: {e}"}]
    except OSError as e:
        return [{"error": f"USBSTOR nie otwarzaa się: {e}"}]

    return results


if __name__ == "__main__":
    for item in get_usbstor_data():
        if "error" in item:
            print(item["error"])
            continue
        status = "GEN" if item["is_generated"] else "HW"
        print(f"[{status}] {item['friendly_name']} | {item['serial']} | {item['last_write_utc']}")
