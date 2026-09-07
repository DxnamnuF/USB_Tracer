# USB_Tracer — How to Run and Validate Using a Windows VM

This guide describes a controlled forensic-validation workflow for **USB_Tracer** using a Windows virtual machine.

The purpose is not only to check that the program runs, but to create a repeatable DFIR test in which:

1. the investigator knows exactly which USB events occurred;
2. the Windows VM is shut down before evidence collection;
3. the virtual disk is preserved as evidence;
4. Windows forensic artefacts are extracted from the disk without modifying the guest system;
5. USB_Tracer analyses the offline artefacts;
6. the output is compared with the known test timeline and, optionally, with another forensic tool.

---

## 1. Important: what USB_Tracer analyses

The primary forensic workflow of USB_Tracer is **offline artefact analysis**.

USB_Tracer does **not** need to boot the acquired Windows system and it should not modify the evidence.

The current main workflow is:

```text
Windows VM
    |
    | controlled USB activity
    v
VM shutdown
    |
    v
Virtual disk copy / forensic image
    |
    v
Read-only examination / artefact extraction
    |
    +--> SYSTEM hive
    +--> SOFTWARE hive
    +--> NTUSER.DAT
    +--> optional EVTX files
    +--> optional setupapi.dev.log
    +--> optional LNK / Jump List artefacts
    |
    v
USB_Tracer
    |
    v
HTML / JSON / CSV / DOT reports
```

The auxiliary `--mode live` mode reads artefacts from the currently running Windows system. It is useful for development and comparison, but it is **not the mode for forensic evidence validation**.

---

# 2. Recommended test environment

Use a Windows host machine and create a separate Windows VM.

The exact hypervisor is not critical. VMware Workstation, VirtualBox, Hyper-V, or another hypervisor may be used.

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

Use a dynamically allocated virtual disk if desired. The disk format itself is not important for the experiment because a preserved copy can later be converted to a raw forensic image.

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

This is important because the virtual disk should no longer be changing when it is preserved.

---

# 9. Preserve the virtual disk

Locate the VM virtual disk on the host.

Common extensions are:

```text
.vmdk   VMware
.vdi    VirtualBox
.vhdx   Hyper-V
```

Example:

```text
USB-Tracer-Test.vmdk
```

Do not analyse the only original copy.

Create an evidence directory:

```powershell
mkdir C:\DFIR_Case
mkdir C:\DFIR_Case\Original
mkdir C:\DFIR_Case\Working
mkdir C:\DFIR_Case\Extracted
mkdir C:\DFIR_Case\Reports
```

Copy the powered-off VM disk into `Original`.

Example:

```powershell
Copy-Item "C:\VMs\USB-Tracer-Test\USB-Tracer-Test.vmdk" `
          "C:\DFIR_Case\Original\USB-Tracer-Test.vmdk"
```

Then make a working copy:

```powershell
Copy-Item "C:\DFIR_Case\Original\USB-Tracer-Test.vmdk" `
          "C:\DFIR_Case\Working\USB-Tracer-Test.vmdk"
```

The `Original` copy should not be modified during testing.

---

# 10. Calculate a SHA-256 hash

Hash the preserved original disk:

```powershell
Get-FileHash "C:\DFIR_Case\Original\USB-Tracer-Test.vmdk" -Algorithm SHA256
```

Save the result.

Example:

```text
Algorithm : SHA256
Hash      : 0123456789ABCDEF...
Path      : C:\DFIR_Case\Original\USB-Tracer-Test.vmdk
```

You can save it directly:

```powershell
Get-FileHash "C:\DFIR_Case\Original\USB-Tracer-Test.vmdk" -Algorithm SHA256 |
    Out-File "C:\DFIR_Case\Original\SHA256.txt"
```

This provides an integrity reference for the preserved evidence copy.

---

# 11. Convert the VM disk to RAW

USB_Tracer itself primarily analyses extracted Windows artefacts, so conversion to RAW is not mandatory.

However, converting the VM disk to a raw image is useful if you want a more conventional forensic disk-image workflow.

With `qemu-img`, the concept is:

```text
VMDK / VDI / VHDX
        |
        v
     qemu-img
        |
        v
    evidence.raw
```

Examples:

For VMDK:

```powershell
qemu-img convert -p -f vmdk -O raw `
    "C:\DFIR_Case\Working\USB-Tracer-Test.vmdk" `
    "C:\DFIR_Case\Working\USB-Tracer-Test.raw"
```

