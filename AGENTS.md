# AGENTS.md

This file is the handoff note for coding agents working in this repository.
Keep it short, current, and operational. Prefer updating this file when a phase
finishes or when local setup changes.

## Repository State

- Current workspace path: `E:\dev\ai-desk-card`
- Active branch used for PaperS3 work: `paper-s3-port`
- Phase 2 baseline commit: `e826a41 Add PaperS3 raw frame push support`
- Current target hardware: M5Stack PaperS3 connected over USB-C, usually `COM3`
- Original M5Paper V1.1 PlatformIO environment is `card`; do not break it.
- PaperS3 PlatformIO environment is `paper-s3`.

## Local Tooling

Use the project-local PlatformIO virtual environment:

```powershell
cd E:\dev\ai-desk-card
$env:PLATFORMIO_CORE_DIR=".pio-core"
.\.pio-venv\Scripts\pio.exe --version
```

Python/Pillow and PlatformIO are installed in `.pio-venv`. After moving the
repo, Windows virtualenv launchers can break. Repair them with:

```powershell
C:\Users\lucyundead\AppData\Local\Programs\Python\Python313\python.exe -m venv --upgrade E:\dev\ai-desk-card\.pio-venv
```

In Codex sandboxed tool calls, `.pio-venv` may need escalated execution because
the venv redirects through the user-local Python install. In the user's normal
PowerShell, the commands below should work directly.

## Verification Commands

Run these before claiming work is complete:

```powershell
.\.pio-venv\Scripts\python.exe -m unittest discover -s test -p "test_*.py"
$env:PLATFORMIO_CORE_DIR=".pio-core"
.\.pio-venv\Scripts\pio.exe run -e paper-s3
.\.pio-venv\Scripts\pio.exe run -e card
```

Use `unittest discover`; direct module names like `test.test_...` can be less
stable on this Windows/Python setup.

## Build, Upload, Monitor

Build PaperS3:

```powershell
$env:PLATFORMIO_CORE_DIR=".pio-core"
.\.pio-venv\Scripts\pio.exe run -e paper-s3
```

Upload PaperS3:

```powershell
$env:PLATFORMIO_CORE_DIR=".pio-core"
.\.pio-venv\Scripts\pio.exe run -e paper-s3 -t upload --upload-port COM3
```

Serial monitor:

```powershell
.\.pio-venv\Scripts\pio.exe device monitor --environment paper-s3 --port COM3 --baud 115200
```

Only one process can own `COM3`. Close monitor before running daemon or upload.

## Completed Work

Phase 1 completed:

- Added `paper-s3` PlatformIO environment.
- PaperS3 builds and uploads.
- PaperS3 boots, prints status JSON, and displays a bring-up/test screen.
- No BLE, deep sleep, or power optimization for PaperS3.

Phase 2 completed:

- PaperS3 receives a full logical `540x960` 4bpp grayscale frame over USB raw
  serial mode.
- Project logical coordinates remain portrait `540x960`.
- PaperS3 HAL maps logical portrait frames to the physical `960x540` panel
  internally using `rotate-cw`.
- Daemon detects PaperS3 frame firmware via `paper-s3-frame` and uses
  `frame_raw_begin` plus raw frame bytes for full-frame serial pushes.
- JSON/base64 chunk mode was unreliable over long serial transfers on PaperS3;
  raw mode is the validated path.
- PaperS3 display uses `epd_quality`; `epd_fastest` left old screen remnants.
- `slot="full"` in the Python renderer no longer draws empty-slot grid lines
  over full-screen content.
- User verified the screen is clean and shows `NOTE` plus test text with no
  cross lines.

Useful Phase 2 test commands:

```powershell
.\.pio-venv\Scripts\python.exe tools\push_paper_s3_test_frame.py --port COM3 --ready-timeout 30 --ack-timeout 30 --listen-after 120
.\.pio-venv\Scripts\python.exe daemon\card_daemon.py --transport serial --port COM3
```

Daemon full-slot test widget:

```powershell
$body = @{slot="full"; type="scratch"; data=@{source="PaperS3"; age=(Get-Date).ToString("HH:mm:ss"); text="Daemon raw frame test"}} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:9877/widget -ContentType "application/json" -Body $body
```

Phase 3 completed:

- PaperS3 GT911 touch is initialized through M5Unified/M5GFX.
- Firmware logs `touch init success/failure`, `touch subsystem ready`, raw
  coordinates, screen coordinates, mapped logical coordinates, event type
  (`down`/`move`/`up`), touch count, hit target, click accepted/ignored, and
  debounce reasons.
- The PaperS3 HAL maps touch to the project logical portrait coordinate space
  `540x960`. Real-device calibration verified:
  - top-left approximately `(5,22)`
  - top-right approximately `(527,6)`
  - center approximately `(266,503)`
  - bottom-left approximately `(12,943)`
  - bottom-right approximately `(523,953)`
- Startup shows a PaperS3 touch calibration/test frame.
- PaperS3 parses daemon `cmd:set_chips` hot zones and hit-tests mapped clicks
  locally before emitting the existing daemon-compatible
  `{"event":"touch","x":...,"y":...,"hold_ms":...}` JSON line.
- Daemon dispatch now handles serial touch actions consistently with `/touch`
  for `settings`, `back`, `refresh`, `sleep`, `restart`, `repair`, and `clear`.
- For PaperS3 raw serial frame pushes, daemon sends `set_chips` after the full
  raw frame completes so the device has hot zones for the freshly painted UI.
- Bottom-bar `sleep` and `settings` chips have a minimum width of 104 px for
  usable PaperS3 touch targets.
