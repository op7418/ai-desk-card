# AI Desk Card · 桌面 AI 副屏 Skill

![GitHub stars](https://img.shields.io/github/stars/op7418/ai-desk-card?style=flat-square)
![License](https://img.shields.io/github/license/op7418/ai-desk-card?style=flat-square)
![Skill](https://img.shields.io/badge/Skill-Agent-111111?style=flat-square)
![M5Paper](https://img.shields.io/badge/M5Paper-V1.1-0A7CFF?style=flat-square)
![Claude Code](https://img.shields.io/badge/Claude%20Code-Supported-6B5B95?style=flat-square)
![Codex](https://img.shields.io/badge/Codex-Supported-222222?style=flat-square)

> 🌏 **English version: [README.en.md](./README.en.md)**

一个适配 Claude Code / Codex 等 Agent 的桌面副屏 Skill。把 [M5Paper V1.1](https://docs.m5stack.com/en/core/m5paper) 4.7 寸墨水屏立在显示器旁边，由 AI Agent 推送 widget：天气、日程、todo、PR 队列、AI 状态、休息提醒……

**装上 Skill 后，烧固件 / 配 Wi-Fi / 推内容 / 设置定时全部由 Agent 引导**，你不用自己跑一行 `pio` 或 `curl`。

![AI Desk Card 桌面效果](https://github.com/user-attachments/assets/b4777ba7-d668-42c1-9920-3e6d8bef534e)

```
你 ──说自然语言──▶ AI Agent ──触发──▶ Skill ──自动执行──▶ M5Paper 屏上
```

## 30 秒开始

```bash
npx skills add https://github.com/op7418/ai-desk-card --skill ai-desk-card
```

也可以把下面这段话直接发给有 shell 权限的 AI Agent：

```text
帮我安装 ai-desk-card Skill。把 https://github.com/op7418/ai-desk-card 克隆到 ~/.claude/skills/ai-desk-card，安装完成后检查 SKILL.md、flows/、daemon/、src/、assets/ 是否存在。
```

已经装过想更新：

```text
帮我更新 ai-desk-card。请进入 ~/.claude/skills/ai-desk-card 执行 git pull，然后告诉我当前最新 commit。
```

装完之后，假设你手上有 M5Paper V1.1 + USB-C 数据线，直接对 Agent 说：

```text
帮我把 ai-desk-card 装上。我手上是 M5Paper V1.1，USB-C 已经插好了。
```

Skill 会自动：

1. 探测当前状态（PlatformIO / USB 设备 / daemon / Wi-Fi 配没配）
2. 缺啥装啥（PlatformIO 没装就 `pipx install`）
3. 编译 + 烧 CJK 字体 + 烧固件（约 1 分钟）
4. 启动 daemon
5. 问你 Wi-Fi 密码 → 自动配上
6. 推第一个 widget 上去

之后日常使用就是和 Agent 自然对话：

```text
在卡片上显示今天北京的天气。
让卡片每 30 分钟刷新天气和未读邮件，工作日 8 点到 22 点。
现在卡片上是啥？
晚上 11 点之后自动息屏显示我的名片。
```

## 效果

- 🖥 **桌面 ambient 副屏**：540×960 墨水屏立在显示器旁，瞥一眼就知道今天的状态
- 🤖 **AI 主动推送**：Agent 决定推什么 widget、什么时候推；你不用自己开浏览器查天气
- 📦 **16 种 widget**：weather / calendar / todo / focus / inbox / pr-queue / ai-status / git-status / now-playing / break-reminder / scratch / messages / deadlines / next-meeting / system / ai-tasks
- 🎨 **服务端渲染**：daemon 用 Python + Pillow 渲染像素帧，固件只负责显示；想加新 widget 只改 Python，不用动 C++
- 🔌 **三种供电模式自动切换**：USB 常开 / USB 数据线 / 电池 + BLE 待机（几个月续航）
- 🌐 **Wi-Fi LAN 0.2 秒一帧**：本地 HTTP 直推，无云依赖
- 💤 **关屏 0 功耗保留最后一帧**：墨水屏特性，电池续航 6 个月（架构 C）
- 👆 **底栏触屏 chip**：点"睡眠"推电子名片 + 深度休眠；点"设置"翻设置页。150ms 点击态反馈
- ⏰ **定时自动息屏**：到 quiet hours 自动切到电子名片，daemon 不需要 Agent 在线

## 适合 / 不适合

**✅ 合适**：

- 想要 always-on 桌面副屏，但不想再开第二台亮屏显示器
- 已经在用 Claude Code / Codex / Cursor 等 Agent，想给它一个物理 ambient 输出
- 喜欢墨水屏低疲劳感（不刺眼、不抢注意力）
- 接受第一次 ~10 分钟硬件配置（之后 0 维护）

**❌ 不合适**：

- 需要快速刷新内容（股票实时、视频、动效）— 墨水屏不行
- 不想买硬件 / 不想烧固件
- 需要复杂触屏交互（墨水屏触屏可用但慢）

## 常见使用场景

| 你说 | Agent 干什么 |
|------|------|
| "帮我把 ai-desk-card 装上" | 完整入职流程：探测状态 → 烧固件 → 起 daemon → 配 Wi-Fi |
| "在卡片上显示今天的天气" | 推 weather widget |
| "把日程贴上去" | 推 calendar widget，自动读 macOS 日历 |
| "显示我现在在做的任务" | 推 focus widget |
| "让卡片每 30 分钟刷新" | 写 `~/.ai-desk-card/interests.yaml` + 注册 loop |
| "23 点自动息屏显示名片" | 配 quiet_hours，daemon 后台自动处理 |
| "卡片连不上" | 触发诊断 flow：探测 → 定位问题 → 给修复建议 |
| "我换 Wi-Fi 了" | 重新走 wifi-setup flow |
| "卡片现在显示啥" | curl daemon 拿当前帧的 PNG 预览 |

## 平台支持

| 平台 | 状态 | 说明 |
|------|------|------|
| Claude Code | ✅ 主力测试 | 原生 Skill 工作流 + slash 命令兼容层 |
| Codex CLI | 🟡 同 SKILL.md 格式 | 应该可用，未深度测试 |
| Gemini CLI | 🟡 应该可用 | 同上 |
| Cursor | 🟡 可用 | 需要 shell 权限 |
| Aider | 🟡 可用 | 同上 |
| 自写 Agent | ✅ | 只要识别 SKILL.md + 有 shell 权限就行 |

## 硬件准备

| 项目 | 说明 |
|------|------|
| **M5Paper V1.1** | 主力支持。约 ¥600 / $90。[官方店](https://shop.m5stack.com/products/m5paper-v1-1) / Amazon / AliExpress |
| M5Paper V1.0 | 大概率可用，电池阈值参数 (`4150 mV`) 可能要调 |
| M5Paper S3 | 需要 1-2 天移植（BLE stack 不同）|
| USB-C **数据线** | 烧固件时用一次。普通"只充电"线不行 |
| (可选) USB-C 充电器 | 想用"常插电 + Wi-Fi 常开"模式需要 |

> ⚠️ **不需要事先装 PlatformIO / 编译器 / Python 环境** — Skill 检测到缺什么会让 Agent 自己装。

## 安装

### 方式一：一行命令（推荐）

```bash
npx skills add https://github.com/op7418/ai-desk-card --skill ai-desk-card
```

### 方式二：让 AI 帮你装

把下面这段话复制粘贴给 Claude Code / Cursor / 任何有 shell 权限的 AI Agent：

> 帮我装 `ai-desk-card` 这个 Skill。请按下面步骤做：
>
> 1. 确保 `~/.claude/skills/` 目录存在（不存在就创建）
> 2. 执行 `git clone https://github.com/op7418/ai-desk-card.git ~/.claude/skills/ai-desk-card`
> 3. 验证：`ls ~/.claude/skills/ai-desk-card/` 应该看到 `SKILL.md`、`flows/`、`plugin/`、`daemon/`、`src/`、`assets/`
> 4. 装好告诉我，之后我说"帮我把卡片装上"就会触发这个 Skill

### 方式三：手动 clone

```bash
git clone https://github.com/op7418/ai-desk-card.git ~/.claude/skills/ai-desk-card
```

### 触发关键词

装好后 Agent 会在你说这些时自动唤起 Skill：

- "卡片" / "副屏" / "墨水屏" / "桌面卡片"
- "把 X 显示在卡片上" / "show X on my card"
- "刚拿到 M5Paper" / "first-time setup" / "刷固件"
- "每 N 分钟刷新" / "auto-refresh"
- "卡片息屏" / "显示名片" / "睡眠"
- "ai-desk-card"

## 使用流程

Skill 是结构化工作流，Agent 会按下面顺序自动跑（你不用记每一步）：

1. **入职 (flow 01)** — 探测 PlatformIO / USB 设备 → 引导你烧固件
2. **传输诊断 (flow 02)** — 设备连不上时定位问题
3. **配 Wi-Fi (flow 03)** — 把 Wi-Fi 凭证写进设备 NVS
4. **写偏好 (flow 04)** — 第一次问"你想看哪些卡片，多久刷一次"
5. **推 widget (flow 05)** — 日常推送的热路径
6. **设定时 (flow 06)** — Agent 用自己的 loop / cron 定时刷
7. **息屏 (flow 07)** — 推电子名片 + 设备深度休眠 0 功耗

完整子流程在 [`flows/`](./flows/) 目录。Skill 主路由在 [`SKILL.md`](./SKILL.md)。

## 16 种 Widget

**工作日常**：
- `weather` 天气 · `calendar` 今日日程 · `next-meeting` 下个会
- `todo` 待办 · `focus` 当前专注任务 · `deadlines` deadline 提醒
- `inbox` 收件箱 · `messages` 消息 · `pr-queue` PR 队列
- `git-status` git 状态 · `system` 系统状态 · `now-playing` 正在播放

**笔记 / 节奏**：
- `scratch` 便签 · `break-reminder` 休息提醒

**AI 监控**：
- `ai-status` 当前 AI session · `ai-tasks` AI 任务列表

**4 个槽位 / 2-1-1 布局**：

```
┌────────────┬────────────┐
│ top-left   │ top-right  │  ← 270×280 各占半
├────────────┴────────────┤
│         middle          │  ← 540×340 整条
├─────────────────────────┤
│         bottom          │  ← 540×280 整条
├─────────────────────────┤
│  bottom bar (chip 区)   │  ← 60 px，含"睡眠""设置"chip
└─────────────────────────┘
```

还有一个 `full`（540×960）覆盖全屏，用来推电子名片 / 启动 splash 等。

完整 schema 在 [`plugin/skills/card-widget/schemas/`](./plugin/skills/card-widget/schemas/)。

## 自动刷新（可选）

Skill 第一次问你"想看哪些卡片、什么时段刷"时，会帮你写 `~/.ai-desk-card/interests.yaml`：

```yaml
version: 1

slots:
  top-left:  weather
  top-right: calendar
  middle:    todo
  bottom:    inbox

schedule:
  cadence:  "30m"           # 5m / 15m / 30m / 1h / 2h
  hours:    "08-22"
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

# 到 quiet_hours.start 自动切到电子名片 + deep sleep
# daemon 后台自动处理，不需要 Agent 在线
quiet_hours:
  enabled: true
  start:   "23:00"
  end:     "07:00"
```

定时触发方式：

- **Agent 原生 loop（推荐）**：Claude Code 的 `/loop 30m`、`ScheduleWakeup` 等
- **cron**：`crontab -e` 加一行 `*/30 8-21 * * 1-5 bash /path/to/ai-desk-card/plugin/skills/card-refresh/scripts/refresh_loop.sh`
- **纯 Python 无 AI 兜底**：weather / system / git 这几个不需要 AI，直接跑 `fallback_refresh.py`

## 三种供电模式

| 模式 | 状态 | 推帧延迟 | 续航 |
|------|------|---------|------|
| **A** 常插电 | USB-C 供电 + Wi-Fi 长开 | 0.2 s | n/a（供电中）|
| **B** USB only | USB 数据线（还没配 Wi-Fi） | 1 s 区域 / 32 s 全帧 | n/a（供电中）|
| **C** 电池 + BLE 待机 | Wi-Fi 关，daemon 通过 BLE 唤醒 | 5 s 唤醒 + 0.2 s 推 | ~6 个月 |

架构 C 是最爱：屏挂在桌边几个月不充电，AI Agent 推内容时 BLE 唤醒一次 → 拉 Wi-Fi → HTTP 推帧 → 30 秒 linger 后断 Wi-Fi。一次推送约 0.2 mAh，24 次/天 × 6 个月 = 1150 mAh 电池。

## 没有 M5Paper？带浏览器的旧设备也能当显示端（实验性）

家里吃灰的旧 Android 墨水屏阅读器、老平板、Kindle——只要有个能跑 `<img>` 的浏览器，就能零固件接入：daemon 侧渲染不变，设备端用浏览器轮询当前帧。

```bash
# 1) 以局域网取帧模式启动 daemon（默认仍是仅环回，行为不变）
python3 daemon/card_daemon.py --http-host 0.0.0.0 --allow-peer <设备IP>

# 2) 设备浏览器打开一个极简轮询页（也可以直接开 http://<Mac IP>:9877/frame.png 手动刷新）
```

```html
<img id="f" style="height:100vh"><script>
setInterval(function(){document.getElementById('f').src=
  'http://<Mac IP>:9877/frame.png?t='+Date.now()},60000);
</script>
```

安全模型（绑定非环回时自动生效）：

- 白名单外的 IP 在 TCP 接受层直接断开（`verify_request`），不进请求解析；
- 白名单内的"显示端"**只能 `GET /frame.png`**——全部控制端点（推 widget、`/provision-wifi`、`/restart` 等）仍然只有本机环回可用，防止显示端浏览器被任意网页用跨域 POST 当跳板；
- 不传 `--http-host` 时一切照旧（127.0.0.1）。

实测：得到阅读器（Onyx 代工，Android 9 + Chrome 83）以 60 秒间隔轮询整天，稳定。

## 目录结构

```
ai-desk-card/
├── SKILL.md                  ← 任意 Agent 的入口
├── scripts/state.sh          ← 状态探测：JSON 输出 daemon/transport/wifi/device/interests 状态
├── flows/                    ← 7 个子流程（每个 ~60-100 行）
│   ├── 01_install.md             零状态硬件 + 固件烧录
│   ├── 02_transport.md           daemon 连不上设备的诊断
│   ├── 03_wifi.md                Wi-Fi 配网
│   ├── 04_interests.md           interests.yaml 引导写入
│   ├── 05_push.md                推 widget 热路径
│   ├── 06_schedule.md            定时刷新协议
│   └── 07_sleep.md               电子名片 + deep sleep
├── plugin/                   ← Claude Code 兼容层（slash 命令 + 共享脚本）
│   ├── plugin.json
│   ├── commands/             ← /card-* 命令
│   ├── scripts/              ← start.sh / stop.sh / status.sh
│   └── skills/               ← 子 skill，由主 SKILL.md 间接调用
├── daemon/
│   ├── card_daemon.py        ← HTTP 桥 + 传输层 + 后台 loop
│   ├── card_render.py        ← widget view 渲染
│   ├── card_render_settings.py
│   └── card_render_sleep.py  ← 电子名片渲染
├── src/                      ← 固件 (frame_receiver / wifi / http / ble / 触屏 poll)
├── assets/
│   ├── profile.yaml          ← 你的电子名片信息（息屏时显示）
│   ├── qr.png                ← 可选 QR
│   └── avatar.png            ← 可选头像
├── data/cjk.ttf              ← CJK 字体（首次烧到 LittleFS）
├── platformio.ini
├── partitions.csv
├── HANDOVER.md               ← 工程交接
└── PRODUCT.md                ← 产品定位
```

## 工作原理（一图看懂）

```
你说话                                        M5Paper
  │                                               ▲
  ▼                                               │
AI Agent ──────┐                                  │
               │ 触发 Skill                        │
               ▼                                  │
          SKILL.md 路由表                          │
               │                                  │
               │  scripts/state.sh 探测：          │
               │  · pio / firmware / daemon       │
               │  · device.alive / wifi           │
               │  · interests.yaml                │
               │                                  │
               └─▶ 选 7 个子 flow 之一             │
                       │                          │
                       ▼                          │
                  Agent 自动执行                   │
                       │                          │
                       ▼                          │
              POST 到 daemon (127.0.0.1:9877)     │
                       │                          │
                       ▼                          │
              daemon 渲染（Python + Pillow）       │
                       │                          │
                       ▼                          │
              HTTP / USB / BLE 推帧 ───────────────┘
```

## FAQ

**Q: 真的不用我自己烧固件？**
不用。装完 Skill 后跟 Agent 说"帮我装卡片"，Agent 会探测状态 → 装 PlatformIO（如果没装）→ `pio run -t upload` → 烧 CJK 字体 → 全程告诉你它在干什么。

**Q: 我没有 M5Paper V1.1，别的硬件可以吗？**
M5Paper V1.0 大概率能用。M5Paper S3 需要移植（BLE stack 不同）。Inkplate / Waveshare 等其他 ESP32 + e-ink 板还没支持，roadmap 上有。

**Q: 必须用 Claude Code 吗？**
不必。`SKILL.md` 是 agent-agnostic 入口，任何识别这格式 + 有 shell 权限的 Agent 都能用（Codex / Cursor / Aider / 自写 Agent）。`plugin/` 里的 slash 命令是 Claude Code 用户的便利层，不是核心。

**Q: 网络情况？**
全本地。daemon 在你电脑上跑 (127.0.0.1:9877)，设备和电脑同 Wi-Fi LAN 直连。**ESP32 只支持 2.4 GHz**，5 GHz only 的 SSID 连不上。

**Q: 中文显示豆腐块？**
漏了烧 LittleFS 字体。跟 Agent 说"再跑一次 uploadfs"就好。

**Q: 怎么更新固件？**
跟 Agent 说"帮我更新 ai-desk-card 然后重新烧一次"。Skill 会拉新代码 + build + upload。

**Q: 不在 macOS 上能用吗？**
daemon 在 Linux 也应该能跑（未深度测试）。Windows 需要 WSL2。烧固件部分 PlatformIO 跨平台。

**Q: 数据会上云吗？**
不会。daemon 默认绑 127.0.0.1（除了 device→daemon 的 status_report 走 LAN）。Wi-Fi 凭证写在设备 NVS，不会进 daemon 日志、不会进 git。

## Roadmap

- M5Paper V1.0 / S3 移植验证
- Inkplate / Waveshare 等其他 e-ink 板支持
- Captive portal Wi-Fi 配网（不用通过 daemon）
- 硬件按钮长按 2s 关机时拦截 → 先推名片再 deep_sleep（Plan C）
- 更多 widget schema（feishu / 微信 / Linear / Notion）
- 多设备 dashboard 同步

## 贡献

欢迎 Issue 和 PR：https://github.com/op7418/ai-desk-card

最有价值的贡献：

- 硬件实拍照 / 视频（帮新用户看清产品形态）
- Linux / Windows 上 daemon 测试报告
- M5Paper V1.0 / S3 移植验证
- 新 widget schema + 渲染器
- 翻译 / 文档优化

## License

GPL-3.0 with attribution clause · 见 [LICENSE](./LICENSE)

内嵌 EPDGUI 框架（来自上游 M5Paper_FactoryTest）：MIT，© 2020 m5stack
