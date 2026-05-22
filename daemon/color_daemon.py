#!/usr/bin/env python3
"""ai-desk-card · Color daemon.

Persistent HTTP server for the M5Paper Color device. Sits between the
AI Agent (which POSTs /widget to fill the on-screen layout) and the
Color hardware (which posts /button events when the user presses one
of the 3 physical user-buttons + which receives rendered frames via
its /frame endpoint).

This is a thin Color-specific counterpart to V1.1's card_daemon.py.
We don't try to unify both yet — different panels, different transports,
different update cadences (V1.1 ~0.2 s, Color ~17 s).

API (all bound to 127.0.0.1):
  POST /widget         agent → daemon. Body: {slot, type, data, theme?}
                       Same shape as V1.1; we cache + re-render + push.
  GET  /widget         current widget cache snapshot.
  POST /widgets/preview render PNG (no push).
  POST /button         firmware → daemon. Body: {button, action}
                       Actions: refresh / settings / sleep.
  GET  /heartbeat      device-alive + last-seen-seconds
  GET  /status         daemon version + cached device telemetry

Run:
  python3 daemon/color_daemon.py --device-ip 192.168.31.162
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


# ---- Imports for the renderers (deferred to first use to keep startup fast) ----

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _import_renderer(name):
    import importlib
    return importlib.import_module(name)


# ---- Module-level state ------------------------------------------------------

# Slot → {type, data, theme, written_at}
WIDGET_CACHE: dict = {}
WIDGET_LOCK = threading.Lock()

# Cached /status from the device — populated on every refresh, used by
# renderers (ambient widget, status bar) and the /heartbeat endpoint.
DEVICE_STATUS: dict = {}
LAST_SEEN_MS = 0

# Current view on the panel. One of: "widgets", "settings", "sleep".
CURRENT_VIEW = "widgets"
VIEW_LOCK = threading.Lock()

# Whether a push is in progress — coalesces rapid button presses.
PUSH_LOCK = threading.Lock()

# CLI args (set in main()).
DEVICE_IP = ""
DEVICE_PORT = 9880
LISTEN_PORT = 9877

# Color panel dimensions (must match the firmware + renderer).
PANEL_W = 600
PANEL_H = 400


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ---- Device I/O --------------------------------------------------------------

def fetch_status() -> dict:
    """Pull /status from the Color device. Updates DEVICE_STATUS +
    LAST_SEEN_MS. Returns latest dict (empty if unreachable)."""
    global DEVICE_STATUS, LAST_SEEN_MS
    if not DEVICE_IP:
        return {}
    url = f"http://{DEVICE_IP}:{DEVICE_PORT}/status"
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            d = json.loads(r.read().decode())
        DEVICE_STATUS = d
        LAST_SEEN_MS = int(time.time() * 1000)
        return d
    except Exception as e:
        log(f"[status] fetch failed: {e!r}")
        return DEVICE_STATUS


def push_frame_to_device(img) -> bool:
    """Convert PIL RGB image to RGB565 LE bytes and POST /frame. Returns
    True on 200. Blocks for ~17 s (Spectra 6 refresh)."""
    if img.size != (PANEL_W, PANEL_H):
        log(f"[frame] resize {img.size} → {PANEL_W}x{PANEL_H}")
        img = img.resize((PANEL_W, PANEL_H))
    # RGB → RGB565 LE
    try:
        import numpy as np
        arr = np.frombuffer(img.tobytes(), dtype="uint8").reshape(-1, 3)
        r = (arr[:, 0] >> 3).astype("uint16")
        g = (arr[:, 1] >> 2).astype("uint16")
        b = (arr[:, 2] >> 3).astype("uint16")
        body = ((r << 11) | (g << 5) | b).astype("<u2").tobytes()
    except ImportError:
        # Pure-python fallback if numpy missing — slower but works.
        pixels = img.tobytes()
        out = bytearray(len(pixels) // 3 * 2)
        for i in range(0, len(pixels), 3):
            R, G, B = pixels[i], pixels[i + 1], pixels[i + 2]
            v = ((R >> 3) << 11) | ((G >> 2) << 5) | (B >> 3)
            o = (i // 3) * 2
            out[o] = v & 0xFF; out[o + 1] = (v >> 8) & 0xFF
        body = bytes(out)

    url = f"http://{DEVICE_IP}:{DEVICE_PORT}/frame?x=0&y=0&w={PANEL_W}&h={PANEL_H}"
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/octet-stream"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            ok = (r.status == 200)
        log(f"[push] {len(body)} B in {time.time()-t0:.2f}s ({'ok' if ok else 'FAIL'})")
        return ok
    except Exception as e:
        log(f"[push] error: {e!r}")
        return False


def send_cmd_to_device(cmd: str, extra: dict | None = None) -> bool:
    body = {"cmd": cmd}
    if extra: body.update(extra)
    url = f"http://{DEVICE_IP}:{DEVICE_PORT}/cmd"
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            log(f"[cmd] {cmd} → {r.status}")
            return r.status == 200
    except Exception as e:
        log(f"[cmd] {cmd} failed: {e!r}")
        return False


# ---- Render dispatch ---------------------------------------------------------

def _widget_snapshot():
    with WIDGET_LOCK:
        return [{"slot": s, **v} for s, v in WIDGET_CACHE.items()]


def _bar_status(device_status: dict) -> dict:
    return {
        "battery_pct": device_status.get("battery_pct"),
        "wifi": (device_status.get("wifi") or {}).get("ssid") or "",
        "time": datetime.now().strftime("%H:%M"),
    }


def render_current_view() -> "Image.Image | None":
    """Render whatever view CURRENT_VIEW says we should show. Returns a
    PIL Image or None on failure."""
    with VIEW_LOCK:
        view = CURRENT_VIEW
    status = fetch_status()

    if view == "settings":
        crsc = _import_renderer("card_render_settings_color")
        return crsc.render_settings(status)
    if view == "sleep":
        crslc = _import_renderer("card_render_sleep_color")
        return crslc.render_sleep()

    # widgets default. Inject ambient widget if device has SHT40 data.
    crc = _import_renderer("card_render_color")
    snap = _widget_snapshot()
    return crc.render_image(snap, status=_bar_status(status))


def render_and_push(also_sleep_cmd: bool = False):
    """Render the current view + push to device. PUSH_LOCK coalesces
    concurrent calls (rapid button presses become one push)."""
    if not PUSH_LOCK.acquire(blocking=False):
        log("[render] busy — push already in progress, skipping")
        return
    try:
        img = render_current_view()
        if img is None:
            log("[render] no image to push")
            return
        push_frame_to_device(img)
        if also_sleep_cmd:
            # Wait briefly for the device to settle the refresh.
            time.sleep(1)
            send_cmd_to_device("sleep_now")
    finally:
        PUSH_LOCK.release()


# ---- Button dispatch ---------------------------------------------------------

def dispatch_button_action(action: str):
    """Map firmware button action → daemon-side view + side-effects."""
    global CURRENT_VIEW
    if action == "refresh":
        with VIEW_LOCK: CURRENT_VIEW = "widgets"
        threading.Thread(target=render_and_push, daemon=True).start()
    elif action == "settings":
        with VIEW_LOCK: CURRENT_VIEW = "settings"
        threading.Thread(target=render_and_push, daemon=True).start()
    elif action == "sleep":
        with VIEW_LOCK: CURRENT_VIEW = "sleep"
        threading.Thread(target=render_and_push,
                         kwargs={"also_sleep_cmd": True},
                         daemon=True).start()
    else:
        log(f"[button] unknown action: {action}")


# ---- HTTP API ----------------------------------------------------------------

VALID_SLOTS = ("top-left", "top-right", "bottom-left", "bottom-right", "full")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def _reply(self, code: int, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try: self.wfile.write(body)
        except BrokenPipeError: pass

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(n) if n > 0 else b""
        return json.loads(body.decode()) if body else {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/widget":
            return self._reply(200, {"widgets": _widget_snapshot()})
        if path == "/heartbeat":
            now = int(time.time() * 1000)
            age_s = (now - LAST_SEEN_MS) / 1000 if LAST_SEEN_MS else None
            return self._reply(200, {
                "alive": age_s is not None and age_s <= 120,
                "last_seen_seconds": int(age_s) if age_s is not None else None,
                "device_ip": DEVICE_IP,
                "device_status": DEVICE_STATUS,
                "current_view": CURRENT_VIEW,
            })
        if path == "/status":
            return self._reply(200, {
                "daemon": "color-daemon/0.10.0",
                "device_ip": DEVICE_IP,
                "current_view": CURRENT_VIEW,
                "widget_count": len(WIDGET_CACHE),
            })
        return self._reply(404, {"error": f"unknown GET {path}"})

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path == "/widget":
            with WIDGET_LOCK: WIDGET_CACHE.clear()
            log("[widget] cleared all")
            threading.Thread(target=render_and_push, daemon=True).start()
            return self._reply(200, {"ok": True})
        return self._reply(404, {"error": f"unknown DELETE {path}"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
        except Exception as e:
            return self._reply(400, {"error": f"bad json: {e}"})

        if path == "/widget":
            slot = payload.get("slot")
            if slot not in VALID_SLOTS:
                return self._reply(400, {
                    "error": f"slot must be one of {VALID_SLOTS}, got {slot!r}"})
            wtype = payload.get("type")
            data = payload.get("data") or {}
            with WIDGET_LOCK:
                WIDGET_CACHE[slot] = {
                    "type": wtype,
                    "data": data,
                    "theme": payload.get("theme") or "",
                    "written_at": time.time(),
                }
            log(f"[widget] {slot} ← {wtype}")
            # Switch back to widgets view + re-render
            global CURRENT_VIEW
            with VIEW_LOCK: CURRENT_VIEW = "widgets"
            threading.Thread(target=render_and_push, daemon=True).start()
            return self._reply(200, {"ok": True, "slot": slot, "type": wtype})

        if path == "/widgets/preview":
            img = render_current_view()
            if img is None:
                return self._reply(500, {"error": "render failed"})
            import io
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            png = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(png)))
            self.end_headers()
            self.wfile.write(png)
            return

        if path == "/button":
            button = payload.get("button", "")
            action = payload.get("action", "")
            log(f"[button] {button} → {action}")
            dispatch_button_action(action)
            return self._reply(200, {"ok": True, "action": action})

        if path == "/refresh":
            threading.Thread(target=render_and_push, daemon=True).start()
            return self._reply(200, {"ok": True})

        return self._reply(404, {"error": f"unknown POST {path}"})


# ---- Background refresh ------------------------------------------------------

def heartbeat_loop():
    """Poll the device's /status periodically so DEVICE_STATUS stays
    warm even when nothing is being pushed. Cheap GET, no panel impact."""
    while True:
        time.sleep(45)
        if DEVICE_IP:
            fetch_status()


# ---- Entry -------------------------------------------------------------------

def main():
    global DEVICE_IP, DEVICE_PORT, LISTEN_PORT
    ap = argparse.ArgumentParser()
    ap.add_argument("--device-ip", required=True,
                    help="M5Paper Color IP on your LAN (from /provision-wifi)")
    ap.add_argument("--device-port", type=int, default=9880,
                    help="Device's HTTP port (default 9880)")
    ap.add_argument("--listen-port", type=int, default=9877,
                    help="Daemon HTTP port on 127.0.0.1 (default 9877)")
    args = ap.parse_args()

    DEVICE_IP = args.device_ip
    DEVICE_PORT = args.device_port
    LISTEN_PORT = args.listen_port

    log(f"[boot] color-daemon v0.10.0 — device {DEVICE_IP}:{DEVICE_PORT}")
    fetch_status()  # warm

    threading.Thread(target=heartbeat_loop, daemon=True).start()

    srv = ThreadingHTTPServer(("127.0.0.1", LISTEN_PORT), Handler)
    log(f"[http] listening on 127.0.0.1:{LISTEN_PORT}")
    log("[ready] POST /widget to push, the device's buttons will dispatch back")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("[exit] bye")


if __name__ == "__main__":
    main()
