# USB_Tracer — How to Run and Validate Using a Windows VM

This guide describes a controlled forensic-validation workflow for **USB_Tracer** using a Windows virtual machine.

The purpose is not only to check that the program runs, but to create a repeatable DFIR test in which:

1. the investigator knows exactly which USB events occurred;
2. the Windows VM is shut down before evidence collection;
3. the virtual disk is preserved as evidence;
4. Windows forensic artefacts are read from a mounted working image without booting or modifying the guest system;
5. USB_Tracer analyses the offline artefacts;
6. the output is compared with the known test timeline and, optionally, with another forensic tool.

---

## 1. Important: what USB_Tracer analyses

The primary forensic workflow of USB_Tracer is **offline artefact analysis**.

USB_Tracer does **not** need to boot the acquired Windows system and it should not modify the evidence.

The current main workflow is:

1. Perform controlled USB activity in the Windows VM.
2. Shut down the VM and preserve its complete disk set.
3. Convert the current VirtualBox disk state to a separate VHD working image.
4. Mount the VHD read-only on the Windows host and locate its Windows partition.
5. Pass explicit paths to the mounted Registry hives and other artefacts to USB_Tracer.
6. Save HTML, JSON, CSV, or DOT reports outside the mounted image.
7. Compare the results with the recorded activity and dismount the VHD.

The auxiliary `--mode live` mode reads artefacts from the currently running Windows system. It is useful for development and comparison, but it is **not the mode for forensic evidence validation**.

---

# 2. Recommended test environment

Use a Windows host machine and create a separate Windows VM.

The procedure below uses VirtualBox on a Windows host, including its VBoxManage utility to convert a VDI disk to VHD. Other hypervisors require an appropriate disk preparation procedure before the same offline artefact analysis can be performed.

The important requirement is that the hypervisor allows a physical USB device to be connected directly to the guest Windows VM.

A VM makes the experiment reproducible.

Instead of analysing an unknown real computer, we create a system where the expected events are known in advance.

Example:

```text
10:00 VM started
10:05 Kingston USB connected
10:07 test_document.pdf copied to Kingston
10:10 Kingston USB disconnected
10:15 SanDisk USB connected
10:18 image.jpg copied from SanDisk to Desktop
10:20 SanDisk USB disconnected
10:25 VM shut down
```

After the VM is shut down, USB_Tracer should reconstruct as much of this activity as possible from Windows forensic artefacts.

If the output matches the known truth, this provides much stronger validation than simply running the software against an arbitrary machine.

---

# 3. Prepare USB_Tracer on the host

Open PowerShell and go to the project directory.

Example:

```powershell
cd C:\Users\pance\Downloads\DFIR_project\DFIR_project
```

Install the required Python packages:

```powershell
python -m pip install -r requirements.txt
```

Check the command-line interface:

```powershell
python main.py --help
```

Do this before starting the VM experiment. It confirms that the local USB_Tracer installation is working.

---

# 4. Create the Windows VM

Create a new Windows VM in your hypervisor.

Use a VDI virtual disk; dynamically allocated storage is suitable. After the experiment, create a VHD working image that Windows can mount read-only. RAW conversion and qemu-img are not required for this procedure.

Suggested naming:

```text
VM name: USB-Tracer-Test
User: forensic-test
Computer name: USBTEST
```

Install Windows normally.

After installation:

1. install the hypervisor guest tools if required;
2. install all drivers needed for USB passthrough;
3. create the local `forensic-test` user;
4. shut down the VM once;
5. create a clean VM snapshot.

Suggested snapshot name:

```text
clean_windows_before_usb_test
```

This snapshot allows the experiment to be repeated from the same starting state.

---

# 5. Prepare the USB test devices

For a useful test, prepare USB devices.

Example:

```text
USB #1
Vendor/model: Kingston DataTraveler
Volume label: KINGSTON_TEST

USB #2
Vendor/model: SanDisk Ultra
Volume label: SANDISK_TEST
```

The exact devices do not matter.

Before starting, record any information that you can observe directly:

```text
Device name
Manufacturer
Model
Serial number if available
Volume label
Filesystem
Approximate capacity
```

---

# 6. Start the controlled experiment

