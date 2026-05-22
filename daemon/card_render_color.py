"""Color renderer for M5Paper Color (600×400 landscape, Spectra 6 palette).

Design constraints learned the hard way on real hardware:
- Reading distance is 30-50 cm (desk side). Anything under ~24 pt body
  text is unreadable on a reflective e-ink panel.
- Per-widget detail must be cut hard: 2 lines of text + one big number +
  one micro footer is the practical max per slot.
- Spectra 6 quantizes RGB → 6 colors aggressively. Use saturated source
  RGB so the snap doesn't desaturate everything to gray.

Layout: 2×2 grid, slot ~292×170 content area each. Bottom 28px status
strip. Title bars 32px tall in accent color. Daemon renders RGB; device
M5GFX handles the Spectra 6 mapping on push.
"""

from __future__ import annotations
from typing import Iterable
from PIL import Image, ImageDraw, ImageFont
import os

CANVAS_W = 600
CANVAS_H = 400

GAP = 6
BAR_H = 34
TITLE_H = 32
SLOT_W = (CANVAS_W - GAP * 3) // 2
SLOT_H = (CANVAS_H - BAR_H - GAP * 3) // 2

SLOT_RECTS = {
    "top-left":     (GAP, GAP,                          SLOT_W, SLOT_H),
    "top-right":    (GAP * 2 + SLOT_W, GAP,             SLOT_W, SLOT_H),
    "bottom-left":  (GAP, GAP * 2 + SLOT_H,             SLOT_W, SLOT_H),
    "bottom-right": (GAP * 2 + SLOT_W, GAP * 2 + SLOT_H, SLOT_W, SLOT_H),
    "full":         (0, 0, CANVAS_W, CANVAS_H),
}

# Saturated RGB targets — Spectra 6 quantizer will pick closest of:
# white / black / red / yellow / green / blue.
COL = {
    "ink":    (0, 0, 0),
    "paper":  (255, 255, 255),
    "red":    (230, 20, 20),
    "yellow": (240, 220, 30),
    "green":  (30, 165, 70),
    "blue":   (30, 80, 200),
    "muted":  (120, 120, 120),
}

# ----- font loading ----------------------------------------------------------
#
# Spectra 6's color-aware waveform breaks thin strokes into dither
# patterns, so default-weight Regular CJK fonts look fuzzy at small
# sizes. We force a Medium-or-heavier weight everywhere — Spectra 6
# renders bold glyphs cleanly because the strokes are wide enough to
# survive quantization.
#
# Priority (face index for .ttc files in parens):
#   1. PingFang.ttc index=4 (PingFang SC Medium) — macOS, best CJK weight
#   2. STHeiti Medium.ttc                         — macOS fallback
#   3. Hiragino Sans GB.ttc index=1 (W6 Bold)     — older macOS
#   4. NotoSansCJK-Bold.ttc                       — Linux
#   5. wqy-zenhei.ttc                             — Linux fallback
_FONT_CANDIDATES = [
    # STHeiti Medium is already medium-weight by default — heavy enough
    # for Spectra 6's color quantization to render clean strokes. We
    # used to prefer PingFang.ttc but that path doesn't exist on
    # macOS 15+ unless CJK locale is set, so we'd silently fall back
    # here anyway. Skip the dance.
    ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 1),   # W6 / bold face
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
]

def _try_font(size: int) -> ImageFont.ImageFont:
    for path, idx in _FONT_CANDIDATES:
        if not os.path.exists(path): continue
        try:
            return ImageFont.truetype(path, size, index=idx)
        except Exception:
            try: return ImageFont.truetype(path, size)
            except Exception: pass
    return ImageFont.load_default()

def font(size: int) -> ImageFont.ImageFont:
    return _try_font(size)

# ----- shared helpers --------------------------------------------------------

def _truncate(d, text, fnt, max_w):
    if d.textlength(text, font=fnt) <= max_w: return text
    while text and d.textlength(text + "...", font=fnt) > max_w:
        text = text[:-1]
    return text + "..."

