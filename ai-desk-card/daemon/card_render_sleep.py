#!/usr/bin/env python3
"""ai-desk-card sleep-frame renderer — the "digital business card" image
shown on the e-ink panel when the device deep-sleeps.

Layout (540×960 portrait):

    ┌────────────────────────────────────┐
    │                                    │
    │   ╭───╮                            │
    │   │ a │   NAME (big)               │
    │   ╰───╯   tagline ─────────────    │
    │                                    │
    │  ─────────────────────────         │
    │                                    │
    │   bio paragraph line 1             │
    │   bio paragraph line 2             │
    │   bio paragraph line 3             │
    │                                    │
    │  ─────────────────────────         │
    │                                    │
    │   💼  产品 · 设计                  │
    │   📍  北京                         │
    │                                    │
    │  ─────────────────────────         │
    │                                    │
    │            ┌──────┐                │
    │            │  QR  │                │
    │            │ code │                │
    │            └──────┘                │
    │       qr label centered            │
    │                                    │
    │       footer (very bottom)         │
    └────────────────────────────────────┘

Reads `assets/profile.yaml` for content. Avatar + QR are PNG files in
`assets/` (placeholders if missing).
"""
from __future__ import annotations
import io
import os
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None

# Reuse core constants / font helpers from the widget renderer.
import card_render

CANVAS_W, CANVAS_H = 540, 960
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")


# ---- profile loader -----------------------------------------------------

def _load_yaml(path: str) -> dict:
    """Tiny YAML loader — handles the subset we use (strings, ints, lists
    of strings, lists of dicts). Avoids the yaml package dependency."""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    root = {}
    i = 0
    stack = [(0, root, None)]   # (indent, container, last_key)

    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        # Pop stack to current indent.
        while stack and stack[-1][0] > indent:
            stack.pop()

        parent = stack[-1][1]

        if line.startswith("- "):
            # List item.
            item_str = line[2:].strip()
            if ":" in item_str and not item_str.startswith('"'):
                # Dict-shaped list item.
                key, _, val = item_str.partition(":")
                item = {key.strip(): _parse_value(val.strip())}
                if isinstance(parent, list):
                    parent.append(item)
                stack.append((indent + 2, item, None))
            else:
                if isinstance(parent, list):
                    parent.append(_parse_value(item_str))
        elif ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val == "":
                # Nested container — assume list (the only multi-line case
                # in our schema).
                child = []
                if isinstance(parent, dict):
                    parent[key] = child
                stack.append((indent + 2, child, key))
            else:
                if isinstance(parent, dict):
                    parent[key] = _parse_value(val)

    return root


def _parse_value(s: str):
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if s.isdigit():
        return int(s)
    return s


def load_profile(path: Optional[str] = None) -> dict:
    """Load profile.yaml, return a dict with safe defaults for missing fields."""
    if path is None:
        path = os.path.join(ASSETS_DIR, "profile.yaml")
    profile = {}
    if os.path.exists(path):
        try:
            profile = _load_yaml(path)
        except Exception as e:
            print(f"[sleep] profile.yaml parse fail: {e!r}", flush=True)
    # Fill defaults.
    profile.setdefault("name", "ai-desk-card")
    profile.setdefault("tagline", "")
    profile.setdefault("bio_lines", [])
    profile.setdefault("tags", [])
    profile.setdefault("qr_label", "")
    profile.setdefault("footer", "ai-desk-card · sleeping")
    return profile


# ---- image asset loaders (with placeholders) ----------------------------

def _circular_avatar(name: str, size: int = 180) -> "Image.Image":
    """Placeholder avatar: gray-filled circle with the first character of
    `name` centred in white. Used when no avatar_image is provided."""
    img = Image.new("L", (size, size), 255)
    d = ImageDraw.Draw(img)
    # Gray circle background.
    d.ellipse((0, 0, size - 1, size - 1), fill=160)
    # Initial character.
    initial = name[0] if name else "?"
    font_size = int(size * 0.55)
    try:
        f = card_render.font(bold=True)
        # font() returns the body 28pt font — too small. We need a bigger
        # variant for this single use. Build inline.
        for p in card_render._FONT_PATHS_BOLD:
            if os.path.exists(p):
                f = ImageFont.truetype(p, font_size, index=1)
                break
    except Exception:
        f = ImageFont.load_default()
    bbox = d.textbbox((0, 0), initial, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) // 2 - bbox[0], (size - th) // 2 - bbox[1] - size // 20),
           initial, fill=255, font=f)
    return img


