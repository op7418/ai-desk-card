#!/usr/bin/env python3
"""claude-card daemon — HTTP API + USB/BLE bridge to the M5Paper card firmware.

Forked + slimmed from ../tools/claude_code_bridge.py. Differences:
  - No Claude Code hook handlers; this daemon is display-only
  - No buddy/dashboard heartbeat (firmware doesn't show one)
  - widget副屏 is the only thing on the device

API:
    POST /widget        push or replace one widget
    DELETE /widget?slot=...   clear a slot (no slot = all)
    GET  /widget        snapshot of cached widgets
    POST /widgets/preview     Pillow-rendered 540x960 PNG for desktop
    GET  /pair-status   { connected, transport }
    POST /unpair        forward unpair cmd to device

Usage:
    python3 card_daemon.py                 # auto: serial first
    python3 card_daemon.py --transport ble
    python3 card_daemon.py --transport serial --port /dev/cu.usbserial-XXX
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import glob
import json
import os
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# v0.6 server-side rendering. Device receives 540×960 4bpp pixel frames
# rather than widget_set JSON. We bump baud accordingly. Push debounce on
# top of M5EPD's ~500ms refresh time means we don't hammer the panel.
SERIAL_BAUD = 115200   # v0.6 first cut — see main.cpp note about baud bump issues
FRAME_W, FRAME_H = 540, 960
FRAME_BYTES = FRAME_W * FRAME_H // 2   # 259,200
PUSH_DEBOUNCE_S = 1.5

NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID      = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID      = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

WIDGET_LOCK = threading.Lock()
WIDGET_CACHE: dict = {}
_WIDGET_CACHE_PATH = os.path.join(
    os.environ.get("TMPDIR", "/tmp"), "claude_card_widget_cache.json")


def _persist_widget_cache():
    """Survive daemon restarts (esp. USB↔BLE transport switches). Cache file
    sits alongside the last-frame PNG."""
    try:
        with open(_WIDGET_CACHE_PATH, "w") as f:
            json.dump(WIDGET_CACHE, f)
    except Exception as e:
        log(f"[cache] persist fail: {e!r}")


def _load_widget_cache():
    global WIDGET_CACHE
    if not os.path.exists(_WIDGET_CACHE_PATH): return
    try:
        with open(_WIDGET_CACHE_PATH) as f:
            WIDGET_CACHE = json.load(f) or {}
        log(f"[cache] loaded {len(WIDGET_CACHE)} widgets from disk")
    except Exception as e:
        log(f"[cache] load fail: {e!r}")

# v0.6.3 — settings page is a full-screen alternate view. Daemon flips
# IN_SETTINGS when the bottom-bar settings chip is tapped (touch dispatch
# arrives in v0.6.4). Render path branches on this flag.
VIEW_LOCK = threading.Lock()
IN_SETTINGS = False
VIEW_HOT_ZONES: list = []          # populated after settings render; firmware uses for tap routing
DEVICE_TELEMETRY: dict = {}        # firmware-reported state (battery, fw, mac, uptime) — fills on /status_report
WIDGET_SLOTS = ("top-left", "top-right", "middle", "bottom", "full")
WIDGET_TYPES = ("weather", "todo", "calendar", "messages",
                "ai-status", "ai-tasks",
                "scratch", "focus", "now-playing", "git-status", "system",
                # v0.6.2 — monitor-side glance widgets
                "inbox", "next-meeting", "pr-queue",
                "break-reminder", "deadlines")
TRANSPORT = None


def log(*a, **kw): print(*a, file=sys.stderr, flush=True, **kw)


# ---- Transports ----

class Transport:
    def start(self, on_byte, on_connect=None): raise NotImplementedError
    def write(self, data: bytes): raise NotImplementedError
    def connected(self) -> bool: raise NotImplementedError


class SerialTransport(Transport):
    def __init__(self, port):
        import serial
        self.ser = serial.Serial(port, SERIAL_BAUD, timeout=0.2)
        self._lock = threading.Lock()
        time.sleep(0.2)
        log(f"[serial] opened {port} @ {SERIAL_BAUD} baud")

    def start(self, on_byte, on_connect=None):
        if on_connect: on_connect()
        threading.Thread(target=self._reader, args=(on_byte,), daemon=True).start()

    def _reader(self, on_byte):
        while True:
            try: chunk = self.ser.read(256)
            except Exception as e:
                log(f"[serial] read fail: {e}"); time.sleep(1); continue
            for b in chunk: on_byte(b)

    def write(self, data: bytes):
        with self._lock:
            try: self.ser.write(data)
            except Exception as e: log(f"[serial] write fail: {e}")

    def connected(self): return True


class WiFiTransport(Transport):
    """v0.8 Wi-Fi transport: HTTP POST to the device's on-board server.
    Frames go to POST /frame (raw 4bpp body + ?x=&y=&w=&h= for region);
    commands go to POST /cmd (JSON body). Stateless — every push opens a
    new connection. LAN throughput beats USB by orders of magnitude
    (~250 KB frame in well under a second)."""

    def __init__(self, ip: str, port: int = 9880):
        self.ip = ip
        self.port = port
        self._connect_ok = True

    def start(self, on_byte, on_connect=None):
        # HTTP has no persistent connection to "start". Run the handshake
        # callback once so the daemon's _handshake fires and any pending
        # WIDGET_CACHE gets pushed.
        if on_connect:
            threading.Thread(target=on_connect, daemon=True).start()

    def write(self, data: bytes):
        # Line-based protocol → JSON command. Route to /cmd over HTTP.
        try:
            line = data.decode("utf-8").strip()
            if not line.startswith("{"): return
            obj = json.loads(line)
        except Exception as e:
            log(f"[wifi] write non-JSON: {e!r}"); return
        if "cmd" not in obj: return        # status / time lines etc. skip
        try:
            import urllib.request
            req = urllib.request.Request(
                f"http://{self.ip}:{self.port}/cmd",
                data=json.dumps(obj).encode(),
                method="POST",
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=4) as r:
                _ = r.read()
            self._connect_ok = True
        except Exception as e:
            log(f"[wifi] cmd {obj.get('cmd')!r}: {e!r}")
            self._connect_ok = False

    def push_frame_http(self, packed: bytes,
                        region: "tuple | None") -> bool:
        import urllib.request
        url = f"http://{self.ip}:{self.port}/frame"
        if region is not None:
            x, y, w, h = region
            url += f"?x={x}&y={y}&w={w}&h={h}"
        try:
            req = urllib.request.Request(
                url, data=packed, method="POST",
                headers={"Content-Type": "application/octet-stream"})
            with urllib.request.urlopen(req, timeout=15) as r:
                ok = (r.status == 200)
            self._connect_ok = ok
            return ok
        except Exception as e:
            log(f"[wifi] frame: {e!r}")
            self._connect_ok = False
            return False

    def connected(self) -> bool:
        # Cheap reachability check — used by /pair-status. We avoid hitting
        # the device every poll; only re-probe if the last operation
        # flagged a failure.
        return self._connect_ok


class BLETransport(Transport):
    # When BLE is the active transport, slow the inter-line cadence so the
    # ESP32 BLE stack has time to deliver each write to the GATT callback
    # before the next one arrives. Empirically 100 ms is enough on M5Paper.
    _NEEDS_INTER_LINE_DELAY = True

    def __init__(self, name_prefix="Card-"):
        self._name_prefix = name_prefix
        self._loop = None; self._client = None
        self._on_byte = None; self._on_connect = None
        self._connected_evt = threading.Event()

    def start(self, on_byte, on_connect=None):
        self._on_byte = on_byte; self._on_connect = on_connect
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._main())
        except Exception as e: log(f"[ble] thread crashed: {e!r}")

    async def _main(self):
        try:
            from bleak import BleakScanner, BleakClient
        except ImportError:
            log("[ble] bleak not installed. pip install bleak"); return
        # Match either ad.local_name (live, from the actual ADV packet) OR
        # d.name (macOS cached). Critical: on Macs that previously paired
        # with the buddy firmware, d.name will be stale ("Claude-XXXX")
        # even after we flash claude-card; the live local_name field has
        # the correct "Card-XXXX". Prefer the live name.
        prefix = self._name_prefix
        def matcher(d, ad):
            for candidate in (ad.local_name, d.name):
                if candidate and candidate.startswith(prefix):
                    return True
            return False

        while True:
            log(f"[ble] scanning for '{prefix}*' (ad.local_name | d.name)...")
            device = None
            try:
                device = await BleakScanner.find_device_by_filter(
                    matcher, timeout=10.0)
            except Exception as e: log(f"[ble] scan: {e}")
            if not device:
                await asyncio.sleep(5); continue
            log(f"[ble] connecting to {device.name} ({device.address})")
            try:
                async with BleakClient(device) as client:
                    self._client = client
                    def _on_notify(_s, data: bytearray):
                        for b in data: self._on_byte(b)
                    await client.start_notify(NUS_TX_UUID, _on_notify)
                    self._connected_evt.set()
                    log("[ble] connected")
                    if self._on_connect:
                        threading.Thread(target=self._on_connect, daemon=True).start()
                    while client.is_connected: await asyncio.sleep(1.0)
                    log("[ble] link lost")
            except Exception as e: log(f"[ble] client: {e!r}")
            finally:
                self._client = None; self._connected_evt.clear()
            await asyncio.sleep(2)

    # CoreBluetooth on macOS does NOT auto-fragment writeWithoutResponse
    # writes larger than the negotiated MTU — they silently get dropped.
    # The line-based frame_chunk JSON is ~2.7 KB per line, so we manually
    # slice into sub-MTU byte payloads. Device's LineBuf reassembles by
    # accumulating until '\n', so as long as we don't insert newlines in
    # the middle the parser still sees one line.
    #
    # v0.7: dropped 182 → 100. ATT_MTU is 185, but encrypted-bonded links
    # add a 4-byte MIC; a payload near MTU may trigger "Long Write" on
    # macOS' side, which becomes an ESP_GATTS_WRITE_EVT with is_prep=true
    # on the firmware. Bluedroid's BLECharacteristic defers onWrite for
    # prepared writes until ESP_GATTS_EXEC_WRITE_EVT — and macOS appears
    # not to send Execute Write in some encrypted-write paths, so the
    # callback never fires. Smaller payloads stay below the long-write
    # threshold and stay is_prep=false.
    _BLE_MTU = 100

    def write(self, data: bytes):
        client = self._client
        if client is None or not client.is_connected: return
        try:
            chunks = [data[i:i + self._BLE_MTU]
                      for i in range(0, len(data), self._BLE_MTU)]
            for c in chunks:
                # response=True (Write With Response) — acknowledged, slow
                # but reliable. response=False on CoreBluetooth silently
                # drops once the OS TX buffer fills (no backpressure signal
                # via bleak), so a big frame_chunk line vanishes mid-transfer.
                fut = asyncio.run_coroutine_threadsafe(
                    client.write_gatt_char(NUS_RX_UUID, c, response=True),
                    self._loop)
                fut.result(timeout=5)
        except Exception as e: log(f"[ble] write: {e!r}")

    def connected(self): return self._connected_evt.is_set()


# ---- Line-based RX parser. Logs every incoming line; also fans out to
#      any listener registered via add_rx_listener (used by /firmware-probe
#      to capture acks within a short window).

_rx_buf = bytearray()
_RX_LISTENERS: list = []          # callables: (str) -> None
_RX_LISTENERS_LOCK = threading.Lock()


def add_rx_listener(fn):
    with _RX_LISTENERS_LOCK: _RX_LISTENERS.append(fn)


def remove_rx_listener(fn):
    with _RX_LISTENERS_LOCK:
        try: _RX_LISTENERS.remove(fn)
        except ValueError: pass


def _telemetry_listener(line: str):
    """Permanent listener: firmware v0.6.4+ emits a status_report JSON line
    every ~60s (and on boot, and in response to cmd:ping). Parse and store
    into DEVICE_TELEMETRY so the bottom bar (battery) and settings page
    (firmware / mac / uptime) have live data."""
    try:
        obj = json.loads(line.strip())
    except Exception:
        return
    if not isinstance(obj, dict) or obj.get("ack") != "status":
        return
    # Map firmware field names → DEVICE_TELEMETRY keys.
    mapping = {
        "fw":              "firmware",
        "mac":             "mac",
        "battery_pct":     "battery_pct",
        "battery_mv":      "battery_mv",
        "on_usb":          "on_usb",
        "wifi_connected":  "wifi_connected",
        "wifi_ssid":       "wifi_ssid",
        "wifi_ip":         "wifi_ip",
        "wifi_rssi":       "wifi_rssi",
    }
    for src, dst in mapping.items():
        if src in obj:
            DEVICE_TELEMETRY[dst] = obj[src]
    if "uptime_s" in obj:
        try:
            s = int(obj["uptime_s"])
            h, m = s // 3600, (s % 3600) // 60
            DEVICE_TELEMETRY["uptime"] = f"{h}h {m}m" if h else f"{m}m"
            # If uptime dropped vs last seen, device rebooted — our cached
            # last-frame image is now invalid (device's framebuffer is the
            # boot splash). Force the next push to be a full frame.
            prev = DEVICE_TELEMETRY.get("_uptime_s_raw", 0)
            if s < prev - 5:
                log(f"[diff] device reboot detected (uptime {prev}s → {s}s) "
                    f"— resetting frame diff cache")
                reset_frame_diff()
            DEVICE_TELEMETRY["_uptime_s_raw"] = s
        except (TypeError, ValueError):
            pass


def on_rx_byte(b: int):
    global _rx_buf
    if b in (0x0A, 0x0D):
        if _rx_buf:
            raw = bytes(_rx_buf); _rx_buf = bytearray()
            try: line = raw.decode("utf-8", errors="replace")
            except Exception: return
            log(f"[dev<] {line}")
            with _RX_LISTENERS_LOCK: listeners = list(_RX_LISTENERS)
            for fn in listeners:
                try: fn(line)
                except Exception as e: log(f"[rx] listener err: {e!r}")
    else:
        if len(_rx_buf) < 4096: _rx_buf.append(b)


SEND_LINE_INTER_DELAY_S = 0.0   # bumped to e.g. 0.1 for BLE if needed


def send_line(obj: dict):
    if TRANSPORT is None: return
    data = (json.dumps(obj, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    TRANSPORT.write(data)
    if SEND_LINE_INTER_DELAY_S > 0:
        time.sleep(SEND_LINE_INTER_DELAY_S)


# ---- Widget cache + outbound frame ----

def _widget_snapshot() -> list:
    now = time.time()
    out = []
    with WIDGET_LOCK:
        for slot, w in list(WIDGET_CACHE.items()):
            written = w.get("written_at", 0)
            ttl = w.get("ttl") or 0
            if ttl > 0 and (now - written) > ttl:
                WIDGET_CACHE.pop(slot, None); continue
            out.append({
                "slot": slot,
                "type": w.get("type"),
                "data": w.get("data") or {},
                "theme": w.get("theme") or "",
                "stale": (w.get("stale_after", 0) > 0
                          and (now - written) > w["stale_after"]),
                "age": int(now - written),
            })
    return out


def send_widget_frame():
    # Legacy widget_set JSON path. v0.6 firmware still parses this into its
    # cache (no-op), but rendering happens via push_frame() instead. Kept
    # so older firmware revisions still work as a fallback.
    send_line({"cmd": "widget_set", "version": 1, "widgets": _widget_snapshot()})


# v0.6 frame push pipeline ----

_FRAME_ID = 0
_FRAME_LAST_PUSH = 0.0   # epoch of last completed push (for bar's "Xs ago")
_FRAME_LOCK = threading.Lock()
_FRAME_DIRTY = threading.Event()

def _crc32(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


# v0.8 architecture C — BLE→Wi-Fi burst.
# Battery-mode device keeps the Wi-Fi radio off until we ask. When a frame
# arrives over BLE, we ask via cmd:wifi_wake_now, wait for the device to
# advertise its IP back in an ack:status, push the frame as a single HTTP
# POST, then linger ~30 s before sending wifi_power_down. Back-to-back
# pushes within the linger window skip the wake step entirely.
_BURST_LOCK         = threading.Lock()
_BURST_LAST_PUSH    = 0.0
_BURST_LINGER_S     = 30.0
_BURST_WAKE_TIMEOUT = 12.0
_BURST_HTTP_PORT    = 9880


def _verify_wifi_reachable(ip: str) -> bool:
    """Cheap HTTP GET /status to confirm the device's Wi-Fi side is up."""
    try:
        import urllib.request
        req = urllib.request.Request(
            f"http://{ip}:{_BURST_HTTP_PORT}/status", method="GET")
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _wake_wifi_via_ble() -> "tuple|None":
    """Send cmd:wifi_wake_now via the active BLE transport and wait for
    the device to report wifi_connected=True with an IP. Returns
    (ip, port) on success, None on failure.

    Fast path: if a recent telemetry already shows wifi_connected with an
    IP that responds to /status, skip the wake."""
    if not isinstance(TRANSPORT, BLETransport):
        return None
    ip = DEVICE_TELEMETRY.get("wifi_ip") or ""
    if DEVICE_TELEMETRY.get("wifi_connected") and ip and _verify_wifi_reachable(ip):
        log(f"[burst] wifi already up at {ip} — skip wake")
        return (ip, _BURST_HTTP_PORT)

    log("[burst] sending cmd:wifi_wake_now via BLE")
    evt = threading.Event()
    captured = {}

    def _watch(line: str):
        try: obj = json.loads(line.strip())
        except Exception: return
        if not isinstance(obj, dict): return
        if obj.get("ack") == "status" and obj.get("wifi_connected") \
                and obj.get("wifi_ip"):
            captured["ip"] = obj["wifi_ip"]
            evt.set()

    add_rx_listener(_watch)
    try:
        send_line({"cmd": "wifi_wake_now"})
        evt.wait(timeout=_BURST_WAKE_TIMEOUT)
    finally:
        remove_rx_listener(_watch)

    new_ip = captured.get("ip")
    if not new_ip:
        log(f"[burst] wifi_wake_now did not produce a wifi_ip in "
            f"{_BURST_WAKE_TIMEOUT}s — falling back to BLE chunked path")
        return None
    log(f"[burst] device Wi-Fi up at {new_ip}")
    return (new_ip, _BURST_HTTP_PORT)


