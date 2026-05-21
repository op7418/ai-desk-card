# claude-card — One-shot v0.5 plan

> **What this is**: a sub-project carved out of m5-paper-buddy to land the
> v0.5 architecture (AI / card / Skill three-layer separation + OTA from
> Skill + better副屏 readability) without disturbing the running buddy
> firmware in `../src/`.
>
> **Boundary rule**: nothing outside `claude-card/` is allowed to change
> for this milestone. If we need code from the parent (EPDGUI vendored
> files, BLE bridge, font), we **copy** rather than import-by-path.

## Product positioning vs buddy

| | buddy (existing, `../src/`) | card (this folder) |
| --- | --- | --- |
| Role | Active companion: approval cards, session dashboard, audio buddy face | Passive副屏: always-on glanceable widget grid |
| Interaction | Touch + side buttons + voice (planned) | Touch only — single-tap to enter settings |
| Primary screen | Dashboard (sessions / approval card / cat) | Frame_WidgetDashboard (4-slot widget grid) |
| Source of data | Claude Code hooks via daemon | Same daemon, but card only consumes the widget payload |
| Approval handling | Yes (BtnP / touch) | No — approvals show as count on ai-tasks widget; approve in terminal |

User can re-flash buddy firmware any time; this is a parallel personality
for the M5Paper, not a replacement of the codebase.

## Architecture (cemented from 2026-05-19 product discussion)

```
┌────────────────────────────────────────────────────────────┐
│  AI (Claude Code session)                                  │
│  Decides:                                                  │
│    - what values to send                                   │
│    - which slot to send to                                 │
│    - when to clear / refresh                               │
└─────────────────────┬──────────────────────────────────────┘
                      │  POST /widget JSON
                      ▼
┌────────────────────────────────────────────────────────────┐
│  Skill (claude-card/skill/)                                │
│  Owns:                                                     │
│    - data schemas (one per widget type)                    │
│    - push helpers (push_widget.py, fetch_reminders.py …)   │
│    - firmware OTA: detect version, pull from cloud, flash  │
└─────────────────────┬──────────────────────────────────────┘
                      │  HTTP loopback
                      ▼
┌────────────────────────────────────────────────────────────┐
│  Daemon (claude-card/daemon/card_daemon.py)                │
│  Owns:                                                     │
│    - HTTP API (POST/GET/DELETE /widget, /preview, /pair)   │
│    - serial / BLE transport to device                      │
│    - widget cache + auto-fill of ai-status from CC hooks   │
└─────────────────────┬──────────────────────────────────────┘
                      │  JSON over USB serial / BLE
                      ▼
┌────────────────────────────────────────────────────────────┐
│  Card firmware (claude-card/src/)                          │
│  Owns:                                                     │
│    - 6 hard-coded widget components (render only)          │
│    - touch-driven settings frame                           │
│    - BLE pairing flow                                      │
└────────────────────────────────────────────────────────────┘
```

## Widget components (6 hard-coded, this is the surface)

| Type | Slot suggestion | Data source | Status |
| --- | --- | --- | --- |
| `weather` | top-left | wttr.in / OpenWeather | schema + render |
| `todo` | bottom | macOS Reminders (existing fetcher) | schema + render |
| `calendar` | middle | macOS EventKit (NEW fetcher stub) | schema + render |
| `messages` | top-right | macOS NotificationCenter (NEW, mock data v0.5) | schema + render |
| `ai-status` | top-right alt | Claude Code hooks (daemon auto-fill) | schema + render |
| `ai-tasks` | top-left alt | Claude Code hooks (daemon auto-fill) | schema + render |

AI decides which TWO ai-* widgets to show vs which TWO work widgets — the
4-slot grid only fits 4 at once. Reasonable defaults: weather / ai-status
/ calendar / todo.

## Font + layout decisions (from user feedback)

副屏 use case = **30-50cm distance, glance not read**. Therefore:

- Base body text: **28 pt** minimum (was 18)
- Title: **36 pt** (was 22)
- Big headline (weather temp): **80 pt** (was 56)
- **Max 3-4 items per list widget** (was 8) — fewer items, bigger glyphs
- Borders thinner, more whitespace
- Status icons / glyphs: 40 px (was small text markers)

## Touch interaction model (V1.1 only has rotary + touch)

- **Always-on widget副屏** — no dashboard mode any more. Boot → directly to widget副屏
- **Touch top-right corner (100×100 px)** held 1 s → Frame_Settings opens
- **Inside settings**: tap items to toggle, tap "Back" or "Done" to exit
- **No approval dialogs** on device — card is display-only

## Skill OTA flow

```
$ claude
> /card-install
[Skill] detecting board... M5Paper V1.1 on /dev/cu.usbserial-5B1F0123251
[Skill] currently running firmware: <none detected> | v0.3-buddy | v0.5-card
[Skill] target firmware: v0.5-card from https://github.com/op7418/m5-paper-buddy/releases/download/card-v0.5/firmware.bin
[Skill] sha256: abc123… — DOES NOT MATCH any known signature
[Skill] (interactive) flash? [y/N]
[Skill] downloading + flashing...
[Skill] done. device booting v0.5-card.
```

v0.5 ships this command with a LOCAL fallback (read .bin from
`claude-card/firmware/firmware.bin`) since we don't have a public Release
yet. The cloud path is plumbing for v0.6.

## What's NOT in v0.5 (out of scope, deferred)

- Real macOS NotificationCenter data source (use mock)
- Signed firmware verification (sha256 only, key infra later)
- Multi-device sync
- User-uploadable widget types
- Settings frame backed by NVS persistence (in-RAM only this round)
- Pairing passkey display on screen (still relies on macOS BT dialog)

## Run order

1. `cd claude-card && pio run -e card -t uploadfs` — flash CJK font once
2. `pio run -e card -t upload` — flash firmware
3. `python3 daemon/card_daemon.py --transport serial` — connect to device
4. From any Claude Code session: `/card-widget show` or just push via Skill
