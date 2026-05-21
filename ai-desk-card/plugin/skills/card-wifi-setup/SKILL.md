---
name: card-wifi-setup
description: |
  Walk a user through provisioning Wi-Fi on their AI Desk Card device.
  After provisioning, device joins the user's home Wi-Fi, advertises via
  mDNS, and the daemon HTTP-pushes frames in ~0.2 s instead of USB's
  32 s. Use whenever the user says "配 wifi" / "card 上 wifi" / "我想用
  无线" / "怎么连 Wi-Fi" / when card-onboard's branch E recommends Wi-Fi.
trigger_keywords:
  - 配 wifi
  - 配 wi-fi
  - card 上 wifi
  - 卡片连 wifi
  - 无线连接
  - wifi setup
  - card wifi
allowed-tools:
  - Bash
  - AskUserQuestion
---

# card-wifi-setup — 把设备搬上 Wi-Fi

把 SSID + 密码喂到设备 NVS，设备自动连，daemon 通过 mDNS 发现 → 后续推帧
0.2 秒到位。

## 先决条件

- 设备能跟 daemon 通信（USB serial OR BLE 已 pair）。如果两条路都没有，
  先去 `/card-onboard`。
- daemon 在跑（`/card-status` 确认）

## 流程

### 1) 跟用户要 SSID + 密码

**关键安全提示**先说：

> 密码会通过本地 daemon 一次性写到设备 NVS。**不会**写进 daemon 日志、
> git 仓库、或者上传到任何远程服务。

然后问：

> 告诉我你家 Wi-Fi 的名称（SSID）和密码。

**注意**：SSID 就是 Wi-Fi 名称 — 用户在手机 Wi-Fi 列表里看到的那个字符串。
**不是** MAC 地址、IP 地址、或者其他什么。如果用户给了一串看起来像 MAC
（`xx:xx:xx:xx:xx:xx`），礼貌地纠正：

> 那看起来像 MAC 地址。我要的是 Wi-Fi 名称 — 手机里看到的那串字。

### 2) 推送

收到 SSID + password 后：

```bash
$CLAUDE_PLUGIN_ROOT/scripts/wifi_setup.sh "<SSID>" "<password>"
```

注意 SSID 一定要加双引号（可能含空格 / 中文 / 特殊字符）。脚本里走 daemon
的 `/provision-wifi` HTTP endpoint，daemon 转发为 `cmd:wifi_set` 给设备。

### 3) 等 15-20 秒看结果

跑 probe：

```bash
bash $CLAUDE_PLUGIN_ROOT/skills/card-onboard/scripts/probe.sh --quick
```

期望 `mdns_peer != null`，里面有 IP。

或者直接看 daemon 日志：

```bash
tail -20 "${TMPDIR:-/tmp}/ai_desk_card_daemon.log" | grep -i wifi
```

成功的话有 `[dev<] {..."wifi_connected":true,"wifi_ip":"192.168.x.y",...}` 行。

### 4) 重启 daemon 切到 Wi-Fi transport

```bash
/card-stop && /card-start
```

新 daemon 启动时会 mDNS 扫到 Wi-Fi peer，自动选 Wi-Fi。看到 `[transport]
found Wi-Fi peer X.X.X.X:9880, using Wi-Fi` 即成功。

## 失败诊断

设备 status 长期 `wifi_connected:false` 不上 Wi-Fi → 看错误 code。daemon
日志里设备会打 `[wifi] connect timeout (status=N)`:

| status | 意义 | 处理 |
|---|---|---|
| 1 | SSID 未找到 | 检查 SSID 拼写；**ESP32 不支持 5GHz**，确保是 2.4 GHz |
| 4 | 鉴权失败（密码错） | 让用户确认密码，重新跑 wifi-setup |
| 6 | DHCP 失败 | 路由器问题；可能是 MAC 过滤、或客户端数已满 |
| 其他 | 各种 | 把 daemon 日志最后 20 行给用户看 |

最常见的：用户家是双频路由器，给的密码对应 5GHz 网络。让用户在路由器后
台**单独建一个 2.4GHz SSID** 或者用 2.4GHz 频段的那个 SSID。

## 架构提示

写完凭据后，设备的"什么时候连 Wi-Fi"由电源状态决定（固件自己判断）：

- **架构 A（USB 接着）**：开机自动连，永远在线
- **架构 C（电池供电）**：连完一次后会断开，等 daemon 的 `cmd:wifi_wake_now`
  按需唤醒（daemon 自动发，用户不用操心）

两种模式下用户都不用做额外操作。

## 不要做的事

- ❌ 不要把 SSID/密码记到 daemon 日志、屏幕、或 git
- ❌ 不要鼓励用户用复杂密码绕过 ESP32 的 WPA2 限制 — ESP32 支持 WPA2/WPA3，
  够用；但有些**新 router 默认 WPA3 而 ESP32 老固件兼容性差**。如果反复
  连不上，建议路由器设回"WPA2/WPA3 mixed"。
- ❌ 不要默认密码长度 ≥ 8。让 ESP32 自己判断；过短的密码也能工作的网络
  确实存在（开发场景）。
- ❌ 不要跳过 step 4（daemon 重启）。Daemon 启动时才扫 mDNS，运行中不会
  自动切 transport。