def _placeholder_qr(size: int = 280) -> "Image.Image":
    """Placeholder QR: a recognisable grid pattern so the user knows where
    to drop their real qr.png. NOT a scannable QR code."""
    img = Image.new("L", (size, size), 255)
    d = ImageDraw.Draw(img)
    # Outer border.
    d.rectangle((0, 0, size - 1, size - 1), outline=0, width=4)
    # Three corner finder patterns (top-left, top-right, bottom-left).
    finder_sz = size // 4
    pad = size // 24
    for cx, cy in [(pad, pad),
                   (size - pad - finder_sz, pad),
                   (pad, size - pad - finder_sz)]:
        d.rectangle((cx, cy, cx + finder_sz, cy + finder_sz), outline=0, width=4)
        inner = finder_sz // 3
        d.rectangle((cx + inner, cy + inner,
                     cx + finder_sz - inner, cy + finder_sz - inner), fill=0)
    # Scattered "data" squares for visual.
    import random
    random.seed(42)
    cell = size // 16
    for r in range(2, 14):
        for c in range(2, 14):
            # Avoid the finder zones.
            if (r < 5 and c < 5) or (r < 5 and c > 10) or (r > 10 and c < 5):
                continue
            if random.random() < 0.45:
                x, y = c * cell, r * cell
                d.rectangle((x, y, x + cell - 2, y + cell - 2), fill=0)
    # Centred placeholder label.
    f = card_render.font()
    label = "QR placeholder"
    bbox = d.textbbox((0, 0), label, font=f)
    tw = bbox[2] - bbox[0]
    bg_pad = 8
    cx, cy = size // 2, size // 2
    d.rectangle((cx - tw // 2 - bg_pad, cy - 14 - bg_pad,
                 cx + tw // 2 + bg_pad, cy + 14 + bg_pad), fill=255)
    d.text((cx - tw // 2, cy - 14), label, fill=0, font=f)
    return img


def _apply_circle_mask(img: "Image.Image") -> "Image.Image":
    """Crop `img` to a circle by compositing over white with a circular
    mask. e-ink output is grayscale (no alpha), so result is L-mode."""
    if img.mode != "L":
        img = img.convert("L")
    size = min(img.size)
    img = img.resize((size, size))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("L", (size, size), 255)
    out.paste(img, (0, 0), mask)
    return out


def load_avatar(profile: dict, size: int = 180) -> "Image.Image":
    name = profile.get("avatar_image")
    if name:
        path = os.path.join(ASSETS_DIR, name)
        if os.path.exists(path):
            try:
                img = Image.open(path).convert("L")
                # Square-crop centre then scale to size.
                w, h = img.size
                short = min(w, h)
                img = img.crop(((w - short) // 2, (h - short) // 2,
                               (w + short) // 2, (h + short) // 2))
                img = img.resize((size, size))
                return _apply_circle_mask(img)
            except Exception as e:
                print(f"[sleep] avatar load fail: {e!r}", flush=True)
    return _circular_avatar(profile.get("name", "?"), size)


def load_qr(profile: dict, size: int = 280) -> "Image.Image":
    name = profile.get("qr_image")
    if name:
        path = os.path.join(ASSETS_DIR, name)
        if os.path.exists(path):
            try:
                img = Image.open(path).convert("L")
                img = img.resize((size, size))
                return img
            except Exception as e:
                print(f"[sleep] qr load fail: {e!r}", flush=True)
    return _placeholder_qr(size)


# ---- main render -------------------------------------------------------

def render_sleep_frame(profile: Optional[dict] = None) -> "Image.Image":
    if Image is None:
        raise RuntimeError("install Pillow")
    if profile is None:
        profile = load_profile()

    img = Image.new("L", (CANVAS_W, CANVAS_H), 255)
    d = ImageDraw.Draw(img)

    PADDING = 32
    DIVIDER_GRAY = 0x88
    INK = 0

    # ---- Layout budget (computed up front so bio + tags know where the
    # QR zone starts). Top section is the avatar+name row. QR is anchored
    # to the bottom. Bio fills the middle, tags stack just above QR.
    line_h = card_render.BODY_SIZE + 10
    qr_size = 220
    footer_h = 30
    qr_label_h = 36
    qr_y = CANVAS_H - footer_h - qr_label_h - qr_size - 16
    qr_zone_top = qr_y - 32

    # --- avatar + name row (top) -----------------------------------------
    avatar_size = 160
    avatar = load_avatar(profile, size=avatar_size)
    avatar_x, avatar_y = PADDING, 40
    img.paste(avatar, (avatar_x, avatar_y))

    name_x = avatar_x + avatar_size + 24
    name_w = CANVAS_W - name_x - PADDING
    # Name big — use auto-fit-style shrinking so long names don't overflow.
    name_font = None
    for sz in (60, 52, 44, 36):
        for p in card_render._FONT_PATHS_BOLD:
            if os.path.exists(p):
                try:
                    f = ImageFont.truetype(p, sz, index=1)
                    if d.textlength(profile.get("name", ""), font=f) <= name_w:
                        name_font = f
                        break
                except Exception: continue
        if name_font: break
    if name_font is None:
        name_font = card_render.font(bold=True)
    d.text((name_x, avatar_y + 18), profile.get("name", ""),
           fill=INK, font=name_font)

    tagline = profile.get("tagline", "")
    if tagline:
        # Auto-fit tagline so long ones don't get clipped.
        tag_font = card_render.font()
        text = tagline
        while text and d.textlength(text + ("..." if text != tagline else ""),
                                     font=tag_font) > name_w:
            text = text[:-1]
        if text != tagline: text += "..."
        d.text((name_x, avatar_y + 92), text,
               fill=DIVIDER_GRAY, font=tag_font)

    # Divider under header row.
    y = avatar_y + avatar_size + 24
    d.rectangle((PADDING, y, CANVAS_W - PADDING, y + 2), fill=INK)

    # --- bio paragraphs (wrap multi-line, hard-stop above tag rows) -----
    y += 28
    f = card_render.font()
    max_w = CANVAS_W - 2 * PADDING
    tag_count = len(profile.get("tags") or [])
    tag_row_h = line_h + 4
    tags_block_h = tag_count * tag_row_h

    # Layout budget bottom-up:
    #   qr_zone_top          ← QR divider, fixed
    #   tag_start_y          = qr_zone_top - tags_block_h - 8
    #   divider_y            = tag_start_y - 18
    #   bio_cap_y            = divider_y - 24   ← bio must stop here
    tag_start_y = qr_zone_top - tags_block_h - 8
    divider_y   = tag_start_y - 18
    bio_cap_y   = divider_y - 24
    for line in profile.get("bio_lines", []):
        if y > bio_cap_y:
            break
        if not line:
            y += line_h // 2
            continue
        cur = ""
        for ch in line:
            trial = cur + ch
            if d.textlength(trial, font=f) > max_w:
                if cur:
                    d.text((PADDING, y), cur, fill=INK, font=f)
                    y += line_h
                    if y > bio_cap_y: break
                    cur = ch
                else:
                    cur = trial
            else:
                cur = trial
        if cur and y <= bio_cap_y:
            d.text((PADDING, y), cur, fill=INK, font=f)
            y += line_h

    # (Tags row is bottom-anchored to the QR zone — see below — so we
    # don't add a divider before them here; the bottom-anchored divider
    # above the QR doubles as the section break.)

    # --- tag chips. Layout coords pre-computed above; just draw here.
    f_bold = card_render.font(bold=True)
    tags_visible = (profile.get("tags") or [])[:4]
    d.rectangle((PADDING, divider_y, CANVAS_W - PADDING, divider_y + 2),
                fill=INK)
    for i, tag in enumerate(tags_visible):
        ty = tag_start_y + i * tag_row_h
        icon = tag.get("icon", "")
        text = tag.get("text", "")
        if icon:
            label = icon.upper()
            lw = d.textlength(label, font=f_bold) + 16
            d.rectangle((PADDING, ty, PADDING + lw, ty + line_h - 6),
                        outline=INK, width=2)
            d.text((PADDING + 8, ty + 2), label, fill=INK, font=f_bold)
            d.text((PADDING + lw + 16, ty + 2), text, fill=INK, font=f)
        else:
            d.text((PADDING, ty + 2), text, fill=INK, font=f)

    # --- QR section (coordinates already computed above) ----------------
    qr_x = (CANVAS_W - qr_size) // 2

    # Divider just above the QR block.
    d.rectangle((PADDING, qr_y - 24, CANVAS_W - PADDING, qr_y - 22), fill=INK)

    qr_img = load_qr(profile, size=qr_size)
    img.paste(qr_img, (qr_x, qr_y))

    qr_label = profile.get("qr_label", "")
    if qr_label:
        f = card_render.font()
        bbox = d.textbbox((0, 0), qr_label, font=f)
        tw = bbox[2] - bbox[0]
        d.text(((CANVAS_W - tw) // 2, qr_y + qr_size + 6),
               qr_label, fill=INK, font=f)

    # --- footer (always at very bottom, never overlaps QR label) --------
    footer = profile.get("footer", "")
    if footer:
        f = card_render.font()
        bbox = d.textbbox((0, 0), footer, font=f)
        tw = bbox[2] - bbox[0]
        d.text(((CANVAS_W - tw) // 2, CANVAS_H - footer_h),
               footer, fill=DIVIDER_GRAY, font=f)

    return img


# ---- CLI ---------------------------------------------------------------

if __name__ == "__main__":
    import argparse, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="-")
    ap.add_argument("--profile", default=None,
                    help="path to profile.yaml (default: ../assets/profile.yaml)")
    args = ap.parse_args()
    profile = load_profile(args.profile)
    img = render_sleep_frame(profile)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()
    if args.out == "-":
        sys.stdout.buffer.write(data)
    else:
        with open(args.out, "wb") as f: f.write(data)
        print(f"wrote {args.out}", file=sys.stderr)
