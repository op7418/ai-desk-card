---
name: ai-desk-card
description: |
  Drive a physical e-ink desk card (M5Paper 540×960) sitting next to the
  user's monitor. Use whenever the user wants to:
    - show / push / display ANYTHING on their card / 卡片 / 副屏 / 墨水屏 /
      e-ink display / desk card / glanceable display / secondary display
    - set up the device for the first time (flash firmware, pair, provision
      Wi-Fi) — phrases like "刚拿到 M5Paper", "怎么装卡片", "first-time
      setup", "刷固件", "卡片没反应"
    - schedule recurring pushes / "每小时刷一次" / "工作时间显示日历" /
      "auto-refresh every 30 min"
    - configure what the card shows (weather, todos, calendar, inbox,
      PR queue, AI status, focus, scratch, deadlines, messages, now-playing,
      git-status, system, next-meeting, break-reminder, ai-tasks)
    - put the device to sleep / show business card / "息屏" / "睡眠"
  Single Skill, agent-agnostic: probes current state, then routes to the
  right sub-flow. Never asks "is the daemon running" — it checks.
trigger_keywords:
  - card
  - desk card
  - 卡片
  - 副屏
  - 墨水屏
  - e-ink
  - M5Paper
  - paper card
  - glanceable display
  - secondary display
  - ai-desk-card
  - 桌面卡片
  - dashboard card
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# ai-desk-card — single Skill entry point

A 540×960 e-ink panel sitting next to the user's monitor. AI agents push
widgets to it; the daemon renders frames server-side and ships pixels over
Wi-Fi / USB / BLE. This Skill is the **only** thing an agent needs to call
— it auto-detects state and routes to the right flow.

## Step 1 — ALWAYS probe state first

Before doing anything, run the state probe. Do not ask the user "have you
done X" — find out by checking.

```bash
bash $SKILL_DIR/scripts/state.sh
```

(`$SKILL_DIR` is wherever this Skill is installed. If your agent runtime
sets `$CLAUDE_PLUGIN_ROOT`, use that. Otherwise use the repo root.)

Output is JSON with this shape:

```jsonc
{
  "hardware":   { "pio_installed": bool, "m5paper_usb": str|null },
  "firmware":   { "flashed": bool, "ours": bool, "version": str|null },
  "daemon":     { "running": bool, "pid": int|null },
  "transport":  { "connected": bool, "type": "BLETransport|SerialTransport|WiFiTransport|null" },
  "device":     { "alive": bool, "last_seen_seconds": int|null,
                  "active_transport": "Wi-Fi|USB|BLE|null",
                  "battery_pct": int|null, "uptime": str|null },
  "wifi":       { "provisioned": bool, "ip": str|null },
  "interests":  { "configured": bool, "path": str|null }
}
```

The most important field is `device.alive`. It tells you whether the
device has sent a status report in the last ~90 s. `transport.connected`
only says "daemon picked a transport class"; `device.alive` says "we're
actually hearing back from the device right now."

## Step 1.5 — Identify the device profile

The Skill supports two devices with different panels + daemons:

- **M5Paper V1.1** (540×960 grayscale, GT911 touch, BLE pair) — original
- **M5Paper Color** (600×400 Spectra 6 color, 3 physical buttons, audio + SHT40) — new in v0.10

If GET `/heartbeat` returns `device_status.device == "M5PaperColor"`
(via `color_daemon.py` running), use the **Color path** described in
[flows/08_paper_color.md](flows/08_paper_color.md):

- env: `pio run -e paper-color`
- daemon: `python3 daemon/color_daemon.py --device-ip <IP>`
- Wi-Fi provision: Serial JSON `cmd:wifi_set` (no BLE pairing UX)
- slot names: `top-left / top-right / bottom-left / bottom-right`
- extra widgets: `ambient` (SHT40 temp+humid)
- physical buttons: 顶=sleep / 下左=refresh / 下中=settings

Otherwise (default) use the **V1.1 path** through the routing table below.

The two daemons can't run on the same port simultaneously — pick one
based on which device is in front of the user. The Skill flows below
work for V1.1 unless explicitly noted.

## Step 2 — Route based on state

Walk the decision tree in this order. First mismatch wins; fix it, then
re-probe.

