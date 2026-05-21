---
description: Inspect / clear / preview the ai-desk-card widget cache.
---

Subcommands:
- (none) — print current widget cache
- `preview [out.png]` — render 540×960 PNG via Pillow + open
- `clear [slot]` — wipe a slot (no slot = all)
- `pair-status` — show daemon ↔ device connection state
- `unpair` — forward unpair to device

!`bash "$CLAUDE_PLUGIN_ROOT/scripts/widget.sh" "$ARGUMENTS"`