- Windows daemon rendering now has CJK font fallbacks (`Microsoft YaHei`,
  `SimHei`, `SimSun`, `Microsoft JhengHei`) so Chinese text no longer renders
  as tofu boxes.
- User verified real-device behavior: `settings` hit target works, CJK text is
  normal, and touch dispatch reaches daemon.

Known Phase 3 boundary:

- `sleep` remains an existing daemon/UI action. It is now dispatched off the
  serial reader thread so raw-frame acks can still be read while the sleep card
  frame is pushed. Do not expand PaperS3 deep sleep/power policy until a later
  phase explicitly asks for it.

Useful Phase 3 manual commands:

```powershell
.\.pio-venv\Scripts\python.exe daemon\card_daemon.py --transport serial --port COM3

$body = @{type="scratch"; slot="middle"; data=@{text="PaperS3 touch test"; source="Codex"; age="now"}} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri http://127.0.0.1:9877/widget -Method Post -ContentType "application/json" -Body $body
```

Expected touch/hot-zone logs:

```text
[touch>] sending chip rects n=2 force=True
[dev<] [touch] hit zone id=sleep rect=(298,900,104,60)
[dev<] [touch] hit zone id=settings rect=(416,900,104,60)
[dev<] [touch] hit target id=settings ...
[touch<] (...) -> settings
```

Phase 4 completed:

- PaperS3 touch clicks now flow through the existing daemon hot-zone/action
  pipeline instead of adding business logic to the PaperS3 HAL.
- Serial touch and HTTP `/touch` share the same daemon-side dispatcher.
- PaperS3 keeps using portrait logical coordinates `540x960`; touch coordinate
  mapping and raw full-frame rendering were not changed.
- Daemon has a simple UI/frame state machine:
  `BOOTING`, `READY`, `RECEIVING_FRAME`, `DISPLAYING_FRAME`, `ERROR`, `STATUS`.
- State transitions log previous state, next state, and reason.
- Implemented/aliased actions:
  - `settings` / `status`: enter the status/settings page.
  - `back` / `home` / `dismiss`: return to the main widget card.
  - `refresh` / `reload` / `retry`: schedule a daemon re-render/re-push.
  - Existing `sleep`, `restart`, `repair`, and `clear` actions still dispatch
    through the daemon action pipeline.
- `confirm` is an explicit stub with a logged reason; no confirm workflow exists
  in this phase.
- PaperS3 status page shows firmware profile, UI state, transport, IP, frame
  receiver state, last frame age/time, and last error.
- PaperS3 status page exposes action-test buttons:
  `REFRESH`, `STATUS`, `BACK`, `RETRY`, `HOME`.
- If a click arrives during a frame push, daemon logs `ignored reason=busy`
  rather than dispatching into the active transfer.
- User verified real-device behavior with `home`: touch mapped coordinates hit
  the `home` target, daemon accepted the action, transitioned
  `STATUS -> DISPLAYING_FRAME -> RECEIVING_FRAME -> DISPLAYING_FRAME`, pushed a
  clean raw serial frame, and refreshed chip rects after the push.

Useful Phase 4 log patterns:

```text
[dev<] [touch] hit target id=home rect=(...)
[touch<serial] mapped x=... y=... hold_ms=...
[touch<serial] hit target id=home rect=(...)
[action] name=home accepted
[state] previous=STATUS next=DISPLAYING_FRAME reason=action:home
[state] previous=DISPLAYING_FRAME next=RECEIVING_FRAME reason=render_and_push
[frame] raw serial push fid=... 259200B full (...) ok
[state] previous=RECEIVING_FRAME next=DISPLAYING_FRAME reason=frame push complete
```

Phase 5 starting boundary:

- Treat Phase 5 as a fresh scoped task. Do not assume BLE, deep sleep, battery
  strategy, power optimization, or complex gestures are in scope unless the user
  says so.
- Preserve the stable PaperS3 raw full-frame push and touch coordinate mapping.
- Keep original M5Paper V1.1 profile behavior intact.

Phase 5 completed:

- PaperS3 still uses the existing daemon/widget/frame rendering architecture:
  `POST /widget` updates `WIDGET_CACHE`, `render_and_push()` renders a
  `540x960` Pillow frame, and PaperS3 raw serial receives a full `259200B`
  4bpp frame.
- Daemon logs now include widget types, render start/end, output size/format,
  transfer method/target/bytes, and result/error.
- `GET /frame-status` exposes the latest render/transfer status for demo
  scripts and debugging.
- `scratch` can now carry an optional `title`; this is the Phase 5 text card.
- `refresh` / `reload` exits the status page before scheduling a real widget
  re-render. `retry` only schedules a retry when there is an existing error;
  otherwise it logs `no error / nothing to retry`.
- `scripts/demo_papers3_widgets.py` pushes Phase 5 demo cards through the
  daemon and waits for `/frame-status`.
- Phase 5 demo widgets supported by the script:
  `text`, `status`, `weather-mock`, `calendar-mock`, `todo-mock`,
  `ai-status`, and `dashboard`.
- `text` and `status` exercise real renderer/daemon status paths.
  `weather-mock`, `calendar-mock`, `todo-mock`, and `ai-status` use
  sample/mock data so Phase 5 does not require external API keys or auth.
- Daemon serial opens now hold DTR/RTS low via `_open_serial_no_reset()` for
  both the main serial transport and side serial reader. This reduces
  USB-CDC reset/reboot behavior where restarting the daemon can repaint the
  PaperS3 startup touch-test page.
