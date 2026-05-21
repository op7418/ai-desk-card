---
description: Refresh widget data on the claude-card. Called by cron; also invocable manually.
---

Invokes the card-refresh skill: AI reads which widgets are currently on
the card, re-fetches their data from the appropriate sources (calendar,
weather, git, etc.), and re-pushes. Idempotent and safe to run any time.

When invoked from cron (via `refresh_loop.sh`), runs silently. When run
in conversation, AI reports what got refreshed and what was skipped.

See REFRESH.md for cron setup + cost notes.

!`bash "$CLAUDE_PLUGIN_ROOT/skills/card-refresh/scripts/refresh_loop.sh"`