Start the Windows VM.

The VM represents the machine being investigated.

The host represents the forensic workstation.

---

# 7. Generate useful forensic activity

Perform several controlled actions.

For example:

```text
1. Open the USB drive in Explorer.
2. Create a folder called DFIR_TEST.
3. Copy test_document.pdf from the VM to the USB drive.
4. Open the copied file once.
5. Copy another file from the USB drive to the Desktop.
6. Close Explorer.
7. Safely eject the USB drive.
```

Record the important actions and times:

```text
10:05 — Kingston connected
10:06 — drive letter E: observed
10:07 — created E:\DFIR_TEST
10:08 — copied test_document.pdf to USB
10:09 — opened test_document.pdf
10:10 — Kingston safely removed
```

The times do not need to be precise to the millisecond. The objective is to have a reliable human-created reference timeline.

---

# 8. Shut down the VM

When the controlled activity is complete, perform a normal Windows shutdown:

```text
Start -> Power -> Shut down
```

Do not suspend or pause the VM.

Confirm in the hypervisor that the VM state is:

```text
Powered Off
```

This is important because the virtual disk should no longer be changing when it is preserved. Close the VM window and VirtualBox Manager after shutdown to release any disk handles. Run the remaining commands on the host, in the same PowerShell session. Use an elevated PowerShell session for mounting and dismounting the VHD.

---

# 9. Locate and preserve the complete virtual disk set

Set the VM name and directories to match your host. The example uses the VM name from section 4:

```powershell
$vmName = "USB-Tracer-Test"
$vmDir = "C:\Users\pance\VirtualBox VMs\USB-Tracer-Test"
$caseDir = "C:\DFIR_Case"
$outDir = Join-Path $caseDir "Working"
$reportDir = Join-Path $caseDir "Reports"
$originalDir = Join-Path $caseDir "Original"
$vbox = "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"

New-Item -ItemType Directory -Path $outDir, $reportDir, $originalDir -Force | Out-Null
& $vbox showvminfo $vmName --details
Get-ChildItem -LiteralPath $vmDir -Recurse -Filter *.vdi |
    Select-Object FullName, Length
```

Identify the disk attached to the VM's **current state**, using the storage information shown by `showvminfo` or the VM's storage settings. A snapshot disk can depend on several parent images. Choosing the largest VDI does not reliably identify the current state.

Preserve the complete powered-off VM folder before conversion:

```powershell
$preservedVm = Join-Path $originalDir "USB-Tracer-Test"
if (Test-Path -LiteralPath $preservedVm) {
    throw "The evidence folder already exists. Use a new case directory."
}
Copy-Item -LiteralPath $vmDir -Destination $preservedVm -Recurse -ErrorAction Stop
```

If a disk or parent image is stored outside the VM folder, preserve it as well and record its location. Keep all parents accessible to VirtualBox during conversion. Do not boot the preserved copy or delete, merge, or rearrange its snapshot files.

---

# 10. Record SHA-256 hashes

Hash all preserved VDI files and write the manifest outside the preserved VM folder:

```powershell
Get-ChildItem -LiteralPath $preservedVm -Recurse -File -Filter *.vdi |
    Get-FileHash -Algorithm SHA256 |
    Export-Csv (Join-Path $originalDir "SHA256.csv") -NoTypeInformation
```

Also hash any preserved disk dependencies stored elsewhere. These values provide an integrity reference for the original evidence set. The converted VHD is a separate working image and will have a different hash.

---

# 11. Convert the current VDI state to VHD

Set `$src` to the exact attached disk identified in section 9. The example below is for a VM without snapshot dependencies; when snapshots exist, replace it with the current attached child image path. VirtualBox must be able to resolve its parent chain.

```powershell
$src = "C:\Users\pance\VirtualBox VMs\USB-Tracer-Test\USB-Tracer-Test.vdi"
$vhd = Join-Path $outDir "USB-Tracer-Test.vhd"

if (-not (Test-Path -LiteralPath $src)) { throw "Source VDI not found: $src" }
if (Test-Path -LiteralPath $vhd) { throw "VHD already exists. Choose a new output name." }

& $vbox clonemedium disk $src $vhd --format VHD
if ($LASTEXITCODE -ne 0) { throw "VDI-to-VHD conversion failed." }
```

