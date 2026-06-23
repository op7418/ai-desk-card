# Flow 04 — Configure user interests

The user wants scheduled / auto-refresh pushes but
`interests.configured == false`. Build a one-time `interests.yaml` that
captures what they care about + how often + when.

## Step 1 — Ask the user

Ask in one round, accept any subset:

> "I'll set up auto-refresh on your card. Tell me which of these you'd
> like and how often. Roughly:
> - **Always visible**: weather, calendar, todos, current focus task
> - **Useful 1-2× per hour**: inbox count, PR queue, AI status
> - **Background context**: deadlines, break reminder, now-playing
>
> Default: weather + calendar + todos + inbox, refresh every 30 min,
> work hours only (08:00-22:00 Mon-Fri). Change any of that?"

Capture user preferences. Don't over-ask — if they say "the defaults are
fine", use them.

## Step 2 — Write the YAML

Path: `~/.ai-desk-card/interests.yaml`. Create the directory if missing:

```bash
mkdir -p "$HOME/.ai-desk-card"
```

PaperS3 / Windows shortcut after asking the user:

```powershell
.\.pio-venv\Scripts\python.exe scripts\card_cli.py interests --profile paper-s3
```

This writes a dashboard-aligned default:
`top-left=weather`, `top-right=ai-status`, `middle=calendar`, and
`bottom=todo`, with a `30m` work-hours cadence. Use flags to reflect the
user's answer, for example:

```powershell
.\.pio-venv\Scripts\python.exe scripts\card_cli.py interests --profile paper-s3 --city Shanghai --cadence 15m --hours 08-22
```

Write this shape (replace based on user input):

```yaml
# ai-desk-card interests — the agent reads this on every scheduled wake
# to know what to push.
version: 1

# What lives in each slot. Slot names are strings; the layout is 2-1-1:
#   top-left (270x280)  | top-right (270x280)
#   middle (540x340, full-width band)
#   bottom (540x280, full-width band)
# (There is also "full" but it takes over the whole screen.)
slots:
  top-left:  weather
  top-right: calendar
  middle:    todo
  bottom:    inbox

# How often to refresh. Agent honors this when self-scheduling.
schedule:
  cadence: "30m"   # 5m / 15m / 30m / 1h / 2h
  hours:   "08-22" # only refresh between these hours
  days:    "mon-fri"
  timezone: "Asia/Shanghai"

# Per-widget data hints (city for weather, repo path for git-status, etc.)
data_sources:
  weather:
    city: "Beijing"
  calendar:
    source: "macos"       # or "google" / "ics-url"
  todo:
    source: "reminders"   # or "things3" / "todoist"
  inbox:
    source: "mail.app"    # or "gmail"
  git_status:
    repo: "/Users/you/code/main-project"

# Optional: a quiet-hours override that swaps to sleep-card automatically.
quiet_hours:
  enabled: false
  start: "23:00"
  end:   "07:00"
```

Tell the user where you wrote it and that they can edit it any time
(the agent re-reads on every wake).

## Step 3 — Confirm + trigger first push

After writing, push a one-shot refresh so the user sees the result
immediately:

```bash
# The schedule kicks in at the next cron / loop tick, but do one now
# so the user sees it work.
for slot in 0 1 2 3; do
  # ... fetch data per slots[$slot] type and POST /widget
  # (see flow 05)
done
```

Then continue to flow 06 to set up the recurring schedule.

## When this flow should NOT run

Don't trigger this flow just because the user pushed one widget. Only
run it when:

- The user explicitly says "schedule" / "auto-refresh" / "定时刷新" /
  "keep updating"
- OR they ask for ≥2 things on the card AND haven't been set up yet
- OR they ask "what should I put on my card" — open-ended config

For a single ad-hoc push, go straight to flow 05.