def _burst_power_down_loop():
    """Background thread: if last burst push was > LINGER seconds ago,
    tell the device to drop its radio. Saves battery in architecture C."""
    global _BURST_LAST_PUSH
    while True:
        time.sleep(5)
        with _BURST_LOCK:
            last = _BURST_LAST_PUSH
        if last == 0: continue
        if time.time() - last < _BURST_LINGER_S: continue
        if not isinstance(TRANSPORT, BLETransport): continue
        log("[burst] linger expired — sending cmd:wifi_power_down")
        send_line({"cmd": "wifi_power_down"})
        with _BURST_LOCK:
            _BURST_LAST_PUSH = 0


def push_frame_bytes(packed: bytes, region: "tuple|None" = None):
    """Send a packed 4bpp frame via the active transport.

    Full frame: packed = FRAME_BYTES, region = None.
    Region update: packed = w*h/2 bytes, region = (x, y, w, h).

    For Wi-Fi (v0.8) we POST raw bytes in a single HTTP request — orders
    of magnitude faster than the chunked-JSON protocol used by serial/BLE.
    Caller serialises (we hold _FRAME_LOCK)."""
    global _FRAME_ID
    if region is None and len(packed) != FRAME_BYTES:
        log(f"[frame] WARN full size {len(packed)} != {FRAME_BYTES}")
    elif region is not None:
        x, y, w, h = region
        expected = w * h // 2
        if len(packed) != expected:
            log(f"[frame] WARN region size {len(packed)} != {expected} "
                f"({w}x{h})")

    # Wi-Fi short path: skip the chunked-base64 protocol entirely.
    if isinstance(TRANSPORT, WiFiTransport):
        with _FRAME_LOCK:
            _FRAME_ID = (_FRAME_ID + 1) & 0xFFFFFFFF
            fid = _FRAME_ID
            t0 = time.time()
            ok = TRANSPORT.push_frame_http(packed, region)
            dt = time.time() - t0
            kind = "full" if region is None else f"region({region[0]},{region[1]} {region[2]}x{region[3]})"
            log(f"[frame] http push fid={fid} {len(packed)}B {kind} ({dt:.2f}s) "
                f"{'ok' if ok else 'FAIL'}")
        return

    # Architecture C: BLE-primary daemon takes a detour through Wi-Fi for
    # this push. ~5 s wake overhead on a cold start, ~0 if Wi-Fi was just
    # used recently (within the LINGER window).
    if isinstance(TRANSPORT, BLETransport):
        peer = _wake_wifi_via_ble()
        if peer:
            ip, port = peer
            wifi_xport = WiFiTransport(ip, port)
            with _FRAME_LOCK:
                _FRAME_ID = (_FRAME_ID + 1) & 0xFFFFFFFF
                fid = _FRAME_ID
                t0 = time.time()
                ok = wifi_xport.push_frame_http(packed, region)
                dt = time.time() - t0
                kind = "full" if region is None else f"region({region[0]},{region[1]} {region[2]}x{region[3]})"
                log(f"[burst] http push fid={fid} {len(packed)}B {kind} ({dt:.2f}s) "
                    f"{'ok' if ok else 'FAIL'}")
            if ok:
                with _BURST_LOCK:
                    global _BURST_LAST_PUSH
                    _BURST_LAST_PUSH = time.time()
                return
            log("[burst] HTTP push failed — falling back to BLE chunked path")
            # fall through to the chunked-JSON code below

    with _FRAME_LOCK:
        _FRAME_ID = (_FRAME_ID + 1) & 0xFFFFFFFF
        fid = _FRAME_ID
        crc = _crc32(packed)
        # 2 KB raw → 2.7 KB base64 + JSON wrapper ≈ 2.8 KB total per line.
        # Must stay comfortably under firmware's LineBuf<8192> with margin
        # for the JSON wrapper. Earlier 3 KB chunks blew past 4096 buffer
        # and got silently truncated → assembled garbage → CRC fail (or
        # worse, no error at all because the chunk parse just dropped).
        CHUNK = 2048
        chunks = [packed[i:i + CHUNK] for i in range(0, len(packed), CHUNK)]

        t0 = time.time()
        if region is None:
            send_line({"cmd": "frame_begin", "fid": fid, "w": FRAME_W,
                       "h": FRAME_H, "bpp": 4,
                       "chunks": len(chunks), "crc": crc})
        else:
            x, y, w, h = region
            send_line({"cmd": "frame_region_begin", "fid": fid,
                       "x": x, "y": y, "w": w, "h": h, "bpp": 4,
                       "chunks": len(chunks), "crc": crc})
        for seq, chunk in enumerate(chunks):
            send_line({"cmd": "frame_chunk", "fid": fid, "seq": seq,
                       "data": base64.b64encode(chunk).decode()})
        send_line({"cmd": "frame_end", "fid": fid})
        dt = time.time() - t0
        kind = "full" if region is None else f"region({region[0]},{region[1]} {region[2]}x{region[3]})"
        log(f"[frame] pushed fid={fid} {len(packed)}B {kind} in {len(chunks)} chunks ({dt:.2f}s)")


