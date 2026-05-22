# AI Desk Card · 中文文档

> 桌面旁边的一块 4.7 英寸墨水屏，由 AI Agent 推送内容。
> 一个 Skill 接入任意 Agent，问一句 "把今天日程显示到卡片上" 就行。

> 英文版 [README.md](README.md) · 工程交接 [HANDOVER.md](HANDOVER.md) · 产品定位 [PRODUCT.md](PRODUCT.md)

---

## 这个项目是什么

把 [M5Paper V1.1](https://docs.m5stack.com/en/core/m5paper) 变成你的**AI 副屏**：

- 540×960 墨水屏立在显示器旁边，瞥一眼就能看
- 内容由 AI Agent 推送（Claude Code / Codex / Gemini CLI 等都行）
- 全程本地：Wi-Fi LAN 直推，0.2 秒一帧，无云依赖
- 电池待机几个月 · 关屏 0 功耗保留最后一帧（息屏当电子名片）

```
你 ──问──▶ AI Agent ──触发──▶ Skill ──HTTP──▶ daemon ──Wi-Fi──▶ M5Paper
                                                                    │
                                                                    └─▶ 4 个槽位 + 16 种 widget
```

## 屏上能放什么

**4 个槽位 / 2-1-1 布局**

| 槽位 | 尺寸 | 位置 |
|---|---|---|
| `top-left` | 270×280 | 左上 |
| `top-right` | 270×280 | 右上 |
| `middle` | 540×340 | 中间整条 |
| `bottom` | 540×280 | 底部整条 |
| `full` | 540×960 | 整屏（覆盖以上）|

**16 种 widget 类型**

- 工作日常：`weather` 天气 · `calendar` 日程 · `next-meeting` 下个会 · `messages` 消息 · `inbox` 收件箱 · `system` 系统状态 · `git-status` git · `pr-queue` PR 队列 · `now-playing` 正在播放
- 笔记 / 专注：`scratch` 便签 · `todo` 待办 · `focus` 当前专注 · `deadlines` deadline · `break-reminder` 休息提醒
- AI 监控：`ai-status` 当前 AI session · `ai-tasks` AI 任务列表

底栏有两个可点 chip：**睡眠**（推电子名片 + 设备深度休眠）· **设置**（弹设置页）。

---

## 硬件准备

| 项目 | 说明 |
|---|---|
| **M5Paper V1.1** | 主力支持。约 ¥600。4.7 寸墨水屏 / ESP32 / 8 MB PSRAM / 16 MB flash / 1150 mAh / USB-C / 2.4 GHz Wi-Fi / BLE 4.2 |
| M5Paper V1.0 | 可能能用，电池阈值参数 (`4150 mV`) 可能要调 |
| M5Paper S3 | 需要 1-2 天移植（BLE stack 不同）|
| USB-C **数据线** | 烧固件用一次。普通充电线不一定行 |
| (可选) USB-C 充电器 | 想常开 Wi-Fi 模式就要 |

## Agent 准备

任何支持 Claude 风格 Skill 格式的 AI Agent 都行。已测 / 大概率兼容：

| Agent | 状态 |
|---|---|
| **Claude Code** | ✅ 主力测试 |
| Codex CLI | 🟡 同 SKILL.md 格式，应该可用 |
| Gemini CLI | 🟡 大概率可用 |
| Aider | 🟡 大概率可用 |
| 自己写的 CLI | 只要识别 `SKILL.md` 就行 |

---

## 一次性安装（约 10 分钟）

### 第 1 步 · 装 PlatformIO

```bash
pipx install platformio
# 或在 VS Code 装 PlatformIO IDE 插件
```

### 第 2 步 · 克隆 + 烧固件

```bash
git clone https://github.com/op7418/ai-desk-card.git
cd ai-desk-card

# 设备 USB-C 接电脑，确认 /dev/cu.usbserial-* 出现
ls /dev/cu.usbserial-* 2>/dev/null

# 编译
pio run -e card

# 烧 CJK 字体到 LittleFS 分区（首次必须，否则中文显示豆腐块）
pio run -e card -t uploadfs

# 烧固件
pio run -e card -t upload
```

总耗时 ~1 分钟（首次会下载工具链，约 500 MB）。烧完设备自动重启，屏上出现 "v0.8 · waiting for daemon..." splash。

### 第 3 步 · 把这个 Skill 装到你的 Agent 里

**Claude Code（推荐用 symlink，便于改了立即生效）：**

```bash
mkdir -p ~/.claude/plugins
ln -s "$(pwd)" ~/.claude/plugins/ai-desk-card
```

**其他 Agent**：把这个 repo 的根目录链或复制到 Agent 的 Skill 目录就行。这个项目本身**就是一个 Skill** —— 根目录的 `SKILL.md` 是入口。

验证 Skill 装好了 —— 打开 Agent，问一句"我有 ai-desk-card 吗"，应该会触发 Skill 的描述。

### 第 4 步 · 启动 daemon

Daemon 是个小 Python 进程，在 Agent 和设备之间转发：

```bash
# 让 Agent 启动
> 把卡片打开

# 或手动
bash plugin/scripts/start.sh
```

Daemon 自动按优先级选传输：**Wi-Fi (0.2s) > USB (1-32s) > BLE**。第一次启动设备还没 Wi-Fi，会走 USB。

确认 daemon 在跑：

```bash
tail -10 "${TMPDIR:-/tmp}/ai_desk_card_daemon.log"
# 看到 "[ready] ai-desk-card daemon v0.8" 就 OK
```

### 第 5 步 · 配 Wi-Fi（重要 · 把推送速度从 32 秒降到 0.2 秒）

```bash
# 让 Agent 做
> 帮我把卡片连到 Wi-Fi "MyWiFi" 密码 "xxxxxx"

# 或手动 curl
curl -X POST http://127.0.0.1:9877/provision-wifi \
  -H 'Content-Type: application/json' \
  -d '{"ssid":"MyWiFi","password":"xxxxxx"}'
```

⚠️ ESP32 **只支持 2.4 GHz** — 5 GHz SSID 连不上。

等 15 秒，daemon 重启就会切到 Wi-Fi 推送：

```bash
bash plugin/scripts/stop.sh && bash plugin/scripts/start.sh
# 日志里看到 "[transport] found Wi-Fi peer X.X.X.X:9880, using Wi-Fi"
```

### 第 6 步 · 推第一个 widget

```
> 在卡片上显示北京今天天气
```

Agent 会调用 `/card-widget`，~0.2 秒后屏上出现。

---

## 日常使用

装完之后，你跟 Agent 说自然语言就行：

| 你说 | Agent 干什么 |
|---|---|
| "把今天日程显示在卡片上" | 推一个 calendar widget |
| "卡片显示我现在在做的任务" | 推一个 focus widget |
| "让卡片每 30 分钟刷新天气和邮件" | 写 `~/.ai-desk-card/interests.yaml` + 设置 loop |
| "晚上 11 点自动息屏显示名片" | 在 interests.yaml 里加 quiet_hours |
| "现在卡片上是啥" | curl `/widgets/preview` 拿当前画面 PNG |
| "把卡片息屏" | 推电子名片 + 设备深度休眠 0 功耗 |
| "卡片连不上" | 触发 `/card-onboard` 流程，自动诊断 |

### 定时自动刷新（可选）

写偏好文件 `~/.ai-desk-card/interests.yaml`：

```yaml
version: 1
slots:
  top-left:  weather
  top-right: calendar
  middle:    todo
  bottom:    inbox

schedule:
  cadence:  "30m"           # 5m / 15m / 30m / 1h / 2h
  hours:    "08-22"         # 只在这个时段刷
  days:     "mon-fri"
  timezone: "Asia/Shanghai"

data_sources:
  weather:
    city: "Beijing"
  calendar:
    source: "macos"          # 或 google / ics-url
  todo:
    source: "reminders"      # 或 things3 / todoist
  git_status:
    repo: "/Users/you/code/main-project"

# 安静时段自动切到名片 + deep sleep（daemon 自己处理，无需 Agent 在线）
quiet_hours:
  enabled: true
  start:   "23:00"
  end:     "07:00"
```

定时触发方式三选一：

- **Agent 原生 loop**（推荐）：让 Agent 用自己的 `/loop` 或 `ScheduleWakeup` 定时跑
- **cron**：编辑 `crontab -e`，加一行 `*/30 8-21 * * 1-5 bash /path/to/ai-desk-card/plugin/skills/card-refresh/scripts/refresh_loop.sh`
- **纯 Python 无 AI 兜底**：只想要 weather/system/git 这几个不需要 AI 的 widget，跑 `fallback_refresh.py`

### 电池模式（架构 C · 几个月续航）

USB-C 拔掉，设备靠电池跑。daemon 默认 Wi-Fi 关，BLE 待机。
- 你要推内容时：daemon 通过 BLE 唤醒设备 → 设备拉 Wi-Fi → daemon HTTP 推帧 → 设备 linger 30 秒后断 Wi-Fi
- 一次唤醒推送 ~0.2 mAh，每天 24 次推送 → 1150 mAh 电池约 6 个月

---

## 工作原理（一图看懂）

```
你说话                                      M5Paper
  │                                             ▲
  ▼                                             │
AI Agent ──┐                                    │
           │ 触发 Skill                          │
           ▼                                    │
       SKILL.md 路由表                           │
           │                                    │
           │  根据 scripts/state.sh 探测：       │
           │  · 固件 / daemon / Wi-Fi 状态       │
           │  · 设备活没活                       │
           │  · 用户兴趣配置                     │
           │                                    │
           └─▶ 选 7 个子流程之一                 │
                  │                             │
                  ▼                             │
                Skill 自动执行：                 │
                · flow 01 烧固件                │
                · flow 02 诊断传输               │
                · flow 03 配 Wi-Fi              │
                · flow 04 问偏好                │
                · flow 05 推 widget ────────────┘
                · flow 06 设定时
                · flow 07 息屏 + 名片
                  │
                  ▼
             POST 到 daemon (127.0.0.1:9877)
                  │
                  ▼
              daemon 渲染（Python + Pillow）
                  │
                  ▼
              HTTP / USB / BLE 推帧到设备
```

完整的子流程在 [flows/](flows/) 目录下。

---

## 触屏 / 按钮 / 唤醒

| 操作 | 行为 |
|---|---|
| 点底栏右下 **"设置"** | 翻到设置页（chip 会快闪一下白色 ACK）|
| 设置页左上 **"返回"** | 翻回 widget 视图 |
| 点底栏 **"睡眠"** | 推电子名片 + 设备深度休眠 |
| 短按旋钮 | 唤醒设备（需要先短按，长按 2s 是关机）|
| 设备背面 RST 键 | 物理硬重启 |

---

## 常见问题

**Q: 屏幕一直在 boot splash**

A: daemon 没推帧。`bash scripts/state.sh` 看 `device.alive` 字段：
- `false` → daemon 没收到设备心跳，检查 USB 或 Wi-Fi
- `true` 但还是 splash → `rm "${TMPDIR:-/tmp}/ai_desk_card_last_frame.png"` 清缓存帧后重启 daemon

**Q: 点按钮没反应**

A: 看 daemon 日志有没有 `[touch<]` 行。没有的话：
- 检查触屏区域：底栏 chip 在屏最下 60 px
- 检查 daemon 是否同时开了侧通道（Wi-Fi + USB 同时插时，日志会有 `[side-serial] reading ...`）

**Q: Wi-Fi 连不上**

A: 看 daemon 日志的 wifi 状态码：
- `1` = SSID 找不到（拼错 / 或者你给的是 5 GHz only 的 SSID）
- `4` = 密码错
- `6` = DHCP 失败（路由器问题）

**Q: 中文显示豆腐块**

A: 忘了 `pio run -e card -t uploadfs` 烧 CJK 字体。重新烧一次就好。

**Q: 不想用 Claude Code，能用别的 Agent 吗**

A: 能。这个 repo 根目录的 `SKILL.md` 是 agent-agnostic 入口。Codex / Gemini / Aider 等只要支持 Skill 格式都能识别。`plugin/` 目录里的 slash 命令（`/card-widget` 等）只是 Claude Code 用户的便利层。

---

## 目录结构

```
ai-desk-card/
├── SKILL.md                 ← 任何 Agent 的入口
├── scripts/state.sh         ← 状态探测脚本
├── flows/                   ← 7 个子流程（install / transport / wifi / interests / push / schedule / sleep）
├── plugin/                  ← Claude Code 兼容层（slash 命令 + 共享 helpers）
│   ├── plugin.json
│   ├── commands/            ← /card-* 命令
│   ├── scripts/             ← start.sh / stop.sh / status.sh ...
│   └── skills/              ← 子 skill（被 SKILL.md 主路由间接调用）
├── daemon/                  ← Python HTTP 桥 + PIL 渲染器
│   ├── card_daemon.py       ← 主进程（HTTP server + 传输层 + 后台 loop）
│   ├── card_render.py       ← widget view 渲染
│   ├── card_render_settings.py
│   └── card_render_sleep.py ← 电子名片渲染
├── src/                     ← 固件（frame_receiver + wifi + http + ble + 触屏 poll）
├── assets/                  ← profile.yaml（你的名片信息）+ qr.png / avatar.png
├── data/                    ← CJK 字体（烧到 LittleFS）
├── HANDOVER.md              ← 工程交接
├── PRODUCT.md               ← 产品定位
├── PLAN.md / PLAN_RENDERING_V06.md   ← 架构 ADR
└── README.md / README.zh-CN.md       ← 英文 / 中文版
```

---

## 三种供电架构

daemon 自动按设备状态选；固件根据是否有 USB-C 供电选 Wi-Fi 策略。

| 模式 | 设备状态 | 单帧延迟 | 续航 |
|---|---|---|---|
| **A** 常插电 | USB-C 供电 + Wi-Fi 长开 | 0.2 s | n/a（供电中）|
| **B** USB only | USB 数据线（还没配 Wi-Fi）| 1 s 区域 / 32 s 全帧 | n/a（供电中）|
| **C** 电池 + BLE 待机 | Wi-Fi 关，daemon BLE 唤醒 | 5 s 唤醒 + 0.2 s 推 | ~6 个月 |

架构 C 是最推荐的电池模式：屏挂在桌边几个月不充电，AI Agent 推内容时 BLE 唤醒一次就够。

---

## 许可证 / 贡献

- 项目本体：[GPL-3.0 + 署名条款](LICENSE)
- 内嵌 EPDGUI 框架（来自上游 M5Paper_FactoryTest）：MIT，© 2020 m5stack
- 欢迎 PR / Issue：https://github.com/op7418/ai-desk-card

最有价值的贡献：
- 硬件实拍照 / 视频（帮新用户看清产品形态）
- Linux / Windows 上 daemon 测试
- M5Paper V1.0 / S3 固件移植验证
- 新 widget schema + 渲染器
- Captive portal Wi-Fi 配网（roadmap）
