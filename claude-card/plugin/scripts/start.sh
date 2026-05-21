#!/usr/bin/env bash
# Start the card daemon in the background. Prefer USB serial when available;
# fall back to BLE. Uses PlatformIO's bundled pyserial via PYTHONPATH so we
# don't require a separate pip install.
set -euo pipefail

PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DAEMON="$PROJ_ROOT/daemon/card_daemon.py"

if pgrep -f "card_daemon.py" >/dev/null 2>&1; then
  echo "card daemon already running (pid $(pgrep -f card_daemon.py))"
  exit 0
fi

# PlatformIO's libexec carries pyserial + bleak, so we don't have to install.
export PYTHONPATH="/opt/homebrew/Cellar/platformio/6.1.19_1/libexec/lib/python3.14/site-packages:${PYTHONPATH:-}"

LOGFILE="${TMPDIR:-/tmp}/claude_card_daemon.log"
nohup python3 "$DAEMON" --transport auto > "$LOGFILE" 2>&1 &
PID=$!
disown
sleep 0.6
if kill -0 "$PID" 2>/dev/null; then
  echo "card daemon started pid=$PID, log=$LOGFILE"
else
  echo "daemon failed to start. last log:"; tail -20 "$LOGFILE" >&2
  exit 1
fi
