from datetime import datetime, timezone

from .artifact_utils import classify_device, extract_drive_letter, extract_serial_from_device_id, extract_volume_guid


def parse_time(value):
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def serial_key(value):
    if not value:
        return None
    text = str(value).upper().strip()
    if text.endswith("&0"):
        text = text[:-2]
    return text


def list_add_unique(target, value):
    if not value:
        return
    if isinstance(value, list):
        for item in value:
            list_add_unique(target, item)
        return
    if value not in target:
        target.append(value)


def registry_action_text(artifact_type):
    mapping = {
        "USBSTOR": "USBSTOR key changed",
        "USB_ENUM": "Enum USB key changed",
        "WPD": "Windows Portable Devices key changed",
        "SWD_WPDBUSENUM": "SWD WPDBUSENUM key changed",
        "MOUNTED_DEVICES": "MountedDevices key changed",
        "MOUNTPOINTS2": "user MountPoints2 key changed",
    }
    return mapping.get(artifact_type or "", "registry artifact")


def registry_to_timeline(registry_items):
    timeline = []
    for item in registry_items:
        if not isinstance(item, dict) or "error" in item:
            continue
        artifact_type = item.get("artifact_type") or "REGISTRY"
        timeline.append({
            "event_kind": "registry",
            "timestamp_utc": item.get("last_write_utc"),
            "timestamp_local": item.get("timestamp_local"),
            "action": f"registry_{artifact_type.lower()}",
            "action_text": registry_action_text(artifact_type),
            "artifact_type": artifact_type,
            "friendly_name": item.get("friendly_name"),
            "device_class": item.get("device_class") or classify_device(item),
            "device_instance_id": item.get("device_instance_id"),
            "device_id": item.get("device_id"),
            "mount_name": item.get("mount_name"),
            "drive_letter": item.get("drive_letter") or extract_drive_letter(item.get("mount_name")),
            "volume_guid": item.get("volume_guid") or extract_volume_guid(item.get("mount_name")),
            "raw_target_text": item.get("raw_target_text"),
            "vendor_product": item.get("vendor_product"),
            "device_type": item.get("device_type"),
            "vendor": item.get("vendor"),
            "product": item.get("product"),
            "revision": item.get("revision"),
            "vid": item.get("vid"),
            "pid": item.get("pid"),
            "serial": item.get("serial"),
            "is_generated": item.get("is_generated"),
            "parent_id_prefix": item.get("parent_id_prefix"),
            "container_id": item.get("container_id"),
            "class_guid": item.get("class_guid"),
            "hardware_id": item.get("hardware_id"),
            "service": item.get("service"),
            "control_set": item.get("control_set"),
            "user_hive": item.get("user_hive"),
            "user_label": item.get("user_label"),
            "artifact_source": item.get("artifact_source"),
            "matched_registry_name": item.get("friendly_name"),
            "matched_registry_serial": item.get("serial"),
            "match_confidence": "source" if item.get("artifact_type") == "USBSTOR" else None,
            "message_short": item.get("message_short") or "Registry LastWrite timestamp.",
            "wpd_device_id": item.get("wpd_device_id"),
            "friendly_name_source": item.get("friendly_name_source"),
        })
    return timeline


def build_registry_index(registry_items):
    by_serial = {}
    by_vendor_product = {}
    by_vid_pid = {}
    by_volume_guid = {}
    by_drive_letter = {}
    serial_links = {}
    volume_links = {}
    for item in registry_items:
        if not isinstance(item, dict) or "error" in item:
            continue
        s = serial_key(item.get("serial"))
        if s and item.get("artifact_type") == "USBSTOR":
            by_serial[s] = item
        elif s and s not in by_serial:
            by_serial[s] = item
        vp = item.get("vendor_product")
        if vp:
            by_vendor_product[str(vp).upper()] = item
        vid = item.get("vid")
        pid = item.get("pid")
        if vid and pid:
            by_vid_pid[f"VID_{str(vid).upper()}&PID_{str(pid).upper()}"] = item
        volume = item.get("volume_guid") or extract_volume_guid(item.get("mount_name"))
        drive = item.get("drive_letter") or extract_drive_letter(item.get("mount_name"))
        if volume:
            by_volume_guid[str(volume).upper()] = item
        if drive:
            by_drive_letter[str(drive).upper()] = item
        if s:
            links = serial_links.setdefault(s, {"drive_letters": [], "volume_guids": []})
            list_add_unique(links["drive_letters"], drive)
            list_add_unique(links["volume_guids"], volume)
        if volume:
            links = volume_links.setdefault(str(volume).upper(), {"drive_letters": [], "serials": []})
            list_add_unique(links["drive_letters"], drive)
            list_add_unique(links["serials"], s)
    return by_serial, by_vendor_product, by_vid_pid, by_volume_guid, by_drive_letter, serial_links, volume_links


