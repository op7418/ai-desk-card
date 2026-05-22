#!/usr/bin/env python3
"""Pre-render the V1.1 sleep / business card and save it as raw 4bpp
packed bytes for the firmware to load from LittleFS at boot.

After running, flash the data/ partition once:
    pio run -e card -t uploadfs

The firmware reads /sleep_card.bin from LittleFS when the idle timer
fires (no daemon needed) and blits it before entering deep sleep.

Card content comes from assets/profile.yaml — same source as the
daemon's `/card-sleep` flow. Edit profile.yaml + re-run this script
to refresh.
"""

from __future__ import annotations
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "daemon"))

import card_render_sleep as crs  # noqa: E402
import card_render as cr          # noqa: E402  (to_4bpp_packed lives here)
from PIL import Image             # noqa: E402

OUT = os.path.join(REPO_ROOT, "data", "sleep_card.bin")
PROFILE = os.path.join(REPO_ROOT, "assets", "profile.yaml")
PANEL_W, PANEL_H = 540, 960   # V1.1 panel native portrait


def main():
    profile = crs.load_profile(PROFILE)
    print(f"[render] profile: name={profile.get('name', '?')!r}")
    img = crs.render_sleep_frame(profile)
    if img.size != (PANEL_W, PANEL_H):
        print(f"[render] resize {img.size} → ({PANEL_W}, {PANEL_H})")
        img = img.resize((PANEL_W, PANEL_H))
    # Reuse the daemon's canonical packer so the byte layout exactly
    # matches what V1.1 firmware expects (M5EPD: 0=white, 15=black —
    # inverted from PIL — packed two pixels per byte, high nibble first).
    packed = cr.to_4bpp_packed(img.convert("L"))
    expected = PANEL_W * PANEL_H // 2
    assert len(packed) == expected, f"size mismatch: {len(packed)} != {expected}"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(packed)
    print(f"[ok] wrote {len(packed)} B → {OUT}")
    print(f"[next] pio run -e card -t uploadfs  # flashes data/ to LittleFS")


if __name__ == "__main__":
    main()
