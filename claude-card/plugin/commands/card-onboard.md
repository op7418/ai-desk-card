---
description: First-time setup wizard — detects daemon/USB/firmware and walks you through whatever's missing.
---

Run the card-onboard skill. AI will probe daemon + connection + firmware
state, then guide you through whichever step (start daemon / plug USB /
flash firmware / pair BLE) needs handling.

Use this:
- first time you connect a claude-card device
- after moving setup to a new machine
- when "card 没反应" / no widget shows up

!`bash "$CLAUDE_PLUGIN_ROOT/skills/card-onboard/scripts/probe.sh"`
