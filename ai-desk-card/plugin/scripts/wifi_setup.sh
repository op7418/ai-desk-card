#!/usr/bin/env bash
# /card-wifi-setup wrapper. POSTs ssid+password to daemon's /provision-wifi
# which forwards as cmd:wifi_set to firmware over whichever transport is
# currently up (serial / BLE / Wi-Fi itself).
#
# Usage:
#   wifi_setup.sh <SSID> <password>
#   wifi_setup.sh ""                  # forget credentials
#
# After provisioning, polls /firmware-probe for up to 20 s and reports
# wifi_connected + wifi_ip.

set -uo pipefail

DAEMON_URL="${CARD_DAEMON_URL:-http://127.0.0.1:9877}"

# --- arg parse ---
SSID=""
PASS=""

if [[ $# -eq 1 && -z "${1//[^[:space:]]/}" ]]; then
  SSID=""; PASS=""
elif [[ $# -eq 1 ]]; then
  # called as a single combined string (typical via slash command)
  eval "set -- $1"
  SSID="${1:-}"
  PASS="${2:-}"
elif [[ $# -ge 2 ]]; then
  SSID="$1"
  PASS="$2"
else
  cat <<EOF
usage: /card-wifi-setup <SSID> [password]
       /card-wifi-setup ""              # forget credentials
EOF
  exit 1
fi

if ! curl -sf -m 2 "$DAEMON_URL/pair-status" >/dev/null 2>&1; then
  cat >&2 <<EOF
✗ daemon unreachable at $DAEMON_URL
  → run /card-start first; then re-try
EOF
  exit 2
fi

echo "→ provisioning Wi-Fi: ssid='$SSID' pass_len=${#PASS}"
PROVISION_RESP=$(python3 - "$SSID" "$PASS" <<'PY' 2>&1
import json, sys, urllib.request, os
ssid, pwd = sys.argv[1], sys.argv[2]
url = os.environ.get("CARD_DAEMON_URL", "http://127.0.0.1:9877") + "/provision-wifi"
body = json.dumps({"ssid": ssid, "password": pwd}).encode()
req  = urllib.request.Request(url, data=body, method="POST",
                              headers={"Content-Type": "application/json"})
try:
  with urllib.request.urlopen(req, timeout=4) as r:
    print(r.read().decode())
except Exception as e:
  print(json.dumps({"error": repr(e)})); sys.exit(3)
PY
)
echo "  daemon: $PROVISION_RESP"

if [[ -z "$SSID" ]]; then
  echo "→ credentials cleared on device."
  exit 0
fi

echo "→ waiting up to 20s for device to join '$SSID'..."
WIFI_OK=false
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 2
  PROBE_OUT=$(curl -sf -m 3 -X POST "$DAEMON_URL/firmware-probe" 2>/dev/null || echo '{}')
  WIFI_CONNECTED=$(echo "$PROBE_OUT" | python3 -c '
import sys, json
try:
  d = json.load(sys.stdin)
  ack = d.get("ack") or {}
  print("true" if ack.get("wifi_connected") else "false")
except Exception: print("false")')
  WIFI_IP=$(echo "$PROBE_OUT" | python3 -c '
import sys, json
try:
  d = json.load(sys.stdin)
  ack = d.get("ack") or {}
  print(ack.get("wifi_ip") or "")
except Exception: print("")')
  if [[ "$WIFI_CONNECTED" == "true" && -n "$WIFI_IP" ]]; then
    WIFI_OK=true
    echo "✓ device on Wi-Fi: $WIFI_IP"
    break
  fi
  echo "  ${i}/10 ..."
done

if [[ "$WIFI_OK" != "true" ]]; then
  cat >&2 <<EOF
✗ device did not report wifi_connected within 20s.
  Diagnostics:
    tail -30 "\${TMPDIR:-/tmp}/ai_desk_card_daemon.log"
  Common causes:
    • SSID typo (case-sensitive — Wi-Fi names are exact)
    • Network is 5GHz only (ESP32 only supports 2.4GHz)
    • Wrong password
    • Router is in WPA3-only mode (set to WPA2/WPA3 mixed)
EOF
  exit 4
fi

cat <<EOF

next steps:
  1. /card-stop && /card-start         (daemon picks up Wi-Fi via mDNS)
  2. push widgets — should land in ~0.2s now
EOF
