# ai-desk-card v0.6 渲染架构计划

> v0.5 一路调下来发现"修一个 bug 冒一个 bug"是架构问题，不是手抖。这份计划做完整调研 + 推一个不会再绕坑的方案。

## 一、现状诊断：为什么 patch 没完没了

到目前为止踩过的 bug（按时间排序）：

1. **`setTextArea` 不移动 cursor** → `print()` 写到 textArea 外被裁
2. **`createRender(N)` 没调 → `setTextSize(N)` 后 drawString 静默不画**（最致命的一个，调试体感是"文本随机消失"）
3. **CJK TTF 不含装饰 Unicode**（▢ ▶ ✎ ♪ ↑ ↓ ° — … 等）→ 渲染成 `.notdef` 方块
4. **`textWidth()` 对 missing glyph 撒谎**（返回 .notdef 宽度，比实际渲染的方块窄）→ auto_fit 误判"装得下"，结果文字溢出 slot
5. **多字号下 PSRAM 用量爆**（每个字号一个 glyph cache，我用 20+ 字号）

每个 bug 都修过，但**根因都是同一个**：**M5GFX 的 on-device TTF 渲染管线有 N 个隐性 invariant**，一个没守住就**静默失败**（不报错、不日志、就是不画）。debug 体感像踩雷区。

## 二、业界做法调研

### 路线 A：设备上 TTF 渲染（我们当前的路）

代表项目：
- **m5stack/M5Paper_FactoryTest 的 frame_txtreader** —— 只用**1 个字号**（26pt），boot 时 `loadFont` + `createRender(26, 128)`，从来不切字号。
- **chromsh/m5paper-google-calendar** —— 同样**1 个字号**（24pt），`createRender(24)` 一次，全部用 24。

**关键洞察：他们都只用 1 个字号**。这不是限制设计美观度，是**业界还没人在 ESP32 + TTF 上稳定用过多字号 + 任意 Unicode**。

我们 widget 副屏要表达层次（标题 26、body 32、headline 80、ctx 20、metric 60 等），路线 A 想做"漂亮排版"就要踩遍所有坑。

### 路线 B：服务端渲染像素流（业界主流大型项目都走这条）