| Condition | Next action | Detail flow |
|---|---|---|
| `firmware.flashed == false` AND no `device.alive` | First-time hardware setup | [flows/01_install.md](flows/01_install.md) |
| `daemon.running == false` | Start the daemon | `bash $SKILL_DIR/plugin/scripts/start.sh` |
| `device.alive == false` AND `transport.connected == false` | Device unreachable — could be asleep, off, BLE not paired. Tell user, suggest physical wake (tap rotary / plug USB) | [flows/02_transport.md](flows/02_transport.md) |
| `device.alive == false` AND `transport.connected == true` (daemon connected something but no status_report in 90s) | Device transport up but not responding — restart daemon, then probe | [flows/02_transport.md](flows/02_transport.md) |
| `wifi.provisioned == false` (and user wants always-on or battery mode) | Provision Wi-Fi | [flows/03_wifi.md](flows/03_wifi.md) |
| `interests.configured == false` AND user just asked for "auto-refresh" or "定时推送" | Ask about interests, write `~/.ai-desk-card/interests.yaml` | [flows/04_interests.md](flows/04_interests.md) |
| `device.alive == true` + user said "push X" | Build widget JSON, POST to daemon | [flows/05_push.md](flows/05_push.md) |
| `device.alive == true` + user said "schedule" / "每 N 分钟" / "auto" | Set up scheduled push | [flows/06_schedule.md](flows/06_schedule.md) |
| `device.alive == true` + user said "sleep" / "息屏" | Push business card + deep sleep | [flows/07_sleep.md](flows/07_sleep.md) |

Always tell the user which step you're on. Don't operate silently.

## Step 3 — Push a widget (the hot path)

When state is OK and user asks to show something:

```bash
curl -sf -X POST "${CARD_DAEMON_URL:-http://127.0.0.1:9877}/widget" \
  -H 'Content-Type: application/json' \
  -d @- <<'JSON'
{
  "slot": "top-left",
  "type": "weather",
  "data": { "city": "Beijing", "temp_c": 22, "icon": "sun", "summary": "晴" }
}
JSON
```

- **slot**: string. Layout is 2-1-1 not 2x2 —
  `top-left` (270×280) · `top-right` (270×280) · `middle` (540×340) ·
  `bottom` (540×280) · `full` (540×960, takes over the whole screen).
- **type**: one of 16 — see `plugin/skills/card-widget/schemas/` for full
  JSON schemas with examples.
- Wi-Fi: response in ~0.2 s. USB: 1–32 s. BLE frame-data: broken — small
  commands only.

Full per-widget schema + theme reference:
[plugin/skills/card-widget/SKILL.md](plugin/skills/card-widget/SKILL.md)

## Step 4 — When to suggest scheduled pushes

If the user's request implies recurrence ("keep my calendar updated",
"check email every hour", "show me today's todos throughout the day"),
**don't** just push once. Instead:

1. Confirm the cadence + which widgets they want
2. Write/update `~/.ai-desk-card/interests.yaml` (see flow 04)
3. Set up the schedule using your agent's native loop primitive:
   - Claude Code: `/loop 30m` or `ScheduleWakeup`
   - Codex / Gemini: equivalent scheduling
   - Fallback: cron line via `plugin/skills/card-refresh/scripts/refresh_loop.sh`

The Skill provides the *what* (interests + push) — your agent provides the
*when* (loop primitive).

## Constraints to never violate

- **No silent operations.** Every sub-step gets a one-line update to the user.
- **No retry loops.** If something fails, surface the diagnostic and stop.
- **No assuming state.** Always re-probe after fixing something.
- **No font escape hatches.** The CJK TTF doesn't include ▢ ▶ ✎ ♪ ↑ ↓ ● ○
  — … °. Use the safe glyph set documented in
  [plugin/skills/card-widget/SKILL.md](plugin/skills/card-widget/SKILL.md).
- **Wi-Fi preferred over USB / BLE.** 0.2 s vs 1-32 s vs broken.

## Hardware: what the user needs

- M5Paper V1.1 (~¥600 / $90) — primary target
- USB-C data cable (one time, for flashing)
- Optional: USB-C charger for always-on Wi-Fi mode

## What this Skill is NOT

- Not a Claude-Code-only plugin. The `plugin/` directory is provided for
  CLIs that consume slash commands, but this `SKILL.md` is the agent-agnostic
  entry point.
- Not a cloud service. Everything runs on the user's machine (daemon at
  `127.0.0.1:9877` by default) + the device's local Wi-Fi.
- Not a generic e-ink renderer. The widgets, themes, and renderer all
  target this specific device + grid.