def _slot_chrome(d, rect, title, accent=COL["ink"]):
    x, y, w, h = rect
    d.rectangle([x, y, x + w, y + h], outline=COL["ink"], width=1)
    d.rectangle([x, y, x + w, y + TITLE_H], fill=accent)
    label_color = COL["paper"] if accent != COL["paper"] else COL["ink"]
    d.text((x + 10, y + 2), title, fill=label_color, font=font(22))
    return (x + 8, y + TITLE_H + 4, w - 16, h - TITLE_H - 4)   # content rect

# ----- per-widget painters ---------------------------------------------------

def paint_weather(d, rect, data, stale=False):
    cx, cy, cw, ch = _slot_chrome(d, rect, "WEATHER", accent=COL["blue"])
    x, y, w, h = rect
    loc = data.get("location") or ""
    cur = data.get("current") or {}
    temp = cur.get("temp_c")
    cond = cur.get("condition") or ""
    forecast = data.get("forecast") or []

    # Location top-right of title bar
    f_loc = font(22)
    lw = d.textlength(loc, font=f_loc)
    d.text((x + w - 12 - lw, y + 3), loc, fill=COL["paper"], font=f_loc)

    # Big temperature
    if temp is not None:
        tx = f"{int(round(temp))}°"
        d.text((cx, cy + 4), tx, fill=COL["ink"], font=font(64))
    # Condition next to temp
    d.text((cx + 120, cy + 28), cond, fill=COL["ink"], font=font(28))

    # 1-line forecast (only first day to keep readable)
    if forecast:
        f = forecast[0]
        line = f"{f.get('day','')}  {f.get('high','')}/{f.get('low','')}°  {f.get('condition','')}"
        d.text((cx, cy + ch - 32), line, fill=COL["ink"], font=font(24))

