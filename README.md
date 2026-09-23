# DFIR_project

DFIR_project is a lightweight Windows DFIR helper for building USB-related timelines from forensic artifacts.

The primary workflow is offline hive analysis. This means the tool is designed to analyze exported or acquired Registry hive files instead of modifying or depending on the current live Windows installation. Live mode still exists, but it is intended mainly for classroom demonstrations and quick testing.

The tool does not decide whether an activity is malicious. It collects and normalizes artifacts, correlates them, builds a timeline, groups devices, and leaves interpretation to the analyst.

## Primary workflow

The default command uses hive mode:

```powershell
python main.py --system-hive C:\Case\Registry\SYSTEM --software-hive C:\Case\Registry\SOFTWARE --ntuser-hive C:\Case\Users\Alice\NTUSER.DAT --html report.html
```

In hive mode, the project reads offline evidence files such as:

```text
SYSTEM
SOFTWARE
NTUSER.DAT
System.evtx
Microsoft-Windows-Kernel-PnP%4Configuration.evtx
setupapi.dev.log
LNK files
Jump List files
```

If `python main.py` is executed without hive paths, the tool prints a clear message explaining that hive mode requires at least one offline Registry hive.

## Why hive mode is the default

Offline hive analysis is closer to real forensic work because the target system does not need to be booted and the current Windows Registry does not need to be touched. An analyst can work on copied evidence from an acquired disk image.

This is safer than live analysis because running tools on the target system can create new artifacts, modify timestamps, generate logs, and affect the evidence environment.

## Main features

- Offline Registry hive parsing as the default workflow.
- Live Windows Registry parsing for testing and demonstration.
- Offline `.evtx` triage through PowerShell `Get-WinEvent`.
- Live Event Log parsing from `Microsoft-Windows-Kernel-PnP/Configuration` and `System`.
- `setupapi.dev.log` parser.
- USB timeline builder.
- Device summary with first seen and last seen information.
- Drive-letter and Volume GUID correlation.
- Multiple `NTUSER.DAT` support.
- Lightweight file activity artifact triage for LNK, Jump Lists, RecentDocs, and ShellBags.
- Relationship graph export in Graphviz DOT format.
- Basic device classification.
- JSON, CSV, HTML, and DOT exports.
- Live mode for visual classroom testing.

## Supported artifact sources

### Offline Registry hives

Hive mode reads exported or acquired Registry hives:

```text
SYSTEM
SOFTWARE
NTUSER.DAT
```

`--ntuser-hive` can be used more than once to process multiple user profiles.

The offline Registry parser can extract artifacts from:

```text
SYSTEM\ControlSetXXX\Enum\USBSTOR
SYSTEM\ControlSetXXX\Enum\USB
SYSTEM\ControlSetXXX\Enum\SWD\WPDBUSENUM
SYSTEM\MountedDevices
SOFTWARE\Microsoft\Windows Portable Devices\Devices
NTUSER.DAT\Software\Microsoft\Windows\CurrentVersion\Explorer\MountPoints2
```

### Offline Event Logs

Offline EVTX files can be provided with `--evtx`:

```powershell
python main.py --evtx C:\Case\Logs\System.evtx --evtx C:\Case\Logs\Microsoft-Windows-Kernel-PnP%4Configuration.evtx
```

EVTX parsing uses PowerShell `Get-WinEvent`, so it is available on Windows systems with PowerShell.

### setupapi.dev.log

The setupapi parser reads device installation sections from:

```text
C:\Windows\inf\setupapi.dev.log
```

For offline cases, provide the copied file from the target system:

```powershell
python main.py --setupapi-log C:\Case\Windows\inf\setupapi.dev.log
```

### File activity artifacts

The file activity mode can triage:

```text
.lnk
.automaticDestinations-ms
.customDestinations-ms
RecentDocs
ShellBags
```

This is lightweight triage. LNK and Jump List parsing is based on readable strings and file timestamps, not a full binary forensic decoder.

### Live sources

