#!/usr/bin/env python3
"""claude-card v0.6 PIL renderer — server-side rendering, authoritative.

Design philosophy (set during v0.6 migration):
  - ONE font size (28pt body, 28pt bold for headlines)
  - Hierarchy via dividers, inverted bars, spacing, boxes
  - No font-size variation. No createRender drama. No glyph gaps.
  - Inspired by Swiss minimalist e-ink dashboards (TRMNL etc.)

Output:
  - 540×960 grayscale PIL Image (mode 'L', 0=black 255=white)
  - Convert to 4bpp packed via to_4bpp_packed() before sending to device
  - On M5EPD: 0=white, 15=black. We invert during pack.
"""
from __future__ import annotations
import io
import os
from typing import Iterable, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None

CANVAS_W, CANVAS_H = 540, 960
PADDING = 20
DIVIDER_GRAY = 0x88
INK_BLACK = 0

SLOT_RECTS = {
    # v0.6.1: shrunk the top row from 380 → 280 because top widgets only
    # need ~240 px of content; extra read as a weird empty band.
    # v0.6.3: shrunk the bottom row from 340 → 280 to make room for the
    # status/settings bar at the very bottom (60 px tall).
    "top-left":  (0,   0,   270, 280),
    "top-right": (270, 0,   270, 280),
    "middle":    (0,   280, 540, 340),
    "bottom":    (0,   620, 540, 280),
    "full":      (0,   0,   540, 960),
}

# Bottom status/settings bar — inverted black strip at the very bottom of
# the canvas. Left side = passive status (USB / BLE / time). Right side
# = action chips (refresh / sleep / restart) — visually styled as
# tappable, touch dispatch is wired in v0.6.4.
BOTTOM_BAR_Y = 900
BOTTOM_BAR_H = 60

# ---- font ---------------------------------------------------------------

# Try macOS system fonts first (PingFang has CJK + Latin-1 + box drawing).
# Falls back to whatever's available.
_FONT_PATHS_REGULAR = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]
_FONT_PATHS_BOLD = [
    "/System/Library/Fonts/PingFang.ttc",   # bold via index
    "/System/Library/Fonts/STHeiti Medium.ttc",
]

BODY_SIZE = 28

_font_cache: dict = {}

def font(bold: bool = False):
    """Return the single-size font. v0.6 design decision: one size, period."""
    key = ("bold" if bold else "regular", BODY_SIZE)
    if key in _font_cache:
        return _font_cache[key]
    paths = _FONT_PATHS_BOLD if bold else _FONT_PATHS_REGULAR
    for p in paths:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, BODY_SIZE, index=1 if bold else 0)
                _font_cache[key] = f
                return f
            except Exception:
                continue
    f = ImageFont.load_default()
    _font_cache[key] = f
    return f


# Status/settings bar font — 22 pt. The "one font size" rule applies to
# widget BODY content; the bar is infrastructure chrome (status + action
# chips) and reads cleanest at a smaller-than-body size so left + right
# zones fit without colliding at 540 px wide.
def font_bar():
    key = ("bar", 22)
    if key in _font_cache:
        return _font_cache[key]
    for p in _FONT_PATHS_REGULAR:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, 22, index=0)
                _font_cache[key] = f
                return f
            except Exception:
                continue
    return font()


def font_bar_bold():
    key = ("bar-bold", 22)
    if key in _font_cache:
        return _font_cache[key]
    for p in _FONT_PATHS_BOLD:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, 22, index=1)
                _font_cache[key] = f
                return f
            except Exception:
                continue
    return font(bold=True)


# A slightly larger font is only used for ONE thing — the inverted bar's
# type label, which should be assertive. Same rule otherwise.
def font_header():
    key = ("header", 32)
    if key in _font_cache:
        return _font_cache[key]
    for p in _FONT_PATHS_BOLD:
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, 32, index=1)
                _font_cache[key] = f
                return f
            except Exception:
                continue
    return font(bold=True)


# ---- design primitives --------------------------------------------------

def header_bar(d: ImageDraw.ImageDraw, rect, label: str, meta: str = ""):
    """Minimal header: black label text on white + a thin horizontal rule.

    v0.6.1 update: dropped the inverted-bar design — on the middle and
    bottom widgets, which span full canvas width, the inverted bar read
    as a heavy horizontal section divider (the 'horizontal black bars'
    we removed earlier kept reappearing because they were the widget
    headers themselves). This lighter treatment keeps the type label
    visible without the section-divider look."""
    x, y, w, h = rect
    bar_h = 52
    # Label on white background (black text).
    d.text((x + PADDING, y + 14), label.upper(),
           fill=INK_BLACK, font=font_header())
    if meta:
        meta_bbox = d.textbbox((0, 0), meta, font=font())
        meta_w = meta_bbox[2] - meta_bbox[0]
        d.text((x + w - PADDING - meta_w, y + 18), meta,
               fill=DIVIDER_GRAY, font=font())
    # Thin underline (3 px) — gives the label visual weight without a
    # full inverted block.
    d.rectangle((x + PADDING, y + bar_h - 3, x + w - PADDING, y + bar_h),
                fill=INK_BLACK)
    return y + bar_h