- If the daemon is stopped, PaperS3 touch actions cannot refresh real content.
  The e-ink panel should retain the last frame unless the device resets; if it
  returns to the startup touch-test page, collect boot logs plus daemon
  `[transfer]` / `[frame]` lines.

Useful Phase 5 Windows PowerShell commands:

```powershell
.\.pio-venv\Scripts\python.exe daemon\card_daemon.py --transport serial --port COM3

.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget text
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget status
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget weather-mock
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget calendar-mock
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget todo-mock
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget ai-status
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget dashboard
```

For failures, collect daemon lines containing `[widget]`, `[render]`,
`[transfer]`, `[frame]`, and `[action]`, plus PaperS3 serial lines containing
`[rx]`, `[frame]`, `[display]`, and `[touch]`.

Phase 5 handoff verification:

```powershell
$env:PYTHONPATH="E:\dev\ai-desk-card\.pio-venv\Lib\site-packages"
C:\Users\lucyundead\AppData\Local\Programs\Python\Python313\python.exe -m unittest discover -s test -p "test_*.py"
C:\Users\lucyundead\AppData\Local\Programs\Python\Python313\python.exe -m py_compile daemon\card_daemon.py daemon\card_render.py daemon\card_render_settings.py scripts\demo_papers3_widgets.py plugin\skills\card-widget\scripts\push_widget.py tools\push_paper_s3_test_frame.py
$env:PLATFORMIO_CORE_DIR=".pio-core"
.\.pio-venv\Scripts\pio.exe run -e paper-s3
.\.pio-venv\Scripts\pio.exe run -e card
git diff --check
```

Phase 6 starting boundary:

- Start from the committed Phase 5 handoff. Read `AGENTS.md` and the latest
  commit before coding.
- Keep the PaperS3 raw full-frame push, portrait `540x960` logical coordinate
  system, and touch mapping stable unless the new Phase 6 goal explicitly
  reopens them.
- Do not introduce BLE, deep sleep, battery strategy, or power optimization
  unless the user explicitly makes that Phase 6 scope.
- Keep original M5Paper V1.1 profile (`card`) buildable.
- Likely next useful checks: real daily-use daemon lifecycle, recoverability
  after daemon/device reconnect, and any user-specified widget/content gaps.

Phase 6 completed:

- Added formal device profile config at `config/device_profiles.json` with
  `m5paper-v1.1` and `paper-s3`.
- `paper-s3` profile metadata:
  `device_name=M5Stack PaperS3`, `platformio_env=paper-s3`,
  logical `540x960`, `display_format=4bpp grayscale`,
  `preferred_transport=USB serial`, widgets/touch/UI actions enabled, BLE /
  deep sleep / battery policy disabled.
- Shared helper `card_profiles.py` normalizes aliases (`card`,
  `M5Paper V1.1`, `PaperS3`, `M5Stack PaperS3`) and conservatively detects
  profile from daemon/device status.
- `daemon/card_daemon.py` accepts `--profile auto|m5paper-v1.1|paper-s3`,
  keeps default backward-compatible, and adds `selected_profile`,
  `profile_source`, `device_name`, and `preferred_transport` to status
  endpoints without changing the public widget/frame API.
- `scripts/card_cli.py` is the profile-aware Windows-friendly wrapper for
  build/upload/monitor/daemon/demo.
- `scripts/diagnose_device.py --profile paper-s3 --port COM3` checks
  PlatformIO, PlatformIO env, serial ports, daemon status, last frame status,
  optional build, optional demo send, and prints log patterns to copy.
- `scripts/demo_papers3_widgets.py --profile paper-s3 --widget ...` now reads
  the shared profile config and logs selected profile, transport,
  render size/format, transfer bytes, result/error.
- Demo widget pushes now leave the status page before posting a widget if the
  previous demo/action left the daemon in `selected_view=status`; this keeps
  text/weather/calendar/todo demos rendering as `selected_view=widgets`.
- `scripts/state.sh` now includes `profile.selected`,
  `profile.source`, and `profile.device_name`.
- Updated `SKILL.md`, README docs, install/transport flows, plugin command
  docs, and card-widget Skill docs with PaperS3 profile rules, Windows 11
  PowerShell quick start, diagnose path, and current PaperS3 limits.
- Profile selection rule for agents: explicit M5Paper V1.1 -> `m5paper-v1.1`;
  explicit PaperS3 / M5Stack PaperS3 / ESP32-S3 Paper -> `paper-s3`; unclear
  hardware -> ask model or run diagnose after the model is known. Do not
  default an unclear e-ink device to M5Paper V1.1.
- Verification run in Phase 6:

```powershell
$env:PYTHONPATH="E:\dev\ai-desk-card\.pio-venv\Lib\site-packages"
C:\Users\lucyundead\AppData\Local\Programs\Python\Python313\python.exe -m unittest discover -s test -p "test_*.py"
C:\Users\lucyundead\AppData\Local\Programs\Python\Python313\python.exe -m py_compile card_profiles.py daemon\card_daemon.py scripts\card_cli.py scripts\diagnose_device.py scripts\demo_papers3_widgets.py plugin\skills\card-widget\scripts\push_widget.py tools\push_paper_s3_test_frame.py
$env:PLATFORMIO_CORE_DIR=".pio-core"
.\.pio-venv\Scripts\pio.exe run -e paper-s3
.\.pio-venv\Scripts\pio.exe run -e card
git diff --check
```

Useful Phase 6 PaperS3 commands:

