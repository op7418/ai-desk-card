# AI Desk Card 自动刷新指南

副屏要持续有价值，widget 数据就得新鲜。这篇讲三种刷新方式 + 我推荐的
那种。

## TL;DR — 推荐方案（v0.8 Wi-Fi 已通后）

```cron
# 工作日 8:00-22:00, 每 30 分钟刷一次. headless Claude 拉数据 + 决策
*/30 8-21 * * 1-5  /Users/<you>/Documents/code/claude-desktop-buddy-repo/ai-desk-card/plugin/skills/card-refresh/scripts/refresh_loop.sh
```

**为什么 30 分钟而不是 2 小时**：v0.8 Wi-Fi 路径下单 widget 改动 0.2 秒
到屏，没有"刷一次要 30 秒"的物理代价。更短的间隔 = 更新鲜的副屏。

预算 ≈ **每天 28 次 × 每次 ¥0.3-0.8 (Sonnet 4.6) ≈ ¥8-22/天**（工作日）。
追求最低成本：

- **换 Haiku** — 把脚本里 `claude -p` 改成 `claude -p --model haiku`，
  ≈ 1/5 成本（¥2-4/天）
- **拉长间隔** — 改回 `0 9,11,13,15,17 * * 1-5`（每 2 小时）→ ¥3-6/天
- **完全用 fallback** — 把 cron 指向 `scripts/fallback_refresh.py`（0
  成本但只能刷 weather / system / git-status 这三个本地能算的）

## 三种刷新架构

### A. cron + headless Claude（**推荐**）

```
cron (系统定时) → claude -p "/card-refresh" → Claude 自己拉数据 → push
```

✅ 简单 — cron 是 macOS/Linux 都自带的成熟机制
✅ 灵活 — Claude 可以智能选数据源，遇到 OAuth 没配也能跳过
✅ 可见 — 用户能 `crontab -l` 看到，不会"神秘进程"
✅ 易调试 — 手动跑一次脚本就能验
❌ 每次刷新 ≈ ¥0.5-1 (Sonnet) / ¥0.1 (Haiku) token 成本

### B. 设备端定时拉起 AI（设备 ping daemon → daemon 触发 Claude session）

❌ Claude Code 本身没有 server mode；要常驻一个 webhook 接收端
❌ 反向通道复杂 — 还要解决设备睡眠时怎么唤醒、怎么不漏触发
❌ 多设备 / 多用户场景几乎跑不通

不推荐。除非你愿意自己维护一个 daemon-of-daemons。

### C. 纯 Python 脚本（不调 AI）

```
cron → scripts/fallback_refresh.py → 硬编码的数据源 → push
```

✅ 0 token 成本
✅ 离线可用
❌ 加新数据源要改代码
❌ 数据源失败 → 整个脚本可能挂；AI 版能跳过
❌ 不能根据 context 智能调整（比如开会时 push next-meeting 提前 15min 警告）

适合：**预算敏感 + 数据源稳定 + 不需要 AI 整理** 的用户。
我们把这个版本留作 fallback，不是默认。

## 安装方案 A（cron + headless Claude）

### 1. 确认 Claude CLI 可用

```bash
which claude        # /usr/local/bin/claude or similar
claude --version
```

如果没有，先装：https://docs.claude.com/cli

### 2. 测试单次刷新

```bash
bash $CLAUDE_PLUGIN_ROOT/skills/card-refresh/scripts/refresh_loop.sh
```

应该看到 stderr 上几行日志，stdout 干净，等 ~30 s 副屏上 widget 数据更新。

### 3. 加 cron 条目

```bash
crontab -e
```

加入：

```cron
0 9,11,13,15,17,19 * * 1-5  /Users/<you>/Documents/code/claude-desktop-buddy-repo/ai-desk-card/plugin/skills/card-refresh/scripts/refresh_loop.sh
```

时区是 macOS 本地时间。**强烈建议限工作时段**（9:00-19:00 周一到周五），
不然半夜也在烧 token + 用户也不看。

### 4. 验证

```bash
crontab -l                                    # 确认条目在
tail -f ~/.ai-desk-card-refresh.log            # 看 cron 日志
```

10 分钟后回来看副屏，widget 应该比 cron 启动前新。

## 安装方案 C（纯脚本 fallback，可选）

如果你想完全离线 / 没预算 / 数据源少：

```cron
0 */2 * * *  /usr/bin/python3 /path/to/ai-desk-card/plugin/skills/card-refresh/scripts/fallback_refresh.py
```

只刷这几个 widget：
- `weather`（wttr.in，根据 `~/.card-refresh.yaml` 里的 `location`）
- `system`（psutil）
- `git-status`（针对 `~/.card-refresh.yaml` 里的 `repo_path`）

其他 widget（calendar / inbox / pr-queue / messages）需要 AI 版才能可靠拉。

## 暂停刷新

短期：注释 crontab 那行。
长期：删掉 crontab 那行 + `rm ~/.ai-desk-card-refresh.log`。

刷新不会自动重启，只有 cron 在跑就会一直来。

## 成本日志

每次 headless Claude 调用都会打 token 用量到 `~/.ai-desk-card-refresh.log`
的 `[cost]` 行。每周看一眼，如果 > ¥50/周就要么换 Haiku 要么减少频次。

## 进阶：让设备主动告诉 cron 跳过

设备端 v0.6.4 + 会上报 `battery_pct`。如果电量 < 15% 你可以让
`refresh_loop.sh` 跳过这次刷新（少一次全屏刷 ≈ 续航多 1-2 天）。

```bash
# 在 refresh_loop.sh 里
BATTERY=$(curl -sf http://127.0.0.1:9877/pair-status | python3 -c 'import sys,json; print(json.load(sys.stdin).get("battery_pct") or 100)')
if [[ "$BATTERY" -lt 15 ]]; then
  echo "[skip] battery low ($BATTERY%); skipping refresh" >&2
  exit 0
fi
```

（v0.6.4 之前 `battery_pct` 永远是 None；该检查会一直走 100 分支。）
