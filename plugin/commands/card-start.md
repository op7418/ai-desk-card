---
description: Start the ai-desk-card daemon (Wi-Fi preferred after provisioning, USB serial fallback).
---

Starts the local card daemon listening on 127.0.0.1:9877 and connects to
the M5Paper running the ai-desk-card firmware. Pushes any cached widgets
on (re)connect.

PaperS3 / Windows PowerShell path:

```powershell
.\.pio-venv\Scripts\python.exe daemon\card_daemon.py --profile paper-s3 --transport serial --port COM3
.\.pio-venv\Scripts\python.exe daemon\card_daemon.py --profile paper-s3 --transport wifi --host <PaperS3-IP> --wifi-port 9880 --http-host 0.0.0.0
```

!`bash "$CLAUDE_PLUGIN_ROOT/scripts/start.sh"`
