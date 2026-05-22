# AI Desk Card

A glanceable e-ink 副屏 driven by an AI agent. The M5Paper sits next to
your monitor and shows weather, todos, today's calendar, message previews,
PR queue, current focus task, and the running AI session's status. Data
is pushed by an AI agent through a plugin Skill; the device just renders.

Designed for: **Wi-Fi LAN push (0.2 s/frame) · battery-powered standby
(months of life) · USB-C optional · zero cloud dependency**.

```
You ──ask──▶ AI agent ──push──▶ Skill ──HTTP──▶ daemon ──Wi-Fi / USB / BLE──▶ M5Paper
                                                                                │
                                                                                └──▶ 16 widgets across a 4-slot grid
```

For the why-this-exists and the architecture in detail, see
[PRODUCT.md](PRODUCT.md). For how each piece is wired, see
[HANDOVER.md](HANDOVER.md).

---

## Supported hardware

| Device | Status | Notes |
|---|---|---|
| **M5Paper V1.1** | ✅ Primary target — fully tested | 4.7-inch 540×960 e-ink, ESP32, 8 MB PSRAM, 16 MB flash, 1150 mAh, USB-C, Wi-Fi 2.4 GHz, BLE 4.2. About ¥600 / $90. |
| M5Paper V1.0 | 🟡 Likely works | Same SoC + panel; battery voltage detection threshold (`4150 mV` in `src/main.cpp`) may need tuning. Not tested in-house. |
| M5Paper S3 | 🟡 Probably needs porting | New ESP32-S3 variant; BLE stack differs (NimBLE default). About 1-2 days of porting. |
| Other ESP32 + e-ink boards | ❌ Not supported | Inkplate / Waveshare / etc. would need a different panel driver. Roadmap item. |

You also need:

- A USB-C data cable (only needed once to flash firmware)
- Optional: USB-C charger if you want always-on Wi-Fi mode

## Supported AI agents

The plugin is **agent-agnostic** — it works with any AI CLI that supports
the plugin spec used by Claude Code (commands + scripts + skills layout).
Tested or likely-compatible:

| Agent | Status |
|---|---|
| **Claude Code** | ✅ Primary target — plugin format is from here |
| Codex CLI | 🟡 Same plugin shape; should work with minor variation in how slash commands route |
| Gemini CLI | 🟡 Likely works |
| Aider | 🟡 Likely works (config flag for slash-command routing) |
| Your own CLI | If it accepts a `plugin/` directory with the same shape, yes |

For the cron-driven auto-refresh, the script auto-detects whichever AI
CLI is on `$PATH` (`claude`, `codex`, `gemini`, `aider`) or honors
`$AI_CLI=<binary>` if you want to pin one. See
[plugin/skills/card-refresh/REFRESH.md](plugin/skills/card-refresh/REFRESH.md).

---

## Installation

### Prerequisites

- macOS (Linux untested) or Windows via WSL2
- [PlatformIO](https://platformio.org) (install via `pipx install platformio`
  or VS Code extension)
- Python 3.10+ — needed for the BLE path; PlatformIO ships a 3.14 that the
  daemon's `start.sh` auto-picks if present
- One of: Claude Code, Codex CLI, Gemini CLI, or Aider installed

### Step 1 — Buy the hardware

Get an M5Paper V1.1 ($90 from M5Stack official store, Amazon, or
AliExpress). Comes with a USB-C cable; if not, any USB-C **data** cable
(not a power-only cable) will do.

### Step 2 — Clone + flash firmware

```bash
git clone https://github.com/op7418/ai-desk-card.git
cd ai-desk-card

# Build the firmware
pio run -e card

# One-time: flash the CJK font to LittleFS partition
pio run -e card -t uploadfs

# Flash firmware
pio run -e card -t upload
```

Total time ~1 minute. After upload the device reboots and shows a
"waiting for daemon..." splash with the firmware version on it.

### Step 3 — Install the plugin

The `plugin/` directory at the root of this repo IS the plugin.
Install it into your AI CLI:

**Option A — symlink (recommended for development)**:

```bash
# Claude Code
ln -s "$(pwd)/plugin" ~/.claude/plugins/ai-desk-card

# Other CLIs follow the same pattern; check your CLI's docs for
# the plugin directory location.
```

**Option B — clone target machine's plugin directory**:

```bash
# If you don't want a symlink, you can clone the repo directly into
# the plugin directory:
mkdir -p ~/.claude/plugins/
git clone https://github.com/op7418/ai-desk-card.git ~/.claude/plugins/ai-desk-card-src
ln -s ~/.claude/plugins/ai-desk-card-src/plugin ~/.claude/plugins/ai-desk-card
```

Verify install — open your AI CLI and run `/card-` and see the
autocomplete pop up with all slash commands.

### Step 4 — Start the daemon

The daemon is a small Python process that bridges your AI agent
(over local HTTP) and the device (over Wi-Fi / USB / BLE).

```bash
/card-start
```

This auto-picks the best available transport (Wi-Fi > USB > BLE).
On first install with the device plugged in via USB, it will pick USB.

