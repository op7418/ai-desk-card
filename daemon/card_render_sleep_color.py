"""Sleep / business-card renderer for M5Paper Color (600×400, Spectra 6).

Counterpart to V1.1's card_render_sleep.py. Reads the same
assets/profile.yaml so existing users don't reconfigure anything. Output
is RGB 600×400 — Color device renders the card and then deep-sleeps; the
panel retains the last frame at 0 W (e-ink physics, same as V1.1).

Layout: name big-left, tagline + bio + tags right; QR placeholder
bottom-left, footer thin at very bottom. Color used sparingly:
- Big name circle in blue
- Tag bullets in colored chips (job/city/web get red/yellow/green)
- Body all black for maximum contrast
"""

from __future__ import annotations
from PIL import Image, ImageDraw
import os
import sys

# Reuse the color renderer's font + palette so look stays consistent.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from card_render_color import font, COL  # noqa: E402

CANVAS_W = 600
CANVAS_H = 400


def _load_profile(path: str) -> dict:
    """Minimal YAML loader for profile.yaml. Reuses the parser from
    card_render_sleep (the V1.1 sleep renderer) if available — same shape."""
    try:
        import card_render_sleep as crs
        return crs.load_profile(path) if hasattr(crs, "load_profile") \
            else (crs._load_yaml(path) if hasattr(crs, "_load_yaml") else {})
    except Exception:
        # Inline fallback (subset of expected schema)
        out, current_key = {}, None
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\n")
                if not line.strip() or line.lstrip().startswith("#"): continue
                indent = len(line) - len(line.lstrip(" "))
                stripped = line.strip()
                if indent == 0 and ":" in stripped:
                    k, _, v = stripped.partition(":")
                    v = v.strip().strip('"').strip("'")
                    if v == "": current_key = k.strip(); out[current_key] = []
                    else: out[k.strip()] = v
                elif stripped.startswith("- ") and current_key:
                    out[current_key].append(stripped[2:].strip().strip('"'))
        return out


def render_card(profile: dict) -> Image.Image:
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), COL["paper"])
    d = ImageDraw.Draw(img)

    name = profile.get("name", "")
    tagline = profile.get("tagline", "")
    bio_lines = profile.get("bio_lines") or []
    tags = profile.get("tags") or []
    footer = profile.get("footer", "ai-desk-card · sleeping")

    # ---- Top: avatar circle + name ----
    avatar_x, avatar_y, avatar_r = 60, 80, 50
    # Background circle in blue
    d.ellipse([avatar_x - avatar_r, avatar_y - avatar_r,
               avatar_x + avatar_r, avatar_y + avatar_r],
              fill=COL["blue"])
    # First glyph of name centred
    initial = name[:1] if name else "•"
    f_init = font(60)
    iw = d.textlength(initial, font=f_init)
    d.text((avatar_x - iw / 2, avatar_y - 38), initial,
           fill=COL["paper"], font=f_init)

    # Name + tagline to the right
    d.text((avatar_x + avatar_r + 24, avatar_y - 40), name,
           fill=COL["ink"], font=font(46))
    if tagline:
        d.text((avatar_x + avatar_r + 24, avatar_y + 14), tagline,
               fill=COL["ink"], font=font(22))

    # ---- Divider ----
    d.line([40, 160, CANVAS_W - 40, 160], fill=COL["ink"], width=2)

    # ---- Bio lines ----
    y = 180
    f_bio = font(22)
    for line in (bio_lines or [])[:3]:
        # truncate if too long
        text = line
        max_w = CANVAS_W - 80
        if d.textlength(text, font=f_bio) > max_w:
            while text and d.textlength(text + "…", font=f_bio) > max_w:
                text = text[:-1]
            text += "…"
        d.text((40, y), text, fill=COL["ink"], font=f_bio)
        y += 32

    # ---- Tags row (job / city / web) ----
    tag_colors = [COL["red"], COL["yellow"], COL["green"], COL["blue"]]
    y = 290
    x = 40
    for i, tag in enumerate(tags[:3]):
        if isinstance(tag, dict):
            icon = tag.get("icon", "")
            text = tag.get("text", "")
        else:
            icon, text = "", str(tag)
        col = tag_colors[i % len(tag_colors)]
        # icon chip
        chip_w = int(d.textlength(icon, font=font(18))) + 18
        d.rectangle([x, y, x + chip_w, y + 30], fill=col)
        d.text((x + 9, y + 4), icon, fill=COL["paper"], font=font(18))
        # text after chip
        d.text((x + chip_w + 8, y + 4), text, fill=COL["ink"], font=font(22))
        x += chip_w + 8 + int(d.textlength(text, font=font(22))) + 24

    # ---- Footer ----
    d.rectangle([0, CANVAS_H - 28, CANVAS_W, CANVAS_H], fill=COL["ink"])
    f_foot = font(18)
    fw = d.textlength(footer, font=f_foot)
    d.text(((CANVAS_W - fw) / 2, CANVAS_H - 24), footer,
           fill=COL["paper"], font=f_foot)

    return img


def render_sleep(profile_path: str = None) -> Image.Image:
    """Convenience: load profile + render. Defaults to ../assets/profile.yaml."""
    if profile_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        profile_path = os.path.join(here, "..", "assets", "profile.yaml")
    profile = _load_profile(profile_path)
    return render_card(profile)