```powershell
[System.IO.Ports.SerialPort]::GetPortNames()
.\.pio-venv\Scripts\python.exe scripts\card_cli.py build --profile paper-s3
.\.pio-venv\Scripts\python.exe scripts\card_cli.py upload --profile paper-s3 --port COM3
.\.pio-venv\Scripts\python.exe scripts\card_cli.py monitor --profile paper-s3 --port COM3
.\.pio-venv\Scripts\python.exe daemon\card_daemon.py --profile paper-s3 --transport serial --port COM3
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget dashboard
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget status
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget text
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget weather-mock
.\.pio-venv\Scripts\python.exe scripts\diagnose_device.py --profile paper-s3 --port COM3
```

For Phase 6 failures, collect daemon lines containing `[widget]`, `[render]`,
`[transfer]`, `[frame]`, and `[action]`; PaperS3 serial lines containing
`[rx]`, `[frame]`, `[display]`, and `[touch]`; and
`GET http://127.0.0.1:9877/frame-status`.

Phase 6 real-device acceptance:

- User ran daemon:
  `.\.pio-venv\Scripts\python.exe daemon\card_daemon.py --profile paper-s3 --transport serial --port COM3`.
- PaperS3 showing its touch calibration/test circle page immediately after
  flashing or rebooting is expected; it is the firmware startup test frame
  and should be replaced after the daemon pushes the first real frame.
- For first setup, push `dashboard` first so the initial card matches the
  original M5Paper V1.1 complete-use demo expectation; use `status` and
  `text` as follow-up checks.
- Daemon opened `COM3`, loaded cached widgets, received PaperS3 status:
  `device=M5Stack PaperS3`, `fw=0.10.7-paper-s3-frame`,
  `battery_pct=90`, `on_usb=true`, `charging=true`,
  `frame_state=displayed`.
- Raw serial frame push completed on hardware:
  `259200B`, `crc=7fc41079`, `frame_raw_begin` ack,
  `frame_raw_end` ack, decoded `540x960` `4bpp`, display update
  `logical=540x960 panel=960x540 map=rotate-cw epd=quality`, update end
  `ms=662`.
- Daemon `/frame-status` after the hardware push reported:
  `selected_profile=paper-s3`, `selected_view=widgets`,
  `selected_widgets=['ai-status']`, output `540x960 4bpp`,
  transfer `raw-serial` target `serial` bytes `259200`, `result=ok`,
  `profile_source=telemetry`, `active_transport=USB`.
- User verified demo commands on hardware:
  `status`, `text`, and `weather-mock` all completed with
  `result=ok`, `profile=paper-s3`, output `540x960 4bpp`, transfer
  `raw-serial` target `serial` bytes `259200`.
- After the demo view fix, user reran `weather-mock`; output reported
  `selected widget=weather-mock`, `selected profile=paper-s3`,
  `render width=540 height=960 format=4bpp grayscale`, and final
  `view=widgets widgets=['weather']`, confirming widget demos return to the
  real widget view rather than remaining on the status page.

Codex usage card follow-up:

- `ai-status` now prefers `data.usage` over the older `data.context` bar.
  Supported usage fields are `five_hour_remaining`, `weekly_remaining`, and
  optional `reset_hint`; old `context.used/limit` payloads still render.
- `scripts/push_codex_ai_status.py` reads real Codex account rate limits via
  `codex app-server` JSON-RPC (`account/rateLimits/read`) and pushes the
  right-side `ai-status` card through the existing daemon `/widget` API.
- Useful command:

```powershell
.\.pio-venv\Scripts\python.exe scripts\push_codex_ai_status.py
```

- Verified on hardware/daemon: app-server source returned `model=gpt-5.5`,
  `5h=64% left`, `weekly=48% left`; daemon accepted the widget with
  `push_scheduled=true`; `/frame-status` reported `paper-s3`, `raw-serial`,
  `259200B`, `result=ok`, `selected_widgets=['weather','calendar','todo','ai-status']`.
- This follow-up did not change firmware, serial frame transfer, touch mapping,
  or daemon public widget/frame API.

Claude Code usage card follow-up:

- Claude Code does not expose quota through `claude auth status`; use its
  statusline JSON instead. Official statusline input includes
  `rate_limits.five_hour.used_percentage` and
  `rate_limits.seven_day.used_percentage` for Claude.ai subscribers after the
  first assistant response in a session.
- `scripts/claude_statusline_sink.py` is the statusline command. It reads the
  JSON from stdin, writes `%USERPROFILE%\.claude\ai-desk-card-usage.json`, and
  prints a compact Claude statusline. It does not read Claude auth tokens.
- `scripts/push_claude_ai_status.py` reads that cache and pushes the existing
  `ai-status` widget through daemon `/widget`.
- Useful commands:

```powershell
C:\Users\lucyundead\AppData\Local\Programs\Python\Python313\python.exe E:\dev\ai-desk-card\scripts\claude_statusline_sink.py
.\.pio-venv\Scripts\python.exe scripts\push_claude_ai_status.py
```

- To make it automatic, configure Claude Code `statusLine` command to the
  absolute `claude_statusline_sink.py` invocation above, then interact once in
  the Claude Code app so it emits fresh statusline JSON.
- Verified on 2026-06-16 after configuring
  `%USERPROFILE%\.claude\settings.json`: statusline cache reported
  `model=Sonnet 4.6`, `5h=100% left`, `weekly=61% left`; pushing
  `scripts/push_claude_ai_status.py` succeeded, and `/frame-status` reported
  `paper-s3`, `raw-serial`, `259200B`, `result=ok`,
  `selected_widgets=['weather','calendar','todo','ai-status']`.

Phase 7 completed:

- PaperS3 now has a profile-local Wi-Fi transport path; USB serial remains the
  provisioning and fallback path.
