#!/usr/bin/env python3
"""Push a PIL image to the M5Paper Color device over Wi-Fi.

Quick-and-dirty Color-port equivalent of the V1.1 daemon's WiFiTransport.
Converts an RGB image to RGB565 LE bytes and POSTs to the device's
/frame endpoint. M5GFX on the device quantizes to the Spectra 6 palette
during canvas.pushSprite().

Usage:
    python3 scripts/color_push.py --ip 192.168.31.162 --test stripes
    python3 scripts/color_push.py --ip 192.168.31.162 --image path.png
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.request

PANEL_W, PANEL_H = 600, 400


def rgb_to_565_bytes(img) -> bytes:
    """Pillow Image (mode 'RGB') → RGB565 LE bytes, length = w*h*2."""
    try:
        from PIL import Image
    except ImportError:
        sys.exit("pip install pillow")
    if img.mode != "RGB":
        img = img.convert("RGB")
    pixels = img.tobytes()    # w*h*3 RGB888
    # Vectorize via numpy if available, else slow pure-Python.
    try:
        import numpy as np
        arr = np.frombuffer(pixels, dtype="uint8").reshape(-1, 3)
        r = (arr[:, 0] >> 3).astype("uint16")
        g = (arr[:, 1] >> 2).astype("uint16")
        b = (arr[:, 2] >> 3).astype("uint16")
        rgb565 = (r << 11) | (g << 5) | b
        return rgb565.astype("<u2").tobytes()
    except ImportError:
        out = bytearray(len(pixels) // 3 * 2)
        for i in range(0, len(pixels), 3):
            R, G, B = pixels[i], pixels[i + 1], pixels[i + 2]
            v = ((R >> 3) << 11) | ((G >> 2) << 5) | (B >> 3)
            out[(i // 3) * 2]     = v & 0xFF
            out[(i // 3) * 2 + 1] = (v >> 8) & 0xFF
        return bytes(out)


def test_stripes_image():
    """6 vertical bars matching the Spectra 6 palette so we can eyeball
    color fidelity."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (PANEL_W, PANEL_H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    # Spectra 6 anchors (approx). M5GFX should snap to its palette.
    colors = [
        ("WHITE",  (255, 255, 255)),
        ("BLACK",  (0, 0, 0)),
        ("RED",    (220, 30, 30)),
        ("YELLOW", (240, 220, 30)),
        ("GREEN",  (40, 160, 80)),
        ("BLUE",   (40, 80, 200)),
    ]
    bar_w = PANEL_W // len(colors)
    for i, (name, rgb) in enumerate(colors):
        x0 = i * bar_w
        x1 = (i + 1) * bar_w if i < len(colors) - 1 else PANEL_W
        d.rectangle([x0, 50, x1, PANEL_H - 50], fill=rgb)
        # Black or white label depending on bg brightness
        lum = sum(rgb) / 3
        label_color = (0, 0, 0) if lum > 128 else (255, 255, 255)
        try:
            f = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 18)
        except Exception:
            f = ImageFont.load_default()
        d.text((x0 + 8, 60), name, fill=label_color, font=f)
    # Header + footer
    try:
        f_big = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 24)
    except Exception:
        f_big = ImageFont.load_default()
    d.text((20, 10),  "AI Desk Card · Color test pattern",
           fill=(0, 0, 0), font=f_big)
    d.text((20, PANEL_H - 35), "Spectra 6 palette · RGB565 over Wi-Fi",
           fill=(0, 0, 0), font=f_big)
    return img


def post_frame(ip: str, img, port: int = 9880,
               x: int = 0, y: int = 0) -> dict:
    w, h = img.size
    body = rgb_to_565_bytes(img)
    url = f"http://{ip}:{port}/frame?x={x}&y={y}&w={w}&h={h}"
    print(f"[host] POST {url}  ({len(body)} bytes RGB565)")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/octet-stream"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = r.read().decode()
    print(f"[host] {r.status} in {time.time()-t0:.2f}s — {resp}")
    print(f"[host] panel will refresh ~15-19 s (Spectra 6 full refresh)")
    return {"status": r.status, "resp": resp}


def _load_renderer():
    return _load_renderer_module("card_render_color")


def _load_renderer_module(name: str):
    import importlib.util, sys as _sys
    here = os.path.dirname(os.path.abspath(__file__))
    daemon_dir = os.path.join(here, "..", "daemon")
    if daemon_dir not in _sys.path:
        _sys.path.insert(0, daemon_dir)
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(daemon_dir, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fetch_device_status(ip: str, port: int = 9880) -> dict:
    """GET the device's /status to pull SHT40 ambient + battery for the
    bottom bar + ambient widget."""
    try:
        with urllib.request.urlopen(f"http://{ip}:{port}/status", timeout=3) as r:
            import json
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"[warn] /status fetch failed: {e!r}")
        return {}


