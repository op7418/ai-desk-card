#!/usr/bin/env bash
set -euo pipefail
PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SUBCMD="${1:-detect}"
shift || true

export PYTHONPATH="/opt/homebrew/Cellar/platformio/6.1.19_1/libexec/lib/python3.14/site-packages:${PYTHONPATH:-}"
INSTALLER="$PROJ_ROOT/plugin/skills/card-widget/scripts/install_firmware.py"

case "$SUBCMD" in
  detect)
    python3 "$INSTALLER" --detect "$@"
    ;;
  flash)
    # If no .pio build present, build first.
    if [ ! -f "$PROJ_ROOT/.pio/build/card/firmware.bin" ]; then
      echo "[install] no firmware.bin yet, building..."
      ( cd "$PROJ_ROOT" && pio run -e card )
    fi
    python3 "$INSTALLER" --flash "$@"
    ;;
  *)
    echo "usage: /card-install [detect|flash]" >&2; exit 1
    ;;
esac
