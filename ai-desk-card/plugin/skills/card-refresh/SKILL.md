---
name: card-refresh
description: |
  Invoked by cron (or manually) to refresh the widgets on the ai-desk-card
  e-ink display with fresh data. Reads the current widget cache, decides
  which widgets need new data, pulls from the user's data sources
  (calendar, mail, git, weather APIs, etc.), and pushes back via the
  card-widget skill. Use when invoked headless from cron, or when user
  says "刷新一下卡片" / "refresh card" / "update widgets now".
trigger_keywords:
  - card refresh
  - 刷新卡片
  - 更新卡片
  - 更新组件
  - refresh widgets
allowed-tools:
  - Bash
  - Read
  - Write
---

# card-refresh — periodic widget data refresh

You're invoked to re-pull data for whatever widgets are currently shown
on the user's ai-desk-card 副屏. This typically runs from cron every 2
hours (see [REFRESH.md](./REFRESH.md) for the setup). Be quick, idempotent,
and silent unless something's wrong.

## Operating principles

- **Read first, push second**. Pull the current widget cache from
  `GET /widget` — it tells you which slots are filled with which widget
  types. Only refresh those; don't push new widget types unprompted.
- **No data → don't push**. If a data source is unreachable (calendar
  not synced, mail offline), skip that widget. Leave the existing one
  in place rather than wiping with stale data.
- **Be fast**. Don't burn 30 s on one data source. 5 s timeout per
  fetcher; move on.
- **Be quiet**. No "I'm refreshing..." chatter when invoked from cron.
  Emit nothing on stdout unless there's an actionable error.

## What to do (every run)

### 1. Snapshot current cache

```bash
curl -sf http://127.0.0.1:9877/widget | python3 -m json.tool
```

Parse `widgets[]`. For each `{slot, type, age}`, decide:
- `age` < 60 s → just pushed, skip.
- `type` in `{ai-status, ai-tasks}` → driven by conversation, skip.
- `type` in `{focus, scratch}` → user-supplied, only refresh if explicitly
  asked.
- All others → refresh if you can.

### 2. Fetch fresh data per widget type

The card-widget skill's schemas tell you the data shape. Below are the
recommended sources per widget (use whatever's actually available on the
user's machine):

| Widget | Source | Notes |
| --- | --- | --- |
| `weather` | wttr.in / OpenWeather / system weather | Need user's location |
| `calendar` | `icalbuddy` on macOS / Google Calendar API / .ics file | macOS easiest |
| `next-meeting` | same as calendar — pick first event with `starts_in_min` ≥ 0 | |
| `inbox` | gmail API / mailctl / IMAP / Slack API | Per-source counts only |
| `messages` | iMessage db / Slack DMs | macOS: `~/Library/Messages/chat.db` (read-only) |
| `pr-queue` | `gh pr list` against user's repos | List repos via config |
| `git-status` | `git -C <cwd> status --porcelain` + `git log -1` | One repo only |
| `system` | psutil / `uptime` / `vm_stat` | macOS: vm_stat for mem, df for disk |
| `now-playing` | macOS: `osascript -e 'tell application "Spotify"...'` | Skip if not running |
| `todo` | macOS Reminders (use `fetch_todo_reminders.py` in card-widget) | |
| `deadlines` | user-maintained list (see assets/deadlines.yaml if it exists) | |
| `break-reminder` | local idle / activity tracking | Best-effort |

**You don't need to support all of these in one refresh.** Start with
the 3-4 widgets the user actually has on the card, refresh those, push,
exit.

### 3. Push back

Use the card-widget skill's `push_widget.py` helper or curl. Re-push the
SAME `{slot, type}` with new `data`. Daemon will replace and trigger a
single debounced frame render.

Per-widget TTL: pass `ttl=7800` (2h 10min) so widgets fade if cron
breaks. That way a stuck cron doesn't leave hours-old data on the panel
forever.

### 4. Done — exit

Don't summarize, don't ask follow-up questions. Just exit. Cron user sees
nothing in their terminal.

## When invoked interactively (not from cron)

If the user says "刷新一下卡片" in conversation, do the same thing but
**briefly tell them what you did**:

> Refreshed: calendar (3 events), weather (24°C 晴), pr-queue (2 reviews
> waiting). Skipped: inbox (gmail API not configured).

## Error handling

- **Daemon down** → run `/card-onboard` decision tree, but don't try to
  start it from cron (user won't see the prompt). Just exit with a
  diagnostic line on stderr.
- **Network down** → skip remote sources, push local ones (system,
  git-status) anyway.
- **Schema mismatch on push** → log to stderr, continue. The daemon
  rejects the bad widget; other widgets still get refreshed.

## What NOT to do

- ❌ Don't change which widgets are in which slot. That's user-controlled.
- ❌ Don't push widgets that weren't already there (e.g., "I noticed you
  don't have a weather widget, let me add one").
- ❌ Don't write `ai-status` from this skill — that's driven by interactive
  Claude Code sessions.
- ❌ Don't fetch data from sources that need OAuth without checking if
  credentials are configured.

## Helper scripts

- `scripts/refresh_loop.sh` — one-shot refresh entry point. Used as the
  cron command. Wraps the headless Claude invocation.
- `scripts/fallback_refresh.py` — pure-Python no-AI version that only
  refreshes `system`, `git-status`, and `weather` (wttr.in). For users
  who don't want token cost.