def demo_widgets_image(device_status=None):
    """4-widget schedule demo using the Color renderer."""
    crc = _load_renderer()

    widgets = [
        {"slot": "top-left", "type": "weather", "data": {
            "location": "北京",
            "current":  {"temp_c": 23, "condition": "晴"},
            "forecast": [
                {"day": "明天", "high": 25, "low": 14, "condition": "晴"},
                {"day": "后天", "high": 21, "low": 12, "condition": "多云"},
            ],
        }},
        {"slot": "top-right", "type": "next-meeting", "data": {
            "title": "v0.10 color review",
            "start_in": "in 18m",
            "start_at": "20:00",
            "attendees": "Cindy · Mark · Liang",
            "location": "Zoom",
        }},
        {"slot": "bottom-left", "type": "focus", "data": {
            "task": "整 ai-desk-card · paper-color port",
            "big_text": "07:24",
            "subtitle": "started 19:18 · 25 min planned",
            "pomodoros_done": 2,
            "pomodoros_planned": 4,
        }},
        {"slot": "bottom-right", "type": "todo", "data": {
            "title": "今天",
            "items": [
                {"text": "Paper Color phase 3 完成", "tag": "today"},
                {"text": "录制双设备 demo 视频", "tag": "today"},
                {"text": "v0.10 release notes", "tag": "tomorrow"},
            ],
        }},
    ]
    status = {"battery_pct": 95, "wifi": "Xiaomi_1303", "time": time.strftime("%H:%M")}
    if device_status:
        bp = device_status.get("battery_pct")
        if bp is not None: status["battery_pct"] = bp
        ssid = (device_status.get("wifi") or {}).get("ssid")
        if ssid: status["wifi"] = ssid
    return crc.render_image(widgets, status=status)


def ambient_dashboard_image(device_status):
    """Phase 4 demo: ALL widgets sourced from the Color device itself
    (SHT40 ambient) + a few work staples. Shows the new color widgets:
    ambient, ai-status, pr-queue, break-reminder."""
    crc = _load_renderer()

    amb = device_status.get("ambient") or {}
    widgets = [
        {"slot": "top-left", "type": "ambient", "data": {
            "temp_c":   amb.get("temp_c", 0),
            "humid_pct": amb.get("humid_pct", 0),
            "age_s":    amb.get("age_s", 0),
        }},
        {"slot": "top-right", "type": "ai-status", "data": {
            "session_name": "paper-color",
            "model": "Opus 4.7",
            "task": "Phase 4 sensors + widgets",
            "context": {"used": 158000, "limit": 200000},
        }},
        {"slot": "bottom-left", "type": "pr-queue", "data": {
            "review_count": 3,
            "your_open_count": 2,
            "items": [
                {"number": "#128", "title": "Add captive portal", "status": "review"},
                {"number": "#127", "title": "Plan C power-off hook", "status": "yours"},
            ],
        }},
        {"slot": "bottom-right", "type": "break-reminder", "data": {
            "last_break_min_ago": 48,
            "sitting_min": 95,
            "next_eye_rest_min": -3,
            "advice": "起身走走 · 远眺 20 秒",
        }},
    ]
    bp = device_status.get("battery_pct") or 100
    ssid = (device_status.get("wifi") or {}).get("ssid") or ""
    status = {"battery_pct": bp, "wifi": ssid, "time": time.strftime("%H:%M")}
    return crc.render_image(widgets, status=status)


def main():
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True, help="Device IP (e.g. 192.168.31.162)")
    ap.add_argument("--port", type=int, default=9880)
    ap.add_argument("--test", choices=["stripes", "demo", "ambient"],
                    help="Built-in pattern: stripes (color test), demo (4 schedule widgets), ambient (SHT40 + AI status + PRs + break)")
    ap.add_argument("--view", choices=["settings", "sleep"],
                    help="Special view: settings (device status page), sleep (business card + deep sleep)")
    ap.add_argument("--image", help="Path to PNG/JPG to push (auto-resized to 600×400)")
    ap.add_argument("--save", help="Save the rendered image locally before pushing")
    ap.add_argument("--beep", choices=["chime", "urgent", "alert"],
                    help="Also POST /beep with this pattern (sound notification)")
    args = ap.parse_args()

    device_status = _fetch_device_status(args.ip, args.port)
    sleep_after = False
    if args.view == "settings":
        crsc = _load_renderer_module("card_render_settings_color")
        img = crsc.render_settings(device_status)
    elif args.view == "sleep":
        crsc = _load_renderer_module("card_render_sleep_color")
        img = crsc.render_sleep()
        sleep_after = True
    elif args.test == "stripes":
        img = test_stripes_image()
    elif args.test == "demo":
        img = demo_widgets_image(device_status)
    elif args.test == "ambient":
        if not device_status.get("ambient"):
            sys.exit("device has no ambient (SHT40) data — is it the Color device?")
        img = ambient_dashboard_image(device_status)
    elif args.image:
        from PIL import Image
        img = Image.open(args.image).convert("RGB")
        if img.size != (PANEL_W, PANEL_H):
            img = img.resize((PANEL_W, PANEL_H))
    else:
        sys.exit("--test {stripes,demo} or --image required")

    if args.save:
        img.save(args.save)
        print(f"[host] saved render to {args.save}")

    post_frame(args.ip, img, args.port)

    if sleep_after:
        # Give the panel ~2 s to finish settling before the device's own
        # sleep_now path takes over (which adds its own 2.5 s settle).
        time.sleep(2)
        import json as _json
        body = _json.dumps({"cmd": "sleep_now"}).encode()
        req = urllib.request.Request(
            f"http://{args.ip}:{args.port}/cmd",
            data=body, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=4) as r:
                print(f"[sleep] cmd:sleep_now → {r.status}")
        except Exception as e:
            print(f"[sleep] error: {e!r}")

    if args.beep:
        import json as _json
        body = _json.dumps({"pattern": args.beep}).encode()
        req = urllib.request.Request(
            f"http://{args.ip}:{args.port}/beep",
            data=body, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=4) as r:
                print(f"[beep] {args.beep} → {r.status}")
        except Exception as e:
            print(f"[beep] error: {e!r}")


if __name__ == "__main__":
    main()
