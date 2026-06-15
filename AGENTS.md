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

## Engineering Rules For This Project

- Keep changes surgical and phase-scoped.
- Preserve the daemon/widget protocol unless the user explicitly agrees.
- Do not modify the stable frame rendering path unless needed for touch test UI.
- After each firmware-related edit, run `pio run -e paper-s3`.
- Before completion, also run `pio run -e card`.
- Do not revert user or WIP changes without explicit approval.
- Prefer `rg`/`rg --files` for searching.