Live mode reads the current Windows system. It can use:

```text
HKLM\SYSTEM\CurrentControlSet\Enum\USBSTOR
HKLM\SYSTEM\CurrentControlSet\Enum\USB
HKLM\SYSTEM\CurrentControlSet\Enum\SWD\WPDBUSENUM
HKLM\SYSTEM\MountedDevices
HKLM\SOFTWARE\Microsoft\Windows Portable Devices\Devices
HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\MountPoints2
Microsoft-Windows-Kernel-PnP/Configuration
System
```

Live mode is useful for testing, but it is not the preferred forensic workflow.

## Installation

Use Python 3.10 or newer.

```powershell
python -m pip install -r requirements.txt
```

For offline Registry hive parsing, `python-registry` is required and is included in `requirements.txt`.

## Basic usage

Show help:

```powershell
python main.py --help
```

Primary offline hive workflow:

```powershell
python main.py --system-hive C:\Case\Registry\SYSTEM --software-hive C:\Case\Registry\SOFTWARE --ntuser-hive C:\Case\Users\Alice\NTUSER.DAT --html report.html
```

Offline hive workflow with EVTX and setupapi.dev.log:

```powershell
python main.py --system-hive C:\Case\Registry\SYSTEM --software-hive C:\Case\Registry\SOFTWARE --ntuser-hive C:\Case\Users\Alice\NTUSER.DAT --evtx C:\Case\Logs\System.evtx --evtx C:\Case\Logs\Microsoft-Windows-Kernel-PnP%4Configuration.evtx --setupapi-log C:\Case\Windows\inf\setupapi.dev.log --html case_report.html
```

Multiple user hives:

```powershell
python main.py --system-hive C:\Case\Registry\SYSTEM --software-hive C:\Case\Registry\SOFTWARE --ntuser-hive C:\Case\Users\Alice\NTUSER.DAT --ntuser-hive C:\Case\Users\Bob\NTUSER.DAT --include-file-activity --html multi_user_report.html
```

Full offline export:

```powershell
python main.py --system-hive C:\Case\Registry\SYSTEM --software-hive C:\Case\Registry\SOFTWARE --ntuser-hive C:\Case\Users\Alice\NTUSER.DAT --evtx C:\Case\Logs\System.evtx --setupapi-log C:\Case\Windows\inf\setupapi.dev.log --include-file-activity --json timeline.json --csv timeline.csv --summary-json summary.json --summary-csv summary.csv --graph-dot graph.dot --html report.html
```

## Additional modes

Hive mode is the default:

```powershell
python main.py --mode hive --system-hive C:\Case\Registry\SYSTEM
```

Registry only:

```powershell
python main.py --mode registry --system-hive C:\Case\Registry\SYSTEM --software-hive C:\Case\Registry\SOFTWARE
```

Event Log only:

```powershell
python main.py --mode events --evtx C:\Case\Logs\System.evtx --max-events 20000
```

SetupAPI only:

```powershell
python main.py --mode setupapi --setupapi-log C:\Case\Windows\inf\setupapi.dev.log
```

File activity only:

```powershell
python main.py --mode file-activity --lnk-dir C:\Case\Users\Alice\Recent --jump-list-dir C:\Case\Users\Alice\AutomaticDestinations
```

Live demo mode:

```powershell
python main.py --mode live --days 1 --max-events 5000 --live-interval 3
```

Run only five live refresh cycles:

```powershell
python main.py --mode live --days 1 --max-events 5000 --live-interval 3 --live-count 5
```

## Output formats

Save main result to JSON and CSV:

```powershell
python main.py --system-hive C:\Case\Registry\SYSTEM --json timeline.json --csv timeline.csv
```

Save device summary:

```powershell
python main.py --system-hive C:\Case\Registry\SYSTEM --summary-json summary.json --summary-csv summary.csv
```

Save HTML report:

```powershell
python main.py --system-hive C:\Case\Registry\SYSTEM --html report.html
```

Save relationship graph:

```powershell
python main.py --system-hive C:\Case\Registry\SYSTEM --graph-dot graph.dot
```

## Output fields

Common fields include:

```text
event_kind
artifact_type
timestamp_utc
timestamp_local
action_text
friendly_name
device_class
device_instance_id
drive_letter
drive_letters
volume_guid
volume_guids
vendor
product
revision
vid
pid
serial
is_generated
first_seen_utc
last_seen_utc
evidence_count
registry_artifacts_count
eventlog_events_count
setupapi_events_count
file_activity_count
sources
user_labels
event_ids
artifact_source
file_path
target_candidates
message_short
```

## Device classification

The tool assigns a simple class to each artifact where possible:

```text
mass_storage
mobile_or_portable_device
camera
input_device
bluetooth_adapter
usb_hub
printer
biometric_device
unknown_or_failed_usb_device
file_activity_artifact
unknown
```

This classification is only a convenience label. It is not a forensic conclusion.

## Project structure

```text
DFIR_project/
  main.py
  README.md
  requirements.txt
  core/
    artifact_utils.py
    eventlog_parser.py
    file_activity_parser.py
    html_report.py
    offline_hive_parser.py
    registry_parser.py
    relationship_graph.py
    setupapi_parser.py
    summary_builder.py
    timeline_builder.py
    __init__.py
```

## Module overview

`main.py` provides the command-line interface and selects the analysis mode.

`core/offline_hive_parser.py` reads SYSTEM, SOFTWARE, and NTUSER.DAT files.

`core/registry_parser.py` reads the live Windows Registry.

`core/eventlog_parser.py` reads live Event Log channels and offline EVTX files.

`core/setupapi_parser.py` extracts USB-related installation sections from setupapi.dev.log.

`core/file_activity_parser.py` performs lightweight triage of LNK, Jump List, RecentDocs, and ShellBags artifacts.

`core/timeline_builder.py` correlates artifacts into one ordered timeline.

`core/summary_builder.py` groups timeline entries into device summaries.

`core/relationship_graph.py` builds graph relationships between devices, serials, drive letters, volumes, users, and artifact sources.

`core/html_report.py` creates the HTML report.

## Testing checklist

1. Run `python main.py --help`.
2. Run hive mode with at least one exported hive.
3. Add SOFTWARE and NTUSER.DAT hives if available.
4. Add offline EVTX files if available.
5. Add setupapi.dev.log if available.
6. Export HTML with `--html report.html`.
7. Export JSON/CSV and check the files in Excel or a text editor.
8. Export DOT with `--graph-dot graph.dot`.
9. Use `--mode live` only for a visual test on the current system.

## Current limitations

- Offline Registry parsing requires readable hive files and the `python-registry` package.
- Offline EVTX parsing uses PowerShell `Get-WinEvent`, so it requires Windows.
- Live Registry and live Event Log modes require Windows.
- LNK and Jump List support is lightweight triage, not full binary decoding.
- ShellBags parsing is based on decoded Registry strings and does not fully decode all Shell Item structures.
- setupapi.dev.log timestamps are local timestamps and should be interpreted with the case timezone.
- The tool does not prove file copying by itself.
- The tool does not identify the human user who physically connected the device.
- The tool does not decide whether an artifact is malicious.

## Future development

Useful next steps:

- Full binary LNK parser.
- Full Jump List parser with DestList support.
- Full Shell Item decoder for ShellBags.
- setupapi.dev.log timezone handling.
- Better USB device vendor lookup by VID/PID.
- Interactive HTML graph visualization.
- Optional SQLite case database.
- Comparison between two timeline snapshots.
- Filtering by serial, drive letter, Volume GUID, device class, or date range.
- Separate report mode for USB mass storage only.
- Integration with `$MFT` and `$UsnJrnl` for stronger file-copy analysis.
- Integration with Prefetch and AmCache for program execution context.
- Unit tests with synthetic Registry, EVTX, setupapi.dev.log, and LNK samples.

## License

Educational DFIR project.
