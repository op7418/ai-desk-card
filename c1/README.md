# C1 桌面助理屏保 · 讯飞 C1 彩色墨水屏

讯飞 C1（1072×1448 彩色 E Ink）上的「职业女性助理 + 任务待办/进展」屏保方案。
架构借鉴 [ai-desk-card](https://github.com/op7418/ai-desk-card) 的 widget/diff 思路
（AI Agent 推内容 → 设备按签名比对 → 内容不变零刷屏），
刷新策略用 C1 ROM 的 per-window 波形 API：主窗口 `GL16` 彩色立绘常驻、任务浮层 `DU|RECT` 黑白局刷。

> 这是 ai-desk-card 的**第二种硬件形态**：原项目跑在 M5Paper（ESP32 固件），
> 本目录跑在讯飞 C1（Android 8.1，定制 ROM）。两者共享 widget 数据模型，
> 但渲染与刷新层完全不同，故独立成目录。

## 效果

锁屏即进入：左侧彩色职业女性立绘（低频眨眼），右侧任务清单 + 今日进展条；
唤醒即退出，回到桌面。

## 交付内容

| 文件 | 作用 |
|---|---|
| `app/` | APK 源码（`com.c1mini.assistant`），Java + 零第三方依赖 |
| `app/assets/assistant.png` | 立绘：黑长发鹅蛋脸知性职业女性、抬手朝右指向任务区（650×1460 瘦高版，纯白底大色块，适配彩色 E Ink） |
| `app/assets/eyes_{open,closed}.png` | 眨眼贴图：睁眼原图像素 + 肤色覆盖弧线闭眼，206×33 GL16 小窗局刷 |
| `core/java/` | 自包含的 `Eink.java`（C1 波形控制）+ `Prefs.java` |
| `build.sh` | 构建脚本，产出 `C1Assistant.apk`（自包含，不依赖外部工程） |
| `debug.keystore` | 调试签名；正式发布请换成自己的 keystore |
| `bridge.py` | 数据桥：AI Agent 推 widget、C1 拉 JSON（带 rev），落盘持久化 |
| `push_demo.py` | 模拟 AI Agent 推任务（内置示例 / stdin / 标记完成 / 清空） |
| `prototype.html` | 电脑端可交互原型：立绘常驻 + 任务局刷 + 脏矩形高亮 + 省电统计 |
| `verify_bridge.py` | 端到端验证：推→拉→解析→签名比对→零刷屏判定 |
| `verify_diff.py` | 纯逻辑验证：脏矩形不侵入立绘区 + 省电比例 |
| `verify_dream.sh` | 唤醒设备后一键抓屏保日志 + 截图验证 |
| `default_screensaver.txt` | 记录被替换前的默认屏保组件（恢复用） |
| `assets/` | 立绘原图（素材源） |
| `tools/gen_avatar.py` | 早期灰度半身像生成器（已被 AI 立绘取代，留作参考） |
| `tools/gen_blink_assets.py` | 从新立绘裁瘦高版 + 标定眼睛坐标生成睁/闭眼贴图（肤色采样自新图脸颊） |

> **形象迭代（2026-11-19）**：按用户参考轮廓重画——黑长发、鹅蛋脸、知性职业女性，深藏青西装；
> 抬手从画面左侧改到**右侧朝右指向任务文字区**（视觉引导关系合理）。原图 1024×1536 → 裁成 650×1460
> 瘦高版（人物更大、全身完整）。眨眼贴图整套重做：眼睛框 206×33@(122,145)、肤色 `(247,216,194)`。
> 真机验证：`avatar bitmap 650x1460` / `blink window 177x28@(105,321)`；屏保 overlay 与手动启动像素完全一致。

## 快速开始

```bash
# 1. 构建（需 Android SDK + JDK）
./build.sh

# 2. 装到设备
adb install -r C1Assistant.apk

# 3. 电脑上起数据桥（AI Agent 往这里推）
python3 bridge.py            # 0.0.0.0:9877，状态存 widget_state.json

# 4. 推点数据看看
python3 push_demo.py
```

真机锁屏即见屏保；唤醒后用 `./verify_dream.sh` 一键抓日志和截图。

> 数据桥地址写在 `app/assets/daemon.txt`（第一行是 URL），改完重新 `./build.sh`。
> 调试期也可临时覆盖：`adb shell am start -n com.c1mini.assistant/.AssistantActivity -e daemon http://x.x.x.x:9877`

## 两个入口（共用核心）

```
ScreenMonitor     动态注册 SCREEN_OFF/ON，自维护状态机，锁屏拉起/唤醒退出 overlay
AssistantActivity 手动入口 + overlay 覆盖层（NEW_TASK|CLEAR_TASK 每次新建）
ScreenOffReceiver （已弃用，静态注册收不到，保留仅供参考）
AssistantDream    （已弃用，C1 不走标准 Daydream）
       │ 共用 ↓
AssistantViewHost 立绘 + 任务浮层的窗口/波形管理（真机 readback=1026 已验证）
ColorMode         打开 sys.use.color —— 不开就是灰阶黑剪影（见踩坑 9）
SyncScheduler     30s 定时同步：进程内定时 → 拉取 → 内容签名比对 → 零刷屏
DebugLog          /sdcard + app 私有目录双写（唤醒后唯一可靠日志来源）
Task / TaskView   数据模型 + 黑白自绘
```

## 屏保 + 省电（最终方案：动态广播覆盖层）

**C1 的默认"彩色屏保"不是 Daydream**。真机证实：按电源键后的彩色画面是
`PowerManagerService.showSuspendLogo()` 画的静态 ImageView，标准 Daydream 框架
（`AssistantDream` / deskclock）在这台 ROM 上是空壳、永不触发。所以改为：
**监听真实 SCREEN_OFF，弹全屏 AssistantActivity overlay 盖住系统 Logo**。

### 真机踩坑（血泪，别再走弯路）
1. **静态注册 `SCREEN_OFF` 收不到**：ROM 在灭屏瞬间冻结三方进程，系统只给自己投。
   → 改 `ctx.registerReceiver()` **动态注册**，能收到。
2. **`SCREEN_OFF` 不能伪造**：受保护广播，连 `adb shell am broadcast` 都被 Permission Denial。
   只能真按电源键触发，日志写 sdcard + app 私有目录（双写），唤醒后读。
3. **`isScreenOn()` 抖动 / `Display.getState()` 恒为 0**：C1 自定义 `wakefulness=4`，
   两个 API 都不可用 → 放弃轮询判亮灭，只认广播。
4. **状态机别依赖 Activity 生命周期**：早期用 `SINGLE_TOP` 复用 Activity，
   onCreate 不跑、intent 不更新 → `overlayActive` 卡死 true，屏保只工作一次。
   → 状态 (`screenOff`) 由 ScreenMonitor 广播自维护；拉起用 `NEW_TASK|CLEAR_TASK`
   保证每次新建；唤醒用 `DISMISS_OVERLAY` 广播让 Activity 自己 finish（比引用可靠）。
5. **overlay 绝不能加 `FLAG_KEEP_SCREEN_ON`**：会占住 Display suspend blocker，
   系统卡在亮屏态、SCREEN_ON 不再发 → overlay 退不掉。墨水屏断电静态保持，本就不需要常亮。
6. **C1 一次按键连发多轮 SCREEN_OFF/ON**：按 `screenOff` 状态去重，同状态直接忽略。
7. **DebugLog 必须声明 `WRITE_EXTERNAL_STORAGE`**，否则写 /sdcard 静默失败、
   唤醒后无日志可查（排查了半天的假象）。同时写 app 私有目录双兜底。
8. **`adb pull` 在这 ROM 上 protocol fault**：截图改用 `adb exec-out 'base64 ...' | base64 -D`。
9. **人物纯黑剪影（不是波形问题，是整块面板被关色）**：`adb screencap` 截的
   framebuffer 是彩色的，容易误判"彩色正常"；但 `logcat -s sunxihwc_eink` 里
   `displayToScreen ... use_color:0` 说明 HWC 刷面板时按灰阶输出 → 真机物理屏是黑白的。
   根因是系统属性 **`sys.use.color=0`**（userdebug 机默认关色省电）。
   → 首帧全刷前用 `ColorMode.enableColor()` 反射 `SystemProperties.set("sys.use.color","1")`
   打开（本机 userdebug + SELinux Permissive 可行；量产 Enforcing 机会静默降级）。
   验证：设完下一帧 flush 日志变 `use_color:1`，立绘恢复藏青色。**排查彩色必须看
   use_color 日志，不能只看 screencap。**
10. **唤醒后 WiFi 不自动连**（两层根因，2026-11-19 真机连环复现）：
    - **① 同步逻辑只会"关"不会"开回来"**：`SyncScheduler` 只在「同步开始时 WiFi 关着」
      才临时开、拉完再关。设备灭屏后系统自己关 WiFi 省电，于是每轮都是「关着进、
      关着出」，唤醒时没人开回来 → 用户醒来是断网态，adb 也连不上。
      → 改成**按屏幕状态区分**：屏幕亮着才「临时开→拉完关」；屏幕灭着（屏保中）
      完全不碰 WiFi 开关，等唤醒时 `ScreenMonitor.restoreWifi()` 开回来。
    - **② 唤醒广播根本收不到**：见下面第 11 条。
11. **overlay 卡死、SCREEN_ON 广播收不到**（真机 10:41 卡死现场）：
    `win.setType(TYPE_KEYGUARD_DIALOG)` **没生效** —— `dumpsys window windows` 显示
    实际 `ty=2(TYPE_APPLICATION)`（Activity 的窗口类型在 setContentView 之后
    已由 WMS 敲定）。普通应用窗口一直可见 → 持有 Display suspend blocker
    （`mHoldingDisplaySuspendBlocker=true`）→ 系统认定"屏幕正被应用使用"
    → 永远不再发 SCREEN_ON → 用户醒来看到的还是屏保，且 WiFi 无人恢复。
    → 三处修复：
      a. 窗口类型改 `TYPE_SYSTEM_ALERT`（系统窗口，不参与 keyguard 状态机，
         不被算作"正在使用屏幕"）；
      b. overlay 里加**自查**：每 2s 读 `dumpsys power` 的 `Display Power: state=ON`，
         发现屏幕已亮就自己 finish，把屏幕还给用户（不依赖任何广播）；
      c. `ScreenMonitor` 轮询同样读电源状态，广播漏了也能恢复 WiFi + 发 dismiss。
12. **屏幕电源状态怎么读**：`Display Power: state=ON` 来自 `dumpsys power`，
    比 `isScreenOn()` 可靠（这台 ROM 上 `isScreenOn()` 会抖、恒 false）。
    注意 mWakefulness=4（Awake）这台机上不能直接当成"亮屏"。
13. **息屏后"WiFi 开关是 on 但连接断了"**：真机 11:28 实测 —— 锁屏后 adb 断连，
    但 `settings get global wifi_on` 仍是 **1**、日志也是 `wifi already on`。
    断的是 **radio 层连接**，不是开关。→ `setWifiEnabled(true)` 对这种情况无效
    （本来就是 true，开了又关才叫开）。能压住的是 **`WifiLock`**：
    息屏时 `createWifiLock(WIFI_MODE_FULL_HIGH_PERF)` 持有，唤醒后**延后 20s** 再 release
    （立刻释放会让系统马上断连，实测唤醒瞬间同步必失败）。
    ⚠️ 但这台 ROM + 路由器侧仍会断（`dumpsys wifi` 看到
    `SCANNING→AUTHENTICATING→DISCONNECTED` 循环，最后才 `CompletedState`），
    **WifiLock 压不住**，属系统/网络侧行为，App 层只能做到"唤醒后自动重连"。
14. **daemon 必须常驻**：`nohup python3 bridge.py &` 在非交互 shell 里会被杀，
    进程一死设备侧就是 `Failed to connect to /192.168.1.18:9877`。
    → 用后台任务方式启动 `bridge.py`，否则同步永远失败（别误判成设备问题）。

### 本轮（2026-11-19 上午）真机验证通过项
- 彩色：`sys.use.color 0 → 1`，HWC 日志持续 `use_color:1` → 物理面板出彩色 ✅
- 屏保闭环：`SCREEN_OFF → overlay(SYSTEM_ALERT) → SCREEN_ON 收到 → wifi re-enabled
  → DISMISS → finish` 全程通 ✅（修复前 SCREEN_ON 收不到、overlay 卡死）
- 数据同步：`changed → 4 tasks, rev=5` ✅
- 立绘+任务区成像正常：藏青西装/肤色/黑发、手势引导在右、4 任务、进展 1/4 ✅

### 恢复系统默认屏保（如需）
本方案是覆盖层，不改系统设置。卸载 APK / force-stop 即恢复原 `showSuspendLogo` 画面。

**按需联网 + 低功耗**（`SyncScheduler`）：
- 每 30s 由进程内 `ScheduledExecutorService` 触发一次。
  **为什么不用 AlarmManager**：iFlytek ROM 对三方 `AlarmManager.set()` 抛
  `SecurityException: GET_INTENT_SENDER_INTENT`，一调就崩（真机验证过）。
  屏保/App 期间本进程常驻，进程内定时足够；设备深度睡眠时定时器暂停，
  唤醒后立即补一次同步 —— 正好契合"睡时不折腾、醒来才更新"。
- 每次同步：`PARTIAL_WAKE_LOCK` → 开 WiFi → `GET /widget` → 关 WiFi → 释放锁 → 继续睡。
- 内容签名不变就不回调 → 零刷屏。只有任务真变了才 `DU|RECT` 局刷。
- **调试开关**：`app/assets/daemon.txt` 里 `keep_wifi=1` 可让 WiFi 常开
  （否则关 WiFi 会断 adb，没法远程验证；生产删掉这行即恢复真断网省电）。

**真机注意**：C1 睡眠后 WiFi + adb 全断（Host is down），无法远程唤醒，
必须物理按电源键。`./verify_dream.sh` 是唤醒后的一键验证脚本。

## 设计核心：为什么是两个窗口

彩色立绘要 16 级波形（`GL16`）才显色；任务文字要省电走 `DU|RECT`，而 DU 只有 2 级灰度。
`setRefreshMode` 是 per-window 的，一个窗口只能一种波形，混用会把立绘量化成黑白。
所以照搬「三个 APK 因刷新策略冲突而分家」的思路，这里也分两层：

```
主窗口 (Activity)      → 彩色立绘，GL16，onCreate 画一次，之后永不 invalidate
浮层窗口 (PopupWindow) → 黑白任务，DU|RECT，只有 todo 内容变化才重驱变化像素
```

## 数据链路（已接通，端到端都局部）

```
AI Agent / push_demo.py
   │  POST /widget {slot,type:"todo",data:{items:[...]}}
   ▼
bridge.py（电脑上，0.0.0.0:9877）
   │  WIDGET_CACHE + rev++ + 落盘；GET /widget → {widgets, rev}
   ▼
AssistantActivity.TaskSource（C1 上，后台线程每 8s 轮询）
   │  只比对 todo 的 data 内容签名 —— 不变就零刷屏
   ▼
TaskView.setTasks() → onTaskAdvanced() → DU|RECT 局刷（立绘区 max=0）
```

**零刷屏的三道闸**：① rev 递增但 todo 内容没变 → 不刷；② 变的是非 todo widget
（日历/PR 等）→ 签名不含它 → 不刷；③ todo 内容真变了 → 才 invalidate 任务浮层。
另按 `cleanEvery=8` 插一帧 GC16 清 DU 攒的淡灰残影。

**任务字段**（兼容骨架 schema，加一个可选扩展）：
`items[].text`（必填）、`due`、`tag`（today/tomorrow/this-week/overdue/later，
无 due 时自动转中文）、`status`（C1 扩展：done/completed → ✓划线；
doing/in_progress → ▶；其余 → □）。不带 status 也正常显示。

## 快速开始

```bash
# 1. 电脑上看原型（立绘常驻 + 点任务看局刷）
python3 -m http.server 8899
# 浏览器打开 http://localhost:8899/prototype.html

# 2. 纯逻辑验证（无需设备）
python3 verify_diff.py      # 4 次推进，脏矩形 0 次侵入立绘区，累计省 69.4%
python3 verify_bridge.py    # 端到端：rev 递增、签名判定、字段映射，全过

# 3. 编译 APK（复用 c1 的 core + build-tools）
./build.sh

# 4. 启动数据桥（电脑，需和 C1 同一局域网；防火墙放行 9877）
python3 bridge.py                       # 0.0.0.0:9877，状态存 widget_state.json
python3 push_demo.py                       # 推内置示例任务
python3 push_demo.py --complete "回复设计评审意见"   # 标记某任务完成 → C1 局部刷新

# 5. 真机安装 + 指定桥地址（C1 走无线 adb，IP 以设备实际为准）
adb connect 192.168.1.204:5555
adb install -r C1Assistant.apk
adb shell am start -n com.c1mini.assistant/.AssistantActivity \
    -e daemon http://192.168.1.5:9877     # 192.168.1.5 换成电脑的局域网 IP
```

也可以把 URL 写进 `app/assets/daemon.txt`（去掉注释）后重新编译；
两者都没配则 APK 用内置 demo 任务、不联网。

构建已在本机验证通过（APK 1.5MB，签名验证 OK）；真机不在手边，**波形隔离需实机确认**。

## 真机必须验证的点（骨架未实机跑过）

1. **双窗口波形隔离**：`logcat -s C1Assistant` 看
   `task window set DU|RECT ok=true readback=N`；再看 `TaskSource started → http://...`。
   DU=2、RECT=1024，回读应接近 1026；若 `ok=false` 或回读是系统默认值，说明
   PopupWindow 的反射 `getWindow()` 没拿到，波形没生效 → 退回系统默认刷新。
2. **网络轮询真的驱动局刷**：推任务后 logcat 应出现
   `daemon → N tasks, rev=X (avatar untouched)`；不推时每 8s 一条 poll 但无刷屏日志。
3. **立绘区不重驱**：推任务时对比前后两帧像素，立绘区应 `max=0`；有跳说明浮层
   波形作用到了主 layer，需要改用 `WindowManager` 独立窗口方案。
4. **彩色立绘是否被 DU 波及**：推几次后立绘若褪色/变黑白，说明两层没真正隔离。
5. **残影**：DU 攒淡灰残影，代码里按 `cleanEvery=8` 插 GC16；观察第 8 次是否黑闪清干净。
6. **连通性**：C1 必须和电脑同网段；若 poll failed，先在 C1 上
   `ping <电脑IP>`，再确认 macOS 防火墙/路由器隔离没挡 9877。
