"""Settings/diagnostics page for M5Paper Color (600×400, Spectra 6).

Counterpart to V1.1's card_render_settings.py. Shows device state pulled
from GET /status: firmware version, panel size, battery, Wi-Fi, SHT40
ambient readings. Layout is two columns — labels left, values right,
all in 22-26 pt for desk-distance readability.

No interactive controls (Color has 3 physical buttons; whatever they
trigger is handled by the firmware + button dispatch path, not by
tappable chips on this page).
"""

from __future__ import annotations
from PIL import Image, ImageDraw
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from card_render_color import font, COL, paint_status_bar  # noqa: E402

CANVAS_W = 600
CANVAS_H = 400
BAR_DIVIDER_PAD = 44   # px above bottom: line above status bar


def render_settings(device_status: dict) -> Image.Image:
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), COL["paper"])
    d = ImageDraw.Draw(img)

    # Title bar — blue with white text
    d.rectangle([0, 0, CANVAS_W, 44], fill=COL["blue"])
    d.text((16, 8), "设置 · DEVICE", fill=COL["paper"], font=font(26))
    fw = device_status.get("firmware") or "?"
    fwt = f"fw {fw}"
    tw = d.textlength(fwt, font=font(20))
    d.text((CANVAS_W - 16 - tw, 14), fwt, fill=COL["paper"], font=font(20))

    # Two-column rows
    rows = []
    rows.append(("型号", device_status.get("device", "?"), COL["ink"]))
    panel_w = device_status.get("panel_w")
    panel_h = device_status.get("panel_h")
    if panel_w and panel_h:
        rows.append(("屏幕", f"{panel_w}×{panel_h} · {device_status.get('color_mode','—')}", COL["ink"]))
    bp = device_status.get("battery_pct")
    if bp is not None:
        bp_col = COL["red"] if bp <= 20 else COL["ink"]
        rows.append(("电量", f"{bp} %", bp_col))
    up = device_status.get("uptime_s")
    if up is not None:
        h = up // 3600; m = (up % 3600) // 60
        ut = f"{h} h {m} m" if h else f"{m} m"
        rows.append(("运行", ut, COL["ink"]))
    # Combine Wi-Fi SSID + IP onto one row; RSSI dropped (rarely useful
    # at desk distance, and we need the vertical space for the SHT40
    # ambient row which is THE Color exclusive value).
    wifi = device_status.get("wifi") or {}
    if wifi.get("ssid") and wifi.get("ip"):
        rows.append(("Wi-Fi", f"{wifi['ssid']} · {wifi['ip']}", COL["blue"]))
    elif wifi.get("ssid"):
        rows.append(("Wi-Fi", wifi["ssid"], COL["ink"]))
    # Combine room temp + humidity into one row to keep the page within
    # 7 entries (otherwise rows overlap the status bar).
    amb = device_status.get("ambient") or {}
    amb_parts = []
    if amb.get("temp_c") is not None:
        amb_parts.append(f"{amb['temp_c']:.1f}°C")
    if amb.get("humid_pct") is not None:
        amb_parts.append(f"{int(round(amb['humid_pct']))}%")
    if amb_parts:
        rows.append(("环境", " · ".join(amb_parts), COL["blue"]))

    # Draw rows. Cap at 7 to leave clean room above the 34 px status bar.
    y = 64
    label_w = 130
    f_lbl = font(22)
    f_val = font(24)
    for label, value, col in rows[:7]:
        d.text((24, y), label, fill=COL["ink"], font=f_lbl)
        d.text((24 + label_w, y), str(value), fill=col, font=f_val)
        y += 38

    # Status bar already shows the A/B/C button hints — no need to repeat
    # them above. Just leave a divider so the page feels framed.
    d.line([24, CANVAS_H - BAR_DIVIDER_PAD,
            CANVAS_W - 24, CANVAS_H - BAR_DIVIDER_PAD],
           fill=COL["ink"], width=1)

    # Bottom status bar
    paint_status_bar(d, {
        "battery_pct": bp,
        "wifi": (wifi.get("ssid") or "")[:12],
        "time": __import__("time").strftime("%H:%M"),
    })

    return img