Wait for the operation to reach 100% and complete successfully. This reads the powered-off source disk and creates a separate VHD; keep the preserved evidence set unchanged. Do not automatically delete an existing output image when repeating the procedure.

---

# 12. Mount the VHD read-only

Run on the Windows host in PowerShell as administrator:

```powershell
Mount-DiskImage -ImagePath $vhd -Access ReadOnly -ErrorAction Stop
Get-DiskImage -ImagePath $vhd | Get-Disk | Get-Partition | Get-Volume
```

The image now appears as a disk on the host. Keep it mounted throughout analysis. Do not initialise, format, or repair its partitions if Windows prompts you to do so.

---

# 13. Locate the Windows partition and user profiles

Search only volumes belonging to this mounted image for the offline SYSTEM hive:

```powershell
$volumes = Get-DiskImage -ImagePath $vhd | Get-Disk | Get-Partition | Get-Volume
$windowsVolumes = @($volumes | Where-Object {
    $_.DriveLetter -and
    (Test-Path -LiteralPath "$($_.DriveLetter):\Windows\System32\config\SYSTEM")
})

if ($windowsVolumes.Count -ne 1) {
    throw "Expected one accessible Windows partition. Inspect the image's volumes and select the correct partition."
}
$root = "$($windowsVolumes[0].DriveLetter):\"
$root
```

For example, `$root` may contain `E:\`. This is the host's current mount letter, not necessarily the drive letter used inside the guest. If no Windows partition is found, check whether it has a drive letter and whether BitLocker is locked before continuing.

List the available user profiles:

```powershell
Get-ChildItem -LiteralPath (Join-Path $root "Users") -Directory -Force |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "NTUSER.DAT") } |
    Select-Object FullName

$guestUser = "forensic-test"
$userDir = Join-Path $root "Users\$guestUser"
```

Replace `forensic-test` with the user who performed the experiment. `NTUSER.DAT` is normally hidden. The relevant artefacts can be read directly from the mounted filesystem; copying them into an `Extracted` directory is optional.

| Artefact | Path relative to the mounted Windows partition |
| --- | --- |
| SYSTEM | `Windows\System32\config\SYSTEM` |
| SOFTWARE | `Windows\System32\config\SOFTWARE` |
| User hive | `Users\<username>\NTUSER.DAT` |
| System event log | `Windows\System32\winevt\Logs\System.evtx` |
| Kernel-PnP event log | `Windows\System32\winevt\Logs\Microsoft-Windows-Kernel-PnP%4Configuration.evtx` |
| Device installation log | `Windows\inf\setupapi.dev.log` |
| Recent shortcuts | `Users\<username>\AppData\Roaming\Microsoft\Windows\Recent` |
| Automatic Jump Lists | `Users\<username>\AppData\Roaming\Microsoft\Windows\Recent\AutomaticDestinations` |
| Custom Jump Lists | `Users\<username>\AppData\Roaming\Microsoft\Windows\Recent\CustomDestinations` |

---

# 14. Analyse the mounted Registry hives

Return to the project directory on the host:

```powershell
Set-Location "C:\Users\pance\Downloads\DFIR_project\DFIR_project"
python .\main.py --help
```

Pass explicit artifact paths to the default offline hive mode:

```powershell
python .\main.py `
  --system-hive (Join-Path $root "Windows\System32\config\SYSTEM") `
  --software-hive (Join-Path $root "Windows\System32\config\SOFTWARE") `
  --ntuser-hive (Join-Path $userDir "NTUSER.DAT") `
  --html (Join-Path $reportDir "registry_report.html")
```

The CLI reads the files from the mounted image. It does not automatically discover the whole Windows installation. At least one offline Registry hive is required; remove an optional input argument if its file is absent. Keep reports in `$reportDir` on the host, outside the mounted image.

---

# 15. Analyse multiple Windows users

Repeat `--ntuser-hive` for the profiles you want to investigate:

```powershell
python .\main.py `
  --system-hive (Join-Path $root "Windows\System32\config\SYSTEM") `
  --software-hive (Join-Path $root "Windows\System32\config\SOFTWARE") `
  --ntuser-hive (Join-Path $root "Users\User1\NTUSER.DAT") `
  --ntuser-hive (Join-Path $root "Users\User2\NTUSER.DAT") `
  --html (Join-Path $reportDir "multi_user_report.html")
```

