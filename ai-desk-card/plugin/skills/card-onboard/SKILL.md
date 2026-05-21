---
name: card-onboard
description: |
  Onboard a user setting up AI Desk Card for the first time, or after moving
  to a new machine, plugging the device into a new network, or after a
  firmware update. Detects daemon state, USB / BLE / Wi-Fi connection,
  firmware version, and mDNS visibility — then walks the user through
  whatever's missing (install firmware, plug USB, pair BLE, provision
  Wi-Fi). Use whenever the user says "first-time setup" / "刚拿到设备" /
  "卡片没反应" / "刷固件" / "怎么连卡片" / "ai-desk-card 连不上".
trigger_keywords:
  - card onboard
  - 入职
  - 第一次用
  - first-time setup
  - 刷固件
  - 怎么连卡片
  - ai-desk-card 连不上
  - 配对
  - 配 wifi
allowed-tools:
  - Bash
  - Read
---

# card-onboard — AI Desk Card 首次接入流程

把用户从"刚拿到设备/啥都没装"带到"四个 widget 在屏上、Wi-Fi 在线、推帧
0.2 秒到位"。

## 一次性原则

- **永远先跑 probe**，不要凭空问"你 daemon 启动了吗"。`scripts/probe.sh` 一
  次拿全所有状态。
- **每一步告诉用户当前进度**："我看到 daemon 跑着了，但还没设备连接，
  现在去查串口..."。不要静默操作。
- **失败别循环重试**。卡住就停，把诊断结果给用户、让他决定。
- **优先推 Wi-Fi**，不要默认走 USB-serial 或 BLE。Wi-Fi 单帧 0.2 秒，USB
  1-32 秒，BLE 命令通但 frame 不通（已知问题）。

## 探针入口

```bash
bash $CLAUDE_PLUGIN_ROOT/skills/card-onboard/scripts/probe.sh
```

输出结构（JSON）：

```jsonc
{
  "daemon":     { "running": bool, "pid": int|null },
  "transport":  { "connected": bool,
                  "type": "SerialTransport|BLETransport|WiFiTransport|null" },
  "firmware":   { "our": bool, "note": str, "banner": str|null },
  "serial_ports": [ "/dev/cu.usbserial-..." ],
  "mdns_peer":  { "ip": "192.168.x.y", "port": 9880,
                  "txt": { "fw": "0.8.0", "proto": "1" } } | null
}
```

`firmware.our=true` = 设备上跑的是我们的固件（daemon 发了 `cmd:owner`
2.5 秒内收到 `ack:owner`）。
`mdns_peer != null` = **设备已经在 LAN 上播 Wi-Fi**，这是最理想的状态。

## 决策树（按顺序处理；命中分支就先修，再回到 probe 验证）

### G — `mdns_peer != null` 且 `transport.type != "WiFiTransport"`

最理想状态被错过了。设备已在 Wi-Fi，但 daemon 没用 Wi-Fi。告诉用户：

> 设备在 Wi-Fi `<ip>` 已上线。你 daemon 没用它，估计是之前没重启过 daemon。

跑：

```bash
/card-stop && /card-start
```

回到 probe，应该看到 `transport.type == "WiFiTransport"`。

### A — `daemon.running == false`

Daemon 没跑。跑 `/card-start`（自动选 Wi-Fi > USB > BLE）。等 1-2 秒重新
probe。

### B — `daemon.running == true && serial_ports == [] && mdns_peer == null`

设备完全离线 — 没插 USB、Wi-Fi 也没起来。可能场景：

- **设备根本没启动**：电池死了，或者没开机。让用户按一下电源键。
- **设备启动了但没配过 Wi-Fi**：第一次开机或者 NVS 凭据被清了。需要先用
  USB 把 daemon 连起来，再走 BLE pair → `/card-wifi-setup` 喂凭据。让
  用户插一条 USB-C **数据线**（注意不是充电线）。
- **设备在 Wi-Fi 但不同网段**：daemon 跑这台 Mac 跟设备不在同一个局域
  网。让用户检查 Wi-Fi 是不是手机热点或公司客网。