代表项目：
- **kyleturman/home-dashboard** ([github](https://github.com/kyleturman/home-dashboard)) —— Node.js 服务渲染 HTML → 1-bit PNG → ESP32 fetch 像素
- **speedyg0nz/MagInkDash / MagInkCal** —— Raspberry Pi 跑 Chromium headless 渲染 HTML → screenshot PNG → 灰度 → e-ink
- **Hackaday "E-Ink dashboard with React serverless backend"** —— React + Lambda 渲染 PNG，ESP32 30 分钟一次 fetch
- **TRMNL（商业产品）** —— 同样架构，服务端渲染 + 像素流

**核心结构**：

```
┌──────────────────────────────────────┐
│  服务端（Daemon / Lambda / Pi）         │
│  - 任意字体（PIL / Chromium / Skia）    │
│  - 任意 Unicode（系统字体兜底）         │
│  - 复杂排版（HTML/CSS / Pillow）        │
│  - 输出：540×960 灰度 / 1-bit 位图     │
└─────────────────┬────────────────────┘
                  │  压缩后 pixel buffer
                  ▼
┌──────────────────────────────────────┐
│  设备（ESP32 + M5EPD）                 │
│  - 接 frame → 直接 push 到 panel      │
│  - 不渲染、不算字号、不查 glyph        │
│  - 处理输入（触屏 → 上传事件）         │
└──────────────────────────────────────┘
```

**优点**：
- 字体 / Unicode / 排版**问题全部在服务端解决**，PIL / 浏览器是工业级排版引擎
- 设备代码极简，bug 收敛快
- UI 迭代用 Python，不用 reflash 固件
- 可以渲染**任何字体 + 任何 glyph**（含 emoji / 颜文字 / 多语言）

**缺点**：
- 串口带宽：540×960×4bpp = 253KB，115200 baud ≈ 22 秒。需要提速 baud 或压缩
- 设备拆机离线时无法显示（除非缓存最后一帧）

### 路线 C：设备上 bitmap 字体

代表项目：
- Watchy、GxEPD2 各 demo —— 用 ASCII bitmap 字体（5×7、Adafruit GFX 标准）
- M5Stack 早期项目用 ASCII bitmap

**优点**：完全确定性、零 surprise
**缺点**：CJK bitmap 字体体积巨大（点阵 24×24 × 7000 字 ≈ 4MB），分级显示困难

不适合我们的 CJK + 多字号需求。

## 三、对比矩阵

| 维度 | A: on-device TTF | B: server-render 像素流 | C: bitmap 字体 |
| --- | --- | --- | --- |
| Bug 收敛速度 | **极慢**（已踩 5 类坑还有更多） | 快（坑都在 PIL，工业级） | 快但功能受限 |
| 字号灵活性 | 名义上任意，实际每个都要 createRender | **任意** | 固定预编译几档 |
| Unicode 覆盖 | 受 TTF 限制，缺字默认静默失败 | **系统字体兜底，几乎无限** | 受 bitmap 集限制 |
| 排版能力 | 手写 `widget_text::wrapped`，简陋 | **PIL textbbox + textwrap**，完整 | 手写 |
| UI 迭代速度 | 每次都要 pio run + flash + 调试 | **改 Python 即时**生效 | 同 A |
| 设备资源占用 | 大（每字号 cache + 字体加载） | 小（只存最后一帧） | 中（字体压缩） |
| CJK 支持 | 受字体限制，常缺字 | **PIL + macOS 字体兜底，完整 CJK + emoji** | 体积爆 |
| 离线 / 无 daemon 时 | 能渲染（但显示陈旧数据） | 显示最后一帧（e-ink 0 功耗保留） | 能渲染 |
| 串口带宽要求 | 低 (~几 KB JSON) | **高 (压缩后 30-60KB 每帧)** | 低 |

## 四、推荐：路线 B（服务端渲染）

**理由**：

1. **业界共识**：所有"产品级"e-ink dashboard 都走 server-render，不是巧合。Watchy 等 1-bit 项目是因为没服务端
2. **bug 收敛速度**：v0.5 调了 4 小时 5 个 bug，且每个 widget 还有新边界。路线 B 的坑都在 PIL，PIL 是 30 年工业级
3. **未来扩展性强**：emoji / 图标 / 渐变 / 任意排版都"白送"
4. **我们已经有 daemon**：基础设施在，不是从零搭建
5. **glance 副屏不需要实时**：30-60KB 带宽 + 几秒延迟完全可接受。e-ink 本来一次更新就要 500ms+

## 五、落地路径（4 个里程碑）

### Milestone 1：bandwidth 升级 + raw frame 协议

**目标**：设备能接受并显示一帧 540×960 raw 像素，3 秒内推完一帧

- daemon ↔ device 串口 baud 从 115200 提到 **921600** 或 **1500000**（ESP32 + USB-CDC 支持 3Mbps，但保守先用 921600）
  - 540×960×4bpp = 253KB，921600 baud (约 92KB/s) → **~2.7 秒/帧**，可接受
  - 提到 1500000 baud → **~1.7 秒/帧**
- 新增协议 `cmd:"frame_chunk"`：
  ```json
  {"cmd":"frame_begin","w":540,"h":960,"bpp":4,"format":"raw","total_chunks":N}
  {"cmd":"frame_chunk","seq":0,"data":"<base64 pixels>"}
  ...
  {"cmd":"frame_end","crc":"..."}
  ```
- 设备拼回 buffer → `M5.EPD.WritePartGram4bpp(0,0,540,960,buf)` → `UpdateFull(GC16)`
- 当前 widget_set JSON 协议**保留**作为 fallback，不一次性切换

### Milestone 2：daemon Pillow 渲染管线变 authoritative

**目标**：daemon push 像素而不是 widget JSON state，固件停止本地渲染

- 现在 `card_render.py` 已有完整 PIL 渲染（之前是 preview 用），把它从 preview-only 变成主路径
- daemon 收到 `POST /widget` 后：
  1. 更新 `WIDGET_CACHE`
  2. 调用 `render_preview_png()` 得到 PIL.Image
  3. 转 4bpp 灰度 buffer
  4. 通过 `cmd:frame_chunk` 协议推到设备
  5. （旧路径 `cmd:widget_set` JSON 不再发）
- 固件主循环：移除 `widget_components.cpp` 渲染调用，改成"收到 frame_end → push 到 panel"
- 触屏依然有：tap 上报 daemon，daemon 知道当前显示什么 widget，分发交互逻辑回服务端

### Milestone 3：PIL renderer 补齐 widget 渲染细节

**目标**：所有 widget 类型在 PIL 端有"产品级"渲染，不是 preview 级

- 当前 `card_render.py` 渲染粗糙（preview 用，能看就行）。补齐：
  - 一致的字体路径（指定一个本地 .ttf 而不是 fallback）
  - 准确的字号 / 行距 / padding
  - 边框 / 分隔线粗细
  - 进度条 / mini bar 样式
  - icons：直接用任意 emoji / Unicode 装饰符（PIL 用系统 font 兜底覆盖率超过 TTF）
- 添加 `theme` 系统：每个 widget 渲染 hook 可选不同 theme（minimal / dense / poster）
- 添加 `paintAllWidgets()` 等价物：合成 4 个 slot 到一张 540×960

### Milestone 4：清理 + 优化

- 删 `src/widget_components.cpp` 全部内容（保留极简头）
- 删 `src/widget_text.{h,cpp}`（用不上了）
- 固件二进制从 1.4MB 缩小到 ~700KB
- 设备 boot 时间缩短（不再 loadFont 3.4MB TTF）
- LittleFS 上的 cjk.ttf **可以删掉**（节省 3.4MB 给 sleep frame 图片 / 名片 QR 等）
- daemon 加帧缓存：如果 widget_cache 没变就不重渲染 + 不重推（省带宽）

## 六、风险 + 取舍

### 串口带宽 / baud 升级

- ESP32 上 USB-CDC 名义支持 12Mbps，UART 实际稳定到 3Mbps。921600 baud 业界用得多
- pyserial 一边也支持高 baud
- **风险**：高 baud 下偶尔丢字节。需要在 chunked protocol 里加 CRC + 重传

### BLE 路径如何处理

- BLE 带宽更低（约 30-50KB/s 实际），推 frame 慢，~5-8 秒
- 选项 1：BLE 模式不支持 frame，回落到老 widget_set JSON 协议（保留固件本地渲染作 fallback）
- 选项 2：BLE 模式压缩更狠（1bpp 黑白 + RLE → 10-20KB），1-2 秒推完
- 推荐：v0.6 先只做 USB serial 高带宽，BLE 作为 v0.6.1

### 设备脱离 daemon 后还能显示啥？

- e-ink 不通电也保留最后一帧 → 用户**永远能看到最后推上去的 dashboard**
- 第一次开机没 daemon → 显示"waiting for daemon"占位帧（固件内置 1 张）
- 这反而是路线 B 的优势

### 离线脱机使用 / 移动场景

- 拆下 Paper 出门，daemon 在远处 → BLE 模式继续推（如上）
- 完全离线 → 显示最后一帧 + 一个"离线"角标。可接受

### 现有 v0.5 代码作废多少？

- **固件**：`widget_components.cpp` (~500 行) 作废、`widget_text.{h,cpp}` (~170 行) 作废、`widgets.{h,cpp}` 大部分作废（只留协议解析），`frame_widget_dashboard.cpp` 大改
- **daemon**：`card_daemon.py` 加 frame 推送逻辑、`card_render.py` 改成主路径并补齐细节
- **Skill**：完全不变 ✓
- **Schema**：完全不变 ✓
- 净代码量预计**减少 30-40%**（固件少很多，PIL 端比 C++ 短得多）

### 不做这条会怎样？

继续路线 A：
- 每加一个 widget 类型，潜在踩 1-2 个 createRender / glyph / 排版 bug
- 每个长字符串 / 缺字场景都要单独调
- CJK + 任意 Unicode 永远受 TTF 限制
- UI 美观度上限低（e-ink 4 灰度 + 自制 wrap 算法）

## 七、立即行动建议

**两条路二选一**：

1. **小修小补走 A**：把当前 `widget_text::use_size` 落实到 100% 调用点（包括 `frame_widget_dashboard.cpp` repaint 里的 `setTextSize`），手动 list 所有用过的字号 + glyph 覆盖率审计。**可能再多撑 2-3 轮迭代后还是会卡**。
2. **下决心走 B**：从 Milestone 1 开始，2-3 个 PR 完成迁移。**3 天工作量左右**，但之后 widget UI 工作变成纯 Python 调，bug 收敛速度提升 5-10x。

我的建议是 B，原因写在第四节。但**最终拍板看你**：
- 如果 v0.5 接近发布、需要稳定 → 选 A
- 如果 v0.6 还有 1-2 周窗口 → 选 B

要 B 就动手，要 A 就告诉我，我把现有 `use_size` 改造扫到底然后做 glyph 审计。

## 八、参考

- [m5stack/M5Paper_FactoryTest](https://github.com/m5stack/M5Paper_FactoryTest) —— 设备渲染但只用 1 字号
- [chromsh/m5paper-google-calendar](https://github.com/chromsh/m5paper-google-calendar) —— 同上，1 字号
- [kyleturman/home-dashboard](https://github.com/kyleturman/home-dashboard) —— Node.js 服务端渲染 1-bit PNG
- [speedyg0nz/MagInkDash](https://github.com/speedyg0nz/MagInkDash) —— Pi + Chromium 渲染 → e-ink
- [Hackaday: E-Ink dashboard with React serverless backend](https://hackaday.io/project/193691) —— Lambda + bmp 服务端架构
- [TRMNL](https://usetrmnl.com) —— 商业产品，相同服务端渲染架构
