# AI Desk Card · An AI-Driven Desk Companion Skill

![GitHub stars](https://img.shields.io/github/stars/op7418/ai-desk-card?style=flat-square)
![License](https://img.shields.io/github/license/op7418/ai-desk-card?style=flat-square)
![Skill](https://img.shields.io/badge/Skill-Agent-111111?style=flat-square)
![M5Paper](https://img.shields.io/badge/M5Paper-V1.1-0A7CFF?style=flat-square)
![Claude Code](https://img.shields.io/badge/Claude%20Code-Supported-6B5B95?style=flat-square)
![Codex](https://img.shields.io/badge/Codex-Supported-222222?style=flat-square)

> 🇨🇳 **中文版（主文档）: [README.md](./README.md)**

A Skill that turns an [M5Paper V1.1](https://docs.m5stack.com/en/core/m5paper)
e-ink panel into a desk companion driven by an AI agent (Claude Code,
Codex, Cursor, etc.). The agent decides what to push: weather, calendar,
todos, PR queue, AI session status, break reminders…

**Once you install the Skill, the agent walks you through firmware
flashing, Wi-Fi provisioning, and daily widget pushes** — you don't run
a single `pio` or `curl` command by hand.

![AI Desk Card hero](https://github.com/user-attachments/assets/b4777ba7-d668-42c1-9920-3e6d8bef534e)

```
You ──ask naturally──▶ AI Agent ──triggers──▶ Skill ──auto-runs──▶ M5Paper
```

## 30 seconds to start

```bash
npx skills add https://github.com/op7418/ai-desk-card --skill ai-desk-card
```

Or paste this to any AI Agent with shell access:

```text
Install the ai-desk-card Skill. Clone https://github.com/op7418/ai-desk-card
into ~/.claude/skills/ai-desk-card. After install, verify SKILL.md, flows/,
daemon/, src/, assets/ all exist.
```

To update an existing install:

```text
Update ai-desk-card. cd into ~/.claude/skills/ai-desk-card, git pull, and
tell me the latest commit.
```

Then assuming you have an M5Paper V1.1 and a USB-C data cable, just say:

```text
Help me set up ai-desk-card. I have an M5Paper V1.1 plugged in over USB-C.
```

The Skill will automatically:

1. Probe current state (PlatformIO, USB device, daemon, Wi-Fi)
2. Install what's missing (`pipx install platformio` if needed)
3. Compile + flash CJK font + flash firmware (~1 minute)
4. Start the daemon
5. Ask for your Wi-Fi password → provision
6. Push the first widget

After that, daily use is a natural conversation:

```text
Show today's Beijing weather on my card.
Refresh weather and unread mail every 30 min on workday 8am-10pm.
What's on my card right now?
Auto-sleep at 11pm and show my business card.
```

## What you get

- 🖥 **Ambient desk display**: a 540×960 e-ink panel sits next to your monitor — glance, don't context-switch
- 🤖 **AI-pushed content**: the agent decides what widget to send and when; you don't open a browser for weather
- 📦 **16 widget types**: weather / calendar / todo / focus / inbox / pr-queue / ai-status / git-status / now-playing / break-reminder / scratch / messages / deadlines / next-meeting / system / ai-tasks
- 🎨 **Server-side render**: daemon uses Python + Pillow; want a new widget? Edit Python, no C++
- 🔌 **Three power modes auto-switch**: USB-powered / USB-data-only / battery + BLE standby (months of life)
- 🌐 **Wi-Fi LAN, 0.2 s per frame**: local HTTP, no cloud
- 💤 **Sleep at zero watts, last frame retained**: e-ink physics; ~6 months on a charge in arch C
- 👆 **Tappable bottom-bar chips**: "Sleep" → push business card + deep sleep; "Settings" → settings page. 150 ms tap-ack flash
- ⏰ **Auto-sleep at quiet hours**: daemon flips to business card without needing the agent online

## When it fits / when it doesn't

**✅ Good fit if**:

- You want an always-on side display but don't want another bright monitor
- You already use Claude Code / Codex / Cursor and want an ambient physical output
- You like e-ink's low-strain feel (not glaring, not distracting)
- You accept a ~10 min one-time hardware setup (then zero maintenance)

**❌ Not a fit if**:

- You need fast-refresh content (stock tickers, video, animation) — e-ink can't
- You don't want to buy hardware or flash firmware
- You need rich touch interaction (touch works but e-ink is slow)

## Common scenarios

| You say | Agent does |
|------|------|
| "Help me set up ai-desk-card" | Full onboarding: probe → flash firmware → start daemon → provision Wi-Fi |
| "Show today's weather on my card" | Push weather widget |
| "Put my schedule on it" | Push calendar widget, auto-read macOS Calendar |
| "Show what I'm working on" | Push focus widget |
| "Refresh every 30 min" | Write `~/.ai-desk-card/interests.yaml` + register loop |
| "Auto-sleep at 11pm with my business card" | Configure quiet_hours, daemon handles it |
| "Card won't connect" | Run diagnostic flow → locate issue → suggest fix |
| "I changed Wi-Fi" | Run wifi-setup flow |
| "What's on my card now?" | curl the daemon for a current-frame PNG preview |

## Platform support

| Agent | Status | Notes |
|------|------|------|
| Claude Code | ✅ Primary | Native Skill + slash command convenience layer |
| Codex CLI | 🟡 Same SKILL.md format | Should work, not deeply tested |
| Gemini CLI | 🟡 Should work | Same |
| Cursor | 🟡 Works | Needs shell permission |
| Aider | 🟡 Works | Same |
| Self-built agent | ✅ | Any agent that recognizes SKILL.md + has shell access |

## Hardware you need

| Item | Notes |
|------|------|
| **M5Paper V1.1** | Primary target. ~¥600 / $90. [Official store](https://shop.m5stack.com/products/m5paper-v1-1) / Amazon / AliExpress |
| M5Paper V1.0 | Likely works, battery threshold (`4150 mV`) may need tuning |
| M5Paper S3 | Needs porting (1-2 days, BLE stack differs) |
| USB-C **data cable** | Used once for flashing. Charge-only cables don't work |
| (optional) USB-C charger | Needed for always-on Wi-Fi mode |

> ⚠️ **You don't need to pre-install PlatformIO / compilers / Python** — if the Skill detects something missing, it lets the agent install it.

## Another hardware target: iFlytek C1 color e-ink (Android)

The main track targets M5Paper (ESP32 firmware). If you have an **iFlytek C1**
(1072×1448 color E Ink, Android 8.1 custom ROM) instead, the repo ships a
complete implementation for it — see [`c1/`](./c1/):

```bash
cd c1 && ./build.sh && adb install -r C1Assistant.apk
```

It's not a firmware flash — it's an Android APK that **replaces the system
screensaver**: a color professional-avatar portrait plus a task list when you
lock the screen, auto-exit on wake; it pulls content from the data bridge every
30s and skips the refresh entirely when nothing changed.

| | M5Paper (main track) | iFlytek C1 (`c1/`) |
|---|---|---|
| Form | ESP32 firmware | Android APK |
| Panel | 4.7" mono | 6"+ color |
| Refresh | firmware-side region refresh | per-window waveform: portrait `GL16` resident / tasks `DU\|RECT` regional |
| Content source | `daemon/card_daemon.py` | `c1/bridge.py` (same widget model) |
| Power | deep sleep | in-process timer + Wi-Fi only when needed |

The C1 track hit quite a few ROM-specific traps (the default screensaver isn't a
Daydream, the panel ships with color disabled, an overlay that deadlocks wake
broadcasts…). All of it is written up in [`c1/README.md`](./c1/README.md).

## Install

### Option 1: One-line install (recommended)

```bash
npx skills add https://github.com/op7418/ai-desk-card --skill ai-desk-card
```

### Option 2: Ask the AI to install

Copy this and paste to Claude Code / Cursor / any AI Agent with shell access:

> Install the `ai-desk-card` Skill. Steps:
>
> 1. Ensure `~/.claude/skills/` exists (create if not)
> 2. Run `git clone https://github.com/op7418/ai-desk-card.git ~/.claude/skills/ai-desk-card`
> 3. Verify: `ls ~/.claude/skills/ai-desk-card/` should show `SKILL.md`, `flows/`, `plugin/`, `daemon/`, `src/`, `assets/`
> 4. Tell me when done; from then on saying "set up the card" will trigger this Skill

### Option 3: Manual clone

```bash
git clone https://github.com/op7418/ai-desk-card.git ~/.claude/skills/ai-desk-card
```

### Trigger keywords

After install, the agent auto-triggers the Skill when you mention any of:

- "card" / "desk card" / "e-ink display" / "secondary display"
- "show X on my card"
- "just got an M5Paper" / "first-time setup" / "flash firmware"
- "refresh every N min" / "auto-refresh"
- "sleep the card" / "show business card"
- "ai-desk-card"

## How it works

The Skill is a structured workflow; the agent steps through it automatically:

1. **Onboarding (flow 01)** — probe PlatformIO + USB → walk through firmware flash
2. **Transport diagnosis (flow 02)** — locate issues when device is unreachable
3. **Wi-Fi setup (flow 03)** — provision credentials into device NVS
4. **Interests (flow 04)** — first-time "what do you want to see, how often"
5. **Push widget (flow 05)** — daily hot path
6. **Schedule (flow 06)** — agent's own loop / cron registration
7. **Sleep (flow 07)** — business card + deep sleep at zero watts

Full sub-flows live in [`flows/`](./flows/). Main routing in [`SKILL.md`](./SKILL.md).

## 16 widget types

**Work staples**:
- `weather` · `calendar` · `next-meeting`
- `todo` · `focus` · `deadlines`
- `inbox` · `messages` · `pr-queue`
- `git-status` · `system` · `now-playing`

**Notes / pacing**:
- `scratch` · `break-reminder`

**AI monitoring**:
- `ai-status` · `ai-tasks`

**4 slots / 2-1-1 layout**:

```
┌────────────┬────────────┐
│ top-left   │ top-right  │  ← 270×280 each
├────────────┴────────────┤
│         middle          │  ← 540×340 full-width
├─────────────────────────┤
│         bottom          │  ← 540×280 full-width
├─────────────────────────┤
│  bottom bar (chips)     │  ← 60 px, "Sleep" + "Settings"
└─────────────────────────┘
```

Plus `full` (540×960) which takes over the whole screen — used for the business card / boot splash.

Full schema in [`plugin/skills/card-widget/schemas/`](./plugin/skills/card-widget/schemas/).

## Auto-refresh (optional)

When the Skill first asks "which widgets do you want, how often", it writes `~/.ai-desk-card/interests.yaml`:

```yaml
version: 1

slots:
  top-left:  weather
  top-right: calendar
  middle:    todo
  bottom:    inbox

schedule:
  cadence:  "30m"           # 5m / 15m / 30m / 1h / 2h
  hours:    "08-22"
  days:     "mon-fri"
  timezone: "Asia/Shanghai"

data_sources:
  weather:
    city: "Beijing"
  calendar:
    source: "macos"          # or google / ics-url
  todo:
    source: "reminders"      # or things3 / todoist
  git_status:
    repo: "/Users/you/code/main-project"

# At quiet_hours.start, switch to business card + deep sleep.
# Daemon handles this in the background — agent doesn't have to be online.
quiet_hours:
  enabled: true
  start:   "23:00"
  end:     "07:00"
```

Three ways to trigger the refresh:

- **Agent's native loop (recommended)**: Claude Code's `/loop 30m`, `ScheduleWakeup`, etc.
- **cron**: `crontab -e` line: `*/30 8-21 * * 1-5 bash /path/to/ai-desk-card/plugin/skills/card-refresh/scripts/refresh_loop.sh`
- **No-AI fallback**: weather / system / git don't need AI — run `fallback_refresh.py` directly

## Three power-mode architectures

| Mode | State | Push latency | Battery |
|------|------|---------|------|
| **A** Always plugged | USB-C power + Wi-Fi always on | 0.2 s | n/a (powered) |
| **B** USB only | USB data cable (no Wi-Fi yet) | 1 s region / 32 s full | n/a (powered) |
| **C** Battery + BLE standby | Wi-Fi off, daemon wakes via BLE | 5 s wake + 0.2 s push | ~6 months |

Arch C is the favorite: the panel sits on your desk for months without charging; when the agent has something to push, BLE wake → bring up Wi-Fi → HTTP push → 30 s linger → drop Wi-Fi. ~0.2 mAh per push × 24 pushes/day × 6 months = 1150 mAh battery.

## Directory structure

```
ai-desk-card/
├── SKILL.md                  ← Agent entry point (any-agent)
├── scripts/state.sh          ← State probe — JSON: daemon / transport / wifi / device / interests
├── flows/                    ← 7 sub-flows (~60-100 lines each)
│   ├── 01_install.md             Zero-state hardware + firmware flash
│   ├── 02_transport.md           Daemon-can't-reach-device diagnostic
│   ├── 03_wifi.md                Wi-Fi provisioning
│   ├── 04_interests.md           interests.yaml guided setup
│   ├── 05_push.md                Widget push hot path
│   ├── 06_schedule.md            Scheduled-push protocol
│   └── 07_sleep.md               Business card + deep sleep
├── plugin/                   ← Claude Code convenience layer (slash + shared scripts)
│   ├── plugin.json
│   ├── commands/             ← /card-* commands
│   ├── scripts/              ← start.sh / stop.sh / status.sh
│   └── skills/               ← Sub-skills, called indirectly by main SKILL.md
├── daemon/
│   ├── card_daemon.py        ← HTTP bridge + transport layer + background loops
│   ├── card_render.py        ← Widget view renderer
│   ├── card_render_settings.py
│   └── card_render_sleep.py  ← Business card renderer
├── src/                      ← Firmware (frame_receiver / wifi / http / ble / touch poll)
├── assets/
│   ├── profile.yaml          ← Your business-card info (shown when sleeping)
│   ├── qr.png                ← Optional QR
│   └── avatar.png            ← Optional avatar
├── c1/                       ← iFlytek C1 color e-ink track (Android APK, independent of the ESP32 main track)
│   ├── app/                      ← APK sources — com.c1mini.assistant
│   ├── core/java/                ← Self-contained Eink.java (waveform control) + Prefs.java
│   ├── build.sh                  ← Builds C1Assistant.apk
│   ├── bridge.py                 ← C1 data bridge (agent pushes → device pulls)
│   └── README.md                 ← Architecture, deployment, real-device pitfalls
├── data/cjk.ttf              ← CJK font (flashed to LittleFS once)
├── platformio.ini
├── partitions.csv
├── HANDOVER.md               ← Engineering handover
└── PRODUCT.md                ← Product narrative
```

## How it really works (one diagram)

```
You speak                                      M5Paper
  │                                               ▲
  ▼                                               │
AI Agent ──────┐                                  │
               │ triggers Skill                   │
               ▼                                  │
          SKILL.md routing                        │
               │                                  │
               │  scripts/state.sh probes:        │
               │  · pio / firmware / daemon       │
               │  · device.alive / wifi           │
               │  · interests.yaml                │
               │                                  │
               └─▶ picks one of 7 sub-flows       │
                       │                          │
                       ▼                          │
                  Agent executes                  │
                       │                          │
                       ▼                          │
              POST to daemon (127.0.0.1:9877)     │
                       │                          │
                       ▼                          │
              daemon renders (Python + Pillow)    │
                       │                          │
                       ▼                          │
              HTTP / USB / BLE push ──────────────┘
```

## FAQ

**Q: I really don't need to flash firmware myself?**
No. After install, just say "set up the card" — the agent probes state, installs PlatformIO (if missing), runs `pio run -t upload`, flashes the CJK font, and tells you what it's doing at each step.

**Q: I don't have M5Paper V1.1 — anything else?**
M5Paper V1.0 likely works. M5Paper S3 needs porting (BLE stack differs). Inkplate / Waveshare / etc. aren't supported yet — roadmap item.

**Q: Do I have to use Claude Code?**
No. `SKILL.md` is agent-agnostic — any agent that recognizes the format + has shell permission works (Codex / Cursor / Aider / self-built). The `plugin/` slash commands are a Claude Code convenience layer, not the core.

**Q: What about network?**
All local. Daemon runs on your machine (127.0.0.1:9877). Device and computer are on the same Wi-Fi LAN. **ESP32 only supports 2.4 GHz** — 5 GHz-only SSIDs won't connect.

**Q: Chinese characters show as tofu boxes?**
You skipped the LittleFS font flash. Ask the agent to "run uploadfs again".

**Q: How do I update the firmware?**
Say "update ai-desk-card and re-flash". The Skill pulls new code + builds + uploads.

**Q: Does it work outside macOS?**
Daemon should work on Linux (not deeply tested). Windows needs WSL2. PlatformIO is cross-platform.

**Q: Does any data go to the cloud?**
No. Daemon binds 127.0.0.1 by default (device→daemon status_report goes over LAN). Wi-Fi credentials live in device NVS, never in daemon logs or git.

## Roadmap

- M5Paper V1.0 / S3 port verification
- Inkplate / Waveshare / other e-ink board support
- Captive portal Wi-Fi provisioning (no daemon needed)
- Hardware power-button intercept (long-press 2s → render business card before deep sleep)
- More widget schemas (Feishu / WeChat / Linear / Notion)
- Multi-device dashboard sync

## Contributing

Issues and PRs welcome at https://github.com/op7418/ai-desk-card.

Most valuable contributions:

- Hardware photos / videos (helps new users see the form factor)
- Linux / Windows daemon testing reports
- M5Paper V1.0 / S3 firmware port verification
- New widget schemas + renderers
- Translation / docs improvements

## License

GPL-3.0 with attribution clause · see [LICENSE](./LICENSE)

Vendored EPDGUI framework (from upstream M5Paper_FactoryTest): MIT, © 2020 m5stack.
