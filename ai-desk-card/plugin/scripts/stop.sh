#!/usr/bin/env bash
set -euo pipefail
if pgrep -f "card_daemon.py" >/dev/null 2>&1; then
  pkill -f "card_daemon.py" || true
  sleep 0.5
  echo "card daemon stopped"
else
  echo "card daemon not running"
fi
