#!/usr/bin/env bash
# claude-card cron 入口 — 每次 cron 触发跑一次。
# 用 headless Claude 来执行 /card-refresh skill。
#
# crontab 示例（工作日 9-19 点 每 2h）:
#   0 9,11,13,15,17,19 * * 1-5  /path/to/this/refresh_loop.sh
#
# 日志：~/.claude-card-refresh.log（每行带时间戳 + 一行 [cost] 汇总）

set -u

LOG="${HOME}/.claude-card-refresh.log"
DAEMON_URL="${CARD_DAEMON_URL:-http://127.0.0.1:9877}"

ts() { date "+%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(ts)] $*" >> "$LOG"; }

log "=== refresh start ==="

# 0. daemon 必须在跑
if ! curl -sf -m 2 "$DAEMON_URL/pair-status" >/dev/null; then
  log "ERROR daemon not reachable at $DAEMON_URL — skipping refresh"
  exit 1
fi

# 1. 跑 headless Claude，让它执行 /card-refresh skill
#    --print          —— 一次性、非交互模式
#    --max-turns 5    —— 限制 turn 数，避免失控
#    /card-refresh   —— skill slash command
CLAUDE_BIN="$(command -v claude || true)"
if [[ -z "$CLAUDE_BIN" ]]; then
  log "ERROR 'claude' CLI not in PATH. Install: https://docs.claude.com/cli"
  exit 2
fi

# stderr 进日志、stdout 默默吃掉（cron 不需要看）
"$CLAUDE_BIN" --print --max-turns 5 "/card-refresh" \
    > /dev/null \
    2>> "$LOG"
RC=$?

log "headless claude rc=$RC"

# 2. 抓最后几行 token 用量（Claude CLI 会在 stderr 打 [cost] 之类）
COST=$(tail -50 "$LOG" | grep -E '(\$|tokens)' | tail -1 || true)
[[ -n "$COST" ]] && log "[cost] $COST"

log "=== refresh end ==="
exit "$RC"
