#!/usr/bin/env bash
# /card-sleep — render the name-card sleep frame, push it, deep-sleep
# the device. e-ink retains the last frame at 0 W.
set -euo pipefail
DAEMON="${CARD_DAEMON_URL:-http://127.0.0.1:9877}"
WAKE_AFTER="${1:-0}"

if ! curl -sfS "$DAEMON/pair-status" > /dev/null 2>&1; then
  echo "daemon unreachable at $DAEMON — run /card-start first" >&2
  exit 2
fi

echo "Rendering name card from claude-card/assets/profile.yaml..."
echo "(edit that YAML + drop avatar.png / qr.png in assets/ to customise)"
echo

curl -sfS -X POST "$DAEMON/sleep" \
  -H 'Content-Type: application/json' \
  -d "{\"wake_after_sec\": $WAKE_AFTER}"
echo
echo
echo "Device will deep-sleep after the frame is fully transferred (~30 s)."
echo "Power-cycle / unplug-replug USB to wake."
