#!/usr/bin/env python3
"""claude-card 设置页 — 全屏视图，替代 widget 副屏。

底部状态栏点"设置"后进入；下次 v0.6.4 接通触屏路由后由
firmware → daemon /touch → 渲染。当前流程：

    daemon POST /settings → IN_SETTINGS=True → render_and_push()
    分发到 render_settings_page()，走同一条 frame_chunk 协议下发。

布局（540 × 960）：

    ┌─────────────────────────────────────┐
    │ ◀ 返回                       设置 ▶ │   ← 顶部反白条
    ├─────────────────────────────────────┤
    │  设备                                │
    │  型号        M5Paper V1.1            │
    │  固件        v0.6                    │
    │  MAC         XX:XX:XX:XX:XX:XX       │
    │  电量        82%  (4.21 V)           │
    │  运行时长    2 小时 14 分            │
    │                                      │
    │  连接                                │
    │  传输方式    USB · 115200 baud       │
    │  守护进程    ● 已连接                │
    │  蓝牙        未配对                  │
    │                                      │
    │  操作                                │
    │  ┌────────────────────────────────┐  │
    │  │  ●   刷新组件                  │  │
    │  ├────────────────────────────────┤  │
    │  │  ○   进入睡眠（显示名片）      │  │
    │  ├────────────────────────────────┤  │
    │  │  ●   重启设备                  │  │
    │  ├────────────────────────────────┤  │
    │  │  ●   重新配对蓝牙              │  │
    │  ├────────────────────────────────┤  │
    │  │  ●   清空所有组件              │  │
    │  └────────────────────────────────┘  │
    │                                      │
    └─────────────────────────────────────┘
              点上方任一项 · 返回退出

设计取舍：
  - 去掉了 PROFILE 段（profile.yaml 路径放 docs / SKILL.md 即可）
  - 行间距 +6px、按钮高度 60、按钮间距 12px，避免上一版"挤"的反馈
  - 全中文标签；所有图标用 ● / ○ / · / — 这种 PingFang 已覆盖字形
"""
from __future__ import annotations
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None

import card_render

CANVAS_W, CANVAS_H = 540, 960
PADDING = 28
INK = 0
MUTED = 0x88

# v0.6.4：触屏点击命中区。每次 render 重建。
HOT_ZONES: list = []


def _section_header(d, x, y, label):
    f = card_render.font(bold=True)
    d.text((x, y), label, fill=INK, font=f)
    return y + card_render.BODY_SIZE + 10


def _kv_row(d, x, y, w, key, value, key_w=180):
    f = card_render.font()
    f_b = card_render.font(bold=True)
    d.text((x, y), key, fill=MUTED, font=f)
    if value:
        vstr = str(value)
        # 简单的尾部截断 — 中文字宽变化大，估保守
        if d.textlength(vstr, font=f) > w - key_w:
            while vstr and d.textlength(vstr + "...", font=f) > w - key_w:
                vstr = vstr[:-1]
            vstr += "..."
        d.text((x + key_w, y), vstr, fill=INK, font=f_b)
    return y + card_render.BODY_SIZE + 10   # v2: 加大行距 6→10


def _action_button(d, x, y, w, h, icon, label, action_id):
    """边框按钮 + 点击热区注册。"""
    d.rectangle((x, y, x + w, y + h), outline=INK, width=2)
    f_b = card_render.font(bold=True)
    text_y = y + (h - card_render.BODY_SIZE) // 2 - 2
    if icon:
        d.text((x + 28, text_y), icon, fill=INK, font=f_b)
    d.text((x + 80, text_y), label, fill=INK, font=f_b)
    HOT_ZONES.append({"action": action_id, "rect": (x, y, x + w, y + h)})
    return y + h


