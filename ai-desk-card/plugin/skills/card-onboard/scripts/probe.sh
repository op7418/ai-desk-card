#!/usr/bin/env bash
# ai-desk-card 入职检测一把梭。
# 输出结构化 JSON，AI 读了就能决策下一步。
#
# 检测项：
#   1. daemon 是否在跑、端口能不能 ping 通
#   2. transport 是否连接（USB serial / BLE）
#   3. /firmware-probe → 我们的固件 vs 别的
#   4. 串口设备清单（用于 USB 未连接时定位问题）
#   5. （可选）通过 install_firmware.py --detect 拿固件版本横幅
#
# 用法：
#   bash probe.sh            # 全量探测
#   bash probe.sh --quick    # 跳过 install_firmware.py（避免抢端口）

set -u

DAEMON_URL="${CARD_DAEMON_URL:-http://127.0.0.1:9877}"
QUICK=0
[[ "${1:-}" == "--quick" ]] && QUICK=1

# 1. daemon
DAEMON_PID="$(pgrep -f card_daemon.py | head -1)"
if [[ -n "${DAEMON_PID}" ]]; then
  DAEMON_RUNNING=true
else
  DAEMON_RUNNING=false
fi

# 2. pair-status
PAIR_RAW="$(curl -sf -m 2 "$DAEMON_URL/pair-status" 2>/dev/null || echo '{}')"
CONNECTED=$(echo "$PAIR_RAW" | python3 -c 'import sys,json
try:
  d=json.load(sys.stdin)
  print("true" if d.get("connected") else "false")
except Exception: print("false")')
TRANSPORT_TYPE=$(echo "$PAIR_RAW" | python3 -c 'import sys,json
try:
  d=json.load(sys.stdin); print(d.get("transport") or "")
except Exception: print("")')

# 3. firmware probe (only if daemon alive)
OUR_FIRMWARE=false
PROBE_NOTE=""
if [[ "$DAEMON_RUNNING" == "true" && "$CONNECTED" == "true" ]]; then
  PROBE_RAW="$(curl -sf -m 4 -X POST "$DAEMON_URL/firmware-probe" 2>/dev/null || echo '{}')"
  OUR_FIRMWARE=$(echo "$PROBE_RAW" | python3 -c 'import sys,json
try:
  d=json.load(sys.stdin); print("true" if d.get("our_firmware") else "false")
except Exception: print("false")')
  PROBE_NOTE=$(echo "$PROBE_RAW" | python3 -c 'import sys,json
try:
  d=json.load(sys.stdin); print(d.get("note") or "")
except Exception: print("")')
fi

# 4. 串口设备
PORTS=$(ls /dev/cu.usbserial-* /dev/cu.SLAB_USBtoUART /dev/ttyUSB* 2>/dev/null | python3 -c '
import sys, json
print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))')
[[ -z "$PORTS" ]] && PORTS="[]"

# 4b. v0.8 — Wi-Fi 状态：直接问 daemon 的 _settings_state（最权威）
#     and mDNS 上看到的 peer（用于"daemon 还没起但设备已经在播"的场景）
WIFI_INFO="null"
if [[ "$DAEMON_RUNNING" == "true" && "$CONNECTED" == "true" ]]; then
  PROBE_RAW="${PROBE_RAW:-{}}"
  WIFI_INFO=$(echo "$PROBE_RAW" | python3 -c '
import sys, json
try:
  d = json.load(sys.stdin)
  out = {"reported_via_telemetry": True}
  # firmware-probe 的 ack 不带 wifi 字段，但 daemon DEVICE_TELEMETRY 可能有
  # 我们额外 GET /pair-status — 没有也无所谓，下面 mDNS 再补
  print(json.dumps(out))
except Exception:
  print("null")')
fi

# mDNS 扫一遍 _ai-desk-card._tcp — 即使 daemon 没起也能看到设备
MDNS_PEER="null"
PIO_PY=/opt/homebrew/Cellar/platformio/6.1.19_1/libexec/bin/python3
if [[ -x "$PIO_PY" ]]; then
  MDNS_PEER=$(PYTHONPATH="/opt/homebrew/Cellar/platformio/6.1.19_1/libexec/lib/python3.14/site-packages:${PYTHONPATH:-}" \
              "$PIO_PY" - 2>/dev/null <<'PY'
import json, time
try:
  from zeroconf import Zeroconf, ServiceBrowser
except ImportError:
  print("null"); raise SystemExit
found = []
class L:
  def add_service(self, zc, t, name):
    info = zc.get_service_info(t, name, timeout=1200)
    if info and info.addresses:
      ip = ".".join(str(b) for b in info.addresses[0])
      txt = {k.decode(): v.decode() if isinstance(v, bytes) else v
             for k, v in (info.properties or {}).items() if k}
      found.append({"ip": ip, "port": info.port, "txt": txt})
  def update_service(self, zc, t, name): pass
  def remove_service(self, zc, t, name): pass
zc = Zeroconf()
try:
  ServiceBrowser(zc, "_ai-desk-card._tcp.local.", L())
  t0 = time.time()
  while time.time() - t0 < 2.5 and not found:
    time.sleep(0.2)
finally:
  zc.close()
print(json.dumps(found[0] if found else None))
PY
)
  [[ -z "$MDNS_PEER" ]] && MDNS_PEER="null"
fi

# 5. install_firmware --detect (跳过模式下不调)
FW_BANNER="null"
if [[ "$QUICK" -eq 0 && "$DAEMON_RUNNING" != "true" ]]; then
  # 只在 daemon 没跑的时候才尝试 detect（避免抢端口）
  PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
  export PYTHONPATH="/opt/homebrew/Cellar/platformio/6.1.19_1/libexec/lib/python3.14/site-packages:${PYTHONPATH:-}"
  DETECT="$(python3 "$PROJ_ROOT/plugin/skills/card-widget/scripts/install_firmware.py" --detect 2>/dev/null || true)"
  if [[ -n "$DETECT" ]]; then
    FW_BANNER=$(python3 -c "import json,sys; print(json.dumps(sys.stdin.read().strip()))" <<< "$DETECT")
  fi
fi

# 输出
export DAEMON_RUNNING CONNECTED OUR_FIRMWARE TRANSPORT_TYPE PROBE_NOTE PORTS FW_BANNER DAEMON_PID MDNS_PEER
python3 - <<'PY'
import json, os
def b(x): return x.lower() == "true"
print(json.dumps({
    "daemon":     {"running": b(os.environ["DAEMON_RUNNING"]),
                   "pid": int(os.environ.get("DAEMON_PID") or 0) or None},
    "transport":  {"connected": b(os.environ["CONNECTED"]),
                   "type": os.environ.get("TRANSPORT_TYPE") or None},
    "firmware":   {"our": b(os.environ["OUR_FIRMWARE"]),
                   "note": os.environ.get("PROBE_NOTE") or "",
                   "banner": json.loads(os.environ["FW_BANNER"])
                             if os.environ["FW_BANNER"] != "null" else None},
    "serial_ports": json.loads(os.environ["PORTS"]),
    "mdns_peer":   json.loads(os.environ["MDNS_PEER"])
                   if os.environ["MDNS_PEER"] not in ("null", "") else None,
}, indent=2, ensure_ascii=False))
PY
