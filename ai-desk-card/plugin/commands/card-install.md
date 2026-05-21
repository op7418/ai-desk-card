---
description: Detect or flash the ai-desk-card firmware.
---

Subcommands:
- `detect` (default) — read [boot] line over serial, print firmware version
- `flash` — flash the local build at `.pio/build/card/firmware.bin`
            (build first with `pio run -e card` from `ai-desk-card/`).
            Always prompts for confirmation; sha256 check on download path.

!`bash "$CLAUDE_PLUGIN_ROOT/scripts/install.sh" "$ARGUMENTS"`