### C — `transport.connected == false` 但 `serial_ports != []`

USB 端口在但 daemon 没接上。最常见原因：上次 daemon 没释放干净，或者
M5Paper 那一头 USB 还在 boot。跑：

```bash
/card-stop && /card-start
```

还不行 → 给我看 probe + `tail -20 "${TMPDIR:-/tmp}/ai_desk_card_daemon.log"`。

### D — `transport.connected == true && firmware.our == false`

USB 通了但固件不是我们的（裸板 / M5 出厂 demo / 旧 buddy 固件）。问：

> 设备已连接，但运行的不是 AI Desk Card 固件。要现在刷上吗？
> （刷固件会清掉设备上的其他程序，30 秒内完成）

用户同意 → `/card-install flash`，等 5 秒重新 probe。

### E — `transport.connected == true && firmware.our == true` 但 `mdns_peer == null`

固件就位但 Wi-Fi 没配过。强烈推荐配 Wi-Fi（之后单 widget 0.2 秒）。让
用户给出 SSID + 密码：

> 设备就绪。要不要现在配 Wi-Fi？这样以后推 widget 0.2 秒一帧，比 USB 快 100 倍。
> 告诉我 SSID 和密码，我帮你写到设备 NVS（凭据只存设备本地，不进 git）。

收到凭据 → 跑：

```bash
/card-wifi-setup "<SSID>" "<密码>"
```

等 15 秒重新 probe，看到 `mdns_peer.ip` → 成功。

如果用户不想配 Wi-Fi（"只是想看看效果"），直接进 **分支 F**。

### F — 全绿，要不要推默认 widget

✅ 一切就位。问用户：

> 推一组默认 widget 上去看看？默认布局：
> top-left = weather, top-right = ai-status,
> middle = focus, bottom = todo

同意 → 切到 **card-widget** skill。

### Z — 用户明确要用 BLE only（不推荐）

USB / Wi-Fi 都不想用的场景。**注意：BLE 推 widget 数据不稳**（已知问题，
小命令通、大块数据 device 端 onWrite 不触发）。提醒用户后：

1. 拔 USB，daemon 自动 fallback 到 BLE
2. `/card-stop && /card-start`
3. daemon 自动扫描 `Card-*` 设备 → 1-2 分钟连上
4. 重 probe → `transport.type == "BLETransport"`
5. 推 widget 失败时回到此分支建议配 Wi-Fi

## 安抚话术

- "为什么 e-ink 显示这么慢" → USB serial 32s/帧是 115200 baud 的物理上
  限。**Wi-Fi 是 0.2 秒**。强烈建议配 Wi-Fi。
- "为什么屏幕一直显示之前内容" → e-ink 0 功耗保留最后一帧，特性不是 bug。
- "电量怎么不准" → 通过电池电压 > 4150 mV 判定"USB 在充"。刚拔 USB 电
  池满电时也会显示 USB 模式，几分钟后会回归正常。
- "我想换显示的人名/二维码" → 编 `ai-desk-card/assets/profile.yaml`，
  跑 `/card-sleep` 推送名片帧。

## 不要做的事

- ❌ 不要自动 `/card-install flash` — 总是先问用户
- ❌ 不要主动重启 daemon 或 device，除非用户同意（或走 /card-stop+start）
- ❌ 不要试图自己解析串口协议 — 走 `/firmware-probe` HTTP endpoint
- ❌ 不要跳过 mDNS 分支直接推 USB / BLE — Wi-Fi 是首选路径
- ❌ 不要把 SSID/密码记到 daemon log 或写进 git — 只通过 `/card-wifi-setup` 一次性写到设备 NVS

## 排错信息收集

如果用户卡某一步：

```bash
bash $CLAUDE_PLUGIN_ROOT/skills/card-onboard/scripts/probe.sh
tail -30 "${TMPDIR:-/tmp}/ai_desk_card_daemon.log"
ioreg -p IOUSB | grep -i 'usb\|m5\|silab\|ftdi' | head -10
```

把这些汇集给用户、问要不要发 issue 到 https://github.com/op7418/m5-paper-buddy
