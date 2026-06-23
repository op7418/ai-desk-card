---
description: First-time setup wizard — detects daemon/USB/firmware and walks you through whatever's missing.
---

Run the card-onboard skill.
For PaperS3 on Windows, the executable path is:

```powershell
.\.pio-venv\Scripts\python.exe scripts\card_cli.py onboard --profile paper-s3 --port COM3
```

After the first dashboard is visible, configure auto-refresh interests with:

```powershell
.\.pio-venv\Scripts\python.exe scripts\card_cli.py interests --profile paper-s3
```

AI will probe daemon + connection + firmware
state, then guide you through whichever step (start daemon / plug USB /
flash firmware / pair BLE) needs handling.

Use this:
- first time you connect a ai-desk-card device
- after moving setup to a new machine
- when "card 没反应" / no widget shows up

!`bash "$CLAUDE_PLUGIN_ROOT/skills/card-onboard/scripts/probe.sh"`
