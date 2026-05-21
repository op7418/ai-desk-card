# AI Desk Card

A glanceable e-ink 副屏 for Claude Code. The M5Paper sits next to your
monitor and shows weather, todos, today's calendar, message previews, and
the running AI's status. Data is pushed by Claude (via a Skill); the
device just renders.

This is a v0.8 successor track to [`../src/`](../src/) (the original buddy
firmware). The two live side-by-side in this repo; flash whichever
personality you want.

```
You ──ask──▶ Claude ──push──▶ Skill ──HTTP──▶ daemon ──Wi-Fi / USB / BLE──▶ M5Paper
                                                                              │
                                                                              └──▶ 16 widgets across a 4-slot grid
```

## Quick start

```bash
# from ai-desk-card/
pio run -e card -t uploadfs    # one-time: flash CJK font to LittleFS
pio run -e card -t upload      # flash firmware

# start the daemon — auto-picks Wi-Fi > USB > BLE
/card-start
```

Then provision Wi-Fi (one-time, via BLE or USB):

```
/card-wifi-setup "MyHomeNet" "password"
```

After the device joins Wi-Fi, the daemon discovers it via mDNS and pushes
frames as a single HTTP POST. Typical single-widget update lands on the
panel in ~0.2 s.

## Architectures

| Mode | When the device is on | Latency | Power |
|---|---|---|---|
| **A** | USB-C power | 0.2 s/frame | ∞ runtime |
| **B** | USB serial (no Wi-Fi) | 1 s region / 32 s full | n/a (powered) |
| **C** | Battery, BLE always-on | 5 s wake + 0.2 s push (cold); 0.2 s within 30 s linger | months |

Pick is automatic per push — daemon dials whatever's available.

## Slash commands

- `/card-onboard` — first-time setup (detects daemon / USB / firmware / pair)
- `/card-widget` — AI-pushable widgets (16 types, 4 slots)
- `/card-wifi-setup "<SSID>" "<password>"` — provision Wi-Fi over BLE/USB
- `/card-refresh` — cron-driven auto-refresh entry point
- `/card-sleep` — show the digital business card + deep-sleep
- `/card-start`, `/card-stop`, `/card-status`, `/card-install` — daemon + flash

## Layout

```
ai-desk-card/
├── PLAN.md                 ← architecture decisions + scope rules
├── platformio.ini          ← env:card (independent from parent's env:m5paper)
├── src/                    ← firmware (frame_receiver + wifi + http + ble)
├── daemon/                 ← Python HTTP/serial/BLE bridge
├── plugin/                 ← Claude Code commands, scripts, skills
└── data/cjk.ttf -> ../../data/cjk.ttf
```

See [PLAN.md](PLAN.md) for the full architecture decisions and
[plugin/skills/card-refresh/REFRESH.md](plugin/skills/card-refresh/REFRESH.md)
for cron + cost considerations.

## License + attribution

- This sub-project: GPL-3.0 with attribution (same as parent repo)
- Vendored EPDGUI framework: MIT, © 2020 m5stack — see [NOTICE.md](../NOTICE.md)
