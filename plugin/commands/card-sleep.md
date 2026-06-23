---
description: Push the name-card sleep frame; V1.1 deep-sleeps, PaperS3 shows sleep-card only.
---

Renders `ai-desk-card/assets/profile.yaml` into a 540×960 e-ink frame
(avatar / name / bio / tags / QR) and pushes it to the device. On M5Paper
V1.1, the daemon then commands ESP32 deep sleep, so e-ink retains the last
frame at near-zero power. On PaperS3, this command displays the sleep-card
frame only; PaperS3 deep sleep is not enabled.

Edit `ai-desk-card/assets/profile.yaml` directly if the user wants to
update their card content. Drop a custom `assets/avatar.png` and/or
`assets/qr.png` in the same directory (placeholders are used otherwise).

PaperS3 onboarding keeps the dashboard on screen. Run `/card-sleep` or
`scripts\onboard_papers3.py --push-sleep-card` only when you want to display
the name-card frame now.

!`bash "$CLAUDE_PLUGIN_ROOT/scripts/sleep.sh" "$ARGUMENTS"`
