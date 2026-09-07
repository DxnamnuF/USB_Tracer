import argparse
import csv
import json
import sys
import time
from pathlib import Path

try:
    from colorama import Fore, Style, init
except ImportError:
    def init(*args, **kwargs):
        pass

    class _NoColor:
        def __getattr__(self, name):
            return ""

    Fore = _NoColor()
    Style = _NoColor()

from core.eventlog_parser import get_usb_eventlog_data, get_usb_evtx_data
from core.file_activity_parser import get_file_activity_data
from core.html_report import save_html_report
from core.offline_hive_parser import get_offline_registry_artifacts
from core.registry_parser import get_live_registry_artifacts
from core.relationship_graph import build_graph_dot
from core.setupapi_parser import get_setupapi_data
from core.summary_builder import build_device_summary
from core.timeline_builder import build_timeline

init(autoreset=True)


def print_header(text):
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'=' * 76}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{text.center(76)}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 76}\n")


def split_errors(data):
    errors = []
    clean = []
    for item in data or []:
        if isinstance(item, dict) and "error" in item:
            errors.append(item)
        else:
            clean.append(item)
    return clean, errors


def print_errors(title, errors):
    if not errors:
        return
    print(f"{Fore.YELLOW}[!] {title}")
    for item in errors:
        print(f"    {item.get('error')}")


