import argparse
import csv
import json
import sys
from pathlib import Path

try:
    from colorama import init, Fore, Style
except ImportError:
    def init(*args, **kwargs):
        pass

    class _NoColor:
        def __getattr__(self, name):
            return ""

    Fore = _NoColor()
    Style = _NoColor()

from core.registry_parser import get_usbstor_data

init(autoreset=True)


def print_header(text):
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'=' * 60}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{text.center(60)}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 60}\n")


def print_device(idx, item):
    source = item.get("friendly_name_source") or "unknown"
    wpd_note = f" {Fore.BLUE}(from WPD)" if item.get("wpd_match") else ""

    print(f"{Fore.YELLOW}[{idx}] Urządzenie: {Style.BRIGHT}{item['friendly_name']}{wpd_note}")
    print(f"    Source : {source}")
    print(f"    Type           : {item.get('device_type') or 'not found'}")
    print(f"    Producent      : {item.get('vendor') or 'not found'}")
    print(f"    Model          : {item.get('product') or 'not found'}")
    print(f"    Revision       : {item.get('revision') or 'not found'}")
    print(f"    USBSTOR ID     : {item['vendor_product']}")

    if item["is_generated"]:
        print(f"    Serial number : {Fore.RED}{item['serial']} {Style.BRIGHT}[СГЕНЕРИРОВАН]")
        print(f"    {Fore.LIGHTBLACK_EX}Chyba Windows sama dała ID w zależności od portu")
    else:
        print(f"    Serial number : {Fore.GREEN}{item['serial']} [original]")

    print(f"    ParentIdPrefix : {item.get('parent_id_prefix') or 'not found'}")
    print(f"    ContainerID    : {item.get('container_id') or 'not found'}")
    print(f"    LastWrite UTC  : {item.get('last_write_utc') or 'not found'}")
    print(f"    Arefakt       : {item.get('artifact_source')}")

    if item.get("wpd_device_id"):
        print(f"    WPD ID         : {item['wpd_device_id']}")

    print(f"{Fore.LIGHTBLACK_EX}{'-' * 60}")


def save_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_csv(path, data):
    fields = [
        "friendly_name",
        "friendly_name_source",
        "device_type",
        "vendor",
        "product",
        "revision",
        "vendor_product",
        "serial",
        "is_generated",
        "parent_id_prefix",
        "container_id",
        "last_write_utc",
        "artifact_source",
        "wpd_device_id",
    ]

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)


def parse_args():
    parser = argparse.ArgumentParser(
        description="USB Forensic Tracer: get USB-artefacts from Windows Registry"
    )
    parser.add_argument("--json", dest="json_path", help="save JSON")
    parser.add_argument("--csv", dest="csv_path", help="save CSV")
    return parser.parse_args()


def main():
    args = parse_args()

    print_header("USB Forensic Tracer")
    print(f"{Fore.WHITE}Reading USBSTOR comparing with Windows Portable Devices...\n")

    data = get_usbstor_data()

    if data and isinstance(data, list) and "error" in data[0]:
        print(f"{Fore.RED}[ERROR] {data[0]['error']}")
        print(f"{Fore.YELLOW}Admina porzebujesz")
        sys.exit(1)

    if not data:
        print(f"{Fore.RED}[!] USB-Artefacts not found.")
        sys.exit(1)

    print(f"Found USBSTORs: {Fore.GREEN}{len(data)}\n")

    for idx, item in enumerate(data, 1):
        print_device(idx, item)

    if args.json_path:
        save_json(args.json_path, data)
        print(f"{Fore.GREEN}[+] JSON saved: {args.json_path}")

    if args.csv_path:
        save_csv(args.csv_path, data)
        print(f"{Fore.GREEN}[+] CSV saved: {args.csv_path}")

    print(f"\n{Fore.GREEN}[+] end.")


if __name__ == "__main__":
    main()
