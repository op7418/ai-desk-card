#!/usr/bin/env bash
# 唤醒 C1 后跑这个：抓屏保日志 + 截图 + 报告状态。
# 用法：唤醒设备（按电源键），等 adb 能连上后执行 ./verify_dream.sh
#
# 设备 IP 可用环境变量覆盖：C1_IP=192.168.1.100:5555 ./verify_dream.sh
set -u
IP="${C1_IP:-192.168.1.100:5555}"
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy 2>/dev/null || true
export NO_PROXY="${NO_PROXY:-},${IP%%:*}"

echo "=== 连接 ==="
adb connect "$IP" 2>&1
adb devices 2>&1 | tail -2

echo "=== 屏保/同步日志 ==="
# 注意：屏幕面板是否为彩色不能靠 screencap 判断（那是 framebuffer，永远有颜色），
# 必须看 HWC 的 use_color 日志 —— use_color:0 就是被按灰阶刷了。
adb logcat -d -s C1Screen:I C1Sync:I C1ViewHost:I C1Color:I 2>&1 \
  | grep -v '^---------' | tail -40

echo "=== 面板彩色输出（HWC use_color）==="
adb logcat -d 2>&1 | grep "displayToScreen" | tail -3
echo "sys.use.color=$(adb shell getprop sys.use.color 2>&1)"

echo "=== 当前屏保配置 ==="
echo "components=$(adb shell settings get secure screensaver_components 2>&1)"
echo "enabled=$(adb shell settings get secure screensaver_enabled 2>&1)"

echo "=== 唤醒状态 ==="
adb shell dumpsys power 2>&1 | grep -m1 'Display Power:' || echo "(取不到)"
adb shell dumpsys power 2>&1 | grep -m1 'mWakefulness=' || echo "(取不到)"

echo "=== WiFi ==="
echo "wifi_on=$(adb shell settings get global wifi_on 2>&1)"

echo "=== 截图 ==="
adb exec-out screencap -p > /tmp/c1-dream.png 2>/dev/null && file /tmp/c1-dream.png || echo "截图失败(设备可能仍睡)"