def enrich_with_drive_links(item, serial_links, volume_links):
    drive_letters = []
    volume_guids = []
    list_add_unique(drive_letters, item.get("drive_letter"))
    list_add_unique(volume_guids, item.get("volume_guid"))
    s = serial_key(item.get("matched_registry_serial") or item.get("serial"))
    if s and s in serial_links:
        list_add_unique(drive_letters, serial_links[s].get("drive_letters"))
        list_add_unique(volume_guids, serial_links[s].get("volume_guids"))
    volume = item.get("volume_guid")
    if volume and str(volume).upper() in volume_links:
        list_add_unique(drive_letters, volume_links[str(volume).upper()].get("drive_letters"))
        for serial in volume_links[str(volume).upper()].get("serials") or []:
            if serial and not item.get("serial"):
                item["serial"] = serial
    if drive_letters:
        item["drive_letters"] = sorted(drive_letters)
        if not item.get("drive_letter"):
            item["drive_letter"] = drive_letters[0]
    if volume_guids:
        item["volume_guids"] = sorted(volume_guids)
        if not item.get("volume_guid"):
            item["volume_guid"] = volume_guids[0]
    return item


def enrich_item_with_registry(item, by_serial, by_vendor_product, by_vid_pid, by_volume_guid, by_drive_letter, serial_links, volume_links):
    matched = None
    confidence = None
    s = serial_key(item.get("serial"))
    if s and s in by_serial:
        matched = by_serial[s]
        confidence = "serial"
    text = " ".join(str(item.get(k) or "") for k in ["device_instance_id", "message", "message_short", "raw_target_text", "file_path", "friendly_name"]).upper()
    if not matched:
        for reg_serial, reg_item in by_serial.items():
            if reg_serial and reg_serial in text:
                matched = reg_item
                confidence = "serial_in_text"
                break
    if not matched:
        vp = item.get("vendor_product")
        if vp and str(vp).upper() in by_vendor_product:
            matched = by_vendor_product[str(vp).upper()]
            confidence = "vendor_product"
    if not matched:
        for reg_vp, reg_item in by_vendor_product.items():
            if reg_vp and reg_vp in text:
                matched = reg_item
                confidence = "vendor_product_in_text"
                break
    if not matched:
        vid = item.get("vid")
        pid = item.get("pid")
        vidpid = f"VID_{str(vid).upper()}&PID_{str(pid).upper()}" if vid and pid else None
        if vidpid and vidpid in by_vid_pid:
            matched = by_vid_pid[vidpid]
            confidence = "vid_pid"
    if not matched:
        for vidpid, reg_item in by_vid_pid.items():
            if vidpid and vidpid in text:
                matched = reg_item
                confidence = "vid_pid_in_text"
                break
    if not matched:
        volume = item.get("volume_guid") or extract_volume_guid(text)
        if volume and str(volume).upper() in by_volume_guid:
            matched = by_volume_guid[str(volume).upper()]
            confidence = "volume_guid"
    if not matched:
        drive = item.get("drive_letter") or extract_drive_letter(text)
        if drive and str(drive).upper() in by_drive_letter:
            matched = by_drive_letter[str(drive).upper()]
            confidence = "drive_letter"
    if matched:
        item["friendly_name"] = item.get("friendly_name") or matched.get("friendly_name")
        item["matched_registry_name"] = matched.get("friendly_name")
        item["matched_registry_serial"] = matched.get("serial")
        item["matched_registry_artifact"] = matched.get("artifact_source")
        item["match_confidence"] = confidence
        for field in [
            "vendor_product", "vendor", "product", "revision", "device_type", "is_generated", "parent_id_prefix", "container_id", "vid", "pid", "device_class"
        ]:
            if not item.get(field):
                item[field] = matched.get(field)
    else:
        item["match_confidence"] = item.get("match_confidence")
    if not item.get("device_class"):
        item["device_class"] = classify_device(item)
    return enrich_with_drive_links(item, serial_links, volume_links)


def artifact_to_timeline(items, default_kind):
    timeline = []
    for item in items or []:
        if not isinstance(item, dict) or "error" in item:
            continue
        copy = dict(item)
        copy["event_kind"] = copy.get("event_kind") or default_kind
        if not copy.get("timestamp_utc") and copy.get("last_write_utc"):
            copy["timestamp_utc"] = copy.get("last_write_utc")
        if not copy.get("device_class"):
            copy["device_class"] = classify_device(copy)
        timeline.append(copy)
    return timeline


def build_timeline(registry_items, eventlog_items=None, setupapi_items=None, file_activity_items=None):
    eventlog_items = eventlog_items or []
    setupapi_items = setupapi_items or []
    file_activity_items = file_activity_items or []
    by_serial, by_vendor_product, by_vid_pid, by_volume_guid, by_drive_letter, serial_links, volume_links = build_registry_index(registry_items)
    timeline = registry_to_timeline(registry_items)
    for item in eventlog_items:
        if isinstance(item, dict) and "error" not in item:
            timeline.append(enrich_item_with_registry(dict(item), by_serial, by_vendor_product, by_vid_pid, by_volume_guid, by_drive_letter, serial_links, volume_links))
    for item in setupapi_items:
        if isinstance(item, dict) and "error" not in item:
            timeline.append(enrich_item_with_registry(dict(item), by_serial, by_vendor_product, by_vid_pid, by_volume_guid, by_drive_letter, serial_links, volume_links))
    for item in file_activity_items:
        if isinstance(item, dict) and "error" not in item:
            timeline.append(enrich_item_with_registry(dict(item), by_serial, by_vendor_product, by_vid_pid, by_volume_guid, by_drive_letter, serial_links, volume_links))
    for item in timeline:
        enrich_with_drive_links(item, serial_links, volume_links)
    timeline.sort(key=lambda item: (parse_time(item.get("timestamp_utc")) or datetime.min.replace(tzinfo=timezone.utc), item.get("timestamp_local") or ""))
    return timeline
