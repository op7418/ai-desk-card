---
description: Inspect / clear / preview the ai-desk-card widget cache.
---

Subcommands:
- (none) — print current widget cache
- `preview [out.png]` — render 540×960 PNG via Pillow + open
- `clear [slot]` — wipe a slot (no slot = all)
- `pair-status` — show daemon ↔ device connection state
- `unpair` — forward unpair to device

PaperS3 demo widgets:

```powershell
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget status
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget text
.\.pio-venv\Scripts\python.exe scripts\demo_papers3_widgets.py --profile paper-s3 --widget weather-mock
```

!`bash "$CLAUDE_PLUGIN_ROOT/scripts/widget.sh" "$ARGUMENTS"`
