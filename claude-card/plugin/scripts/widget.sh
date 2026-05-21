#!/usr/bin/env bash
set -euo pipefail
DAEMON="${CARD_DAEMON_URL:-http://127.0.0.1:9877}"
SUBCMD="${1:-show}"
shift || true

case "$SUBCMD" in
  ""|show)
    curl -sf "$DAEMON/widget" 2>/dev/null | python3 -m json.tool 2>/dev/null || {
      echo "daemon unreachable at $DAEMON — run /card-start first" >&2; exit 2;
    }
    ;;
  preview)
    out="${1:-/tmp/claude_card_preview.png}"
    if curl -sf -X POST "$DAEMON/widgets/preview" -o "$out" 2>/dev/null; then
      echo "wrote $out"
      command -v open >/dev/null 2>&1 && open "$out"
    else
      echo "preview failed (Pillow missing?)" >&2; exit 1
    fi
    ;;
  clear)
    slot="${1:-}"
    if [ -n "$slot" ]; then curl -sf -X DELETE "$DAEMON/widget?slot=$slot"
    else                    curl -sf -X DELETE "$DAEMON/widget"; fi
    echo
    ;;
  pair-status)
    curl -sf "$DAEMON/pair-status"; echo
    ;;
  unpair)
    curl -sf -X POST "$DAEMON/unpair"; echo
    ;;
  *)
    echo "usage: /card-widget [show|preview [out.png]|clear [slot]|pair-status|unpair]" >&2; exit 1
    ;;
esac