def render_and_push_sleep():
    """Render the sleep-frame name card and push it. Caller is expected to
    follow up with send_line({cmd:sleep_now}) so the device enters deep
    sleep with the last frame on the panel."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import card_render_sleep
        import importlib
        importlib.reload(card_render_sleep)
        # card_render_sleep imports card_render internally — reload that too
        # so any divider / font edits propagate without daemon restart.
        import card_render
        importlib.reload(card_render)
    except Exception as e:
        log(f"[sleep] import fail: {e!r}")
        return False
    try:
        profile = card_render_sleep.load_profile()
        img = card_render_sleep.render_sleep_frame(profile)
        packed = card_render.to_4bpp_packed(img)
    except Exception as e:
        log(f"[sleep] render failed: {e!r}")
        return False
    log(f"[sleep] rendering name card for '{profile.get('name', '?')}'")
    push_frame_bytes(packed)
    return True


def _bar_status() -> dict:
    """Build the bottom-bar status payload at render time."""
    age = None
    if _FRAME_LAST_PUSH > 0:
        age = int(time.time() - _FRAME_LAST_PUSH)
    return {
        "transport":  type(TRANSPORT).__name__.replace("Transport", "").upper()
                       if TRANSPORT else None,
        "ble_paired": False,   # firmware doesn't report this yet (v0.6.4 TODO)
        "battery_pct": DEVICE_TELEMETRY.get("battery_pct"),
        "time":       datetime.now().strftime("%H:%M"),
        "frame_age":  age,
    }


def _settings_state() -> dict:
    """Build the state blob passed to render_settings_page. Mostly mirrors
    DEVICE_TELEMETRY (firmware-reported via /status_report) plus daemon-
    visible facts (transport, baud, daemon_ok)."""
    transport_name = (type(TRANSPORT).__name__.replace("Transport", "").upper()
                      if TRANSPORT else "—")
    state = dict(DEVICE_TELEMETRY)   # battery, firmware, mac, uptime, battery_mv ...
    state.setdefault("model", "M5Paper V1.1")
    state["transport"] = transport_name
    state["baud"]      = str(SERIAL_BAUD) if isinstance(TRANSPORT, SerialTransport) else ""
    state["daemon_ok"] = TRANSPORT is not None and TRANSPORT.connected()
    state["ble_paired"] = False
    # Pass through firmware's wifi_* fields if available (v0.8).
    # Renderer reads wifi_connected / wifi_ssid / wifi_ip / wifi_rssi.
    return state


# v0.7 dirty-region diff: remember the last frame we pushed so the next
# push can compute a bounding box of changed pixels and ship only that.
# Skips entirely if nothing changed. Full-frame fallback when the diff
# covers more than DIFF_FULL_THRESHOLD of the canvas.
_LAST_FRAME_IMG = None
_LAST_FRAME_PATH = os.path.join(
    os.environ.get("TMPDIR", "/tmp"), "claude_card_last_frame.png")
DIFF_FULL_THRESHOLD = 0.50    # diff area > 50% of canvas → just push full
DIFF_REGION_ALIGN   = 4       # x/w aligned to multiple of 4 for safe 4bpp packing


def _persist_last_frame(img):
    """Save the last successfully-pushed frame to disk so the diff cache
    survives daemon restart. Critical for the USB → BLE switch flow: we
    want the first push after restart to be a region (not a full 260 KB
    frame BLE struggles with)."""
    try:
        img.save(_LAST_FRAME_PATH, format="PNG")
    except Exception as e:
        log(f"[diff] persist fail: {e!r}")


def _load_persisted_frame():
    global _LAST_FRAME_IMG
    if not os.path.exists(_LAST_FRAME_PATH): return
    try:
        from PIL import Image
        img = Image.open(_LAST_FRAME_PATH).convert("L")
        if img.size == (FRAME_W, FRAME_H):
            _LAST_FRAME_IMG = img
            log(f"[diff] loaded persisted frame ({_LAST_FRAME_PATH})")
        else:
            log(f"[diff] persisted frame wrong size {img.size}; ignoring")
    except Exception as e:
        log(f"[diff] load fail: {e!r}")


def _compute_diff(new_img):
    """Returns (kind, packed_bytes, region_tuple_or_None).
    kind: 'full' / 'region' / 'noop'.
    region_tuple: (x, y, w, h) when kind=='region'."""
    global _LAST_FRAME_IMG
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import card_render
        from PIL import ImageChops
    except ImportError as e:
        log(f"[diff] PIL missing: {e!r} — full-frame only")
        return "full", card_render.to_4bpp_packed(new_img), None

    if _LAST_FRAME_IMG is None:
        # First push — must be full so device's framebuffer aligns.
        _LAST_FRAME_IMG = new_img.copy()
        _persist_last_frame(_LAST_FRAME_IMG)
        return "full", card_render.to_4bpp_packed(new_img), None

    diff_img = ImageChops.difference(_LAST_FRAME_IMG, new_img)
    bbox = diff_img.getbbox()
    if bbox is None:
        return "noop", b"", None

    x0, y0, x1, y1 = bbox
    log(f"[diff] raw bbox: ({x0},{y0})-({x1},{y1}) = {x1-x0}x{y1-y0}")
    # Align x and w to multiple of 4 (safe for any 4bpp panel driver
    # alignment requirement; expands diff slightly but keeps the pack
    # path simple).
    A = DIFF_REGION_ALIGN
    x0 = (x0 // A) * A
    x1 = ((x1 + A - 1) // A) * A
    x1 = min(x1, FRAME_W)
    w  = x1 - x0
    h  = y1 - y0

    diff_area = w * h
    full_area = FRAME_W * FRAME_H
    if diff_area > full_area * DIFF_FULL_THRESHOLD:
        log(f"[diff] {diff_area} of {full_area} ({diff_area*100//full_area}%) "
            f"→ full")
        _LAST_FRAME_IMG = new_img.copy()
        _persist_last_frame(_LAST_FRAME_IMG)
        return "full", card_render.to_4bpp_packed(new_img), None

    crop = new_img.crop((x0, y0, x1, y1))
    packed = card_render.to_4bpp_packed(crop)
    _LAST_FRAME_IMG = new_img.copy()
    _persist_last_frame(_LAST_FRAME_IMG)
    log(f"[diff] region ({x0},{y0} {w}x{h}) = {len(packed)}B "
        f"vs full {FRAME_BYTES}B ({len(packed)*100//FRAME_BYTES}%)")
    return "region", packed, (x0, y0, w, h)


def reset_frame_diff():
    """Force the next render_and_push() to send a full frame. Called when
    we lose sync with the device (firmware restart, daemon restart, etc.)."""
    global _LAST_FRAME_IMG
    _LAST_FRAME_IMG = None
    try: os.unlink(_LAST_FRAME_PATH)
    except OSError: pass


def render_and_push():
    """Build current widget snapshot, render with PIL, pack 4bpp, push.
    importlib.reload(card_render) on every call so edits to the renderer
    take effect without restarting the daemon. Dispatches to the settings
    page renderer when IN_SETTINGS is set. Uses dirty-region diff so the
    typical "one widget changed" path only ships the changed rectangle."""
    global _FRAME_LAST_PUSH, VIEW_HOT_ZONES
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import card_render
        import importlib
        importlib.reload(card_render)
    except Exception as e:
        log(f"[render] import fail: {e!r}")
        return
    try:
        if IN_SETTINGS:
            import card_render_settings
            importlib.reload(card_render_settings)
            img = card_render_settings.render_settings_page(_settings_state())
            VIEW_HOT_ZONES = card_render_settings.get_hot_zones()
        else:
            img = card_render.render_image(_widget_snapshot(),
                                           status=_bar_status())
            VIEW_HOT_ZONES = []
    except Exception as e:
        log(f"[render] failed: {e!r}")
        return

    kind, packed, region = _compute_diff(img)
    if kind == "noop":
        log("[render] no pixel change — skipping push")
        return
    push_frame_bytes(packed, region=region)
    _FRAME_LAST_PUSH = time.time()


def schedule_push():
    """Debounce trigger. Sets a dirty flag; the push_loop thread coalesces
    rapid POSTs into a single render+push after PUSH_DEBOUNCE_S of quiet."""
    _FRAME_DIRTY.set()


def push_loop():
    """Background coalescing thread. Wakes on dirty flag, waits for the
    debounce window, then renders + pushes once. Multiple POSTs inside the
    debounce window collapse to one push."""
    while True:
        _FRAME_DIRTY.wait()
        # Wait for quiet: as long as dirty keeps getting set, restart timer.
        while True:
            time.sleep(PUSH_DEBOUNCE_S)
            if _FRAME_DIRTY.is_set():
                # Reset so we can detect new dirties during render.
                _FRAME_DIRTY.clear()
                # If anyone set it again during the sleep, the next wait
                # below sees it immediately.
                break
        if not (TRANSPORT and TRANSPORT.connected()):
            log("[frame] no transport — skipping push (will retry on next dirty)")
            continue
        render_and_push()


def widget_validate(payload: dict) -> tuple:
    t = payload.get("type")
    if t not in WIDGET_TYPES:
        return False, f"type must be one of {WIDGET_TYPES}, got {t!r}"
    s = payload.get("slot")
    if s not in WIDGET_SLOTS:
        return False, f"slot must be one of {WIDGET_SLOTS}, got {s!r}"
    if not isinstance(payload.get("data"), dict):
        return False, "data must be an object"
    return True, ""


# ---- HTTP server ----

class CardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def _reply(self, code: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try: self.wfile.write(body)
        except BrokenPipeError: pass

    def _handle_sleep_post(self, payload: dict):
        """Render name card → push → tell device to deep-sleep."""
        if not (TRANSPORT and TRANSPORT.connected()):
            return self._reply(503, {"error": "device not connected"})
        ok = render_and_push_sleep()
        if not ok:
            return self._reply(500, {"error": "render or push failed"})
        # Tell device to enter deep sleep. Optional "wake_after_sec" in the
        # payload (currently unused on firmware side; reserved for v0.7+).
        wake_after = int(payload.get("wake_after_sec") or 0)
        send_line({"cmd": "sleep_now", "wake_after_sec": wake_after})
        log(f"[sleep] sleep_now sent (wake_after_sec={wake_after})")
        return self._reply(200, {"ok": True, "wake_after_sec": wake_after,
                                  "note": "device will enter deep sleep; "
                                          "e-ink retains last frame"})

    def _reply_png(self, code: int, png: bytes):
        self.send_response(code)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(png)))
        self.end_headers()
        try: self.wfile.write(png)
        except BrokenPipeError: pass

    def do_GET(self):
        path = (self.path or "/").split("?", 1)[0]
        if path == "/widget":
            return self._reply(200, {"widgets": _widget_snapshot()})
        if path == "/pair-status":
            return self._reply(200, {
                "connected": TRANSPORT is not None and TRANSPORT.connected(),
                "transport": type(TRANSPORT).__name__ if TRANSPORT else None,
            })
        if path == "/version":
            return self._reply(200, {"daemon": "claude-card/0.5"})
        return self._reply(404, {"error": f"unknown GET {path!r}"})

    def do_DELETE(self):
        path = (self.path or "/").split("?", 1)[0]
        if path == "/widget":
            qs = parse_qs(urlparse(self.path).query)
            slot = (qs.get("slot") or [None])[0]
            with WIDGET_LOCK:
                if slot: WIDGET_CACHE.pop(slot, None)
                else:    WIDGET_CACHE.clear()
            _persist_widget_cache()
            schedule_push()
            return self._reply(200, {"ok": True, "cleared": slot or "all"})
        return self._reply(404, {"error": f"unknown DELETE {path!r}"})

    def do_POST(self):
        global IN_SETTINGS
        path = (self.path or "/").split("?", 1)[0]
        try:
            n = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(n) if n > 0 else b""
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception as e:
            return self._reply(400, {"error": str(e)})

        if path == "/widget":
            ok, err = widget_validate(payload)
            if not ok: return self._reply(400, {"error": err})
            slot = payload["slot"]
            entry = {
                "type":  payload["type"],
                "data":  payload["data"],
                "theme": payload.get("theme") or "",
                "ttl":   int(payload.get("ttl") or 0),
                "stale_after": int(payload.get("stale_after") or 0),
                "written_at": time.time(),
            }
            with WIDGET_LOCK:
                WIDGET_CACHE[slot] = entry
            _persist_widget_cache()
            log(f"[widget] {slot} ← {entry['type']}")
            # v0.6: schedule a debounced render+push instead of sending
            # widget_set JSON. The push thread coalesces bursts.
            schedule_push()
            return self._reply(200, {"ok": True, "slot": slot,
                                     "type": entry["type"],
                                     "push_scheduled": TRANSPORT is not None and TRANSPORT.connected()})

        if path == "/widgets/preview":
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from card_render import render_preview_png
            except ImportError as e:
                return self._reply(500, {"error": f"Pillow missing: {e}"})
            try:
                png = render_preview_png(_widget_snapshot(),
                                          status=_bar_status())
            except Exception as e:
                return self._reply(500, {"error": f"render failed: {e!r}"})
            return self._reply_png(200, png)

        if path == "/unpair":
            send_line({"cmd": "unpair"})
            return self._reply(200, {"ok": True})

        if path == "/sleep":
            # Render the name-card sleep frame from assets/profile.yaml,
            # push it as a regular frame_chunk frame, then send cmd:sleep_now
            # so the firmware enters deep_sleep (e-ink retains the last
            # frame at 0 W).
            return self._handle_sleep_post(payload)

        if path == "/refresh":
            # Force a re-render + re-push of current widget cache. Bound
            # to the bottom-bar "refresh" chip in v0.6.4.
            schedule_push()
            return self._reply(200, {"ok": True, "note": "push scheduled"})

        if path == "/restart":
            # Tell device to esp_restart. Bottom-bar "restart" chip target.
            send_line({"cmd": "restart"})
            return self._reply(200, {"ok": True,
                                     "note": "device restart command sent"})

        if path == "/settings":
            # Bottom-bar "settings" chip → enter settings page.
            with VIEW_LOCK: IN_SETTINGS = True
            schedule_push()
            return self._reply(200, {"ok": True, "in_settings": True})

        if path == "/back":
            # Settings-page "back" chip → return to widget view.
            with VIEW_LOCK: IN_SETTINGS = False
            schedule_push()
            return self._reply(200, {"ok": True, "in_settings": False})

        if path == "/status_report":
            # Firmware v0.6.4 reports {battery_pct, battery_mv, firmware,
            # mac, uptime_s} every ~60s. We store the latest in
            # DEVICE_TELEMETRY for the settings page + bottom bar.
            try:
                if "battery_pct" in payload: DEVICE_TELEMETRY["battery_pct"] = int(payload["battery_pct"])
                if "battery_mv"  in payload: DEVICE_TELEMETRY["battery_mv"]  = int(payload["battery_mv"])
                if "firmware"    in payload: DEVICE_TELEMETRY["firmware"]    = str(payload["firmware"])[:32]
                if "mac"         in payload: DEVICE_TELEMETRY["mac"]         = str(payload["mac"])[:32]
                if "uptime_s"    in payload:
                    s = int(payload["uptime_s"])
                    h, m = s // 3600, (s % 3600) // 60
                    DEVICE_TELEMETRY["uptime"] = f"{h}h {m}m" if h else f"{m}m"
            except (TypeError, ValueError) as e:
                return self._reply(400, {"error": f"bad telemetry: {e}"})
            return self._reply(200, {"ok": True})

        if path == "/firmware-probe":
            # Used by /card-onboard to decide between:
            #   - "我们的固件 OK"              (ack:owner heard)
            #   - "端口开但不是我们的固件"     (transport ok, no ack)
            #   - "transport 都没起来"          (TRANSPORT is None / not connected)
            if not TRANSPORT:
                return self._reply(200, {"connected": False,
                                          "our_firmware": False,
                                          "note": "no transport"})
            if not TRANSPORT.connected():
                return self._reply(200, {"connected": False,
                                          "our_firmware": False,
                                          "note": "transport not connected"})
            heard: dict = {}
            evt = threading.Event()

            def _capture(line: str):
                # Firmware acks for cmd:owner look like:
                #     {"ack":"owner","ok":true}
                # Future v0.6.4 status_report will add fw/mac fields. Capture
                # the first ack-shaped line we see.
                try:
                    obj = json.loads(line.strip())
                except Exception:
                    return
                if isinstance(obj, dict) and "ack" in obj:
                    heard.update(obj); evt.set()

            add_rx_listener(_capture)
            try:
                # v0.6.4+ firmware replies to cmd:ping with a rich status
                # (fw + mac + battery + uptime). Older firmware ignores
                # cmd:ping but acks cmd:owner. Send both; the listener
                # captures whichever fires first.
                send_line({"cmd": "ping"})
                send_line({"cmd": "owner",
                           "name": os.environ.get("USER", "")})
                evt.wait(timeout=2.5)
            finally:
                remove_rx_listener(_capture)

            if heard:
                return self._reply(200, {
                    "connected":    True,
                    "our_firmware": True,
                    "ack":          heard,
                    "firmware":     DEVICE_TELEMETRY.get("firmware"),
                    "mac":          DEVICE_TELEMETRY.get("mac"),
                    "battery_pct":  DEVICE_TELEMETRY.get("battery_pct"),
                })
            return self._reply(200, {
                "connected":    True,
                "our_firmware": False,
                "note":         "port open, no ack within 2.5s — wrong firmware?",
            })

        if path == "/provision-wifi":
            # v0.8: forward Wi-Fi credentials to firmware via whatever
            # transport is up (serial / BLE / Wi-Fi itself works too).
            ssid = (payload.get("ssid") or "").strip()
            pwd  = payload.get("password", "")
            if not ssid:
                return self._reply(400, {"error": "ssid required (use \"\" to forget)"})
            send_line({"cmd": "wifi_set", "ssid": ssid, "password": pwd})
            return self._reply(200, {"ok": True,
                                     "note": "credentials sent to device; "
                                             "watch ack:status for wifi_connected"})

        if path == "/touch":
            # Firmware v0.6.4: device sends {x, y} from touch panel; daemon
            # maps to a hot-zone action against the last rendered view.
            try:
                x, y = int(payload["x"]), int(payload["y"])
            except (KeyError, TypeError, ValueError):
                return self._reply(400, {"error": "x,y required"})
            action = None
            for hz in VIEW_HOT_ZONES:
                x0, y0, x1, y1 = hz["rect"]
                if x0 <= x <= x1 and y0 <= y <= y1:
                    action = hz["action"]; break
            if action is None:
                return self._reply(200, {"ok": True, "action": None})
            log(f"[touch] ({x},{y}) → {action}")
            # Dispatch internally — equivalent of hitting the endpoint
            # by hand. Keeps logic in one place.
            if action == "back":     return self._reply(200, _internal_dispatch("back"))
            if action == "settings": return self._reply(200, _internal_dispatch("settings"))
            if action == "refresh":  schedule_push(); return self._reply(200, {"action": "refresh"})
            if action == "sleep":    return self._reply(200, _internal_dispatch("sleep"))
            if action == "restart":  send_line({"cmd": "restart"}); return self._reply(200, {"action": "restart"})
            if action == "repair":   send_line({"cmd": "unpair"});  return self._reply(200, {"action": "repair"})
            if action == "clear":
                with WIDGET_LOCK: WIDGET_CACHE.clear()
                schedule_push(); return self._reply(200, {"action": "clear"})
            return self._reply(200, {"ok": True, "action": action})

        return self._reply(404, {"error": f"unknown POST {path!r}"})


def _internal_dispatch(action: str) -> dict:
    """Helper for /touch — runs the side-effects of a chip action without
    re-entering the HTTP layer."""
    global IN_SETTINGS
    if action == "settings":
        with VIEW_LOCK: IN_SETTINGS = True
        schedule_push(); return {"action": "settings"}
    if action == "back":
        with VIEW_LOCK: IN_SETTINGS = False
        schedule_push(); return {"action": "back"}
    if action == "sleep":
        if render_and_push_sleep():
            send_line({"cmd": "sleep_now", "wake_after_sec": 0})
        return {"action": "sleep"}
    return {"action": action}


# ---- Periodic re-push (for widget freshness while idle) ----

def keepalive_loop():
    """Re-push the current frame every 5 minutes as a safety net (in case
    the device dropped a chunk + CRC failed). Cheap: render is fast, the
    transfer is the slow part. Skipped when transport isn't connected.

    Note: v0.6 push_loop already handles debounced pushes; keepalive only
    kicks in when nothing else has changed the cache for 5 minutes."""
    while True:
        time.sleep(300)
        if WIDGET_CACHE and TRANSPORT and TRANSPORT.connected():
            schedule_push()


def tz_offset_seconds() -> int:
    now = time.time()
    local = datetime.fromtimestamp(now)
    utc_dt = datetime(*datetime.fromtimestamp(now, tz=None).utctimetuple()[:6])
    return int((local - utc_dt).total_seconds())


def discover_wifi_device(timeout_s: float = 3.0) -> "tuple|None":
    """Return (ip, port) of a claude-card peer on the LAN via mDNS, or None."""
    try:
        from zeroconf import Zeroconf, ServiceBrowser
    except ImportError:
        log("[mdns] zeroconf not installed; skipping Wi-Fi discovery")
        return None
    found = []

    class _Listener:
        def add_service(self, zc, t, name):
            info = zc.get_service_info(t, name, timeout=1500)
            if not info or not info.addresses: return
            ip = ".".join(str(b) for b in info.addresses[0])
            found.append((ip, info.port))
        def update_service(self, zc, t, name): pass
        def remove_service(self, zc, t, name): pass

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, "_claude-card._tcp.local.", _Listener())
        deadline = time.time() + timeout_s
        while time.time() < deadline and not found:
            time.sleep(0.2)
    finally:
        try: zc.close()
        except Exception: pass
    return found[0] if found else None


def pick_transport(kind: str, port: str | None) -> Transport:
    if port:
        return SerialTransport(port)
    candidates = sorted(glob.glob("/dev/cu.usbserial-*") + glob.glob("/dev/ttyUSB*"))
    if kind == "serial":
        if not candidates: sys.exit("no /dev/cu.usbserial-* device found")
        return SerialTransport(candidates[0])
    if kind == "ble":
        return BLETransport()
    if kind == "wifi":
        peer = discover_wifi_device(timeout_s=5.0)
        if not peer: sys.exit("no _claude-card._tcp peer found on LAN")
        ip, p = peer
        log(f"[transport] using Wi-Fi {ip}:{p}")
        return WiFiTransport(ip, p)
    # kind == "auto": prefer Wi-Fi > USB > BLE
    peer = discover_wifi_device(timeout_s=2.5)
    if peer:
        ip, p = peer
        log(f"[transport] found Wi-Fi peer {ip}:{p}, using Wi-Fi")
        return WiFiTransport(ip, p)
    if candidates:
        log("[transport] no Wi-Fi peer; found serial device, using USB")
        return SerialTransport(candidates[0])
    log("[transport] no Wi-Fi, no serial; falling back to BLE")
    return BLETransport()


def main():
    global TRANSPORT
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--transport", choices=("auto", "serial", "ble", "wifi"),
                    default="auto")
    ap.add_argument("--http-port", type=int, default=9877)
    ap.add_argument("--owner", default=os.environ.get("USER", ""))
    args = ap.parse_args()

    TRANSPORT = pick_transport(args.transport, args.port)
    if getattr(TRANSPORT, "_NEEDS_INTER_LINE_DELAY", False):
        global SEND_LINE_INTER_DELAY_S
        SEND_LINE_INTER_DELAY_S = 0.1
        log(f"[transport] inter-line delay: {SEND_LINE_INTER_DELAY_S*1000:.0f}ms")

    def _handshake():
        if args.owner:
            send_line({"cmd": "owner", "name": args.owner})
        send_line({"time": [int(time.time()), tz_offset_seconds()]})
        if WIDGET_CACHE:
            schedule_push()

    _load_widget_cache()
    _load_persisted_frame()
    add_rx_listener(_telemetry_listener)
    TRANSPORT.start(on_rx_byte, on_connect=_handshake)
    threading.Thread(target=keepalive_loop, daemon=True).start()
    threading.Thread(target=push_loop, daemon=True).start()
    if isinstance(TRANSPORT, BLETransport):
        # Architecture C: only relevant when BLE is the long-lived
        # transport. USB and Wi-Fi don't have anything to power down.
        threading.Thread(target=_burst_power_down_loop, daemon=True).start()

    srv = ThreadingHTTPServer(("127.0.0.1", args.http_port), CardHandler)
    log(f"[http] listening on 127.0.0.1:{args.http_port}")
    log(f"[ready] claude-card daemon v0.5 — push widgets via POST /widget")
    try: srv.serve_forever()
    except KeyboardInterrupt: log("\n[exit] bye")


if __name__ == "__main__":
    main()
