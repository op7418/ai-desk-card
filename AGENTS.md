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

## Phase 3 Status: PaperS3 Touch

Phase 3 has not been completed yet. The user wants:

1. Raw GT911 touch debug on PaperS3.
2. Logical `540x960` mapped touch coordinates inside the PaperS3 HAL.
3. A touch calibration/test screen with `TOP LEFT`, `TOP RIGHT`, `CENTER`,
   `BOTTOM LEFT`, `BOTTOM RIGHT`.
4. Only after calibration, connect mapped clicks to the existing daemon/UI
   hit-test flow.
5. Basic click only, minimal debounce, no BLE/deep sleep/power work.

Important: after the interrupted first Phase 3 attempt, there may be uncommitted
WIP changes in:

- `daemon/card_daemon.py`
- `src/paper_s3/main.cpp`
- `src/paper_s3/paper_s3_hw.cpp`
- `src/paper_s3/paper_s3_hw.h`
- `test/test_card_daemon_paper_s3_raw.py`

Before continuing Phase 3, inspect `git diff` and decide whether to keep,
finish, or discard those WIP edits. Do not silently overwrite them.

## Engineering Rules For This Project

- Keep changes surgical and phase-scoped.
- Preserve the daemon/widget protocol unless the user explicitly agrees.
- Do not modify the stable frame rendering path unless needed for touch test UI.
- After each firmware-related edit, run `pio run -e paper-s3`.
- Before completion, also run `pio run -e card`.
- Do not revert user or WIP changes without explicit approval.
- Prefer `rg`/`rg --files` for searching.