Replace `User1` and `User2` with actual profile names. This allows user-specific artefacts to be correlated with system-wide USB information.

---

# 16. Include logs and file activity in the offline analysis

After the basic hive analysis works, include the other available artefacts. The following example assumes all listed files and directories exist:

```powershell
$recentDir = Join-Path $userDir "AppData\Roaming\Microsoft\Windows\Recent"

python .\main.py `
  --mode hive `
  --system-hive (Join-Path $root "Windows\System32\config\SYSTEM") `
  --software-hive (Join-Path $root "Windows\System32\config\SOFTWARE") `
  --ntuser-hive (Join-Path $userDir "NTUSER.DAT") `
  --evtx (Join-Path $root "Windows\System32\winevt\Logs\System.evtx") `
  --evtx (Join-Path $root "Windows\System32\winevt\Logs\Microsoft-Windows-Kernel-PnP%4Configuration.evtx") `
  --setupapi-log (Join-Path $root "Windows\inf\setupapi.dev.log") `
  --include-file-activity `
  --lnk-dir $recentDir `
  --jump-list-dir (Join-Path $recentDir "AutomaticDestinations") `
  --jump-list-dir (Join-Path $recentDir "CustomDestinations") `
  --max-events 20000 `
  --html (Join-Path $reportDir "disk_report.html") `
  --json (Join-Path $reportDir "disk_timeline.json") `
  --csv (Join-Path $reportDir "disk_timeline.csv") `
  --summary-csv (Join-Path $reportDir "disk_summary.csv") `
  --graph-dot (Join-Path $reportDir "disk_graph.dot")
```

Remove each argument whose source is absent. For additional users, repeat both their hive and directory arguments. Do not enable host live-event or live-user options when analysing this offline image. EVTX parsing uses Windows PowerShell. `--max-events` limits the number of events read from each EVTX file; increase it if the test records fall outside that limit.

PowerShell's backtick at the end of a line continues the command. It must be the last character on that line.

---

# 17. Open the reports and dismount the image

After the analysis completes successfully, open the HTML report:

```powershell
Start-Process (Join-Path $reportDir "disk_report.html")
```

Use HTML for manual inspection, JSON/CSV for checking parsed fields, and DOT for examining relationships. Compare the reported artefacts with the known test activity as described in section 18.

When no further reading from the image is required, dismount it from the same elevated PowerShell session:

```powershell
Dismount-DiskImage -ImagePath $vhd -ErrorAction Stop
```

The reports remain available on the host after the VHD is dismounted.

---

# 18. Validate the result against the truth

Now compare the USB_Tracer report with the actions recorded during the experiment.

Create a table like this:

| Ground-truth event | Expected artefact/result | USB_Tracer result | Match |
|---|---|---|---|
| Kingston connected at ~10:05 | Kingston device identified | Device found | Yes/No |
| Kingston assigned E: | Volume/drive correlation | E: linked | Yes/No |
| Kingston removed at ~10:10 | Timeline evidence | Event found | Yes/No |
| SanDisk connected at ~10:15 | Separate device identity | Device found | Yes/No |
| SanDisk assigned F: | Volume/drive correlation | F: linked | Yes/No |

Do not expect every human action to be represented by a single perfect Windows timestamp.

Different artefacts may record different parts of the activity.

The correct forensic question is not:

> "Does one registry value contain the complete history?"

The correct question is:

> "Can multiple independent artefacts be correlated into a defensible USB-device timeline?"

---

# 19. What must never be done

For a proper offline forensic test:

- do not boot the preserved evidence copy;
- do not analyse the only copy of the VM disk;
- do not overwrite extracted evidence files;
- do not intentionally modify registry hives;
- do not mix output reports with original evidence;
- do not treat the live mode as equivalent to offline forensic acquisition;
- do not claim that a timestamp means more than the underlying artefact actually proves.

USB_Tracer should read evidence and generate new report files separately.

---
