#!/usr/bin/env bash
set -euo pipefail
DAEMON_URL="${CARD_DAEMON_URL:-http://127.0.0.1:9877}"

echo "=== daemon process ==="
if pgrep -fl "card_daemon.py" 2>/dev/null; then
  echo
else
  echo "(not running — try /card-start)"
  echo
fi

echo "=== pair status ==="
curl -sf "$DAEMON_URL/pair-status" 2>/dev/null && echo || echo "(unreachable)"
echo

echo "=== widget cache ==="
curl -sf "$DAEMON_URL/widget" 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "(unreachable)"
echo

LOG="${TMPDIR:-/tmp}/claude_card_daemon.log"
if [ -f "$LOG" ]; then
  echo "=== last 8 lines of $LOG ==="
  tail -8 "$LOG"
fi
