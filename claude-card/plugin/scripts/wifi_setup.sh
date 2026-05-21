#!/usr/bin/env bash
# /card-wifi-setup wrapper. Parses "<ssid> <password>" and POSTs to daemon's
# /provision-wifi endpoint. SSID with spaces should be quoted.
set -euo pipefail

DAEMON_URL="${CARD_DAEMON_URL:-http://127.0.0.1:9877}"
ARGS="${1:-}"

if [[ -z "$ARGS" ]]; then
  cat <<EOF
usage: /card-wifi-setup <SSID> [password]
       /card-wifi-setup ""              # forget credentials
EOF
  exit 1
fi

# crude parse: split on first space — supports quoted SSID via the shell's
# argv handling
eval "set -- $ARGS"
SSID="${1:-}"
PASS="${2:-}"

if [[ -z "$SSID" && "${ARGS:0:2}" != '""' ]]; then
  echo "missing SSID" >&2; exit 1
fi

# Reject obvious mistakes early.
if [[ -n "$PASS" && "${#PASS}" -lt 8 ]]; then
  echo "warning: WPA2 password should be ≥8 chars (you sent ${#PASS})" >&2
fi

curl -sf -X POST "$DAEMON_URL/provision-wifi" \
     -H 'Content-Type: application/json' \
     -d "$(python3 -c "import json,sys; print(json.dumps({'ssid':'''$SSID''','password':'''$PASS'''}))")" \
  | python3 -m json.tool
