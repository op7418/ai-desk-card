#!/usr/bin/env python3
"""Generate a 4bpp-friendly anime assistant bust for the e-ink card.

Draws at 3x resolution with Pillow, downsamples with LANCZOS for clean
anti-aliased curves, then quantizes to 4 gray levels (the M5Paper panel
is 4bpp). Output: assets/assistant_avatar.png (270x280, mode L).

Design constraints (e-ink):
  - High contrast only: black hair/outlines, white face/shirt, one mid-gray.
  - No fine halftone — it flickers on partial refresh.
  - Static: rendered once, pasted into the top-left slot; never changes.
"""
from __future__ import annotations
import os
from PIL import Image, ImageDraw

S = 3                      # supersample factor
W, H = 270, 280            # target size = top-left slot
OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "assistant_avatar.png")

INK = 0                    # black
PAPER = 255                # white
GRAY = 150                 # mid tone (hair highlight / blush)
HAIR = 45                  # near-black hair


def pts(*pairs):
    """Scale a sequence of (x,y) points -> [(x*S,y*S), ...]."""
    return [(int(x * S), int(y * S)) for x, y in pairs]


def bb(x0, y0, x1, y1):
    """Scale a bounding box for ellipse/arc/rounded_rectangle."""
    return (int(x0 * S), int(y0 * S), int(x1 * S), int(y1 * S))


def main():
    img = Image.new("L", (W * S, H * S), PAPER)
    d = ImageDraw.Draw(img)

    def poly(points, fill=None, outline=None, width=2):
        d.polygon(pts(*points), fill=fill)
        if outline is not None:
            d.line(pts(*points, points[0]), fill=outline, width=width * S, joint="curve")

    # ---- hair back (big silhouette behind head + long side strands) ----
    d.ellipse(bb(60, 30, 210, 235), fill=HAIR)
    poly([(72, 120), (58, 190), (52, 262), (92, 262), (100, 170)], fill=HAIR)
    poly([(198, 120), (212, 190), (218, 262), (178, 262), (170, 170)], fill=HAIR)

    # ---- torso / shoulders (blazer) ----
    poly([(78, 280), (86, 228), (104, 206), (135, 198), (166, 206),
          (184, 228), (192, 280)], fill=PAPER, outline=INK, width=3)
    # collar V
    poly([(112, 205), (135, 238), (158, 205), (143, 200), (135, 214), (127, 200)],
         fill=None, outline=INK, width=2)
    # shirt accent (tie)
    poly([(135, 214), (128, 226), (135, 262), (142, 226)], fill=HAIR)
    # shoulder epaulette lines
    d.line(pts((92, 224), (118, 232)), fill=INK, width=2 * S)
    d.line(pts((178, 224), (152, 232)), fill=INK, width=2 * S)

    # ---- neck ----
    poly([(122, 180), (148, 180), (150, 210), (120, 210)], fill=PAPER,
         outline=INK, width=2)

    # ---- face (egg with pointed chin) ----
    face = [(135, 52), (161, 56), (179, 72), (189, 96), (190, 122),
            (183, 146), (168, 168), (150, 186), (135, 194), (120, 186),
            (102, 168), (87, 146), (80, 122), (81, 96), (91, 72), (109, 56)]
    poly(face, fill=PAPER, outline=INK, width=3)

    # ---- ears ----
    d.ellipse(bb(76, 118, 90, 142), fill=PAPER, outline=INK, width=2 * S)
    d.ellipse(bb(180, 118, 194, 142), fill=PAPER, outline=INK, width=2 * S)

    # ---- bangs (front hair over forehead) ----
    poly([(80, 116), (84, 80), (104, 58), (135, 50), (168, 58), (188, 82),
          (190, 116), (176, 96), (166, 112), (152, 92), (135, 110),
          (118, 92), (104, 112), (92, 96)], fill=HAIR, outline=INK, width=1)
    # side locks framing cheeks
    poly([(80, 110), (74, 160), (78, 205), (94, 200), (92, 150)], fill=HAIR)
    poly([(190, 110), (196, 160), (192, 205), (176, 200), (178, 150)], fill=HAIR)

    # ---- eyes ----
    for cx in (111, 159):
        d.ellipse(bb(cx - 15, 122, cx + 15, 152), fill=PAPER, outline=INK, width=2 * S)
        d.ellipse(bb(cx - 8, 126, cx + 8, 150), fill=HAIR)
        d.ellipse(bb(cx - 4, 132, cx + 4, 146), fill=INK)
        d.arc(bb(cx - 17, 118, cx + 17, 140), 190, 350, fill=INK, width=3 * S)
        d.ellipse(bb(cx - 5, 129, cx - 1, 135), fill=PAPER)
        d.arc(bb(cx - 13, 108, cx + 13, 124), 195, 345, fill=INK, width=2 * S)

    # ---- nose + mouth ----
    d.line(pts((135, 150), (132, 160), (137, 161)), fill=GRAY, width=2 * S)
    d.arc(bb(124, 160, 146, 178), 20, 160, fill=INK, width=2 * S)

    # ---- subtle blush ----
    d.ellipse(bb(92, 150, 108, 158), fill=GRAY)
    d.ellipse(bb(162, 150, 178, 158), fill=GRAY)

    # ---- headset: band over head ----
    d.arc(bb(66, 34, 204, 120), 200, 340, fill=HAIR, width=6 * S)
    d.rounded_rectangle(bb(184, 116, 202, 146), radius=6 * S, fill=HAIR,
                        outline=INK, width=2 * S)
    d.line(pts((190, 144), (182, 170), (155, 176)), fill=HAIR, width=3 * S)
    d.ellipse(bb(150, 172, 160, 182), fill=INK)

    # ---- downsample + quantize to 4 levels (0/85/170/255) ----
    small = img.resize((W, H), Image.LANCZOS)
    lut = [min(3, (v * 4) // 256) * 85 for v in range(256)]
    out = small.point(lut)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out.save(OUT)
    print(f"wrote {OUT} ({W}x{H}, levels={sorted(set(out.getdata()))})")


if __name__ == "__main__":
    main()
