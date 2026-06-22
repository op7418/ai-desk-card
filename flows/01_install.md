# Flow 01 — First-time hardware install + firmware flash

The user has the M5Paper but the device has no compatible firmware on it
(`firmware.flashed == false`). Walk them through PlatformIO install +
build + flash + LittleFS upload.

## Pre-flight

State this to the user, then verify each:

1. **Identify the device profile.** M5Paper V1.1 uses env `card`.
   M5Stack PaperS3 uses env `paper-s3`. If the user is unsure, ask the
   model or run `python scripts/diagnose_device.py --profile paper-s3
   --skip-build --no-send-test` only after they say it is PaperS3.
2. **A USB-C *data* cable** (not power-only). Most cables that came in
   the box are fine.
3. **M5Paper V1.1:** macOS 10.15+ or Linux with USB CDC. **PaperS3:**
   Windows 11 PowerShell is supported through native COM ports; do not
   require VS Code or WSL USB passthrough.

If `hardware.pio_installed == false`:

```bash
pipx install platformio
# OR via VS Code: install the PlatformIO IDE extension
```

Tell the user this is a one-time setup, takes ~2 min, downloads ~500 MB
of toolchains the first time `pio run` is invoked.

## Step 1 — Plug the device in

Tell the user to plug their M5Paper into USB. Then verify:

```bash
ls /dev/cu.usbserial-* 2>/dev/null || ls /dev/ttyUSB* 2>/dev/null
```

Expected: one line like `/dev/cu.usbserial-XXXXXXXX`. If empty:

- Cable is power-only — try a different USB-C cable
- Device isn't powered on (hold side button 2 s)
- macOS hasn't loaded the CP2104 driver — usually auto-loaded on 10.15+
- USB port issue — try another port

## Step 2 — Build + flash firmware

Pick the right env for the user's device:

**M5Paper V1.1** (default):

```bash
pio run -e card
pio run -e card -t uploadfs        # one-time: flash CJK font to LittleFS
pio run -e card -t upload          # flash firmware
```

**M5Paper Color** (color panel, ESP32-S3 — see [flow 08](08_paper_color.md)
for the full Color profile):

```bash
pio run -e paper-color
pio run -e paper-color -t upload   # no uploadfs needed (built-in font)
```

**M5Stack PaperS3** (`paper-s3` profile):

```powershell
$env:PLATFORMIO_CORE_DIR=".pio-core"
.\.pio-venv\Scripts\python.exe scripts\card_cli.py build --profile paper-s3
.\.pio-venv\Scripts\python.exe scripts\card_cli.py upload --profile paper-s3 --port COM3
.\.pio-venv\Scripts\python.exe scripts\card_cli.py monitor --profile paper-s3 --port COM3
```

PaperS3 does not use the M5Paper V1.1 BLE/deep-sleep path. Its conservative
power policy is `always-on` plus sleep-card; battery/USB status is exposed in
diagnose and frame status. Use USB serial for the first daemon/provisioning
step, then switch to Wi-Fi:

```powershell
.\.pio-venv\Scripts\python.exe daemon\card_daemon.py --profile paper-s3 --transport serial --port COM3
$body = @{ssid="<2.4GHz Wi-Fi SSID>"; password="<Wi-Fi password>"} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:9877/provision-wifi -ContentType "application/json" -Body $body
.\.pio-venv\Scripts\python.exe daemon\card_daemon.py --profile paper-s3 --transport wifi --host <PaperS3-IP> --wifi-port 9880 --http-host 0.0.0.0
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget dashboard
.\.pio-venv\Scripts\python.exe scripts\diagnose_device.py --profile paper-s3 --transport wifi --host <PaperS3-IP> --wifi-port 9880 --http-host 0.0.0.0
```

The first successful post-install push should be `dashboard`, not `text`.
The firmware's touch calibration/test screen is normal immediately after
flashing or rebooting; it should be replaced once the daemon pushes the
dashboard frame.

Total ~60 seconds the second time; the first run downloads toolchains.
Echo each command's outcome to the user.

If `pio run` fails with "Could not find a version that satisfies the
requirement":

- Internet/proxy issue — `pio run` downloads platform from PlatformIO
  registry on first invocation

If `pio run -t upload` fails with "Could not open port":

- Another process holds the serial port. `/card-stop` or `pkill -f
  card_daemon.py`, then retry.
- Wrong board selected (`platformio.ini` should have `board = m5stack-fire`
  or equivalent — verify before reflashing)

After successful upload, the device reboots and shows a splash with
"v0.8 · waiting for daemon...". Tell the user to confirm they see this.

## Step 3 — Re-probe to verify

```bash
bash scripts/state.sh
```

Expected change: `hardware.m5paper_usb` is populated, but `firmware.ours`
is still false because the daemon isn't running yet. Return to SKILL.md
step 2 — next mismatch will route to "start daemon".

## Common pitfalls

- **CJK font missing**: skip `uploadfs` and the device boots but every
  Chinese character renders as a tofu box. Always do `uploadfs` once.
- **Wrong partition table**: if the user previously flashed unrelated
  ESP32 firmware, the partition table may not match. `pio run -t erase`
  first, then `uploadfs && upload`.
- **Battery too low to flash**: M5Paper V1.1 needs ~3.6 V to flash
  reliably. If flashing reboots mid-way, plug to a charger for 10 min.