def stringify(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def save_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_csv(path, data):
    if not data:
        Path(path).write_text("", encoding="utf-8")
        return
    preferred = [
        "event_kind", "artifact_type", "timestamp_utc", "timestamp_local", "action", "action_text",
        "friendly_name", "device_class", "device_instance_id", "device_id", "mount_name", "drive_letter",
        "drive_letters", "volume_guid", "volume_guids", "device_type", "vendor", "product", "revision",
        "vid", "pid", "vendor_product", "serial", "is_generated", "first_seen_utc", "last_seen_utc",
        "first_seen_local", "last_seen_local", "evidence_count", "registry_artifacts_count", "eventlog_events_count",
        "setupapi_events_count", "file_activity_count", "sources", "user_labels", "event_ids", "parent_id_prefix",
        "container_id", "channel", "provider", "event_id", "level", "record_id", "machine_name",
        "match_confidence", "matched_registry_name", "matched_registry_serial", "artifact_source",
        "file_path", "target_candidates",
        "message_short", "wpd_device_id", "friendly_name_source", "raw_target_text",
    ]
    extra = sorted({k for row in data for k in row.keys()} - set(preferred))
    fields = [field for field in preferred if any(field in row for row in data)] + extra
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in data:
            writer.writerow({key: stringify(value) for key, value in row.items()})


def print_device(idx, item):
    artifact_type = item.get("artifact_type") or "REGISTRY"
    name = item.get("friendly_name") or item.get("mount_name") or item.get("device_instance_id") or "unknown artifact"
    print(f"{Fore.YELLOW}[{idx}] {Style.BRIGHT}{artifact_type}: {name}")
    print(f"    Class          : {item.get('device_class') or 'unknown'}")
    if item.get("vendor") or item.get("product"):
        print(f"    Vendor/Product : {item.get('vendor') or '?'} / {item.get('product') or '?'}")
    if item.get("vid") or item.get("pid"):
        print(f"    VID/PID        : {item.get('vid') or '?'} / {item.get('pid') or '?'}")
    if item.get("vendor_product"):
        print(f"    USBSTOR ID     : {item.get('vendor_product')}")
    if item.get("device_instance_id"):
        print(f"    Device ID      : {item.get('device_instance_id')}")
    if item.get("serial"):
        label = "generated" if item.get("is_generated") else "hardware-like"
        print(f"    Serial         : {item.get('serial')} ({label})")
    if item.get("drive_letter"):
        print(f"    Drive letter   : {item.get('drive_letter')}")
    if item.get("volume_guid"):
        print(f"    Volume GUID    : {item.get('volume_guid')}")
    if item.get("container_id"):
        print(f"    ContainerID    : {item.get('container_id')}")
    if item.get("parent_id_prefix"):
        print(f"    ParentIdPrefix : {item.get('parent_id_prefix')}")
    if item.get("last_write_utc"):
        print(f"    LastWrite UTC  : {item.get('last_write_utc')}")
    print(f"    Artifact       : {item.get('artifact_source')}")
    if item.get("message_short"):
        print(f"    Note           : {item.get('message_short')}")
    print(f"{Fore.LIGHTBLACK_EX}{'-' * 76}")


def print_event(idx, item):
    device = item.get("device_instance_id") or item.get("matched_registry_name") or "device was not extracted"
    print(f"{Fore.MAGENTA}[{idx}] {item.get('timestamp_utc') or item.get('timestamp_local') or 'time not found'} | {item.get('event_kind')} | {item.get('action_text')}")
    print(f"    Source         : {item.get('channel') or item.get('artifact_type') or item.get('event_file')}")
    if item.get("provider"):
        print(f"    Provider       : {item.get('provider')}")
    if item.get("event_id"):
        print(f"    Event ID       : {item.get('event_id')}")
    if item.get("record_id"):
        print(f"    Record ID      : {item.get('record_id')}")
    print(f"    Device ID      : {device}")
    print(f"    Class          : {item.get('device_class') or 'unknown'}")
    if item.get("serial"):
        print(f"    Serial         : {item.get('serial')}")
    if item.get("drive_letter"):
        print(f"    Drive letter   : {item.get('drive_letter')}")
    if item.get("volume_guid"):
        print(f"    Volume GUID    : {item.get('volume_guid')}")
    if item.get("matched_registry_name"):
        print(f"    Registry match : {item.get('matched_registry_name')} ({item.get('match_confidence')})")
    print(f"    Note           : {item.get('message_short') or 'empty'}")
    print(f"{Fore.LIGHTBLACK_EX}{'-' * 76}")


def print_timeline_item(idx, item):
    color = Fore.MAGENTA if item.get("event_kind") in ["eventlog", "setupapi"] else Fore.YELLOW
    source = item.get("channel") if item.get("event_kind") == "eventlog" else item.get("artifact_type") or item.get("event_kind")
    name = item.get("friendly_name") or item.get("matched_registry_name") or item.get("device_instance_id") or item.get("artifact_source") or "unknown device"
    print(f"{color}[{idx}] {item.get('timestamp_utc') or item.get('timestamp_local') or 'time not found'} | {source} | {item.get('action_text')}")
    print(f"    Device         : {name}")
    print(f"    Class          : {item.get('device_class') or 'unknown'}")
    if item.get("serial"):
        print(f"    Serial         : {item.get('serial')}")
    if item.get("drive_letters") or item.get("drive_letter"):
        print(f"    Drive letters  : {', '.join(item.get('drive_letters') or [item.get('drive_letter')])}")
    if item.get("volume_guids") or item.get("volume_guid"):
        print(f"    Volume GUIDs   : {', '.join(item.get('volume_guids') or [item.get('volume_guid')])}")
    if item.get("vendor") or item.get("product"):
        print(f"    Vendor/Product : {item.get('vendor') or '?'} / {item.get('product') or '?'}")
    if item.get("vid") or item.get("pid"):
        print(f"    VID/PID        : {item.get('vid') or '?'} / {item.get('pid') or '?'}")
    if item.get("match_confidence"):
        print(f"    Match          : {item.get('match_confidence')} -> {item.get('matched_registry_name')}")
    print(f"    Artifact       : {item.get('artifact_source')}")
    if item.get("message_short"):
        print(f"    Note           : {item.get('message_short')}")
    print(f"{Fore.LIGHTBLACK_EX}{'-' * 76}")


def print_summary(summary):
    if not summary:
        print(f"{Fore.RED}[!] Summary is empty.")
        return
    for idx, item in enumerate(summary, 1):
        print(f"{Fore.GREEN}[{idx}] {Style.BRIGHT}{item.get('friendly_name') or item.get('device_key')}")
        print(f"    Class          : {item.get('device_class') or 'unknown'}")
        print(f"    Serial         : {item.get('serial') or 'not found'}")
        print(f"    First seen UTC : {item.get('first_seen_utc') or 'not found'}")
        print(f"    Last seen UTC  : {item.get('last_seen_utc') or 'not found'}")
        if item.get("first_seen_local") or item.get("last_seen_local"):
            print(f"    Local times    : {item.get('first_seen_local') or 'not found'} -> {item.get('last_seen_local') or 'not found'}")
        print(f"    Evidence       : {item.get('evidence_count')} records")
        print(f"    Registry/Event : {item.get('registry_artifacts_count')} / {item.get('eventlog_events_count')}")
        print(f"    SetupAPI/File  : {item.get('setupapi_events_count')} / {item.get('file_activity_count')}")
        if item.get("drive_letters"):
            print(f"    Drive letters  : {', '.join(item.get('drive_letters'))}")
        if item.get("volume_guids"):
            print(f"    Volume GUIDs   : {', '.join(item.get('volume_guids'))}")
        if item.get("user_labels"):
            print(f"    User hives     : {', '.join(item.get('user_labels'))}")
        print(f"    Sources        : {', '.join(item.get('sources') or [])}")
        print(f"{Fore.LIGHTBLACK_EX}{'-' * 76}")


def parse_args():
    parser = argparse.ArgumentParser(description="DFIR_project: offline hive-first USB DFIR timeline builder")
    parser.add_argument("--mode", choices=["hive", "live", "registry", "events", "setupapi", "file-activity", "timeline", "summary"], default="hive", help="analysis mode; default is hive for offline forensic work")
    parser.add_argument("--days", type=int, default=30, help="recent days for live Event Log; 0 disables the StartTime filter")
    parser.add_argument("--max-events", type=int, default=2000, help="maximum events per live channel or EVTX file")
    parser.add_argument("--system-hive", help="offline SYSTEM hive path; primary source for hive mode")
    parser.add_argument("--software-hive", help="offline SOFTWARE hive path")
    parser.add_argument("--ntuser-hive", action="append", default=[], help="offline NTUSER.DAT hive path; can be used multiple times")
    parser.add_argument("--live-events", action="store_true", help="read live Event Log with timeline or summary mode when this is intentional")
    parser.add_argument("--evtx", action="append", default=[], help="offline EVTX file; can be used multiple times")
    parser.add_argument("--setupapi-log", action="append", default=[], help="setupapi.dev.log path; can be used multiple times")
    parser.add_argument("--lnk-dir", action="append", default=[], help="directory with LNK files; can be used multiple times")
    parser.add_argument("--jump-list-dir", action="append", default=[], help="directory with Jump List files; can be used multiple times")
    parser.add_argument("--include-file-activity", action="store_true", help="include LNK, Jump Lists, RecentDocs, and ShellBags in timeline, summary, and hive mode")
    parser.add_argument("--include-live-user-artifacts", action="store_true", help="read live HKCU RecentDocs and ShellBags")
    parser.add_argument("--include-default-live-paths", action="store_true", help="scan current user's default Recent and Jump List directories")
    parser.add_argument("--file-scan-limit", type=int, default=5000, help="maximum number of LNK and Jump List files to scan")
    parser.add_argument("--no-extended-registry", action="store_true", help="read only USBSTOR/WPD without MountedDevices, Enum USB, SWD WPDBUSENUM, and MountPoints2")
    parser.add_argument("--keep-unmatched-events", action="store_true", help="keep Event Log entries even when no USB identifier was extracted")
    parser.add_argument("--live-interval", type=float, default=3.0, help="seconds between live mode refreshes")
    parser.add_argument("--live-count", type=int, default=0, help="number of live refresh cycles; 0 means until Ctrl+C")
    parser.add_argument("--json", dest="json_path", help="save the main result to JSON")
    parser.add_argument("--csv", dest="csv_path", help="save the main result to CSV")
    parser.add_argument("--summary-json", help="save the device summary to JSON")
    parser.add_argument("--summary-csv", help="save the device summary to CSV")
    parser.add_argument("--html", dest="html_path", help="save the HTML report")
    parser.add_argument("--graph-dot", help="save the relationship graph as Graphviz DOT")
    return parser.parse_args()


def using_offline_hives(args):
    return bool(args.system_hive or args.software_hive or args.ntuser_hive)


def needs_registry(args):
    return args.mode in ["hive", "registry", "timeline", "summary", "live"] or args.html_path or args.summary_json or args.summary_csv or args.graph_dot


def needs_events(args):
    if args.mode == "hive":
        return bool(args.evtx) or args.html_path or args.summary_json or args.summary_csv or args.graph_dot
    return args.mode in ["events", "timeline", "summary", "live"] or bool(args.evtx) or args.html_path or args.summary_json or args.summary_csv or args.graph_dot


def needs_setupapi(args):
    return args.mode in ["setupapi", "timeline", "summary", "hive"] or bool(args.setupapi_log) or args.html_path or args.summary_json or args.summary_csv or args.graph_dot


def needs_file_activity(args):
    return args.mode == "file-activity" or args.include_file_activity or (bool(args.lnk_dir or args.jump_list_dir or args.ntuser_hive) and args.mode in ["hive", "timeline", "summary"])


def collect_registry(args):
    include_extended = not args.no_extended_registry
    if args.mode == "hive":
        print(f"{Fore.WHITE}Reading offline Registry hives...")
        data = get_offline_registry_artifacts(args.system_hive, args.software_hive, args.ntuser_hive, include_extended=include_extended)
    elif using_offline_hives(args):
        print(f"{Fore.WHITE}Reading offline Registry hives...")
        data = get_offline_registry_artifacts(args.system_hive, args.software_hive, args.ntuser_hive, include_extended=include_extended)
    else:
        print(f"{Fore.WHITE}Reading live Registry artifacts...")
        data = get_live_registry_artifacts(include_extended=include_extended)
    clean, errors = split_errors(data)
    print_errors("Registry parsing messages", errors)
    print(f"{Fore.GREEN}[+] Registry artifacts: {len(clean)}")
    return clean, errors


def collect_events(args):
    clean = []
    errors = []
    offline = using_offline_hives(args)
    if args.evtx:
        print(f"{Fore.WHITE}Reading offline EVTX files...")
        data = get_usb_evtx_data(args.evtx, max_events=args.max_events, keep_unmatched=args.keep_unmatched_events)
        part, err = split_errors(data)
        clean += part
        errors += err
    if args.mode == "hive":
        if not args.evtx:
            print(f"{Fore.YELLOW}[!] No offline EVTX files were provided. Hive mode will use Registry hives and other offline artifacts only.")
    elif not offline or args.live_events or args.mode in ["events", "live"]:
        print(f"{Fore.WHITE}Reading live Event Log channels...")
        data = get_usb_eventlog_data(days=args.days, max_events=args.max_events, keep_unmatched=args.keep_unmatched_events)
        part, err = split_errors(data)
        clean += part
        errors += err
    elif offline and not args.live_events:
        print(f"{Fore.YELLOW}[!] Live Event Log skipped because offline hives are enabled. Add --live-events if intentional.")
    print_errors("Event Log parsing messages", errors)
    print(f"{Fore.GREEN}[+] Event Log entries: {len(clean)}")
    return clean, errors


def collect_setupapi(args):
    if not args.setupapi_log:
        return [], []
    print(f"{Fore.WHITE}Reading setupapi.dev.log files...")
    data = get_setupapi_data(args.setupapi_log)
    clean, errors = split_errors(data)
    print_errors("SetupAPI parsing messages", errors)
    print(f"{Fore.GREEN}[+] SetupAPI entries: {len(clean)}")
    return clean, errors


def collect_file_activity(args):
    if not needs_file_activity(args):
        return [], []
    print(f"{Fore.WHITE}Reading file activity artifacts...")
    data = get_file_activity_data(
        lnk_dirs=args.lnk_dir,
        jump_list_dirs=args.jump_list_dir,
        ntuser_hive_paths=args.ntuser_hive,
        include_live_user_registry=args.include_live_user_artifacts,
        include_default_live_paths=args.include_default_live_paths,
        limit=args.file_scan_limit,
    )
    clean, errors = split_errors(data)
    print_errors("File activity parsing messages", errors)
    print(f"{Fore.GREEN}[+] File activity artifacts: {len(clean)}")
    return clean, errors


def collect_all(args):
    registry_data = []
    event_data = []
    setupapi_data = []
    file_activity_data = []
    errors = []
    if needs_registry(args):
        registry_data, err = collect_registry(args)
        errors += err
    if needs_events(args):
        event_data, err = collect_events(args)
        errors += err
    if needs_setupapi(args):
        setupapi_data, err = collect_setupapi(args)
        errors += err
    if needs_file_activity(args):
        file_activity_data, err = collect_file_activity(args)
        errors += err
    timeline = build_timeline(registry_data, event_data, setupapi_data, file_activity_data)
    summary = build_device_summary(timeline)
    return registry_data, event_data, setupapi_data, file_activity_data, timeline, summary, errors


def make_key(item):
    return "|".join(str(item.get(k) or "") for k in ["event_kind", "artifact_source", "timestamp_utc", "timestamp_local", "serial", "action_text"])


def run_live(args):
    print_header("Live USB Test Mode")
    print("Live mode refreshes Registry and Event Log data and prints newly observed artifacts.")
    print("Connect or disconnect a USB device now. Press Ctrl+C to stop.")
    registry_data, event_data, setupapi_data, file_activity_data, timeline, summary, errors = collect_all(args)
    seen = {make_key(item) for item in timeline}
    print(f"{Fore.GREEN}[+] Baseline artifacts: {len(seen)}")
    cycle = 0
    try:
        while True:
            if args.live_count and cycle >= args.live_count:
                break
            cycle += 1
            time.sleep(max(args.live_interval, 1.0))
            print(f"\n{Fore.CYAN}Refresh {cycle}")
            registry_data, event_data, setupapi_data, file_activity_data, timeline, summary, errors = collect_all(args)
            new_items = [item for item in timeline if make_key(item) not in seen]
            if not new_items:
                print("No new USB artifacts detected.")
            else:
                for item in new_items:
                    seen.add(make_key(item))
                print(f"{Fore.GREEN}[+] New artifacts: {len(new_items)}")
                for idx, item in enumerate(new_items, 1):
                    print_timeline_item(idx, item)
    except KeyboardInterrupt:
        print("\nLive mode stopped by user.")


def print_runtime_plan(args):
    offline = args.mode == "hive" or using_offline_hives(args)
    print_header("DFIR_project")
    print(f"Mode: {Fore.CYAN}{args.mode}")
    print(f"Primary workflow: {Fore.CYAN}{'offline hive analysis' if args.mode == 'hive' else 'selected mode'}")
    print(f"Registry source: {Fore.CYAN}{'offline hives' if offline else 'live registry'}")
    print(f"Extended registry artifacts: {Fore.CYAN}{'off' if args.no_extended_registry else 'on'}")
    print(f"SYSTEM hive: {Fore.CYAN}{args.system_hive or 'not provided'}")
    print(f"SOFTWARE hive: {Fore.CYAN}{args.software_hive or 'not provided'}")
    print(f"NTUSER.DAT hives: {Fore.CYAN}{len(args.ntuser_hive)}")
    print(f"EVTX files: {Fore.CYAN}{len(args.evtx)}")
    print(f"SetupAPI logs: {Fore.CYAN}{len(args.setupapi_log)}")
    print(f"File activity enabled: {Fore.CYAN}{'yes' if needs_file_activity(args) else 'no'}")
    if args.mode != "hive":
        print(f"Event Log window: latest {Fore.CYAN}{args.days}{Style.RESET_ALL} days, maximum {Fore.CYAN}{args.max_events}{Style.RESET_ALL} events per source")
    print()


def validate_args(args):
    if args.mode == "hive" and not using_offline_hives(args):
        print_header("DFIR_project")
        print(f"{Fore.RED}[!] Hive mode is the default forensic workflow and requires at least one offline Registry hive.")
        print("Provide --system-hive, --software-hive, or --ntuser-hive.")
        print("Example:")
        print(r"python main.py --system-hive C:\Case\Registry\SYSTEM --software-hive C:\Case\Registry\SOFTWARE --ntuser-hive C:\Case\Users\Alice\NTUSER.DAT --html report.html")
        print("For classroom testing on the current computer, use:")
        print("python main.py --mode live")
        sys.exit(2)


def save_outputs(args, output_data, timeline, summary):
    if args.json_path:
        save_json(args.json_path, output_data)
        print(f"{Fore.GREEN}[+] JSON saved: {args.json_path}")
    if args.csv_path:
        save_csv(args.csv_path, output_data)
        print(f"{Fore.GREEN}[+] CSV saved: {args.csv_path}")
    if args.summary_json:
        save_json(args.summary_json, summary)
        print(f"{Fore.GREEN}[+] Summary JSON saved: {args.summary_json}")
    if args.summary_csv:
        save_csv(args.summary_csv, summary)
        print(f"{Fore.GREEN}[+] Summary CSV saved: {args.summary_csv}")
    if args.graph_dot:
        Path(args.graph_dot).write_text(build_graph_dot(timeline, summary), encoding="utf-8")
        print(f"{Fore.GREEN}[+] Graph DOT saved: {args.graph_dot}")
    if args.html_path:
        save_html_report(args.html_path, timeline, summary)
        print(f"{Fore.GREEN}[+] HTML report saved: {args.html_path}")

def main():
    args = parse_args()
    validate_args(args)
    if args.mode == "live":
        run_live(args)
        return
    print_runtime_plan(args)
    registry_data, event_data, setupapi_data, file_activity_data, timeline, summary, errors = collect_all(args)
    if args.mode == "registry":
        output_data = registry_data
        if not output_data:
            print(f"{Fore.RED}[!] Registry USB artifacts were not found.")
        for idx, item in enumerate(output_data, 1):
            print_device(idx, item)
    elif args.mode == "events":
        output_data = event_data
        if not output_data:
            print(f"{Fore.RED}[!] USB/PnP events were not found.")
        for idx, item in enumerate(output_data, 1):
            print_event(idx, item)
    elif args.mode == "setupapi":
        output_data = setupapi_data
        if not output_data:
            print(f"{Fore.RED}[!] SetupAPI USB sections were not found.")
        for idx, item in enumerate(output_data, 1):
            print_event(idx, item)
    elif args.mode == "file-activity":
        output_data = file_activity_data
        if not output_data:
            print(f"{Fore.RED}[!] File activity artifacts were not found.")
        for idx, item in enumerate(output_data, 1):
            print_event(idx, item)
    elif args.mode == "summary":
        output_data = summary
        print_header("Device Summary")
        print_summary(summary)
    elif args.mode == "hive":
        output_data = timeline
        if not timeline:
            print(f"{Fore.RED}[!] Hive timeline is empty. No offline Registry, EVTX, SetupAPI, or file activity data was found.")
        else:
            print_header("Hive Timeline")
            for idx, item in enumerate(timeline, 1):
                print_timeline_item(idx, item)
            print_header("Device Summary")
            print_summary(summary)
    else:
        output_data = timeline
        if not timeline:
            print(f"{Fore.RED}[!] Timeline is empty. No Registry, Event Log, SetupAPI, or file activity data was found.")
        else:
            print_header("USB Timeline")
            for idx, item in enumerate(timeline, 1):
                print_timeline_item(idx, item)
            print_header("Device Summary")
            print_summary(summary)
    save_outputs(args, output_data, timeline, summary)
    print(f"\n{Fore.GREEN}[+] Analysis finished.")
    if not output_data and not any([args.html_path, args.graph_dot]):
        sys.exit(1)


if __name__ == "__main__":
    main()
