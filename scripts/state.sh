#!/usr/bin/env bash
# ai-desk-card Skill — full-state probe.
#
# Wraps plugin/skills/card-onboard/scripts/probe.sh and adds three fields
# the Skill's router needs:
#   hardware.pio_installed   — is PlatformIO on PATH?
#   firmware.flashed         — derived: serial port present + ack heard
#   wifi.provisioned         — derived: mDNS peer found OR daemon reports IP
#   interests.configured     — ~/.ai-desk-card/interests.yaml exists
#
# Output is a single JSON blob written to stdout. The Skill reads it and
# routes to the right sub-flow.
#
# Usage:
#   bash scripts/state.sh           # full probe
#   bash scripts/state.sh --quick   # skip firmware-detect (faster, no port grab)

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROBE="$REPO_ROOT/plugin/skills/card-onboard/scripts/probe.sh"
INTERESTS="${HOME}/.ai-desk-card/interests.yaml"
DAEMON_URL="${CARD_DAEMON_URL:-http://127.0.0.1:9877}"

# 1. Run the inner probe
if [[ ! -x "$PROBE" && ! -f "$PROBE" ]]; then
  echo "{\"error\": \"probe.sh not found at $PROBE\"}"
  exit 1
fi
INNER_JSON="$(bash "$PROBE" "${1:-}" 2>/dev/null)"
if [[ -z "$INNER_JSON" ]]; then
  echo "{\"error\": \"probe.sh produced no output\"}"
  exit 1
fi

# 2. PlatformIO
if command -v pio >/dev/null 2>&1 || command -v platformio >/dev/null 2>&1; then
  PIO_INSTALLED=true
else
  PIO_INSTALLED=false
fi

# 3. Interests config
if [[ -f "$INTERESTS" ]]; then
  INTERESTS_CONFIGURED=true
else
  INTERESTS_CONFIGURED=false
fi

# 4. Live device heartbeat — distinguishes "we lost the transport at
#    startup so everything's false" from "transport's there but device
#    isn't reporting back". Daemon's /heartbeat aggregates the answer.
HEARTBEAT_JSON="$(curl -sf -m 2 "$DAEMON_URL/heartbeat" 2>/dev/null || echo '{}')"

# 5. Merge: emit unified shape
export INNER_JSON PIO_INSTALLED INTERESTS_CONFIGURED INTERESTS HEARTBEAT_JSON
python3 - <<'PY'
import json, os
inner = json.loads(os.environ["INNER_JSON"])
pio   = os.environ["PIO_INSTALLED"] == "true"
icfg  = os.environ["INTERESTS_CONFIGURED"] == "true"
ipath = os.environ["INTERESTS"]
try:
    hb = json.loads(os.environ["HEARTBEAT_JSON"])
    if not isinstance(hb, dict): hb = {}
except Exception:
    hb = {}

ports = inner.get("serial_ports") or []
fw    = inner.get("firmware") or {}
mdns  = inner.get("mdns_peer")

# flashed: any of these confirms the device has our firmware on it,
# even if it's currently asleep (heartbeat.alive=false but daemon
# remembers the last-seen firmware version + uptime).
#   1. heartbeat reports firmware version (DEVICE_TELEMETRY persists
#      across device sleep cycles within one daemon run)
#   2. live ack (firmware-probe sees us)
#   3. heartbeat says alive right now
#   4. mDNS sees the device advertising
# Banner alone isn't enough — install_firmware --detect can yield
# "unknown" even when no device is present.
flashed = (bool(hb.get("firmware"))
           or bool(fw.get("our"))
           or bool(hb.get("alive"))
           or bool(mdns))

state = {
  "hardware": {
    "pio_installed": pio,
    "m5paper_usb":   ports[0] if ports else None,
    "all_ports":     ports,
  },
  "firmware": {
    "flashed":  flashed,
    "ours":     bool(fw.get("our")) or bool(hb.get("firmware")),
    "version":  hb.get("firmware") or ((mdns or {}).get("txt") or {}).get("fw"),
    "note":     fw.get("note") or "",
  },
  "daemon":    inner.get("daemon"),
  "transport": inner.get("transport"),
  "device": {
    # Heartbeat is the single source of truth for "is the device alive
    # RIGHT NOW". Distinguishes "transport offline because daemon hasn't
    # connected yet" from "transport offline because device is asleep".
    "alive":             bool(hb.get("alive")),
    "last_seen_seconds": hb.get("last_seen_seconds"),
    "active_transport":  hb.get("active_transport"),
    "battery_pct":       hb.get("battery_pct"),
    "uptime":            hb.get("uptime"),
  },
  "profile": {
    "selected":    hb.get("selected_profile"),
    "source":      hb.get("profile_source"),
    "device_name": hb.get("device_name"),
  },
  "wifi": {
    "provisioned": bool(mdns) or bool(hb.get("wifi_ip")),
    "ip":          hb.get("wifi_ip") or (mdns or {}).get("ip"),
    "port":        (mdns or {}).get("port"),
  },
  "interests": {
    "configured": icfg,
    "path":       ipath if icfg else None,
  },
}
print(json.dumps(state, indent=2, ensure_ascii=False))
PY