For VDI:

```powershell
qemu-img convert -p -f vdi -O raw `
    "C:\DFIR_Case\Working\USB-Tracer-Test.vdi" `
    "C:\DFIR_Case\Working\USB-Tracer-Test.raw"
```

For VHDX:

```powershell
qemu-img convert -p -f vhdx -O raw `
    "C:\DFIR_Case\Working\USB-Tracer-Test.vhdx" `
    "C:\DFIR_Case\Working\USB-Tracer-Test.raw"
```

Always convert the **working copy**, not the preserved original.

---

# 12. Extract the Windows forensic artefacts

The next objective is to obtain the offline Windows artefacts that USB_Tracer can analyse.

At minimum, extract:

```text
Windows\System32\config\SYSTEM
Windows\System32\config\SOFTWARE
Users\<username>\NTUSER.DAT
```

For the example VM:

```text
Windows\System32\config\SYSTEM
Windows\System32\config\SOFTWARE
Users\forensic-test\NTUSER.DAT
```

Place them in:

```text
C:\DFIR_Case\Extracted\Registry\
```

For example:

```text
C:\DFIR_Case\Extracted\Registry\SYSTEM
C:\DFIR_Case\Extracted\Registry\SOFTWARE
C:\DFIR_Case\Extracted\Users\forensic-test\NTUSER.DAT
```

Use a forensic image viewer or another method that allows the disk/image to be examined without booting the acquired Windows installation.

The hives should be copied from the offline filesystem.

---

# 13. Additional artefacts to extract

USB_Tracer can use more than the core registry hives.

Depending on which features you want to validate, also extract Windows event logs and additional artefacts.

Typical locations include:

```text
Windows\System32\winevt\Logs\
Windows\inf\setupapi.dev.log
Users\<username>\AppData\Roaming\Microsoft\Windows\Recent\
```

For the project workflow, useful inputs may include:

- offline `.evtx` files;
- `setupapi.dev.log`;
- LNK files;
- Jump Lists;
- multiple users' `NTUSER.DAT` hives.

Do not rename the original extracted artefacts unless necessary. It is easier to preserve provenance when paths and filenames remain recognizable.

---

# 14. Run USB_Tracer in the primary offline mode

Return to the USB_Tracer project directory:

```powershell
cd C:\Users\pance\Downloads\DFIR_project\DFIR_project
```

Run the main offline analysis:

```powershell
python main.py `
  --system-hive "C:\DFIR_Case\Extracted\Registry\SYSTEM" `
  --software-hive "C:\DFIR_Case\Extracted\Registry\SOFTWARE" `
  --ntuser-hive "C:\DFIR_Case\Extracted\Users\forensic-test\NTUSER.DAT" `
  --html "C:\DFIR_Case\Reports\report.html"
```

This is the preferred mode for the VM forensic test.

---

# 15. Multiple Windows users

If the image contains several user profiles, provide multiple `--ntuser-hive` arguments.

Conceptually:

```powershell
python main.py `
  --system-hive "C:\DFIR_Case\Extracted\Registry\SYSTEM" `
  --software-hive "C:\DFIR_Case\Extracted\Registry\SOFTWARE" `
  --ntuser-hive "C:\DFIR_Case\Extracted\Users\User1\NTUSER.DAT" `
  --ntuser-hive "C:\DFIR_Case\Extracted\Users\User2\NTUSER.DAT" `
  --html "C:\DFIR_Case\Reports\report.html"
```

This allows user-specific artefacts to be correlated with system-wide USB information.

---

# 16. Add other offline evidence

After the basic registry-only test works, extend the command with additional evidence sources supported by the current CLI.

Examples of supported input types include:

```text
--evtx
--setupapi-log
--lnk-dir
--jump-list-dir
```

Always confirm the exact current syntax with:

```powershell
python main.py --help
```

A typical extended analysis should include the SYSTEM and SOFTWARE hives first, then user hives, and then supplementary artefacts.

The objective is to allow USB_Tracer to correlate evidence from several independent Windows sources instead of relying on one registry key alone.

---

# 17. Export all useful report formats

For testing, generate more than only the HTML report.

The current project supports output options including:

```text
--html
--json
--csv
--summary-csv
--graph-dot
```

Use the HTML report for manual inspection.

Use JSON/CSV for checking exact parsed fields and for automated comparison.

Use the DOT graph output when testing relationships between devices, volumes, users, and artefacts.

Check the current CLI before running:

```powershell
python main.py --help
```

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