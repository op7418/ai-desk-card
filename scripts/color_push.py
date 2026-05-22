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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True, help="Device IP (e.g. 192.168.31.162)")
    ap.add_argument("--port", type=int, default=9880)
    ap.add_argument("--test", choices=["stripes"], help="Test pattern to push")
    ap.add_argument("--image", help="Path to PNG/JPG to push (auto-resized to 600x400)")
    args = ap.parse_args()

    if args.test == "stripes":
        img = test_stripes_image()
    elif args.image:
        from PIL import Image
        img = Image.open(args.image).convert("RGB")
        if img.size != (PANEL_W, PANEL_H):
            img = img.resize((PANEL_W, PANEL_H))
    else:
        sys.exit("--test or --image required")

    post_frame(args.ip, img, args.port)


if __name__ == "__main__":
    main()
