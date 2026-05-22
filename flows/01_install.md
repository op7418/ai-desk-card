# Flow 01 — First-time hardware install + firmware flash

The user has the M5Paper but the device has no compatible firmware on it
(`firmware.flashed == false`). Walk them through PlatformIO install +
build + flash + LittleFS upload.

## Pre-flight

State this to the user, then verify each:

1. **Have an M5Paper V1.1 in front of you?** Other variants (V1.0, S3)
   may work but aren't tested.
2. **A USB-C *data* cable** (not power-only). Most cables that came in
   the box are fine.
3. **macOS 10.15+ or Linux** with USB CDC. (Windows via WSL2 untested.)

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
