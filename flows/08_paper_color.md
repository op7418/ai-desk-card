# Flow 08 — Paper Color device profile

Use this flow whenever the user's hardware is **M5Paper Color**
(ESP32-S3 + 4" Spectra 6 panel) rather than M5Paper V1.1. Two devices,
same Skill, different routing.

Quick detect: ask the user which they have, OR query their daemon's
`/heartbeat` and check `device_status.device == "M5PaperColor"`.

## Build env

```bash
# (V1.1 uses env:card; Color uses env:paper-color — both live in the
# same platformio.ini, src/ is split by build_src_filter.)
pio run -e paper-color
pio run -e paper-color -t upload
```

No `uploadfs` step — Color uses the M5GFX built-in font (no LittleFS
CJK TTF needed). Saves the partition headache.

## Wi-Fi provisioning

Color has **no BLE pairing UX** and **no touch panel** — V1.1's
`/card-wifi-setup` flow doesn't apply. Instead, use the Serial JSON
command over USB CDC (port shows up as `/dev/cu.usbmodem*`):

```bash
python3 -c "
import serial, time
s = serial.Serial('/dev/cu.usbmodem83101', 115200, timeout=2)
time.sleep(0.5)
s.write(b'{\"cmd\":\"wifi_set\",\"ssid\":\"<SSID>\",\"password\":\"<PW>\"}\n')
print(s.read(200).decode('utf-8', errors='replace'))
s.close()
"
```

Verify with `{"cmd":"ping"}` — should respond with current IP and SSID.

## Daemon

Color uses a separate daemon. **V1.1 and Color daemons can't run at
the same time on port 9877** — start whichever device is on the desk.

```bash
# Stop V1.1 if running
bash plugin/scripts/stop.sh

# Start Color
python3 daemon/color_daemon.py --device-ip <device-IP> &
```

The Color daemon binds `0.0.0.0:9877` (LAN-reachable so device's
`/button` events can hit it) but with an IP allowlist limiting callers
to `127.0.0.1` + the device's IP. Everyone else gets 403.

## Push pace

Spectra 6 panel is **15-19 s per full refresh**. The Color daemon
defaults debounce, but agents should:

- Push **at most** once per minute for steady widgets (weather / focus)
- Push **immediately** for time-sensitive ones (next-meeting, deadlines
  firing now) — accept the 17 s latency
- **Don't** push a tiny region change for "update time string" type
  triffs — they aren't worth a 17 s refresh

Status bar at the bottom updates every full render, so don't worry
about it going stale; user won't perceive it as broken.

## Layout

600 × 400 landscape **2×2 grid**, slot names are `top-left` /
`top-right` / `bottom-left` / `bottom-right` (NOT V1.1's
`top-left / top-right / middle / bottom`). Plus `full` for splash /
business card.

Same widget data shape as V1.1 — `POST /widget` with `{slot, type, data}`
just works.

## Physical buttons

Color has 3 user buttons + 1 power. The mapping (verified on hardware,
NOT obvious from M5 lib's BtnA/B/C naming):

| Physical | Action | Notes |
|---|---|---|
| Top (alone) | **sleep** | Renders business card + deep sleep, panel keeps card at 0 W |
| Bottom-left | **refresh** | Re-renders current view + pushes |
| Bottom-middle | **settings** | Renders settings page (device status / SHT40 / Wi-Fi) |
| Bottom-right | (power) | AXP-managed: long-press off, short-press wake |

Button events POST `/button` to the daemon. The daemon receives over
LAN (allowlist-gated), dispatches `_internal_dispatch(action)`.

## Color-exclusive widgets

Beyond the 16 widgets V1.1 supports, Color adds:

- **ambient** — SHT40 temp + humidity. Daemon pulls from
  device's GET /status (no cloud / no API). Push as:
  ```json
  {"slot":"top-left","type":"ambient",
   "data":{"temp_c":25.6,"humid_pct":47}}
  ```
  Or let `color_daemon.py` auto-fill from its cached device status.

## Audio notifications

Color has a 1 W speaker + ES8311 codec. POST `/beep` with a pattern:

```bash
curl -X POST http://<color-ip>:9880/beep \
  -H 'Content-Type: application/json' \
  -d '{"pattern":"chime"}'   # chime | urgent | alert
```

Use:
- `chime` (3 ascending notes) — soft "look at card" / meeting in 5 min
- `urgent` (3 fast beeps) — deadline fired now / overdue
- `alert` (single tone) — generic ambient ping / push completed

See [`flow 06`](./06_schedule.md) for when to fire these in the
scheduled-push loop.

V1.1 has no speaker — `/beep` returns 404 there. Detect via `device`
field in `/status`, or catch the 404 silently.

## RGB LED

2× WS2812 LEDs on the device (driver chain). Currently:
- Button press → short white flash (ack)
- /frame inbound → green pulse (bytes-flowing nudge during the 17 s
  refresh wait)

No daemon-side endpoint to set LED colors directly yet — the firmware
fires them on its own events. Agent can't drive LED from the Skill
for now.

## Common pitfalls

- **PingFang.ttc** doesn't exist on macOS 15+ without CJK locale; the
  Color renderer auto-falls-back to STHeiti Medium. Don't add PingFang
  to font candidates that aren't verified to exist.
- **Body text below 20 pt is unreadable** on Spectra 6 — strokes
  break into dither during color quantization. See
  [[reference-spectra6-readability]] memory for the full guideline.
- **M5.BtnA/B/C ≠ physical left-to-right** on Paper Color. Verify
  with per-button beeps before binding actions.
- **No touch panel.** Don't try to render tappable chips in the bottom
  bar — physical button labels (顶/左/中) replace them.

## V1.1 → Color migration cheat-sheet

For Agents that already know V1.1:

| V1.1 | Color | Notes |
|---|---|---|
| `env:card` | `env:paper-color` | New PlatformIO env |
| `card_daemon.py` | `color_daemon.py` | Same API surface, different transport + renderer |
| 540×960 grayscale | 600×400 color | Layout + palette |
| GT911 touch chip | 3 physical buttons | No tap dispatch needed |
| BLE pair + Wi-Fi | Serial JSON cmd | No BLE provisioning UX |
| 0.2 s push | 15-19 s push | Debounce harder |
| (no sensor) | SHT40 / mic / speaker / LEDs | New widget types |
