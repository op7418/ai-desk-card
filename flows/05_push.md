# Flow 05 — Push a widget (the hot path)

The user said something like "show me X on my card". State is fully OK.
Pick widget type + slot + data, POST to daemon.

## Step 1 — Pick the widget type

| User intent | Widget type |
|---|---|
| weather / temp / 天气 | `weather` |
| today's meetings / 日历 | `calendar` |
| next meeting | `next-meeting` |
| todo / 待办 | `todo` |
| focus task / "currently working on" | `focus` |
| inbox / mail count | `inbox` |
| unread messages | `messages` |
| PR queue | `pr-queue` |
| git status | `git-status` |
| AI session status | `ai-status` |
| AI task list | `ai-tasks` |
| free-form note | `scratch` |
| break reminder | `break-reminder` |
| deadlines | `deadlines` |
| now playing music | `now-playing` |
| CPU / RAM / battery | `system` |

Full schema (every field, every constraint) for each type:
`plugin/skills/card-widget/schemas/<type>.schema.json`. Always read the
schema before pushing if you haven't pushed that type recently — fields
can be strict (e.g., `temp_c` must be int, not float).

## Step 2 — Pick the slot

The card uses a **2-1-1 layout, slot names are strings**:

| Slot | Size | Position |
|---|---|---|
| `top-left` | 270×280 | top-left quarter |
| `top-right` | 270×280 | top-right quarter |
| `middle` | 540×340 | full-width middle band |
| `bottom` | 540×280 | full-width bottom band |
| `full` | 540×960 | the entire screen (overrides the others) |

```bash
# See what's currently in each slot:
curl -sf "${CARD_DAEMON_URL:-http://127.0.0.1:9877}/widget" | python3 -m json.tool
```

Heuristics:
- If `~/.ai-desk-card/interests.yaml` exists and the user's intent
  matches a slot mapping, **use that slot** (overwrites the previous
  data of the same type).
- Otherwise pick the first empty slot (top-left → top-right → middle →
  bottom).
- If all 4 are occupied AND the user didn't say which to replace, ASK
  before overwriting.
- Use `full` only for splash / business-card / single-purpose displays
  — it hides everything else.

## Step 3 — Push

```bash
curl -sf -X POST "${CARD_DAEMON_URL:-http://127.0.0.1:9877}/widget" \
  -H 'Content-Type: application/json' \
  -d @- <<'JSON'
{
  "slot": "top-left",
  "type": "weather",
  "data": {
    "city": "Beijing",
    "temp_c": 22,
    "icon": "sun",
    "summary": "晴 22°C"
  },
  "theme": "",
  "ttl": 0,
  "stale_after": 3600
}
JSON
```

Latency:
- Wi-Fi: ~0.2 s
- USB: 1 s for single region update, 32 s for full frame
- BLE: frame-data broken — small commands only

## Step 4 — Confirm visible result

```bash
curl -sf -X POST "${CARD_DAEMON_URL:-http://127.0.0.1:9877}/widgets/preview" \
  -o /tmp/card-preview.png
open /tmp/card-preview.png       # macOS
# or: xdg-open on Linux
```

This renders what's currently on the device as a PNG. Useful when the
user asks "what's on my card?" without having to look up.

## Glyph safety

The CJK TTF doesn't include these — substitute or skip:
- ▢ ▶ ✎ ♪ ↑ ↓ ● ○ — … °

For unicode arrows use `>` / `<`; for bullets use `*` or `-`; for the
degree symbol just write "C" inline (`22°C` → `22C`).

## Removing a widget

```bash
curl -sf -X DELETE "${CARD_DAEMON_URL:-http://127.0.0.1:9877}/widget?slot=top-left"
# Or clear all:
curl -sf -X DELETE "${CARD_DAEMON_URL:-http://127.0.0.1:9877}/widget"
```