def divider(d: ImageDraw.ImageDraw, x1, y, x2, weight: int = 1, gray: int = DIVIDER_GRAY):
    """Horizontal divider. weight 1 = subtle, 2-3 = stronger."""
    for w in range(weight):
        d.line((x1, y + w, x2, y + w), fill=gray)


def body_text(d, x, y, max_w: int, text: str, bold: bool = False) -> int:
    """Draw single line of body text, return next-y. Auto-truncate with '...'
    if too wide. No font-size shrinking (v0.6 single-size rule)."""
    if not text:
        return y
    f = font(bold)
    # Truncate to width.
    truncated = text
    if d.textlength(text, font=f) > max_w:
        while truncated and d.textlength(truncated + "...", font=f) > max_w:
            # Strip one char at a time (UTF-8 aware via Python string).
            truncated = truncated[:-1]
        truncated = (truncated + "...") if truncated != text else text
    d.text((x, y), truncated, fill=INK_BLACK, font=f)
    return y + BODY_SIZE + 8


def wrapped_text(d, x, y, max_w: int, max_h: int, text: str) -> int:
    """Multi-line wrap. Word-aware (preserves Latin word boundaries),
    falls back to per-codepoint for CJK runs. Truncate last visible line
    with '...' if overflows max_h."""
    if not text:
        return y
    f = font()
    line_h = BODY_SIZE + 8

    # Tokenise into atoms we won't break across lines.
    atoms = []
    buf = ""
    def flush():
        nonlocal buf
        if buf: atoms.append(buf); buf = ""
    for ch in text:
        if ch == "\n":
            flush(); atoms.append("\n")
        elif ch.isspace():
            flush(); atoms.append(ch)
        elif ord(ch) >= 0x2E80:    # CJK + fullwidth — break per codepoint
            flush(); atoms.append(ch)
        else:
            buf += ch
    flush()

    lines = []
    cur = ""
    for atom in atoms:
        if atom == "\n":
            lines.append(cur.rstrip()); cur = ""
            continue
        trial = cur + atom
        if d.textlength(trial, font=f) > max_w:
            if cur.strip():
                lines.append(cur.rstrip())
                cur = atom.lstrip()
                # Fallback for atoms that are themselves wider than the
                # line (super-long Latin words) — char-split that atom.
                while cur and d.textlength(cur, font=f) > max_w:
                    lo, hi = 1, len(cur)
                    while lo < hi:
                        mid = (lo + hi + 1) // 2
                        if d.textlength(cur[:mid], font=f) <= max_w:
                            lo = mid
                        else:
                            hi = mid - 1
                    lines.append(cur[:lo])
                    cur = cur[lo:]
            else:
                cur = atom
        else:
            cur = trial
    if cur.strip():
        lines.append(cur.rstrip())

    max_lines = max_h // line_h
    if max_lines < 1: max_lines = 1
    if len(lines) > max_lines:
        last = lines[max_lines - 1]
        while last and d.textlength(last + "...", font=f) > max_w:
            last = last[:-1]
        lines = lines[:max_lines - 1] + [last + "..."]

    for i, line in enumerate(lines):
        d.text((x, y + i * line_h), line, fill=INK_BLACK, font=f)
    return y + len(lines) * line_h


# ---- per-widget painters ------------------------------------------------

def _resolve_widget(slot_name, widget_snapshot):
    for w in widget_snapshot:
        if w.get("slot") == slot_name:
            return w
    return None


def paint_weather(d, rect, data, stale=False):
    x, y, w, h = rect
    next_y = header_bar(d, rect, "WEATHER", data.get("location", "") or "")
    next_y += PADDING

    cur = data.get("current") or {}
    if cur:
        # Combine temp + condition into one line (single-size design — no
        # huge headline, but use bold to emphasise).
        temp = cur.get("temp_c")
        cond = cur.get("condition", "")
        if temp is not None:
            line = f"{temp}°  {cond}".strip()
        else:
            line = cond
        next_y = body_text(d, x + PADDING, next_y, w - 2 * PADDING, line, bold=True)
        next_y += 8

    divider(d, x + PADDING, next_y, x + w - PADDING)
    next_y += 12

    for f in (data.get("forecast") or [])[:2]:
        line = f"{f.get('day','')}  {f.get('high','-')}° / {f.get('low','-')}°  {f.get('condition','')}"
        next_y = body_text(d, x + PADDING, next_y, w - 2 * PADDING, line.strip())


def paint_todo(d, rect, data, stale=False):
    x, y, w, h = rect
    title = data.get("title") or ""
    next_y = header_bar(d, rect, "TODO", title)
    next_y += PADDING
    for it in (data.get("items") or [])[:3]:   # tighter cap with single size
        tag = it.get("tag", "")
        if tag == "overdue":    prefix = "▪"
        elif tag == "today":    prefix = "▶"
        else:                   prefix = "□"
        line = f"{prefix}  {it.get('text','')}"
        next_y = body_text(d, x + PADDING, next_y, w - 2 * PADDING, line, bold=(tag in ("today", "overdue")))


