---
description: Start the claude-card daemon (USB serial preferred, BLE fallback).
---

Starts the local card daemon listening on 127.0.0.1:9877 and connects to
the M5Paper running the claude-card firmware. Pushes any cached widgets
on (re)connect.

!`bash "$CLAUDE_PLUGIN_ROOT/scripts/start.sh"`