- PaperS3 firmware adds Wi-Fi credential storage, bounded reconnect attempts,
  HTTP server endpoints (`GET /status`, `POST /cmd`, `POST /frame`), and mDNS
  advertising for `_ai-desk-card._tcp`.
- PaperS3 HTTP frames remain full logical `540x960` 4bpp frames (`259200B`).
  The device validates width, height, bpp, byte count, and CRC before painting;
  bad or partial frames keep the previous e-ink image.
- The daemon can run directly against a known PaperS3 IP:
  `--profile paper-s3 --transport wifi --host <PaperS3-IP> --wifi-port 9880 --http-host 0.0.0.0`.
- Daemon Wi-Fi frame pushes include integrity headers:
  `X-Frame-Fid`, `X-Frame-Width`, `X-Frame-Height`, `X-Frame-Bpp`,
  `X-Frame-Bytes`, and `X-Frame-Crc`.
- `POST /provision-wifi` still goes through the daemon, sends credentials over
  the active device transport, and supports an empty SSID to clear credentials.
- PaperS3 status and `/frame-status` now expose Wi-Fi state/error/IP/RSSI so
  failures are visible without guessing.
- `scripts/diagnose_device.py` supports PaperS3 Wi-Fi checks with
  `--transport wifi --host <PaperS3-IP> --wifi-port 9880 --http-host 0.0.0.0`.
- `scripts/collect_papers3_wifi_report.py` prints a redacted Markdown report
  for daemon, frame, and PaperS3 `/status`; it masks SSIDs and redacts secrets.
- README, install/transport flows, `SKILL.md`, card-widget skill docs, and
  `card-start` command docs now treat PaperS3 Wi-Fi as the recommended route
  after USB serial provisioning.
- BLE, deep sleep, battery policy, and power optimization remain out of scope.
  Do not add them unless a later phase explicitly asks.

Useful Phase 7 PaperS3 commands:

```powershell
.\.pio-venv\Scripts\python.exe daemon\card_daemon.py --profile paper-s3 --transport serial --port COM3

$body = @{ssid="YOUR_WIFI_SSID"; password="YOUR_WIFI_PASSWORD"} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:9877/provision-wifi -ContentType "application/json" -Body $body

.\.pio-venv\Scripts\python.exe daemon\card_daemon.py --profile paper-s3 --transport wifi --host <PaperS3-IP> --wifi-port 9880 --http-host 0.0.0.0
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget dashboard
.\.pio-venv\Scripts\python.exe scripts\diagnose_device.py --profile paper-s3 --transport wifi --host <PaperS3-IP> --wifi-port 9880 --http-host 0.0.0.0
.\.pio-venv\Scripts\python.exe scripts\collect_papers3_wifi_report.py --host <PaperS3-IP>
```

For Phase 7 failures, collect daemon lines containing `[widget]`, `[render]`,
`[transfer]`, `[frame]`, `[action]`, and `[wifi]`; PaperS3 serial lines
containing `[rx]`, `[frame]`, `[display]`, `[touch]`, `[wifi]`, `[http]`, and
`[mdns]`; plus `GET http://127.0.0.1:9877/frame-status` and the redacted
report from `scripts\collect_papers3_wifi_report.py`.

Phase 7 real-device acceptance:

- User provisioned PaperS3 onto Wi-Fi and ran the daemon with
  `--profile paper-s3 --transport wifi --host 192.168.137.143 --wifi-port 9880
  --http-host 0.0.0.0`.
- Redacted Wi-Fi report showed PaperS3 online at `192.168.137.143`,
  `state=WIFI_CONNECTED`, RSSI `-38`, `last_error=none`, battery `73%`,
  `on_usb=true`, and firmware `/status` `frame_state=displayed`.
- Daemon `/frame-status` reported `selected_profile=paper-s3`,
  `active_transport=Wi-Fi`, transfer `method=http`, `target=wifi`,
  `bytes=259200`, `result=ok`, output `540x960` `4bpp`.
- After adding `--http-host 0.0.0.0`, daemon `/heartbeat` reported
  `alive=true`, `last_seen_seconds=10`, `battery_pct=77`, `uptime=49m`,
  `wifi_connected=true`, `wifi_ip=192.168.137.143`, and
  `wifi_state=WIFI_CONNECTED`.
- User tapped the PaperS3 settings chip over Wi-Fi. Daemon logged
  `[touch<http] mapped x=469 y=953 hold_ms=168`, hit target
  `id=settings rect=(416, 900, 520, 960)`, accepted `action:settings`,
  transitioned `DISPLAYING_FRAME -> STATUS -> RECEIVING_FRAME`, rendered the
  status view, and pushed a full HTTP frame `259200B` with
  `crc=86b4e7d3` in `1.76s`.

Verification run in Phase 7:

```powershell
$env:PYTHONPATH="E:\dev\ai-desk-card;E:\dev\ai-desk-card\.pio-venv\Lib\site-packages"
C:\Users\lucyundead\AppData\Local\Programs\Python\Python313\python.exe -m unittest discover -s test -p "test_*.py"
C:\Users\lucyundead\AppData\Local\Programs\Python\Python313\python.exe -m py_compile card_profiles.py daemon\card_daemon.py daemon\card_render.py daemon\card_render_settings.py scripts\card_cli.py scripts\diagnose_device.py scripts\demo_papers3_widgets.py scripts\collect_papers3_wifi_report.py plugin\skills\card-widget\scripts\push_widget.py tools\push_paper_s3_test_frame.py
$env:PLATFORMIO_CORE_DIR=".pio-core"
.\.pio-venv\Scripts\pio.exe run -e paper-s3
.\.pio-venv\Scripts\pio.exe run -e card
git diff --check
```

