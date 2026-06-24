# Flow 03 — Provision Wi-Fi

Daemon + transport are OK but the device isn't on Wi-Fi yet
(`wifi.provisioned == false`). After this flow, frame push latency drops
from 1-32 s (USB) to 0.2 s (Wi-Fi).

## Step 1 — Ask the user for credentials

> "What's your Wi-Fi SSID and password? (ESP32 only supports 2.4 GHz —
> make sure that's not the 5 GHz-only SSID.)"

Capture the response. **Never** echo the password back to the user; do
NOT write the password into logs, transcripts, or any other file.

## Step 2 — Provision

```bash
curl -sf -X POST "${CARD_DAEMON_URL:-http://127.0.0.1:9877}/provision-wifi" \
  -H 'Content-Type: application/json' \
  -d @- <<JSON
{ "ssid": "<USER_SSID>", "password": "<USER_PASSWORD>" }
JSON
```

The daemon forwards the credentials to the device via the active
transport (serial / BLE). Credentials are stored in the device's NVS
flash — never on the daemon side, never in git.

PaperS3 Windows shortcut: `scripts\card_cli.py onboard --profile paper-s3 --port COM3`
performs this provisioning step through the serial daemon, then restarts the
daemon with `--transport wifi --http-host 0.0.0.0`. It then continues into
flow 04 by asking for the weather location and sleep-card business card
fields, writing dashboard-aligned PaperS3 interests/profile files, and pushing
the configured first dashboard. It then prints the flow 06 scheduling handoff. If the
PaperS3 is already provisioned, pass `--host <PaperS3-IP>` to skip re-entering
credentials; pass `--skip-interests --skip-card-profile` only when preserving
existing flow 04 files.

## Step 3 — Wait for connect

Allow ~15 seconds, then re-probe:

```bash
sleep 15 && bash scripts/state.sh
```

Expected: `wifi.provisioned == true` with `wifi.ip` populated.

If still `false` after 30 seconds: look at firmware status reports.
Common failure codes (visible in firmware splash or `/status_report`):

- `wl_status = 1` — SSID not found (typo, or 5 GHz-only)
- `wl_status = 4` — auth fail (wrong password)
- `wl_status = 6` — DHCP fail (router-side issue)

Tell the user what went wrong; do not retry blindly.

## Step 4 — Restart daemon to switch to Wi-Fi transport

```bash
bash plugin/scripts/stop.sh
bash plugin/scripts/start.sh
```

Look in the daemon log for: `[transport] found Wi-Fi peer X.X.X.X:9880,
using Wi-Fi`.

## Forgetting Wi-Fi

If the user wants to clear credentials (e.g., moving networks):

```bash
curl -sf -X POST "${CARD_DAEMON_URL:-http://127.0.0.1:9877}/provision-wifi" \
  -H 'Content-Type: application/json' \
  -d '{"ssid": ""}'
```

Empty SSID = clear NVS. Device stays off Wi-Fi on next boot.