Verify — daemon writes to `${TMPDIR:-/tmp}/ai_desk_card_daemon.log`:

```bash
tail -10 "${TMPDIR:-/tmp}/ai_desk_card_daemon.log"
```

Expected lines:

```
[serial] opened /dev/cu.usbserial-XXX @ 115200 baud
[http] listening on 127.0.0.1:9877
[ready] ai-desk-card daemon v0.8 — push widgets via POST /widget
```

### Step 5 — Pair BLE (one-time)

The device's BLE radio is on by default and advertising as `Card-XXXX`.
Pairing is needed only if you want to use BLE later — for the initial
setup over USB you can skip this.

Pair flow: when daemon connects to the device's BLE characteristic for
the first time, macOS prompts to pair. The device displays a 6-digit
PIN on its e-ink screen; type that into the macOS prompt. Done.

### Step 6 — Provision Wi-Fi

This is the big quality-of-life step. After Wi-Fi, frame push latency
drops from 1-32 s (USB) to 0.2 s (Wi-Fi).

```bash
/card-wifi-setup "<your SSID>" "<your password>"
```

The credentials go from your AI CLI → daemon → device NVS (over USB
or BLE). They are **never** written to git, daemon logs, or any
remote service.

Wait ~15 seconds; the device will join your Wi-Fi and advertise via
mDNS. Verify:

```bash
bash plugin/skills/card-onboard/scripts/probe.sh
```

Look for `"mdns_peer": { "ip": "...", "port": 9880 }` in the output.

### Step 7 — Restart daemon to switch to Wi-Fi

```bash
/card-stop && /card-start
```

Now look for `[transport] found Wi-Fi peer X.X.X.X:9880, using Wi-Fi`.

### Step 8 — Push your first widget

In your AI CLI, ask:

> Show me today's weather on my card.

The agent will use `/card-widget` to push a weather widget. ~0.2
seconds later it's on the screen.

---

## Configuration

All optional. Defaults work fine for typical use.

### Sleep-card content (`assets/profile.yaml`)

Edit this YAML to customise the digital business card shown when you
run `/card-sleep`:

```yaml
name: "Your Name"
tagline: "what you do"
bio_lines:
  - "interests / focus areas"
  - "second line"
tags:
  - icon: "JOB"
    text: "your job title"
  - icon: "CITY"
    text: "your city"
  - icon: "WEB"
    text: "yoursite.com"
qr_image: "qr.png"    # optional; drop a PNG in assets/
qr_label: "scan to connect"
avatar_image: "avatar.png"
footer: "ai-desk-card · sleeping"
```

After editing, run `/card-sleep` to push the new card and put the
device to sleep.

### Cron auto-refresh (`~/.ai-desk-card-refresh.log`)

To have widgets refresh automatically, add a cron line:

```bash
crontab -e
```

Add:

```cron
# Workday 8:00-22:00, every 30 min
*/30 8-21 * * 1-5  /path/to/ai-desk-card/plugin/skills/card-refresh/scripts/refresh_loop.sh
```

The script auto-picks any AI CLI on your `$PATH`. To pin a specific
one:

```cron
*/30 8-21 * * 1-5  AI_CLI=codex /path/to/refresh_loop.sh
```

Full cost / cadence / no-AI-fallback story:
[plugin/skills/card-refresh/REFRESH.md](plugin/skills/card-refresh/REFRESH.md).

### No-AI fallback config (`~/.card-refresh.yaml`)

If you'd rather skip the AI entirely and just refresh weather +
system + git widgets locally:

```yaml
location: "Beijing"
repo_path: "/Users/you/code/main-project"
```

Then point cron at `fallback_refresh.py` instead of `refresh_loop.sh`:

```cron
0 */2 * * *  /usr/bin/python3 /path/to/ai-desk-card/plugin/skills/card-refresh/scripts/fallback_refresh.py
```

### Daemon URL (`$CARD_DAEMON_URL`)

By default the daemon listens on `http://127.0.0.1:9877`. If you need
to override (e.g., running daemon on a different machine):

```bash
export CARD_DAEMON_URL=http://192.168.1.50:9877
```

All slash commands and scripts honor this env var.

### AI CLI selection (`$AI_CLI`)

For the cron refresh script, default is auto-detect from
`{claude, codex, gemini, aider}`. To force one:

```bash
export AI_CLI=codex
```

### Forgetting Wi-Fi credentials

```bash
/card-wifi-setup ""
```

Empty SSID clears the NVS-stored credentials. The device will stay off
Wi-Fi on next boot.

---

## Three power-mode architectures

The daemon picks transport automatically per push; the firmware picks
Wi-Fi strategy based on whether USB-C is supplying power.

| Mode | Device on | Latency | Battery life |
|---|---|---|---|
| **A** Always plugged in | USB-C power, Wi-Fi always on | 0.2 s/frame | n/a (powered) |
| **B** USB serial only | USB-C data cable (no Wi-Fi yet) | 1 s region / 32 s full | n/a (powered) |
| **C** Battery + BLE standby | Wi-Fi off until daemon BLE-wakes it | 5 s wake + 0.2 s push | months |

