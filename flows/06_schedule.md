# Flow 06 — Set up scheduled push

The user wants the card to auto-refresh on a cadence. State is OK,
interests.yaml exists. Now wire up the recurring push.

This Skill provides the *what* (interests + push). The *when* comes
from the agent's own scheduling primitive. Pick whichever fits your
runtime:

## Option A — Agent's native loop primitive (preferred)

If you're an agent with a native loop or wake-up tool, use it. You stay
in control; no external daemon to babysit.

### Claude Code

```
/loop 30m
  Refresh the user's ai-desk-card from ~/.ai-desk-card/interests.yaml.
  For each slot in slots, fetch fresh data via the source listed in
  data_sources, then POST /widget. Skip if outside schedule.hours.
```

Or `ScheduleWakeup({ delaySeconds: 1800, reason: "card refresh tick" })`
with the same prompt at fire time.

### Codex / Gemini / Aider

Use the equivalent recurring-task primitive in those agents (if any).

## Option B — Cron + the bundled refresh script

If the agent has no native loop OR the user wants refresh even when the
agent isn't running, fall back to cron.

```bash
crontab -e
```

Add a line like:

```cron
# Workday 08:00-22:00, every 30 minutes
*/30 8-21 * * 1-5  /path/to/ai-desk-card/plugin/skills/card-refresh/scripts/refresh_loop.sh
```

The script auto-picks any AI CLI on PATH (claude / codex / gemini /
aider). To pin one:

```cron
*/30 8-21 * * 1-5  AI_CLI=codex /path/to/refresh_loop.sh
```

## Option C — No-AI fallback (lowest cost)

Some widgets (weather, system, git-status) need no AI at all — they can
be refreshed by a pure Python script:

```cron
0 */2 * * *  /usr/bin/python3 /path/to/plugin/skills/card-refresh/scripts/fallback_refresh.py
```

Configure via `~/.card-refresh.yaml`:

```yaml
location: "Beijing"
repo_path: "/Users/you/code/main-project"
```

Trade-off: zero per-tick cost, but only the AI-free widgets refresh.

## What to do on each tick

Whichever scheduler you wire up, the per-tick logic is:

1. Read `~/.ai-desk-card/interests.yaml`
2. Check `schedule.hours` + `schedule.days` — skip if outside window
3. For each `slots[N]` entry:
   - Fetch fresh data from the matching `data_sources[type]`
   - POST `/widget` (see flow 05)
4. Done. Each tick is idempotent; no extra state needed.

## Sound notifications (Paper Color only)

The Color device has a 1 W speaker + ES8311 codec. When the scheduled
tick detects a deadline event (calendar `now` / next-meeting `start_in
< 1m` / todo with `tag: overdue` newly arrived / urgent deadline), also
POST a beep to the device:

```bash
curl -sf -X POST "http://<color-device-ip>:9880/beep" \
  -H 'Content-Type: application/json' \
  -d '{"pattern":"chime"}'        # chime|urgent|alert
```

Three preset patterns:

- `chime` — three ascending notes (C5→E5→G5), ~600 ms. Use for soft
  "look at the card" cues: meeting in 5 min, todo deadline approaching.
- `urgent` — three rapid 880 Hz beeps, ~400 ms. Use for fired
  deadlines: meeting starting now, overdue todo.
- `alert` — single sharp 1320 Hz tone, ~150 ms. Use for ambient updates
  that don't need rich melody: new mail arrived, push completed.

Custom tone (advanced): send `{"freq": 660, "ms": 200}` instead of
pattern. Range 50–12000 Hz, 1–3000 ms.

V1.1 has no speaker — `/beep` doesn't exist there. Detect by reading
`device.color_mode == "spectra6"` in the `/status` response, or by
catching the 404 silently.

## Stopping the schedule

- Native loop: stop the loop in the agent's UI / cancel the scheduled
  wakeup
- Cron: `crontab -e` and remove the line
- Tell the user the card will keep showing the last frame indefinitely. On
  M5Paper V1.1 deep sleep this is near-zero power; on PaperS3 it is the
  normal sleep-card/always-on behavior.
