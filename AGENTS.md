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

## Engineering Rules For This Project

- Keep changes surgical and phase-scoped.
- Preserve the daemon/widget protocol unless the user explicitly agrees.
- Do not modify the stable frame rendering path unless needed for touch test UI.
- After each firmware-related edit, run `pio run -e paper-s3`.
- Before completion, also run `pio run -e card`.
- Do not revert user or WIP changes without explicit approval.
- Prefer `rg`/`rg --files` for searching.