def paint_focus(d, rect, data, stale=False):
    cx, cy, cw, ch = _slot_chrome(d, rect, "FOCUS", accent=COL["ink"])
    x, y, w, h = rect
    task = data.get("task", "")
    big = data.get("big_text", "")
    sub = data.get("subtitle", "")
    done = int(data.get("pomodoros_done") or 0)
    plan = int(data.get("pomodoros_planned") or 0)

    f_t = font(22)
    task_line = _truncate(d, task, f_t, cw)
    d.text((cx, cy + 4), task_line, fill=COL["ink"], font=f_t)

    # Big countdown centered
    big_color = COL["red"] if big.startswith("+") else COL["ink"]
    f_big = font(56)
    bw = d.textlength(big, font=f_big)
    d.text((cx + (cw - bw) // 2, cy + 36), big, fill=big_color, font=f_big)

    # Pomodoro dots — single line at bottom
    if plan > 0:
        dy = cy + ch - 14
        dx = cx
        for i in range(min(plan, 6)):
            color = COL["green"] if i < done else COL["muted"]
            d.ellipse([dx, dy - 6, dx + 12, dy + 6], fill=color)
            dx += 18
    # Subtitle right side of dots — bumped to 20pt; drop if too long
    if sub:
        sub_t = _truncate(d, sub, font(20), cw - 130)
        d.text((cx + 130, cy + ch - 28), sub_t, fill=COL["ink"], font=font(20))

def paint_next_meeting(d, rect, data, stale=False):
    cx, cy, cw, ch = _slot_chrome(d, rect, "NEXT", accent=COL["yellow"])
    x, y, w, h = rect
    title = data.get("title", "")
    start_in = data.get("start_in", "")
    start_at = data.get("start_at", "")
    attendees = data.get("attendees", "")
    location = data.get("location", "")

    # Time block: start_in (countdown) left, start_at (HH:MM) right
    in_color = COL["red"] if "now" in start_in.lower() or "m" in start_in else COL["ink"]
    d.text((cx, cy + 4), start_in, fill=in_color, font=font(30))
    f_at = font(26)
    at_w = d.textlength(start_at, font=f_at)
    d.text((cx + cw - at_w, cy + 6), start_at, fill=COL["blue"], font=f_at)

    # Title bold-ish
    title_t = _truncate(d, title, font(22), cw)
    d.text((cx, cy + 50), title_t, fill=COL["ink"], font=font(22))

    # Attendees + location — bumped to 20pt readable
    if attendees:
        line = _truncate(d, attendees, font(20), cw)
        d.text((cx, cy + ch - 52), line, fill=COL["ink"], font=font(20))
    if location:
        line = _truncate(d, location, font(20), cw)
        d.text((cx, cy + ch - 26), line, fill=COL["ink"], font=font(20))

def paint_todo(d, rect, data, stale=False):
    cx, cy, cw, ch = _slot_chrome(d, rect, "TODO", accent=COL["green"])
    x, y, w, h = rect
    items = data.get("items") or []
    title = data.get("title", "")
    if title:
        tw = d.textlength(title, font=font(22))
        d.text((x + w - 12 - tw, y + 3), title, fill=COL["paper"], font=font(22))

    tag_colors = {
        "today":    COL["red"],
        "tomorrow": COL["yellow"],
        "this-week":COL["blue"],
        "overdue":  COL["red"],
        "later":    COL["muted"],
        "":         COL["ink"],
    }
    # Up to 2 items. Color of bullet conveys tag — drop the tag text
    # (was 15pt, unreadable on Spectra 6).
    for i, it in enumerate(items[:2]):
        ty = cy + 8 + i * 64
        tag = it.get("tag", "") or ""
        color = tag_colors.get(tag, COL["ink"])
        d.ellipse([cx, ty + 8, cx + 18, ty + 26], fill=color)
        text = _truncate(d, it.get("text", ""), font(24), cw - 28)
        d.text((cx + 28, ty + 2), text, fill=COL["ink"], font=font(24))

def paint_ambient(d, rect, data, stale=False):
    """Local temperature + humidity from the device's SHT40 sensor.
    Color-exclusive widget — V1.1 has no on-board sensor."""
    cx, cy, cw, ch = _slot_chrome(d, rect, "AMBIENT", accent=COL["green"])
    temp = data.get("temp_c")
    humid = data.get("humid_pct")
    age_s = data.get("age_s")

    # Two halves: temperature left, humidity right
    if temp is not None:
        tx = f"{temp:.1f}°"
        d.text((cx, cy + 0), tx, fill=COL["ink"], font=font(64))
        d.text((cx, cy + 80), "温度", fill=COL["ink"], font=font(22))
    if humid is not None:
        hx = f"{int(round(humid))}%"
        hw = d.textlength(hx, font=font(64))
        d.text((cx + cw - hw, cy + 0), hx, fill=COL["blue"], font=font(64))
        lw = d.textlength("湿度", font=font(22))
        d.text((cx + cw - lw, cy + 80), "湿度", fill=COL["ink"], font=font(22))
    # Drop the "读数 N s 前" footnote — unreadable at small size and
    # not critical to the glance.

def paint_ai_status(d, rect, data, stale=False):
    cx, cy, cw, ch = _slot_chrome(d, rect, "AI", accent=COL["blue"])
    x, y, w, h = rect
    session = data.get("session_name", "")
    model = data.get("model", "")
    task = data.get("task", "")
    ctx = data.get("context") or {}
    used = ctx.get("used")
    limit = ctx.get("limit")

    if session:
        sw = d.textlength(session, font=font(22))
        d.text((x + w - 12 - sw, y + 3), session, fill=COL["paper"], font=font(22))

    if model:
        d.text((cx, cy + 4), model, fill=COL["ink"], font=font(28))
    if task:
        task_t = _truncate(d, task, font(22), cw)
        d.text((cx, cy + 44), task_t, fill=COL["ink"], font=font(22))

    # Context bar
    if used and limit:
        bar_y = cy + ch - 30
        d.text((cx, bar_y - 28), f"ctx {used // 1000}K / {limit // 1000}K",
               fill=COL["ink"], font=font(20))
        d.rectangle([cx, bar_y, cx + cw, bar_y + 16],
                    outline=COL["ink"], width=1)
        filled = int(cw * used / limit)
        fill_color = COL["red"] if used / limit > 0.9 else COL["ink"]
        d.rectangle([cx, bar_y, cx + filled, bar_y + 16], fill=fill_color)

def paint_pr_queue(d, rect, data, stale=False):
    cx, cy, cw, ch = _slot_chrome(d, rect, "PRS", accent=COL["red"])
    x, y, w, h = rect
    review = data.get("review_count", 0)
    yours = data.get("your_open_count", 0)
    items = data.get("items") or []

    # Counts top-right of header
    counts = f"{review} / {yours}"
    cwidth = d.textlength(counts, font=font(22))
    d.text((x + w - 12 - cwidth, y + 3), counts,
           fill=COL["paper"], font=font(22))

    # Up to 2 items. Color of #number conveys status — drop the
    # status word (was 14pt, unreadable).
    status_colors = {
        "review": COL["red"],
        "yours": COL["blue"],
        "approved": COL["green"],
        "blocked": COL["yellow"],
        "": COL["muted"],
    }
    for i, it in enumerate(items[:2]):
        py = cy + 8 + i * 64
        num = it.get("number", "")
        title = it.get("text") or it.get("title", "")
        status = it.get("status", "")
        col = status_colors.get(status, COL["ink"])
        d.text((cx, py), num, fill=col, font=font(24))
        nw = d.textlength(num, font=font(24))
        title_t = _truncate(d, title, font(22), cw - nw - 16)
        d.text((cx + nw + 12, py + 2), title_t,
               fill=COL["ink"], font=font(22))

def paint_deadlines(d, rect, data, stale=False):
    cx, cy, cw, ch = _slot_chrome(d, rect, "DEADLINES", accent=COL["red"])
    items = data.get("items") or []
    for i, it in enumerate(items[:2]):
        py = cy + 4 + i * 60
        urgent = bool(it.get("is_urgent"))
        col = COL["red"] if urgent else COL["ink"]
        if urgent:
            d.ellipse([cx, py + 8, cx + 14, py + 22], fill=col)
            tx = cx + 22
        else:
            tx = cx
        title = _truncate(d, it.get("title", ""), font(20), cw - (tx - cx))
        d.text((tx, py + 2), title, fill=col, font=font(20))
        due = it.get("due_label", "")
        if due:
            d.text((tx, py + 30), due, fill=COL["ink"], font=font(20))

def paint_calendar(d, rect, data, stale=False):
    cx, cy, cw, ch = _slot_chrome(d, rect, "TODAY", accent=COL["yellow"])
    x, y, w, h = rect
    events = data.get("events") or []
    now_iso = data.get("now_iso", "")
    if now_iso and "T" in now_iso:
        nowhm = now_iso.split("T")[1][:5]
        nw = d.textlength(nowhm, font=font(22))
        d.text((x + w - 12 - nw, y + 3), nowhm, fill=COL["paper"], font=font(22))
    for i, ev in enumerate(events[:3]):
        py = cy + 4 + i * 40
        start = ev.get("start", "")
        title = ev.get("title", "")
        d.text((cx, py + 2), start, fill=COL["blue"], font=font(22))
        title_t = _truncate(d, title, font(20), cw - 90)
        d.text((cx + 88, py + 4), title_t, fill=COL["ink"], font=font(20))

def paint_break_reminder(d, rect, data, stale=False):
    cx, cy, cw, ch = _slot_chrome(d, rect, "BREAK", accent=COL["yellow"])
    sit = data.get("sitting_min")
    eye = data.get("next_eye_rest_min")
    advice = data.get("advice", "")

    # Show only the 2 highest-signal lines (drop last_break — implied by
    # sit). Color stays MINIMAL — red only when truly urgent, body in
    # ink black for max contrast on e-ink. Green washed out on Spectra 6.
    primary_lines = []
    if sit is not None:
        col = COL["red"] if sit > 60 else COL["ink"]
        primary_lines.append((f"已坐 {sit} 分钟", col))
    if eye is not None:
        if eye < 0:
            primary_lines.append((f"护眼超时 {-eye} 分钟", COL["red"]))
        else:
            primary_lines.append((f"下次护眼 {eye} 分钟", COL["ink"]))

    for i, (txt, col) in enumerate(primary_lines[:2]):
        d.text((cx, cy + 6 + i * 38), txt, fill=col, font=font(24))

    if advice:
        adv = _truncate(d, advice, font(24), cw)
        # Black for readability — drop the green decoration that
        # quantized poorly on Spectra 6.
        d.text((cx, cy + ch - 36), adv, fill=COL["ink"], font=font(24))


PAINTERS = {
    "weather":        paint_weather,
    "focus":          paint_focus,
    "next-meeting":   paint_next_meeting,
    "todo":           paint_todo,
    "ambient":        paint_ambient,
    "ai-status":      paint_ai_status,
    "pr-queue":       paint_pr_queue,
    "deadlines":      paint_deadlines,
    "calendar":       paint_calendar,
    "break-reminder": paint_break_reminder,
}

def paint_empty(d, rect, label="—"):
    x, y, w, h = rect
    d.rectangle([x, y, x + w, y + h], outline=COL["muted"], width=1)
    f = font(22)
    lw = d.textlength(label, font=f)
    d.text((x + (w - lw) // 2, y + h // 2 - 14), label, fill=COL["muted"], font=f)

def paint_status_bar(d, status: dict):
    """Bottom 34 px strip. LEFT = physical button hints (Color exclusive —
    V1.1 had tappable chips). RIGHT = battery / wifi / time, ordered by
    glance-priority. Yellow accent for button letters to make A/B/C
    instantly distinguishable from the body text."""
    y = CANVAS_H - BAR_H
    d.rectangle([0, y, CANVAS_W, CANVAS_H], fill=COL["ink"])

    # LEFT — button hints by physical position. PaperColor's 3 user
    # buttons aren't in a row: top one alone + two on bottom. So we
    # label by location instead of M5's internal A/B/C.
    btn_hints = [
        ("顶", "睡眠"),
        ("左", "刷新"),
        ("中", "设置"),
    ]
    f_pos   = font(20)
    f_label = font(20)
    x = 12
    for pos, label in btn_hints:
        d.text((x, y + 4), pos, fill=COL["yellow"], font=f_pos)
        lw = d.textlength(pos, font=f_pos)
        d.text((x + lw + 4, y + 4), label, fill=COL["paper"], font=f_label)
        x += lw + 4 + int(d.textlength(label, font=f_label)) + 18

    # RIGHT — battery / wifi / time, right-aligned
    bp = status.get("battery_pct")
    wifi = status.get("wifi", "")
    ts = status.get("time", "")
    right_pieces = []
    if ts: right_pieces.append((ts, COL["paper"]))
    if wifi:
        # truncate ssid if huge
        if len(wifi) > 12: wifi = wifi[:11] + "…"
        right_pieces.append((wifi, COL["paper"]))
    if bp is not None:
        col = COL["red"] if bp <= 20 else COL["paper"]
        right_pieces.append((f"{bp}%", col))
    # measure total width, place from right edge
    f = font(20)
    total_w = sum(int(d.textlength(t, font=f)) for t, _ in right_pieces)
    total_w += 22 * (len(right_pieces) - 1) if right_pieces else 0
    rx = CANVAS_W - 12 - total_w
    for i, (txt, col) in enumerate(right_pieces):
        d.text((rx, y + 4), txt, fill=col, font=f)
        rx += int(d.textlength(txt, font=f)) + 22

# ----- public API ------------------------------------------------------------

def render_image(widgets: Iterable[dict],
                 status: "dict | None" = None) -> Image.Image:
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), COL["paper"])
    d = ImageDraw.Draw(img)
    seen = set()
    for w in widgets or []:
        slot = w.get("slot")
        wtype = w.get("type")
        rect = SLOT_RECTS.get(slot)
        fn = PAINTERS.get(wtype)
        if rect and fn:
            seen.add(slot)
            try: fn(d, rect, w.get("data") or {})
            except Exception as e:
                d.text((rect[0] + 6, rect[1] + 40),
                       f"err {wtype}: {e!r}"[:36],
                       fill=COL["red"], font=font(12))
    for slot, rect in SLOT_RECTS.items():
        if slot == "full" or slot in seen: continue
        paint_empty(d, rect, slot.replace("-", " "))
    paint_status_bar(d, status or {})
    return img