Architecture C: device sleeps with BLE in standby, daemon sends
`cmd:wifi_wake_now` over BLE, device brings Wi-Fi up, daemon pushes
the frame via HTTP, device drops Wi-Fi after a 30-second linger.
~0.2 mAh per wake-and-push; 24 pushes/day → 6 months on a charge.

For more architecture detail see [PRODUCT.md](PRODUCT.md).

---

## 16 widget types

**Work staples**: `weather`, `calendar`, `next-meeting`, `messages`,
`inbox`, `system`, `git-status`, `pr-queue`, `now-playing`

**Note-taking & focus**: `scratch`, `todo`, `focus`, `deadlines`,
`break-reminder`

**AI monitoring**: `ai-status`, `ai-tasks`

Every widget is a JSON schema. AI agents fill the schema; the daemon
renders server-side (Python + Pillow) and ships pixels to the device.
See [plugin/skills/card-widget/schemas/](plugin/skills/card-widget/schemas/)
for the full schemas.

## Slash commands

| Command | What it does |
|---|---|
| `/card-onboard` | First-time setup walkthrough (detects daemon / USB / firmware / Wi-Fi state) |
| `/card-widget` | Push widgets to slots (AI uses this when you ask it to show something) |
| `/card-wifi-setup "<SSID>" "<pw>"` | Provision Wi-Fi credentials to the device's NVS |
| `/card-sleep` | Show your digital business card + put device to deep sleep |
| `/card-refresh` | Cron-driven auto-refresh entry point |
| `/card-start`, `/card-stop`, `/card-status` | Daemon lifecycle |
| `/card-install` | Build (if needed) + flash firmware |

---

## Troubleshooting

### "Daemon won't start"

```bash
tail -30 "${TMPDIR:-/tmp}/ai_desk_card_daemon.log"
```

Common causes: serial port held by another process, no Python 3.10+
for BLE path, port 9877 already in use.

### "Wi-Fi connect keeps failing"

```bash
tail -30 "${TMPDIR:-/tmp}/ai_desk_card_daemon.log" | grep wifi
```

Status codes:

- `1` = SSID not found (typo, or **ESP32 doesn't support 5 GHz** — make
  sure your router exposes a 2.4 GHz SSID)
- `4` = auth fail (wrong password)
- `6` = DHCP fail (router issue)

### "I want to see the rendered frame without flashing"

```bash
curl -sf -X POST http://127.0.0.1:9877/widgets/preview -o /tmp/preview.png
open /tmp/preview.png
```

### "Device shows boot splash forever"

The daemon isn't connected. Run:

```bash
bash plugin/skills/card-onboard/scripts/probe.sh
```

Read the JSON output; the skill `/card-onboard` will walk you through
fixing whatever's wrong.

### "I want to verify my firmware is v0.8"

```bash
curl -sf -X POST http://127.0.0.1:9877/firmware-probe | python3 -m json.tool
# expect: ack.fw = "0.8.0"
```

### "It used to work over BLE but now hangs"

The BLE frame-data path has a known issue (the daemon completes the
write but the device-side `onWrite` callback doesn't fire for sustained
writes). Workaround: provision Wi-Fi, restart the daemon — it'll switch
to HTTP via mDNS. See [HANDOVER.md § Known Issues](HANDOVER.md#known-issues--workarounds)
for the full story.

### Deeper debugging

See [HANDOVER.md § Debugging recipes](HANDOVER.md#debugging-recipes).

---

## Layout

```
ai-desk-card/
├── README.md
├── HANDOVER.md             engineering handover (for the next maintainer)
├── PRODUCT.md              product positioning + use cases
├── PLAN.md                 architecture decisions + scope rules
├── PLAN_RENDERING_V06.md   v0.6 server-side rendering migration notes
├── platformio.ini          env:card
├── partitions.csv          custom partition table (LittleFS for the CJK font)
├── LICENSE                 GPL-3.0 with attribution clause
├── assets/                 sleep-card profile + assets
├── data/                   CJK font for the daemon's PIL renderer
├── src/                    firmware (frame_receiver + wifi + http + ble)
├── daemon/                 Python HTTP bridge + renderers
└── plugin/                 commands, scripts, skills (this IS the plugin)
```

## Versioning

- `plugin.json` `version` is the plugin spec version
- `platformio.ini` `-DCARD_VERSION` is the firmware version
- Daemon picks up firmware version via `/firmware-probe`

Both should match across release tags.

## License

GPL-3.0 with attribution clause. See [LICENSE](LICENSE).

Vendored EPDGUI framework (parent project's `src/paper/epdgui/`): MIT,
© 2020 m5stack — see the parent repo's NOTICE.md.

## Contributing

Issues and PRs welcome at https://github.com/op7418/ai-desk-card.

Especially valuable contributions:
- Hardware photos / videos (helps new users see what they're getting)
- Linux / Windows daemon testing
- M5Paper V1.0 / S3 firmware port confirmation
- New widget schemas + renderers
- Captive portal Wi-Fi provisioning (roadmap)