Stage 8 completed:

- Stage 8 keeps PaperS3 on the validated raw full-frame, Wi-Fi HTTP,
  portrait `540x960`, and touch-action paths from earlier phases.
- PaperS3 has a conservative profile-local power policy in
  `config/device_profiles.json`: default `always-on`, supported modes
  `always-on`, `idle-low-power`, and `sleep-card`; deep sleep and BLE are
  explicitly unsupported until wake/recovery is verified on hardware.
- PaperS3 firmware now reads battery percentage, battery mV, VBUS mV,
  charging state, USB/source state, and wake reason. Unknown USB/charging
  readings are reported as JSON null instead of guessed booleans.
- PaperS3 firmware `/status` and serial `status_report` expose
  `power_mode`, `power_source`, `vbus_mv`, `deep_sleep_enabled=false`,
  `wake_reason`, and `last_power_read_ms`.
- Daemon `/heartbeat` and `/frame-status` expose a merged `power` section
  from profile policy plus latest firmware telemetry.
- PaperS3 settings/status page now shows power mode/source, battery/VBUS,
  USB/charging, and wake reason.
- PaperS3 `sleep` action is sleep-card only: it renders/pushes the sleep
  card and returns `deep_sleep=false` without sending `cmd:sleep_now`.
  M5Paper V1.1 still sends `cmd:sleep_now`.
- `scripts/diagnose_device.py` prints a PaperS3 power section, and
  `scripts/collect_papers3_wifi_report.py` includes a redacted Power section.
- README, `SKILL.md`, card-widget docs, install/transport/sleep flows, and
  `/card-sleep` command docs now describe the profile-specific sleep behavior.
- Wi-Fi transport `connected()` is deterministic: a failed HTTP frame/command
  marks it disconnected until a later HTTP frame/command succeeds.

Useful Stage 8 PaperS3 real-device checks:

```powershell
.\.pio-venv\Scripts\python.exe scripts\card_cli.py upload --profile paper-s3 --port COM3
.\.pio-venv\Scripts\python.exe daemon\card_daemon.py --profile paper-s3 --transport wifi --host <PaperS3-IP> --wifi-port 9880 --http-host 0.0.0.0
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget dashboard
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget status
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:9877/sleep -ContentType "application/json" -Body "{}"
.\.pio-venv\Scripts\python.exe scripts\diagnose_device.py --profile paper-s3 --transport wifi --host <PaperS3-IP> --wifi-port 9880 --http-host 0.0.0.0
.\.pio-venv\Scripts\python.exe scripts\collect_papers3_wifi_report.py --host <PaperS3-IP>
```

Expected Stage 8 real-device evidence:

- Firmware boot/status logs include `[power] source=... usb=... charging=...`
  with battery, VBUS, `mode=always-on`, and `wake=...`.
- PaperS3 `/status` includes a `power` object and top-level power fields.
- Daemon `/frame-status` includes `power.mode=always-on`,
  `deep_sleep_status=unsupported`, and `ble_status=unsupported`.
- `/sleep` returns `mode=sleep-card`, `deep_sleep=false`, and PaperS3 keeps
  accepting later Wi-Fi/USB pushes without a deep-sleep wake sequence.

Stage 8 real-device acceptance:

- User uploaded PaperS3 firmware successfully over `COM3`; upload wrote
  `990560` bytes and reset via RTS.
- `pio run -e paper-s3 -t upload -t monitor --upload-port COM3` captured boot
  logs on real hardware:
  `[probe] setup entered before M5.begin`, `[probe] M5.begin returned`,
  `[boot] ai-desk-card PaperS3 bring-up`,
  `[power] source=unknown usb=unknown charging=yes battery=86% battery_mv=3988 vbus_mv=-1 mode=always-on wake=boot`,
  and `[feature] deep sleep unsupported for paper-s3 (sleep-card only)`.
- Firmware serial status reports included Stage 8 fields:
  `vbus_mv=-1`, `power_source=unknown`, `power_mode=always-on`,
  `deep_sleep_enabled=false`, `wake_reason=boot`, and
  `last_power_read_ms`.
- PaperS3 joined Wi-Fi at `192.168.137.253`, RSSI approximately `-30` to
  `-34`, and advertised HTTP/mDNS.
- Daemon was restarted with Wi-Fi transport. `/pair-status` reported
  `connected=true`, `transport=WiFiTransport`, `selected_profile=paper-s3`,
  `profile_source=telemetry`, and preferred transport `Wi-Fi`.
- Daemon `/heartbeat` reported `alive=true`, `active_transport=Wi-Fi`,
  `transport_connected=true`, battery around `87%`, `vbus_mv=-1`,
  `on_usb=null`, `charging=true`, and merged power status:
  `mode=always-on`, `deep_sleep_status=unsupported`,
  `ble_status=unsupported`, `last_wake_reason=boot`.
- PaperS3 HTTP `/status` reported top-level and nested `power` fields:
  `power_mode=always-on`, `deep_sleep_enabled=false`, `wake_reason=boot`,
  `last_power_read_ms`, `on_usb=null`, and `charging=true`.
- User reported `dashboard` and `status` demo pushes were normal over Wi-Fi.
- `POST /sleep` returned `ok=true`, `mode=sleep-card`,
  `deep_sleep=false`, and `deep_sleep_status=unsupported`.
- Daemon `/frame-status` after sleep/status reported `result=ok`,
  transfer `method=http`, `target=wifi`, `bytes=259200`,
  `active_transport=Wi-Fi`, `wifi_state=WIFI_CONNECTED`, and power
  `mode=always-on`, `deep_sleep_status=unsupported`, `ble_status=unsupported`.