def render_settings_page(state: Optional[dict] = None) -> "Image.Image":
    if Image is None:
        raise RuntimeError("install Pillow")
    state = state or {}
    HOT_ZONES.clear()

    img = Image.new("L", (CANVAS_W, CANVAS_H), 255)
    d = ImageDraw.Draw(img)

    # ---- 顶部反白条 ----
    header_h = 68
    d.rectangle((0, 0, CANVAS_W, header_h), fill=INK)
    f_h = card_render.font_header()
    f_b = card_render.font_bar_bold()
    d.text((PADDING, 20), "返回", fill=255, font=f_b)
    title = "设置"
    tw = d.textlength(title, font=f_h)
    d.text((CANVAS_W - PADDING - tw, 16), title, fill=255, font=f_h)
    HOT_ZONES.append({"action": "back", "rect": (0, 0, 180, header_h)})

    y = header_h + 28

    # ---- 设备 ----
    y = _section_header(d, PADDING, y, "设备")
    w = CANVAS_W - 2 * PADDING
    y = _kv_row(d, PADDING, y, w, "型号", state.get("model", "M5Paper V1.1"))
    y = _kv_row(d, PADDING, y, w, "固件", state.get("firmware", "—"))
    y = _kv_row(d, PADDING, y, w, "MAC",  state.get("mac",      "—"))
    bat = state.get("battery_pct"); bat_v = state.get("battery_mv")
    bat_str = "—"
    if bat is not None:
        bat_str = f"{bat}%"
        if bat_v: bat_str += f"   ({bat_v / 1000:.2f} V)"
    y = _kv_row(d, PADDING, y, w, "电量",     bat_str)
    y = _kv_row(d, PADDING, y, w, "运行时长", state.get("uptime", "—"))
    y += 18

    # ---- 连接 ----
    y = _section_header(d, PADDING, y, "连接")
    transport = state.get("transport", "—")
    baud = state.get("baud", "")
    t_str = f"{transport} · {baud} baud" if baud else transport
    y = _kv_row(d, PADDING, y, w, "传输方式", t_str)
    y = _kv_row(d, PADDING, y, w, "守护进程",
                "● 已连接" if state.get("daemon_ok") else "○ 未连接")
    y = _kv_row(d, PADDING, y, w, "蓝牙",
                "已配对" if state.get("ble_paired") else "未配对")
    y += 22

    # ---- 操作 ----
    y = _section_header(d, PADDING, y, "操作")
    btn_h = 62
    btn_w = w
    actions = [
        ("●", "刷新组件",           "refresh"),
        ("○", "进入睡眠（名片）",   "sleep"),
        ("●", "重启设备",           "restart"),
        ("●", "重新配对蓝牙",       "repair"),
        ("●", "清空所有组件",       "clear"),
    ]
    for icon, label, aid in actions:
        y = _action_button(d, PADDING, y, btn_w, btn_h, icon, label, aid)
        y += 12

    # ---- 底部提示 ----
    foot = "点击上方任一项执行  ·  左上 返回 退出"
    f = card_render.font()
    fw = d.textlength(foot, font=f)
    d.text(((CANVAS_W - fw) // 2, CANVAS_H - 44), foot, fill=MUTED, font=f)

    return img


def get_hot_zones():
    return list(HOT_ZONES)


if __name__ == "__main__":
    import argparse, io, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    fake = {
        "model":       "M5Paper V1.1",
        "firmware":    "v0.6",
        "mac":         "B0:B2:1C:AB:CD:EF",
        "battery_pct": 82,
        "battery_mv":  4210,
        "uptime":      "2 小时 14 分",
        "transport":   "USB",
        "baud":        "115200",
        "daemon_ok":   True,
        "ble_paired":  False,
    }
    img = render_settings_page(fake)
    buf = io.BytesIO(); img.save(buf, format="PNG"); data = buf.getvalue()
    if a.out == "-": sys.stdout.buffer.write(data)
    else:
        with open(a.out, "wb") as f: f.write(data)
        print(f"wrote {a.out}", file=sys.stderr)