def paint_calendar(d, rect, data, stale=False):
    x, y, w, h = rect
    now_iso = data.get("now_iso") or ""
    meta = now_iso[11:16] if len(now_iso) >= 16 else ""
    next_y = header_bar(d, rect, "TODAY", meta)
    next_y += PADDING
    for ev in (data.get("events") or [])[:3]:
        line = f"{ev.get('start','')}   {ev.get('title','')}"
        next_y = body_text(d, x + PADDING, next_y, w - 2 * PADDING, line.strip())


def paint_messages(d, rect, data, stale=False):
    x, y, w, h = rect
    next_y = header_bar(d, rect, "MESSAGES")
    next_y += PADDING - 4
    for m in (data.get("items") or [])[:2]:
        sender = m.get("sender", "")
        preview = m.get("preview", "")
        age = m.get("age", "")
        # sender + age share one line (bold sender, age right-aligned)
        f_bold = font(bold=True)
        d.text((x + PADDING, next_y), sender, fill=INK_BLACK, font=f_bold)
        if age:
            age_w = d.textlength(age, font=font())
            d.text((x + w - PADDING - age_w, next_y + 4), age, fill=DIVIDER_GRAY, font=font())
        next_y += BODY_SIZE + 6
        next_y = body_text(d, x + PADDING, next_y, w - 2 * PADDING, preview)
        divider(d, x + PADDING, next_y + 2, x + w - PADDING)
        next_y += 16


def paint_ai_status(d, rect, data, stale=False):
    x, y, w, h = rect
    session = data.get("session_name", "")
    next_y = header_bar(d, rect, "AI", session)
    next_y += PADDING

    model = data.get("model", "")
    if model:
        next_y = body_text(d, x + PADDING, next_y, w - 2 * PADDING, model, bold=True)

    task = data.get("task", "")
    if task:
        next_y = wrapped_text(d, x + PADDING, next_y, w - 2 * PADDING, BODY_SIZE * 2 + 16, task)
        next_y += 8

    ctx = data.get("context") or {}
    if ctx.get("limit"):
        used, lim = ctx.get("used", 0), ctx["limit"]
        # Inline progress bar.
        bar_y = next_y
        bar_w = w - 2 * PADDING
        d.rectangle((x + PADDING, bar_y, x + PADDING + bar_w, bar_y + 12),
                    outline=INK_BLACK, width=1)
        fill = max(1, min(bar_w, int(bar_w * used / lim))) if used > 0 else 0
        if fill:
            d.rectangle((x + PADDING, bar_y, x + PADDING + fill, bar_y + 12),
                        fill=INK_BLACK)
        next_y = bar_y + 24
        body_text(d, x + PADDING, next_y, w - 2 * PADDING,
                  f"ctx {used // 1000}K / {lim // 1000}K")