- The `vbus_mv=-1` / `on_usb=null` result is accepted for this hardware
  reading: Stage 8 intentionally reports unknown rather than guessing USB
  presence when VBUS is unavailable, while battery and charging remain visible.
Verification run in Stage 8 implementation:

```powershell
$env:PYTHONPATH="E:\dev\ai-desk-card;E:\dev\ai-desk-card\.pio-venv\Lib\site-packages"
C:\Users\lucyundead\AppData\Local\Programs\Python\Python313\python.exe -m unittest discover -s test -p "test_*.py"
C:\Users\lucyundead\AppData\Local\Programs\Python\Python313\python.exe -m py_compile card_profiles.py daemon\card_daemon.py daemon\card_render.py daemon\card_render_settings.py scripts\card_cli.py scripts\diagnose_device.py scripts\demo_papers3_widgets.py scripts\collect_papers3_wifi_report.py plugin\skills\card-widget\scripts\push_widget.py tools\push_paper_s3_test_frame.py
$env:PLATFORMIO_CORE_DIR=".pio-core"
.\.pio-venv\Scripts\pio.exe run -e paper-s3
.\.pio-venv\Scripts\pio.exe run -e card
git diff --check
```

Final PaperS3 polish after Stage 8:

- Continued from commit `9da2d6a feat: finish PaperS3 power release path`.
- Added `scripts/onboard_papers3.py`, a thin PaperS3 first-run wrapper that
  reuses existing commands instead of reimplementing rendering:
  - probes serial ports, daemon `/pair-status`, and `/heartbeat`;
  - builds and uploads PaperS3 firmware unless `--skip-build` /
    `--skip-upload` is passed;
  - starts a serial daemon for initial provisioning when no usable Wi-Fi daemon
    is already connected;
  - provisions Wi-Fi through `/provision-wifi` without logging the password;
  - switches to / reuses Wi-Fi daemon with `--http-host 0.0.0.0` when an IP is
    known;
  - pushes the first real `dashboard` via `scripts/demo_papers3_widgets.py`;
  - leaves the dashboard visible by default and only pushes sleep-card with
    explicit `--push-sleep-card`.
- `scripts/card_cli.py onboard --profile paper-s3 --port COM3` delegates to the
  wrapper. If PaperS3 is already provisioned, use `--host <PaperS3-IP>` to skip
  re-entering credentials; the wrapper also reuses an already connected Wi-Fi
  daemon instead of starting a second daemon on port 9877.
- PaperS3 firmware startup now shows a formal waiting/dashboard page via
  `paintWaitingForDashboardScreen(CARD_VERSION, wifiIPStr())` instead of the
  old touch calibration/test target page. Touch mapping, touch logs, raw
  full-frame rendering, Wi-Fi HTTP push, and sleep-card policy were not changed.
- Text-position request status: existing render surfaces were located
  (`daemon/card_render_settings.py`, `daemon/card_render_sleep.py`,
  `daemon/card_render.py`, `src/paper_s3/paper_s3_hw.cpp`,
  `src/paper_s3/main.cpp`). No Python renderer text positions were changed
  because no page/photo-specific offset was provided; ask for a photo or exact
  page before adjusting layout.
- Docs updated: `README.md`, `SKILL.md`, `flows/01_install.md`,
  `flows/03_wifi.md`, `flows/07_sleep.md`, `/card-install`, `/card-onboard`,
  `/card-start`, and `/card-sleep` now point to the PaperS3 onboarding wrapper
  and the waiting/dashboard startup behavior.
- Local verification completed after implementation:

```powershell
$env:PYTHONPATH="E:\dev\ai-desk-card;E:\dev\ai-desk-card\.pio-venv\Lib\site-packages"
C:\Users\lucyundead\AppData\Local\Programs\Python\Python313\python.exe -m unittest discover -s test -p "test_*.py"
C:\Users\lucyundead\AppData\Local\Programs\Python\Python313\python.exe -m py_compile card_profiles.py daemon\card_daemon.py daemon\card_render.py daemon\card_render_settings.py daemon\card_render_sleep.py scripts\card_cli.py scripts\diagnose_device.py scripts\demo_papers3_widgets.py scripts\onboard_papers3.py scripts\collect_papers3_wifi_report.py plugin\skills\card-widget\scripts\push_widget.py tools\push_paper_s3_test_frame.py
$env:PLATFORMIO_CORE_DIR=".pio-core"
.\.pio-venv\Scripts\pio.exe run -e paper-s3
.\.pio-venv\Scripts\pio.exe run -e card
git diff --check
```

- Real-device acceptance commands for the startup/dashboard polish:

```powershell
cd E:\dev\ai-desk-card
$env:PLATFORMIO_CORE_DIR=".pio-core"
.\.pio-venv\Scripts\python.exe scripts\card_cli.py upload --profile paper-s3 --port COM3
.\.pio-venv\Scripts\python.exe scripts\card_cli.py onboard --profile paper-s3 --port COM3 --host 192.168.137.48 --skip-build --skip-upload
Invoke-RestMethod -Uri http://127.0.0.1:9877/frame-status | ConvertTo-Json -Depth 6
Invoke-RestMethod -Uri http://127.0.0.1:9877/heartbeat | ConvertTo-Json -Depth 6
```

- User uploaded/rebooted PaperS3 over `COM3` and captured real hardware boot
  logs. Firmware startup now shows the production waiting page:
  `[display] PaperS3 waiting dashboard screen pushed`, followed by
  `[boot] ready; start daemon and push the first dashboard frame`.
