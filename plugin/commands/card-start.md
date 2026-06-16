---
description: Start the ai-desk-card daemon (USB serial preferred, BLE fallback).
---

Starts the local card daemon listening on 127.0.0.1:9877 and connects to
the M5Paper running the ai-desk-card firmware. Pushes any cached widgets
on (re)connect.

PaperS3 / Windows PowerShell path:

```powershell
.\.pio-venv\Scripts\python.exe daemon\card_daemon.py --profile paper-s3 --transport serial --port COM3
```

!`bash "$CLAUDE_PLUGIN_ROOT/scripts/start.sh"`
