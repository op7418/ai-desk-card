---
description: Provision Wi-Fi credentials to the ai-desk-card device (one-time, via current transport).
---

Usage: `/card-wifi-setup <SSID> <password>`

Sends a `cmd:wifi_set` to the device through whatever transport the
daemon is currently using (serial / BLE / Wi-Fi itself). Device stores
the credentials in NVS and tries to connect. Once connected it shows up
in mDNS as `_ai-desk-card._tcp` and the next daemon restart will pick
Wi-Fi as the preferred transport.

To clear credentials (forget Wi-Fi): pass an empty string for SSID:
`/card-wifi-setup ""`

!`bash "$CLAUDE_PLUGIN_ROOT/scripts/wifi_setup.sh" "$ARGUMENTS"`
