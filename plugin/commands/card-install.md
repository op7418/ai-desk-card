---
description: Detect or flash the ai-desk-card firmware.
---

Subcommands:
- `detect` (default) — read [boot] line over serial, print firmware version
- `flash` — flash the local build at `.pio/build/card/firmware.bin`
            (build first with `pio run -e card` from `ai-desk-card/`).
            Always prompts for confirmation; sha256 check on download path.

PaperS3 / Windows PowerShell path:

```powershell
.\.pio-venv\Scripts\python.exe scripts\card_cli.py build --profile paper-s3
.\.pio-venv\Scripts\python.exe scripts\card_cli.py upload --profile paper-s3 --port COM3
.\.pio-venv\Scripts\python.exe scripts\card_cli.py monitor --profile paper-s3 --port COM3
```

!`bash "$CLAUDE_PLUGIN_ROOT/scripts/install.sh" "$ARGUMENTS"`
