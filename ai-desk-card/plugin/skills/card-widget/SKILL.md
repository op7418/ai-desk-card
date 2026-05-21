---
name: card-widget
description: |
  Push live data to the user's ai-desk-card M5Paper e-ink companion display.
  Use whenever the user asks to show todos, calendar, weather, AI status,
  inbox counts, next meeting, or any glanceable info on their card / 卡片 /
  副屏 / 墨水屏 / e-ink display. 16 widget types available; AI picks slot
  + widget type, fills data, POSTs to the local card daemon (default
  127.0.0.1:9877). Communicates over loopback, so individual widget writes
  don't trigger Claude Code approval prompts.
trigger_keywords:
  - card widget
  - 卡片
  - 副屏
  - 墨水屏
  - paper card
  - 显示器副屏
  - secondary display
allowed-tools:
  - Bash
  - Read
  - Write
---

# card-widget — drive the M5Paper 副屏

The card is a 540 × 960 e-ink panel sitting next to the user's monitor.
You push 1-4 widgets and the daemon renders a single frame. Frame transfer
takes ~32 s (one-time, debounced); idle power is 0 W. **Once-a-burst
updates are fine; per-keystroke updates are not.**

## Layout cheat-sheet

Four slots. **Narrow slots (top-left, top-right) are 270 px wide**; wide
slots (middle, bottom, full) span the full 540 px. Some widgets only
shine when wide — see the catalog below.

```
┌───────────┬───────────┐   top-left  / top-right : 270×280   (narrow)
│ top-left  │ top-right │
├───────────┴───────────┤   middle               : 540×340   (wide)
│        middle         │
├───────────────────────┤   bottom               : 540×280   (wide)
│        bottom         │
└───────────────────────┘
        bar (60 px)         status/settings bar — always on
```

### How to pick a layout

Walk this in order:

1. **Ask user what's most important** (or infer from context). The card
   only fits 4 widgets — be choosy.
2. **One headline widget → middle**. The biggest, most readable slot.
   Use for the day's most important info (calendar, focus, next-meeting).
3. **Two glance widgets → top-left + top-right**. Pick widgets whose
   most-important info fits a narrow column (weather, inbox, ai-status,
   git-status).
4. **One detail widget → bottom**. Lists, multi-row info (todo, deadlines,
   pr-queue, messages).

Default fallback if the user has no opinion:

```
top-left  = weather       top-right = ai-status
middle    = calendar      bottom    = todo
```

If the user is deep in a coding session, swap to:

```
top-left  = git-status    top-right = ai-status
middle    = focus         bottom    = ai-tasks
```

If it's a desk-companion / meeting-heavy day:

```
top-left  = weather       top-right = inbox
middle    = next-meeting  bottom    = pr-queue
```

## Widget catalog

Every widget has a JSON schema at `schemas/<type>.schema.json`. The
"shape" lines below are summaries — read the schema for full constraints.

### Work staples

#### `weather` — _narrow OK_
City + big temp + condition + up to 2-day forecast.
```json
{"location":"Beijing",
 "current":{"temp_c":22,"condition":"晴"},
 "forecast":[{"day":"明","high":26,"low":14,"condition":"多云"}]}
```

#### `calendar` — _wide preferred_ (narrow shows fewer rows)
Today's events. Pass `now_iso` so the renderer can mark which is current.
```json
{"now_iso":"2026-05-21T13:30:00",
 "events":[{"start":"09:30","title":"standup"},
           {"start":"14:00","end":"15:00","title":"design review"}]}
```

#### `next-meeting` — _wide preferred_
The single next event with big countdown. Use when only ONE thing matters.
```json
{"title":"design review","start_in":"in 42m","start_at":"14:00",
 "location":"Zoom","attendees":"Alice, Bob, Carol"}
```

#### `messages` — _wide preferred_
Up to 3 IM previews. Each item: sender + preview + age.
```json
{"items":[{"sender":"Bob","preview":"PR ready for review","age":"2m"}]}
```

