---
description: First-time setup wizard — detects daemon/USB/firmware and walks you through whatever's missing.
---

Run the card-onboard skill.
For PaperS3 on Windows, the executable path is:

```powershell
.\.pio-venv\Scripts\python.exe scripts\card_cli.py onboard --profile paper-s3 --port COM3
```

This follows the README workflow for PaperS3: probe, install/provision when
needed, ask flow 04 inputs (weather location plus sleep-card business card),
write dashboard-aligned interests/profile files, push the configured first
dashboard, and print the schedule handoff. If existing flow 04 files should be
preserved, ask the user first and then use:

```powershell
.\.pio-venv\Scripts\python.exe scripts\card_cli.py onboard --profile paper-s3 --port COM3 --skip-interests --skip-card-profile
```

Do not treat a healthy daemon, a current `result=ok` frame, or an existing
weather-only `interests.yaml` as enough to complete a PaperS3 onboard request.
Those facts prove transport health; they do not replace the flow 04
rewrite-or-preserve question.

AI will probe daemon + connection + firmware
state, then guide you through whichever step (start daemon / plug USB /
flash firmware / pair BLE) needs handling.

Use this:
- first time you connect a ai-desk-card device
- after moving setup to a new machine
- when "card 没反应" / no widget shows up

!`bash "$CLAUDE_PLUGIN_ROOT/skills/card-onboard/scripts/probe.sh"`
