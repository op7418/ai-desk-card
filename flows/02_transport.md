# Flow 02 — Diagnose transport (daemon up, device not connected)

`daemon.running == true` but `transport.connected == false`. The daemon
is alive but can't reach the device.

## Reading the state

| What state shows | Most likely cause |
|---|---|
| `hardware.m5paper_usb == null` AND `wifi.provisioned == false` | Device is unplugged AND not on Wi-Fi |
| `hardware.m5paper_usb != null` AND firmware just flashed | Daemon started before serial port settled — restart daemon |
| `wifi.provisioned == true` (mdns peer seen) AND no transport | Daemon picked USB/BLE and missed the Wi-Fi peer — restart daemon |
| `firmware.flashed == false` | Device has wrong / no firmware — return to flow 01 |

## Step 1 — Restart the daemon

Most "transport not connected" cases resolve by restarting the daemon,
which re-runs transport auto-pick:

```bash
bash plugin/scripts/stop.sh
bash plugin/scripts/start.sh
sleep 3
bash scripts/state.sh
```

If `transport.connected == true` now, done.

## Step 2 — Check the serial port isn't held

```bash
lsof /dev/cu.usbserial-* 2>/dev/null
```

If another process holds the port (PlatformIO IDE, screen, minicom):
kill it. Then retry step 1.

## Step 3 — BLE-only mode (battery-powered + no Wi-Fi)

Skip this step for `paper-s3`: BLE standby, deep sleep, and battery policy
are not implemented for PaperS3. For PaperS3 after Wi-Fi provisioning,
restart the daemon with `--profile paper-s3 --transport wifi --host
<PaperS3-IP> --wifi-port 9880 --http-host 0.0.0.0`. Before Wi-Fi provisioning, close any serial
monitor, use `--transport serial --port <COM port>`, then run
`scripts/diagnose_device.py --profile paper-s3`.

If the user is operating in battery + BLE-standby mode (architecture C),
the device's Wi-Fi may be off — the daemon needs to wake it via BLE
first. This only works if BLE is paired:

```bash
curl -sf "${CARD_DAEMON_URL:-http://127.0.0.1:9877}/pair-status" | python3 -m json.tool
```

If `transport == "BLETransport"` shows up, BLE is paired but didn't wake
Wi-Fi. Possible causes:
- Battery too low — plug in via USB-C and re-pair
- Device hung — hold side button 2 s to power-cycle (V1.1 has no reset
  button; long-press the rotary)

## Step 4 — Last resort: factory state

If nothing connects, push factory-reset firmware:

```bash
pio run -e card -t erase
pio run -e card -t uploadfs
pio run -e card -t upload
```

Then re-pair BLE + re-provision Wi-Fi from scratch.