def paint_ai_tasks(d, rect, data, stale=False):
    x, y, w, h = rect
    next_y = header_bar(d, rect, "SESSIONS")
    next_y += 12

    cells = [
        (data.get("running", 0), "running"),
        (data.get("waiting", 0), "waiting"),
        (data.get("blocked", 0), "blocked"),
        (data.get("completed_today", 0), "done today"),
    ]
    f_b = font(bold=True)
    f_l = font()
    if w < 350:
        # Narrow slot — stack vertically. Black number box on left + label.
        row_h = (h - (next_y - y) - 20) // 4
        row_h = max(min(row_h, 60), 48)
        box_size = min(row_h - 10, 50)
        for i, (n, label) in enumerate(cells):
            ry = next_y + i * row_h
            # Black number box.
            d.rectangle((x + PADDING, ry, x + PADDING + box_size, ry + box_size),
                        fill=INK_BLACK)
            n_str = str(n)
            n_bbox = d.textbbox((0, 0), n_str, font=f_b)
            nw, nh = n_bbox[2] - n_bbox[0], n_bbox[3] - n_bbox[1]
            d.text((x + PADDING + (box_size - nw) // 2,
                    ry + (box_size - nh) // 2 - 2),
                   n_str, fill=255, font=f_b)
            d.text((x + PADDING + box_size + 16, ry + (box_size - BODY_SIZE) // 2),
                   label, fill=INK_BLACK, font=f_l)
    else:
        cell_w = (w - 3 * PADDING) // 2
        cell_h = 90
        for i, (n, label) in enumerate(cells):
            row, col = i // 2, i % 2
            cx = x + PADDING + col * (cell_w + PADDING)
            cy = next_y + row * (cell_h + 8)
            d.rectangle((cx, cy, cx + 60, cy + 50), fill=INK_BLACK)
            n_str = str(n)
            n_bbox = d.textbbox((0, 0), n_str, font=f_b)
            n_w = n_bbox[2] - n_bbox[0]
            d.text((cx + 30 - n_w // 2, cy + 8), n_str, fill=255, font=f_b)
            d.text((cx + 72, cy + 12), label, fill=INK_BLACK, font=f_l)


# v0.5.1 widget types

def paint_scratch(d, rect, data, stale=False):
    x, y, w, h = rect
    source = data.get("source") or ""
    age = data.get("age") or ""
    meta = f"{source} · {age}".strip(" ·") if source or age else ""
    next_y = header_bar(d, rect, "NOTE", meta)
    next_y += PADDING
    text = data.get("text") or ""
    body_h = h - (next_y - y) - PADDING
    wrapped_text(d, x + PADDING, next_y, w - 2 * PADDING, body_h, text)


def paint_focus(d, rect, data, stale=False):
    x, y, w, h = rect
    next_y = header_bar(d, rect, "FOCUS")
    next_y += 12

    task = data.get("task", "")
    if task:
        next_y = wrapped_text(d, x + PADDING, next_y,
                              w - 2 * PADDING, BODY_SIZE * 2 + 8, task)
        next_y += 8

    big = data.get("big_text", "")
    if big:
        box_w = w - 2 * PADDING
        # Narrower slot → shorter box so we leave room for subtitle + dots
        # without overlapping.
        box_h = 56 if w < 350 else 64
        d.rectangle((x + PADDING, next_y, x + PADDING + box_w, next_y + box_h),
                    outline=INK_BLACK, width=2)
        f_b = font(bold=True)
        bbox = d.textbbox((0, 0), big, font=f_b)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text((x + PADDING + (box_w - tw) // 2, next_y + (box_h - th) // 2 - 4),
               big, fill=INK_BLACK, font=f_b)
        next_y += box_h + 10

    # Subtitle on its OWN line — no longer split with dots (which would
    # overlap on the narrow 270 px top slot).
    subtitle = data.get("subtitle", "")
    if subtitle:
        body_text(d, x + PADDING, next_y, w - 2 * PADDING, subtitle)
        next_y += BODY_SIZE + 6

    # Pomodoro dots on their OWN line below subtitle.
    done = data.get("pomodoros_done", 0)
    planned = data.get("pomodoros_planned", 0)
    if planned:
        dot_str = " ".join(["●" if i < done else "○" for i in range(min(planned, 8))])
        d.text((x + PADDING, next_y), dot_str, fill=DIVIDER_GRAY, font=font())


def paint_now_playing(d, rect, data, stale=False):
    x, y, w, h = rect
    source = data.get("source", "")
    next_y = header_bar(d, rect, "PLAYING", source)
    next_y += 12

    track = data.get("track", "")
    artist = data.get("artist", "")
    # Track may need 2 lines on narrow slots. Use wrapped_text instead of
    # body_text so long titles don't get aggressively "..."-truncated.
    if track:
        max_lines_h = (BODY_SIZE + 8) * 2
        next_y = wrapped_text(d, x + PADDING, next_y,
                              w - 2 * PADDING, max_lines_h, track)
        next_y += 4
    if artist:
        next_y = body_text(d, x + PADDING, next_y, w - 2 * PADDING, artist)
    next_y += 8

    # Progress bar.
    pos = data.get("position_sec", 0)
    dur = data.get("duration_sec", 0)
    bar_w = w - 2 * PADDING
    d.rectangle((x + PADDING, next_y, x + PADDING + bar_w, next_y + 10),
                outline=INK_BLACK, width=1)
    if dur > 0:
        fill = max(1, min(bar_w, int(bar_w * pos / dur))) if pos > 0 else 0
        if fill:
            d.rectangle((x + PADDING, next_y, x + PADDING + fill, next_y + 10), fill=INK_BLACK)
    next_y += 22
    def mmss(s): return f"{s // 60}:{s % 60:02d}"
    # Drop the play/pause glyph on narrow slots to avoid the "▶ ..." ellipsis.
    if w < 350:
        body_text(d, x + PADDING, next_y, w - 2 * PADDING, f"{mmss(pos)} / {mmss(dur)}")
    else:
        state = "▶ playing" if data.get("playing", True) else "❚❚ paused"
        body_text(d, x + PADDING, next_y, w - 2 * PADDING,
                  f"{mmss(pos)} / {mmss(dur)}   {state}")


def paint_git_status(d, rect, data, stale=False):
    x, y, w, h = rect
    repo = data.get("repo_name", "") or ""
    next_y = header_bar(d, rect, "GIT", repo)
    next_y += PADDING - 4

    branch = data.get("branch", "") or "(detached)"
    # Box around branch — single-size design means we lean on the box for emphasis.
    box_w = w - 2 * PADDING
    box_h = 50
    d.rectangle((x + PADDING, next_y, x + PADDING + box_w, next_y + box_h),
                outline=INK_BLACK, width=2)
    f_b = font(bold=True)
    bbox = d.textbbox((0, 0), branch, font=f_b)
    bw = bbox[2] - bbox[0]
    # Truncate branch if too wide for box.
    if bw > box_w - 32:
        trunc = branch
        while trunc and d.textlength(trunc + "...", font=f_b) > box_w - 32:
            trunc = trunc[:-1]
        branch = trunc + "..." if trunc else branch
        bw = d.textlength(branch, font=f_b)
    d.text((x + PADDING + (box_w - bw) // 2, next_y + 8), branch, fill=INK_BLACK, font=f_b)
    next_y += box_h + 12

    parts = []
    if data.get("staged"):    parts.append(f"{data['staged']} staged")
    if data.get("modified"):  parts.append(f"{data['modified']} modified")
    if data.get("untracked"): parts.append(f"{data['untracked']} new")
    if not parts:
        parts.append("clean")
    next_y = body_text(d, x + PADDING, next_y, w - 2 * PADDING, "  ·  ".join(parts))

    ahead, behind = data.get("ahead", 0), data.get("behind", 0)
    if ahead or behind:
        next_y = body_text(d, x + PADDING, next_y, w - 2 * PADDING,
                           f"↑ {ahead}   ↓ {behind}")

    h_str = data.get("last_commit_hash", "")
    msg = data.get("last_commit_msg", "")
    if h_str:
        divider(d, x + PADDING, next_y + 2, x + w - PADDING)
        body_text(d, x + PADDING, next_y + 10, w - 2 * PADDING, f"{h_str}  {msg}")


def paint_system(d, rect, data, stale=False):
    x, y, w, h = rect
    next_y = header_bar(d, rect, "SYSTEM")
    next_y += 12

    cells = []
    if data.get("cpu_pct") is not None:    cells.append((data["cpu_pct"], "CPU"))
    if data.get("memory_pct") is not None: cells.append((data["memory_pct"], "MEM"))
    if data.get("disk_pct") is not None:   cells.append((data["disk_pct"], "DISK"))
    bp = data.get("battery_pct")
    if bp is not None and bp != 255:       cells.append((bp, "BAT"))

    # Narrow slot (270 px top-left/right) — stack vertically, 4 rows of
    # [val  LABEL ─────── bar]. Wide slot (540 px middle/bottom) — keep
    # 2×2 grid because there's room.
    f_b = font(bold=True)
    f_l = font()
    if w < 350:
        # Vertical stack: each row is a full-width metric.
        row_h = (h - (next_y - y) - 60) // max(len(cells), 1)
        row_h = min(row_h, 60)
        for i, (pct, label) in enumerate(cells):
            ry = next_y + i * row_h
            val = f"{pct}%"
            d.text((x + PADDING, ry), val, fill=INK_BLACK, font=f_b)
            d.text((x + PADDING + 80, ry + 6), label,
                   fill=DIVIDER_GRAY, font=f_l)
            bar_x0 = x + PADDING + 160
            bar_x1 = x + w - PADDING
            bar_y = ry + 18
            d.rectangle((bar_x0, bar_y, bar_x1, bar_y + 10),
                        outline=INK_BLACK, width=1)
            fill = max(1, int((bar_x1 - bar_x0) * pct / 100))
            d.rectangle((bar_x0, bar_y, bar_x0 + fill, bar_y + 10),
                        fill=INK_BLACK)
    else:
        cell_w = (w - 3 * PADDING) // 2
        cell_h = 64
        for i, (pct, label) in enumerate(cells[:4]):
            row, col = i // 2, i % 2
            cx = x + PADDING + col * (cell_w + PADDING)
            cy = next_y + row * (cell_h + 8)
            val = f"{pct}%"
            d.text((cx, cy), val, fill=INK_BLACK, font=f_b)
            d.text((cx + 90, cy + 6), label, fill=DIVIDER_GRAY, font=f_l)
            d.rectangle((cx, cy + 38, cx + cell_w - 8, cy + 46),
                        outline=INK_BLACK, width=1)
            fill = max(1, int((cell_w - 10) * pct / 100))
            d.rectangle((cx, cy + 38, cx + fill, cy + 46), fill=INK_BLACK)

    foot_parts = []
    nd, nu = data.get("net_down_kbps", 0), data.get("net_up_kbps", 0)
    if nd or nu:
        foot_parts.append(f"↓ {nd / 1024:.1f}MB  ↑ {nu / 1024:.1f}MB")
    t = data.get("temp_c")
    if t is not None and t != -32768:
        foot_parts.append(f"{t}°C")
    if foot_parts:
        body_text(d, x + PADDING, y + h - PADDING - BODY_SIZE - 4,
                  w - 2 * PADDING, "  ·  ".join(foot_parts))


def paint_inbox(d, rect, data, stale=False):
    """Aggregated unread count + per-source breakdown."""
    x, y, w, h = rect
    total = data.get("total", 0)
    next_y = header_bar(d, rect, "INBOX", str(total) if total else "")
    next_y += 16
    f = font()
    f_b = font(bold=True)
    sources = (data.get("sources") or [])[:4]
    if not sources:
        body_text(d, x + PADDING, next_y, w - 2 * PADDING, "all caught up")
        return
    row_h = BODY_SIZE + 14
    for src in sources:
        name = src.get("name", "")
        cnt = src.get("count", 0)
        cnt_str = str(cnt)
        cnt_w = d.textlength(cnt_str, font=f_b)
        d.text((x + PADDING, next_y), name, fill=INK_BLACK, font=f)
        d.text((x + w - PADDING - cnt_w, next_y), cnt_str,
               fill=INK_BLACK if cnt > 0 else DIVIDER_GRAY, font=f_b)
        # Dotted leader between name and count.
        name_w = d.textlength(name, font=f)
        leader_x0 = x + PADDING + name_w + 12
        leader_x1 = x + w - PADDING - cnt_w - 12
        cx = leader_x0
        while cx + 2 < leader_x1:
            d.rectangle((cx, next_y + BODY_SIZE - 4,
                         cx + 2, next_y + BODY_SIZE - 2),
                        fill=DIVIDER_GRAY)
            cx += 8
        next_y += row_h
        if next_y > y + h - PADDING: break


def paint_next_meeting(d, rect, data, stale=False):
    """Single upcoming meeting with prominent countdown."""
    x, y, w, h = rect
    start_in = data.get("start_in", "")
    next_y = header_bar(d, rect, "NEXT", start_in)
    next_y += 12

    title = data.get("title", "")
    if title:
        next_y = wrapped_text(d, x + PADDING, next_y,
                              w - 2 * PADDING, BODY_SIZE * 2 + 8, title)
        next_y += 10

    start_at = data.get("start_at", "")
    if start_at:
        box_w = w - 2 * PADDING
        box_h = 50
        d.rectangle((x + PADDING, next_y, x + PADDING + box_w, next_y + box_h),
                    outline=INK_BLACK, width=2)
        f_b = font(bold=True)
        bbox = d.textbbox((0, 0), start_at, font=f_b)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text((x + PADDING + (box_w - tw) // 2,
                next_y + (box_h - th) // 2 - 4),
               start_at, fill=INK_BLACK, font=f_b)
        next_y += box_h + 12

    attendees = data.get("attendees", "")
    if attendees:
        next_y = body_text(d, x + PADDING, next_y, w - 2 * PADDING,
                           f"with {attendees}")

    location = data.get("location", "")
    if location:
        d.text((x + PADDING, next_y), location,
               fill=DIVIDER_GRAY, font=font())


def paint_pr_queue(d, rect, data, stale=False):
    """GitHub PR review queue + your own open PRs."""
    x, y, w, h = rect
    rc = data.get("review_count", 0)
    yc = data.get("your_open_count", 0)
    meta = f"{rc} / {yc}" if (rc or yc) else ""
    next_y = header_bar(d, rect, "PRs", meta)
    next_y += 12

    f = font()
    f_b = font(bold=True)
    items = (data.get("items") or [])[:4]
    if not items:
        body_text(d, x + PADDING, next_y, w - 2 * PADDING, "queue empty — nice")
        return

    row_h = BODY_SIZE * 2 + 16
    for it in items:
        status = it.get("status", "")
        # ASCII / wide-Unicode-safe markers. PingFang Bold variant lacks
        # ▸ ✓ ✕ — renders as .notdef tofu. ● / ○ are reliably present
        # across both Regular and Bold variants.
        marker = "●"
        if status == "yours":      marker = "○"
        elif status == "approved": marker = "+"
        elif status == "blocked":  marker = "!"
        num = it.get("number", "")
        title = it.get("title", "")
        author = it.get("author", "")
        head = f"{marker}  {num}  {title}" if num else f"{marker}  {title}"
        head_trunc = head
        if d.textlength(head_trunc, font=f_b) > w - 2 * PADDING:
            while head_trunc and d.textlength(head_trunc + "...", font=f_b) > w - 2 * PADDING:
                head_trunc = head_trunc[:-1]
            head_trunc += "..."
        d.text((x + PADDING, next_y), head_trunc, fill=INK_BLACK, font=f_b)
        sub_parts = []
        if author: sub_parts.append(f"by {author}")
        if status: sub_parts.append(status)
        if sub_parts:
            d.text((x + PADDING + 38, next_y + BODY_SIZE + 4),
                   "  ·  ".join(sub_parts), fill=DIVIDER_GRAY, font=f)
        next_y += row_h
        if next_y > y + h - PADDING: break


def paint_break_reminder(d, rect, data, stale=False):
    """Health-nudge: time since last break + sitting + eye-rest countdown."""
    x, y, w, h = rect
    next_y = header_bar(d, rect, "BREAK")
    next_y += 16

    f = font()
    f_b = font(bold=True)

    def fmt_mins(m):
        if m is None: return "—"
        if m < 60: return f"{m}m"
        return f"{m // 60}h {m % 60:02d}m"

    rows = []
    if data.get("last_break_min_ago") is not None:
        rows.append(("last break", fmt_mins(data["last_break_min_ago"]) + " ago",
                     data["last_break_min_ago"] > 45))
    if data.get("sitting_min") is not None:
        rows.append(("sitting", fmt_mins(data["sitting_min"]),
                     data["sitting_min"] > 60))
    eye = data.get("next_eye_rest_min")
    if eye is not None:
        if eye < 0:
            rows.append(("eye rest", f"overdue {fmt_mins(-eye)}", True))
        else:
            rows.append(("eye rest", f"in {fmt_mins(eye)}", False))

    row_h = BODY_SIZE + 14
    for label, val, urgent in rows:
        d.text((x + PADDING, next_y), label, fill=INK_BLACK, font=f)
        val_font = f_b if urgent else f
        vw = d.textlength(val, font=val_font)
        d.text((x + w - PADDING - vw, next_y), val,
               fill=INK_BLACK if urgent else DIVIDER_GRAY, font=val_font)
        next_y += row_h

    advice = data.get("advice", "")
    if advice:
        divider(d, x + PADDING, next_y + 4, x + w - PADDING)
        body_text(d, x + PADDING, next_y + 16, w - 2 * PADDING, advice, bold=True)


def paint_deadlines(d, rect, data, stale=False):
    """Upcoming deadlines countdown — list of title + days-remaining."""
    x, y, w, h = rect
    next_y = header_bar(d, rect, "DEADLINES")
    next_y += 12

    f = font()
    f_b = font(bold=True)
    items = (data.get("items") or [])[:5]
    if not items:
        body_text(d, x + PADDING, next_y, w - 2 * PADDING, "no deadlines")
        return

    row_h = BODY_SIZE + 12
    for it in items:
        title = it.get("title", "")
        due = it.get("due_label", "")
        urgent = it.get("is_urgent", False)
        title_font = f_b if urgent else f
        due_w = d.textlength(due, font=f_b) if due else 0
        title_max_w = w - 2 * PADDING - due_w - 16
        title_trunc = title
        if d.textlength(title_trunc, font=title_font) > title_max_w:
            while title_trunc and d.textlength(title_trunc + "...", font=title_font) > title_max_w:
                title_trunc = title_trunc[:-1]
            title_trunc += "..."
        marker = "● " if urgent else "  "
        d.text((x + PADDING, next_y), marker + title_trunc,
               fill=INK_BLACK, font=title_font)
        if due:
            d.text((x + w - PADDING - due_w, next_y), due,
                   fill=INK_BLACK if urgent else DIVIDER_GRAY,
                   font=f_b if urgent else f)
        next_y += row_h
        if next_y > y + h - PADDING: break


PAINTERS = {
    "weather":        paint_weather,
    "todo":           paint_todo,
    "calendar":       paint_calendar,
    "messages":       paint_messages,
    "ai-status":      paint_ai_status,
    "ai-tasks":       paint_ai_tasks,
    "scratch":        paint_scratch,
    "focus":          paint_focus,
    "now-playing":    paint_now_playing,
    "git-status":     paint_git_status,
    "system":         paint_system,
    # v0.6.2 — monitor-side glance widgets.
    "inbox":          paint_inbox,
    "next-meeting":   paint_next_meeting,
    "pr-queue":       paint_pr_queue,
    "break-reminder": paint_break_reminder,
    "deadlines":      paint_deadlines,
}


def paint_empty(d, rect):
    """Empty slot — dashed outline + faint label."""
    x, y, w, h = rect
    # Dashed border.
    for i in range(x + 8, x + w - 8, 14):
        d.line((i, y + 8, i + 7, y + 8), fill=DIVIDER_GRAY)
        d.line((i, y + h - 8, i + 7, y + h - 8), fill=DIVIDER_GRAY)
    for j in range(y + 8, y + h - 8, 14):
        d.line((x + 8, j, x + 8, j + 7), fill=DIVIDER_GRAY)
        d.line((x + w - 8, j, x + w - 8, j + 7), fill=DIVIDER_GRAY)


# ---- top-level render ---------------------------------------------------

def paint_bottom_bar(d: "ImageDraw.ImageDraw", status: dict):
    """Inverted black strip at the very bottom of the canvas. v0.6.3:
    LEFT = battery + transport + age (3 quick-glance status items).
    RIGHT = sleep + settings chips. Other actions (refresh / restart /
    re-pair) moved into the settings page since they're rare.

    `status` dict shape:
        {
          "battery_pct": int / None,   # firmware status_report, v0.6.4
          "transport":   "USB" / "BLE" / None,
          "frame_age":   int seconds since last push / None,
        }
    """
    bar_y = BOTTOM_BAR_Y
    bar_h = BOTTOM_BAR_H
    d.rectangle((0, bar_y, CANVAS_W, bar_y + bar_h), fill=INK_BLACK)
    pad = 20
    f = font_bar()
    f_b = font_bar_bold()
    text_y = bar_y + (bar_h - 22) // 2 - 2

    # ---- LEFT zone: status pieces ----
    pieces = []
    bp = status.get("battery_pct")
    if bp is None:
        pieces.append(("--%", False))
    else:
        pieces.append((f"{bp}%", bp <= 20))   # bold + caller-visible if low
    t = status.get("transport")
    if t:
        pieces.append((t, False))
    age = status.get("frame_age")
    if age is not None:
        age_label = "刚刚" if age < 5 else (
            f"{age} 秒前" if age < 60 else f"{age // 60} 分钟前")
        pieces.append((age_label, False))

    cx = pad
    for i, (text, bold) in enumerate(pieces):
        if i > 0:
            d.line((cx, bar_y + 14, cx, bar_y + bar_h - 14), fill=140, width=1)
            cx += 14
        fnt = f_b if bold else f
        d.text((cx, text_y), text, fill=255, font=fnt)
        cx += d.textlength(text, font=fnt) + 14

    # ---- RIGHT zone: sleep + settings chips ----
    actions = ["睡眠", "设置"]
    chip_pad = 20
    sep_w = 14
    total_w = sum(d.textlength(a, font=f_b) for a in actions) \
            + chip_pad * 2 * len(actions) \
            + sep_w * (len(actions) - 1)
    chip_x = CANVAS_W - pad - total_w
    if chip_x < cx + 16:
        return   # left + right would collide; safer to skip right zone

    for i, label in enumerate(actions):
        if i > 0:
            d.line((chip_x, bar_y + 14, chip_x, bar_y + bar_h - 14),
                   fill=140, width=1)
            chip_x += sep_w
        d.text((chip_x + chip_pad, text_y), label, fill=255, font=f_b)
        chip_x += d.textlength(label, font=f_b) + chip_pad * 2


def render_image(widget_snapshot: Iterable[dict],
                 status: "dict | None" = None) -> "Image.Image":
    if Image is None:
        raise RuntimeError("install Pillow")

    img = Image.new("L", (CANVAS_W, CANVAS_H), 255)
    d = ImageDraw.Draw(img)

    seen = set()
    for w in widget_snapshot:
        slot = w.get("slot")
        wtype = w.get("type")
        rect = SLOT_RECTS.get(slot)
        fn = PAINTERS.get(wtype)
        if rect and fn:
            seen.add(slot)
            try:
                fn(d, rect, w.get("data") or {}, w.get("stale", False))
            except Exception as e:
                d.text((rect[0] + 16, rect[1] + 16),
                       f"render err: {e!r}", fill=INK_BLACK, font=font())

    for slot, rect in SLOT_RECTS.items():
        if slot == "full" or slot in seen:
            continue
        paint_empty(d, rect)

    # Structural dividers — drawn AFTER widget content so they sit on top
    # of any widget chrome and bind the grid together visually. Made
    # generously chunky (~4-8 px) so 4bpp packing + e-ink low-contrast
    # don't smear them into invisibility.
    mid_y = SLOT_RECTS["middle"][1]

    # Single vertical 3 px black line between top-left / top-right.
    d.rectangle((269, 16, 272, mid_y - 16), fill=INK_BLACK)

    # Bottom status/settings bar (always rendered).
    paint_bottom_bar(d, status or {})

    return img


def to_4bpp_packed(img: "Image.Image") -> bytes:
    """Convert PIL L-mode image to M5EPD 4bpp packed buffer.

    M5EPD convention: 0=white, 15=black. PIL L: 0=black, 255=white.
    So invert + quantize. 2 pixels per byte, high nibble first.
    """
    if img.mode != "L":
        img = img.convert("L")
    if img.size != (CANVAS_W, CANVAS_H):
        img = img.resize((CANVAS_W, CANVAS_H))
    pixels = img.tobytes()   # row-major, 1 byte per pixel
    out = bytearray(CANVAS_W * CANVAS_H // 2)
    for i in range(0, len(pixels), 2):
        a = pixels[i]
        b = pixels[i + 1] if i + 1 < len(pixels) else 255
        # invert + quantize to 4 bits
        na = (255 - a) >> 4
        nb = (255 - b) >> 4
        out[i // 2] = (na << 4) | nb
    return bytes(out)


# ---- legacy PNG preview API (kept for /widgets/preview HTTP endpoint) ----

def render_preview_png(widget_snapshot: Iterable[dict], theme: str = "minimal",
                       status: "dict | None" = None) -> bytes:
    img = render_image(widget_snapshot, status=status)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---- CLI ---------------------------------------------------------------

if __name__ == "__main__":
    import argparse, json, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--out", default="-")
    a = ap.parse_args()
    if a.sample:
        widgets = [
            {"slot": "top-left", "type": "weather", "data": {
                "location": "上海",
                "current": {"temp_c": 22, "condition": "多云"},
                "forecast": [{"day": "明", "high": 26, "low": 19, "condition": "晴"}]
            }},
            {"slot": "top-right", "type": "ai-status", "data": {
                "session_name": "claude-card",
                "model": "Opus 4.7",
                "task": "测试 v0.6 服务端渲染 + 单字号设计",
                "context": {"used": 45000, "limit": 200000}
            }},
            {"slot": "middle", "type": "calendar", "data": {
                "now_iso": "2026-05-20T18:30",
                "events": [
                    {"start": "10:00", "title": "晨会"},
                    {"start": "16:00", "title": "设计评审"},
                    {"start": "19:00", "title": "晚饭"}
                ]
            }},
            {"slot": "bottom", "type": "todo", "data": {
                "title": "未来 3 天",
                "items": [
                    {"text": "v0.6 端到端跑通", "tag": "today"},
                    {"text": "服务端渲染 + 一字号", "tag": "today"},
                    {"text": "回邮件", "tag": "overdue"}
                ]
            }}
        ]
    else:
        widgets = json.load(sys.stdin)
    # CLI sample: fake a status payload so the bottom bar isn't blank.
    from datetime import datetime as _dt
    fake_status = {
        "transport":  "USB",
        "ble_paired": True,
        "time":       _dt.now().strftime("%H:%M"),
        "frame_age":  5,
    }
    png = render_preview_png(widgets, status=fake_status)
    if a.out == "-":
        sys.stdout.buffer.write(png)
    else:
        with open(a.out, "wb") as f: f.write(png)
        print(f"wrote {a.out}", file=sys.stderr)