- The reboot logs confirmed the verified paths stayed intact:
  touch `rotate-cw-inverse` logical `540x960`, PSRAM frame buffer
  `259200` bytes, serial frame stream active, PaperS3 power mode
  `always-on`, BLE disabled, and deep sleep unsupported / sleep-card only.
- PaperS3 rejoined Wi-Fi at `192.168.137.48` with RSSI around `-28`,
  started HTTP on `:9880`, and advertised mDNS as
  `papers3-ff40.local _ai-desk-card._tcp:9880`.
- Serial `status_report` after reboot reported firmware
  `0.10.7-paper-s3-frame`, `wifi_connected=true`,
  `wifi_state=WIFI_CONNECTED`, `frame_state=ready`, battery `100%`,
  `vbus_mv=-1`, `on_usb=null`, and `charging=false`.
- User then pushed the first dashboard over Wi-Fi. Final `/frame-status`
  reported `render_id=5`, `selected_profile=paper-s3`,
  `selected_view=widgets`, selected widgets
  `weather`, `ai-status`, `calendar`, and `todo`, output `540x960` `4bpp`,
  HTTP/Wi-Fi transfer `259200B`, `result=ok`, `ui_state=DISPLAYING_FRAME`,
  `transport_connected=true`, `active_transport=Wi-Fi`,
  `wifi_ip=192.168.137.48`, `wifi_state=WIFI_CONNECTED`, and power mode
  `always-on`.
- Final `/heartbeat` reported `alive=true`, `last_seen_seconds=23`,
  firmware `0.10.7-paper-s3-frame`, profile source `telemetry`, device
  `M5Stack PaperS3`, Wi-Fi connected at `192.168.137.48`, battery `100%`,
  `vbus_mv=-1`, `on_usb=null`, `charging=false`, `deep_sleep_status=unsupported`,
  and `ble_status=unsupported`.

Final PaperS3 polish Wi-Fi recovery note:

- On 2026-06-23, a first dashboard push reported `/frame-status result=failed`
  with `paper-s3 wifi frame push failed: frame HTTP 192.168.137.253:9880: 502`
  and `/heartbeat alive=false`.
- Root cause was two-part:
  - the desktop environment had `HTTP_PROXY` / `ALL_PROXY` set to
    `http://127.0.0.1:7897` while `NO_PROXY` only covered localhost, so Python
    `urllib` could send PaperS3 LAN requests through the proxy and report a
    proxy `502`;
  - PaperS3 was no longer at `192.168.137.253`. ARP showed
    `192.168.137.48` for MAC `E8:F6:0A:84:FF:40`, and direct
    `curl.exe --noproxy "*"` confirmed PaperS3 `/status` there.
- `daemon/card_daemon.py` now uses a direct no-proxy opener for PaperS3
  device-side Wi-Fi HTTP (`/cmd`, `/frame`, and reachability `/status`).
  `scripts/diagnose_device.py` and `scripts/collect_papers3_wifi_report.py`
  also bypass proxies for direct PaperS3 `/status` diagnostics.
- The stale daemon PID `2056` was stopped and restarted against the current IP:

```powershell
.\.pio-venv\Scripts\python.exe daemon\card_daemon.py --profile paper-s3 --transport wifi --host 192.168.137.48 --wifi-port 9880 --http-host 0.0.0.0
```

- Hardware Wi-Fi recovery was verified after daemon restart:
  `scripts\demo_papers3_widgets.py --profile paper-s3 --widget dashboard`
  completed with `result=ok`, output `540x960` `4bpp`, HTTP/Wi-Fi transfer
  `259200B`; `/frame-status` reported `transport_connected=true`,
  `active_transport=Wi-Fi`, `wifi_ip=192.168.137.48`, `result=ok`; `/heartbeat`
  reported `alive=true`, firmware `0.10.7-paper-s3-frame`, Wi-Fi connected,
  battery `100%`, and power mode `always-on`.
- Verification after the recovery fix:

```powershell
$env:PYTHONPATH="E:\dev\ai-desk-card;E:\dev\ai-desk-card\.pio-venv\Lib\site-packages"
C:\Users\lucyundead\AppData\Local\Programs\Python\Python313\python.exe -m unittest discover -s test -p "test_*.py"
C:\Users\lucyundead\AppData\Local\Programs\Python\Python313\python.exe -m py_compile card_profiles.py daemon\card_daemon.py daemon\card_render.py daemon\card_render_settings.py daemon\card_render_sleep.py scripts\card_cli.py scripts\diagnose_device.py scripts\demo_papers3_widgets.py scripts\onboard_papers3.py scripts\collect_papers3_wifi_report.py plugin\skills\card-widget\scripts\push_widget.py tools\push_paper_s3_test_frame.py
$env:PLATFORMIO_CORE_DIR=".pio-core"
.\.pio-venv\Scripts\pio.exe run -e paper-s3
.\.pio-venv\Scripts\pio.exe run -e card
git diff --check
```

All passed; `git diff --check` only reported LF-to-CRLF warnings.
- Startup waiting/dashboard firmware page real-device acceptance is complete.
## Engineering Rules For This Project

- Keep changes surgical and phase-scoped.
- Preserve the daemon/widget protocol unless the user explicitly agrees.
- Do not modify the stable frame rendering path unless needed for touch test UI.
- After each firmware-related edit, run `pio run -e paper-s3`.
- Before completion, also run `pio run -e card`.
- Do not revert user or WIP changes without explicit approval.
- Prefer `rg`/`rg --files` for searching.
