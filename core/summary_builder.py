from datetime import datetime, timezone


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
    text = str(value).upper().replace("&0", "").strip()
    return text or None


def list_add_unique(target, value):
    if not value:
        return
    if isinstance(value, list):
        for item in value:
            list_add_unique(target, item)
        return
    if value not in target:
        target.append(value)


def device_group_key(item):
    serial = serial_key(item.get("matched_registry_serial") or item.get("serial"))
    if serial:
        return f"serial:{serial}"
    volume = item.get("volume_guid")
    if volume:
        return f"volume:{str(volume).upper()}"
    drive = item.get("drive_letter")
    if drive:
        return f"drive:{str(drive).upper()}"
    container_id = item.get("container_id")
    if container_id:
        return f"container:{str(container_id).upper()}"
    device_id = item.get("device_instance_id")
    if device_id:
        return f"device:{str(device_id).upper()}"
    vendor_product = item.get("vendor_product")
    if vendor_product:
        return f"vendor_product:{str(vendor_product).upper()}"
    return f"source:{item.get('artifact_source') or id(item)}"


def nice_source(item):
    kind = item.get("event_kind") or "registry"
    if kind == "eventlog":
        return f"EventLog:{item.get('channel') or 'unknown'}"
    if kind == "setupapi":
        return "SetupAPI.dev.log"
    if kind == "file_activity":
        return item.get("artifact_type") or "FileActivity"
    return item.get("artifact_type") or "Registry"


def build_device_summary(timeline):
    groups = {}
    for item in timeline:
        if not isinstance(item, dict) or "error" in item:
            continue
        key = device_group_key(item)
        dt = parse_time(item.get("timestamp_utc"))
        source = nice_source(item)
        summary = groups.setdefault(key, {
            "device_key": key,
            "friendly_name": None,
            "device_class": None,
            "serial": None,
            "vendor": None,
            "product": None,
            "revision": None,
            "vid": None,
            "pid": None,
            "first_seen_utc": None,
            "last_seen_utc": None,
            "first_seen_local": None,
            "last_seen_local": None,
            "evidence_count": 0,
            "registry_artifacts_count": 0,
            "eventlog_events_count": 0,
            "setupapi_events_count": 0,
            "file_activity_count": 0,
            "sources": [],
            "drive_letters": [],
            "volume_guids": [],
            "user_labels": [],
            "event_ids": [],
            "is_generated": False,
        })
        for field in ["friendly_name", "device_class", "serial", "vendor", "product", "revision", "vid", "pid"]:
            if not summary.get(field) and item.get(field):
                summary[field] = item.get(field)
        if item.get("matched_registry_serial") and not summary.get("serial"):
            summary["serial"] = item.get("matched_registry_serial")
        if item.get("matched_registry_name") and not summary.get("friendly_name"):
            summary["friendly_name"] = item.get("matched_registry_name")
        if item.get("is_generated"):
            summary["is_generated"] = True
        list_add_unique(summary["sources"], source)
        list_add_unique(summary["drive_letters"], item.get("drive_letter"))
        list_add_unique(summary["drive_letters"], item.get("drive_letters"))
        list_add_unique(summary["volume_guids"], item.get("volume_guid"))
        list_add_unique(summary["volume_guids"], item.get("volume_guids"))
        list_add_unique(summary["user_labels"], item.get("user_label"))
        list_add_unique(summary["event_ids"], item.get("event_id"))
        summary["evidence_count"] += 1
        kind = item.get("event_kind")
        if kind == "eventlog":
            summary["eventlog_events_count"] += 1
        elif kind == "setupapi":
            summary["setupapi_events_count"] += 1
        elif kind == "file_activity":
            summary["file_activity_count"] += 1
        else:
            summary["registry_artifacts_count"] += 1
        if dt:
            current_first = parse_time(summary.get("first_seen_utc"))
            current_last = parse_time(summary.get("last_seen_utc"))
            if current_first is None or dt < current_first:
                summary["first_seen_utc"] = dt.isoformat().replace("+00:00", "Z")
            if current_last is None or dt > current_last:
                summary["last_seen_utc"] = dt.isoformat().replace("+00:00", "Z")
        local_time = item.get("timestamp_local")
        if local_time:
            if not summary.get("first_seen_local") or str(local_time) < str(summary.get("first_seen_local")):
                summary["first_seen_local"] = local_time
            if not summary.get("last_seen_local") or str(local_time) > str(summary.get("last_seen_local")):
                summary["last_seen_local"] = local_time
    result = list(groups.values())
    for item in result:
        item["sources"] = sorted(item["sources"])
        item["drive_letters"] = sorted(item["drive_letters"])
        item["volume_guids"] = sorted(item["volume_guids"])
        item["user_labels"] = sorted(item["user_labels"])
        item["event_ids"] = sorted(str(x) for x in item["event_ids"] if x is not None)
    result.sort(key=lambda x: (parse_time(x.get("last_seen_utc")) or datetime.min.replace(tzinfo=timezone.utc), x.get("last_seen_local") or ""), reverse=True)
    return result