#### `inbox` — _narrow OK_
Total unread + per-source breakdown. Cap 4 sources.
```json
{"total":12,
 "sources":[{"name":"gmail","count":4},{"name":"slack","count":8}]}
```

#### `system` — _narrow OK_
CPU / mem / disk / battery / net / temp. Vertical 4-row in narrow slot.
**Note**: field is `memory_pct` (not `mem_pct`); `battery_pct=255` means no battery.
```json
{"cpu_pct":42,"memory_pct":63,"disk_pct":81,"battery_pct":88,
 "net_down_kbps":120,"temp_c":56}
```

#### `git-status` — _narrow OK_
Branch + modified/untracked/staged + ahead/behind + last commit.
```json
{"repo_name":"ai-desk-card","branch":"main",
 "modified":3,"untracked":1,"staged":0,"ahead":2,"behind":0,
 "last_commit_msg":"add login flow"}
```

#### `pr-queue` — _wide preferred_
PR counts + up to 4 items. Status: `review` | `yours` | `approved` | `blocked`.
```json
{"review_count":2,"your_open_count":1,
 "items":[{"number":"#42","title":"fix race","author":"alice","status":"review"},
          {"number":"#51","title":"feat: cron","author":"you","status":"yours"}]}
```

#### `now-playing` — _wide preferred_
Track + artist + position/duration (seconds, not float progress).
```json
{"track":"Stairway","artist":"Led Zeppelin",
 "source":"Spotify","position_sec":252,"duration_sec":482,"playing":true}
```

### Note-taking & focus

#### `scratch` — _wide preferred_
Free-form sticky note. **The most flexible 记事 component**. Use when
nothing else fits ("Bob coming at 3pm", "remember to update LinkedIn").
```json
{"text":"3pm 见 Bob — 带上昨天那张设计稿","source":"manual","age":"5m"}
```

#### `todo` — _either_
Up to 4 tasks. `tag`: `today` | `tomorrow` | `this-week` | `later` | `overdue`.
```json
{"title":"今天",
 "items":[{"text":"刷固件","tag":"today"},
          {"text":"写文档","tag":"overdue","due":"2026-05-20"}]}
```

#### `focus` — _wide preferred_
ONE active task + big text + subtitle + Pomodoro dots.
```json
{"task":"finish onboarding doc",
 "big_text":"18 min","subtitle":"started 12:18 · 番茄 2/4",
 "pomodoros_done":2,"pomodoros_planned":4}
```

#### `deadlines` — _either_
Multi-day countdown of must-finish-by dates. (Different from `todo`
which is today-focused.)
```json
{"items":[{"title":"H1 review","due_label":"in 2d","is_urgent":true},
          {"title":"tax filing","due_label":"3 weeks"}]}
```

#### `break-reminder` — _narrow OK_
Health nudge. Last-break + sitting + eye-rest.
```json
{"last_break_min_ago":78,"sitting_min":120,"next_eye_rest_min":-5,
 "advice":"stand up + look 20ft away"}
```

### AI monitoring

#### `ai-status` — _narrow OK_
Model + task + context bar. Push at the start of any non-trivial task.
```json
{"session_name":"refactor auth","model":"Sonnet 4.6","task":"writing tests",
 "context":{"used":42000,"limit":200000},"elapsed_seconds":480}
```

#### `ai-tasks` — _narrow OK_
Running / waiting / blocked / done-today counters. Vertical in narrow.
```json
{"running":2,"waiting":1,"blocked":0,"completed_today":7}
```

## Disambiguation — common confusions

- **inbox vs messages**: `inbox` is counts per source; `messages` is
  named senders' previews. Use inbox for "how much is waiting", messages
  for "who's poking me".
- **next-meeting vs calendar**: `next-meeting` is THE next event (big
  countdown); `calendar` is today's schedule (list).
- **deadlines vs todo vs calendar**: `deadlines` = multi-day countdown;
  `todo` = today's tasks; `calendar` = today's schedule.
