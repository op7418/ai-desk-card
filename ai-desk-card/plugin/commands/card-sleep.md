---
description: Push the name-card sleep frame + put the device into deep sleep.
---

Renders `ai-desk-card/assets/profile.yaml` into a 540×960 e-ink frame
(avatar / name / bio / tags / QR), pushes it to the device, then commands
the device into ESP32 deep sleep. e-ink retains the last frame at zero
power, so the user sees their name card until they power-cycle the
device.

Edit `ai-desk-card/assets/profile.yaml` directly if the user wants to
update their card content. Drop a custom `assets/avatar.png` and/or
`assets/qr.png` in the same directory (placeholders are used otherwise).

!`bash "$CLAUDE_PLUGIN_ROOT/scripts/sleep.sh" "$ARGUMENTS"`
