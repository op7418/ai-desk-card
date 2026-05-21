---
name: card-onboard
description: |
  Onboard a user setting up claude-card for the first time (or after moving
  to a new machine / re-pairing a device). Detects daemon state, USB/BLE
  connection, and firmware version; walks the user through whatever's
  missing — installing firmware, plugging in the device, pairing BLE.
  Use whenever the user says "我刚拿到设备" / "first-time setup" / "card
  没反应" / "刷固件" / "怎么连卡片" / "claude-card 连不上".
trigger_keywords:
  - card onboard
  - 入职
  - 第一次用
  - first-time setup
  - 刷固件
  - 怎么连卡片
  - claude-card 连不上
  - 配对
allowed-tools:
  - Bash
  - Read
---

# card-onboard — claude-card 首次接入流程

你的工作：把用户从"刚拿到设备 / 啥都没装"带到"四个 widget 已经在屏上"。

## 一次性原则

- **永远先跑 probe**：不要凭空问用户"你 daemon 启动了吗"。运行
  `scripts/probe.sh`，它会一口气检测所有状态返回 JSON，再据此发问。
- **每一步都告知用户当前进度**："我看到 daemon 在跑，但还没有设备连接，
  现在去检查串口..."。不要静默操作。
- **失败不要循环重试**。任何步骤失败 → 把诊断结果给用户，让用户决定。

## 探针入口

```bash
bash $CLAUDE_PLUGIN_ROOT/skills/card-onboard/scripts/probe.sh
```

输出结构：

```json
{
  "daemon":     { "running": bool, "pid": int|null },
  "transport":  { "connected": bool, "type": "SerialTransport|BLETransport|null" },
  "firmware":   { "our": bool, "note": str, "banner": str|null },
  "serial_ports": [ "/dev/cu.usbserial-..." ]
}
```

`firmware.our=true` 表示我们对设备发了 `cmd:owner` 并在 2.5 秒内收到了
`ack:owner` — 这是"我们的固件在跑"的强信号。

## 决策树

按这个顺序处理。一旦命中分支，**先帮用户解决该步**再回到 probe 验证。

### 分支 A：`daemon.running == false`

Daemon 没起。告诉用户：

> claude-card daemon 还没启动。我帮你拉起。

然后跑：

```bash
/card-start
```

等 1-2 秒，重新跑 probe。

### 分支 B：`daemon.running == true && serial_ports == []`

设备没插 USB。告诉用户：

> 没有检测到 /dev/cu.usbserial-* 设备。请把 M5Paper V1.1 用 USB-C 数据线
> 插到电脑上（注意不是充电线，要数据线）。如果你已经插了：
> - macOS 第一次插需要在 系统设置 > 隐私与安全性 里"允许"USB 驱动
> - 或者改用蓝牙连接（B-2 分支）

等用户回复后再 probe。如果用户表示"不想用 USB，用蓝牙"→ 直接跳到
**分支 D**。

### 分支 C：`transport.connected == false` 但 `serial_ports != []`

端口存在但 daemon 没连上。最常见原因是 daemon 在用错端口或上次连接没释放。
建议：

```bash
/card-stop && /card-start
```

如果还不行，把 probe 输出和 `tail -20 /tmp/claude_card_daemon.log` 给用户看。

### 分支 D：`transport.connected == true && firmware.our == false`

端口开着但设备不是我们的固件（要么裸板，要么是 M5 出厂演示固件，要么旧版
buddy 固件）。

询问用户：

> 设备已连接，但运行的不是 claude-card 固件。要现在刷上吗？
> （刷固件会清除设备上的其他程序，但只需 30 秒）

如果用户同意 → 跑 `/card-install flash`。
刷完后等 5 秒重新 probe，应该看到 `firmware.our == true`。

### 分支 E：`transport.connected == true && firmware.our == true`

✅ 设备就位。问用户：

> 设备好了。要不要我帮你推一组默认 widget 上去？默认是：
> top-left = weather, top-right = ai-status,
> middle = calendar, bottom = todo

如果用户同意 → 切换到 **card-widget** skill 推这四个 widget。

### 分支 F：用户明确要用蓝牙（BLE 路径）

USB 连接更稳定推荐优先用，但如果用户坚持 BLE：

1. 让用户先拔掉 USB（daemon 看到串口就会优先走串口）
2. 重启 daemon：`/card-stop && /card-start`
3. daemon 自动切到 BLE，开始扫描 `Card-*` 设备
4. 设备端：长按电源 1 秒进入配对模式（屏幕应显示 "Pairing..."）
5. 1-2 分钟内 daemon 日志会显示 `[ble] connected`
6. 重新 probe，应该看到 `transport.type == "BLETransport"`

配对 PIN 走 NUS（透传），不需要手动输入。

## 安抚话术 / 常见误解

- "为什么 e-ink 显示这么慢" → 一次全屏刷新约 32 秒（115200 baud 限制 +
  GC16 刷新时间）。这正常，平时不会全屏刷。
- "为什么屏幕一直显示之前的内容" → e-ink 关机后 0 功耗保留最后一帧，这是
  特性不是 bug。
- "我想换显示的人名 / 二维码" → 编辑 `claude-card/assets/profile.yaml`，
  跑 `/card-sleep` 推送名片帧。

## 不要做的事

- ❌ 不要自动 `/card-install flash` —— 总是先问用户
- ❌ 不要主动重启用户的 daemon 或 device（除非用户明确同意 / 走 /card-stop+start）
- ❌ 不要试图自己解析串口协议来"检测"固件 —— 走 `/firmware-probe` endpoint
- ❌ 不要 ble pair 时 hardcode 设备名 —— 走 daemon 的 `Card-*` 扫描默认

## 排错信息收集（如果用户卡在某一步）

```bash
bash $CLAUDE_PLUGIN_ROOT/skills/card-onboard/scripts/probe.sh
tail -30 /tmp/claude_card_daemon.log
ioreg -p IOUSB | grep -i 'usb\|m5\|silab\|ftdi' | head -10   # macOS USB 设备
```

把这些粘给用户、问他要不要发 issue 到 https://github.com/op7418/m5-paper-buddy