- **focus vs todo**: `focus` = ONE active task; `todo` = a list. If user
  has one main task and 3 background items, push `focus` middle + `todo`
  bottom.

## Pushing — three ways

### A. The helper (recommended; validates schema)

```bash
$CLAUDE_PLUGIN_ROOT/scripts/widget.sh push <type> <slot> <<EOF
{ "title":"今天", "items":[...] }
EOF
```

Or directly:

```bash
$CLAUDE_PLUGIN_ROOT/skills/card-widget/scripts/push_widget.py \
    todo --slot bottom --data-stdin <<EOF
{ "title":"今天", "items":[{"text":"刷固件","tag":"today"}] }
EOF
```

### B. curl

```bash
curl -sf -X POST http://127.0.0.1:9877/widget \
    -H 'Content-Type: application/json' \
    -d '{"type":"todo","slot":"bottom","data":{...},"ttl":1800}'
```

### C. Preview without device

```bash
curl -sf -X POST http://127.0.0.1:9877/widgets/preview -o /tmp/p.png && open /tmp/p.png
```

### Pushing fields

- `type` — required, one of the 16 above
- `slot` — `top-left | top-right | middle | bottom | full`
- `data` — required, matches the type's schema
- `ttl` — seconds; 0 = no expiry. Use ~1800 for ephemeral info.
- `stale_after` — seconds; widget gets a "stale" badge but stays visible
- `theme` — `""` default. Don't set unless user asks.

### Failure modes

- **Schema mismatch** → daemon returns HTTP 400 with the failing field.
  Fix and re-push.
- **Daemon unreachable** → run `/card-onboard` to diagnose.
- **Widget shows but text is truncated** → you sent too much. Fewer items,
  shorter strings. The card is glanceable, not a Kindle.
- **Pushed but nothing changed on screen** → daemon debounces by ~1.5 s.
  Wait. If 30 s passes and still no change, check `tail /tmp/ai_desk_card_daemon.log`.

## Before pushing — check connection

```bash
bash $CLAUDE_PLUGIN_ROOT/skills/card-onboard/scripts/probe.sh --quick
```

If `transport.connected` is false → run `/card-onboard` first; don't try
to push.

## Sleep-frame (name card)

The device has a "digital business card" mode: when it deep-sleeps the
e-ink panel retains the last frame at 0 W until power-cycled. To push the
card and put the device to sleep:

```bash
/card-sleep
```

The card content comes from `ai-desk-card/assets/profile.yaml`. When the
user asks to update their card, **edit the YAML directly**:

```yaml
name: "..."           # Big name (≤ ~10 chars wide ideal)
tagline: "..."        # One short subtitle (≤ 36 chars)
bio_lines:            # 2-5 lines, auto-wrap. Empty string = half-gap.
  - "..."
tags:                 # Up to 4 chips
  - icon: "Job"
    text: "..."
qr_image: "qr.png"    # Optional; placeholder if missing
qr_label: "..."       # One line under QR
avatar_image: "avatar.png"
footer: "..."
```

Avatar + QR are PNGs in `ai-desk-card/assets/`. If user wants a custom
image, ask them to provide it; don't try to generate emoji or scannable
QR — Pillow's bundled fonts lack emoji and we use image-based QR
intentionally. Tag icons should be plain short labels (`Job` / `City` /
`Web`), not emoji.

## When to push proactively

- **Starting a non-trivial task**: push `ai-status` with `session_name` +
  `task`. Once per task, not per action — e-ink doesn't like frequent
  refreshes.
- **Long-running operation finishes**: push `scratch` with a success
  line ("PR opened: #1234"). User glances at card and knows.
- **Don't push** for trivial state changes or every tool call.

## Auto-refresh (every 2 hours)

If the user has set up the cron-driven refresh (see `/card-refresh` skill
+ `REFRESH.md`), the cron job will re-invoke headless Claude every 2
hours to refresh widgets with fresh data. **You don't need to manually
poll** — just push widgets when relevant during the conversation.
