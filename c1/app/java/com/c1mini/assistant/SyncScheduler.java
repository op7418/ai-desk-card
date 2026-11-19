package com.c1mini.assistant;

import android.content.Context;
import android.net.wifi.WifiManager;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * 30s 定时同步调度器 —— Activity 和 DreamService 共用的数据核心。
 *
 * 设计目标（对应用户需求）：
 *  1. 每 30s 才动一次网，其余时间 CPU 睡（进程内定时 + 每次同步拿短时 WakeLock）。
 *  2. 只在同步瞬间开 WiFi，拉完立刻关 —— 省电大头。
 *  3. 内容签名不变就不回调上层 → 上层零刷屏。
 *  4. 与 UI 完全解耦：只抛 onTasksChanged(List<Task>)，不碰 View/波形。
 *
 * 为什么不用 AlarmManager：iFlytek C1 的 ROM 对 AlarmManager.set() 做了
 * GET_INTENT_SENDER_INTENT 权限限制，三方 App 一调就 SecurityException 崩溃
 * （真机验证过）。屏保/App 期间本进程常驻，进程内定时足够可靠且无权限坑。
 * 设备深度睡眠时 Handler/定时器会暂停，唤醒后立即补一次同步 —— 正好契合
 * "睡眠时不折腾、醒来才更新"的省电语义。
 */
final class SyncScheduler {
    private static final String TAG = "C1Sync";
    static final long INTERVAL_MS = 30_000L;

    /** 上层实现此接口接收新任务（运行在主线程）。 */
    interface Callback {
        void onTasksChanged(List<Task> tasks);
    }

    private final Context ctx;
    private final Callback callback;
    private final String daemon;
    private final boolean keepWifi;
    private final Handler main;
    private ScheduledExecutorService worker;

    private volatile boolean running = false;
    private volatile String lastSig = "";
    private volatile int lastRev = -1;

    SyncScheduler(Context ctx, String daemon, boolean keepWifi, Callback cb) {
        this.ctx = ctx.getApplicationContext();
        this.daemon = daemon;
        this.keepWifi = keepWifi;
        this.callback = cb;
        this.main = new Handler(Looper.getMainLooper());
    }

    /** 开始：立即拉一次（后台线程）+ 排 30s 周期。 */
    void start() {
        if (running) return;
        running = true;
        worker = Executors.newSingleThreadScheduledExecutor();
        DebugLog.i(TAG, "started → " + daemon + " every 30s, keepWifi=" + keepWifi);
        worker.execute(new Runnable() {
            @Override public void run() { tick(); }   // 首屏立刻拉一次，不在主线程
        });
        worker.scheduleAtFixedRate(new Runnable() {
            @Override public void run() {
                if (running) tick();
            }
        }, INTERVAL_MS, INTERVAL_MS, TimeUnit.MILLISECONDS);
    }

    /** 停止：关掉定时器。屏保退出/Activity 销毁时调。 */
    void stop() {
        if (!running) return;
        running = false;
        if (worker != null) {
            worker.shutdownNow();
            worker = null;
        }
        Log.i(TAG, "stopped");
    }

    private void tick() {
        PowerManager pm = (PowerManager) ctx.getSystemService(Context.POWER_SERVICE);
        PowerManager.WakeLock wl = pm.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK, "C1Assistant:sync");
        wl.acquire(15_000L);   // 兜底 15s 自动释放，防止异常时永久持锁耗电
        // 省电策略的关键修正（2026-11-19 真机反馈：唤醒后 WiFi 连不回来）：
        //
        // 原来只在「同步开始时 WiFi 关着」才临时开、拉完再关。但设备灭屏后
        // 系统自己会把 WiFi 关掉（省电），于是每轮同步都是「关着进、关着出」，
        // 而唤醒时没有任何人把它开回来 —— 用户醒来就是断网态，adb 也连不上。
        //
        // 现在按屏幕状态区分：
        //   屏幕亮着（用户在场）→ 保持「临时开 → 拉完关」，这是真省电场景。
        //   屏幕灭着（屏保中）  → 不再碰 WiFi 开关，只保持现状拉一次就完事。
        //     屏保期间本来就不需要新数据（内容不变零刷屏），等用户唤醒、
        //     ScreenMonitor.restoreWifi() 把 WiFi 开回来之后再拉。
        boolean screenOn = isDisplayOn();
        boolean wifiWasOff = false;
        try {
            WifiManager wm = (WifiManager) ctx.getSystemService(Context.WIFI_SERVICE);
            if (!keepWifi && screenOn && wm != null && !wm.isWifiEnabled()) {
                wifiWasOff = true;
                wm.setWifiEnabled(true);
                waitForWifi(wm, 12_000L);   // 等 WiFi 连上（最多 12s）
            }
            String body = httpGet(daemon + "/widget", 4000);
            Feed feed = parseFeed(body);
            if (feed != null && !feed.sig.equals(lastSig)) {
                lastSig = feed.sig;
                lastRev = feed.rev;
                final List<Task> fresh = feed.tasks;
                // 回调抛到主线程，上层据此刷屏
                main.post(new Runnable() {
                    @Override public void run() { callback.onTasksChanged(fresh); }
                });
                DebugLog.i(TAG, "changed → " + fresh.size() + " tasks, rev=" + lastRev);
            } else {
                DebugLog.i(TAG, "unchanged (rev=" + (feed == null ? "null" : feed.rev) + "), no refresh");
            }
        } catch (Exception e) {
            DebugLog.e(TAG, "sync failed: " + e.getMessage(), e);
        } finally {
            // 拉完立刻关 WiFi（省电关键）—— 但只关"本次临时开的"，
            // 且只在屏幕亮着（用户在场）时才关。屏保中不关，否则用户醒来是断网态。
            if (wifiWasOff && !keepWifi && isDisplayOn()) {
                WifiManager wm = (WifiManager) ctx.getSystemService(Context.WIFI_SERVICE);
                if (wm != null) wm.setWifiEnabled(false);
                Log.i(TAG, "wifi off after sync (saved power)");
            }
            if (wl.isHeld()) wl.release();
        }
    }

    /**
     * 读电源服务的显示状态（Display Power: state=ON）。
     * 不用 isScreenOn()——这台 ROM 上它会抖/恒 false。
     */
    private boolean isDisplayOn() {
        try {
            Process p = Runtime.getRuntime().exec(new String[]{"dumpsys", "power"});
            BufferedReader br = new BufferedReader(
                    new InputStreamReader(p.getInputStream(), "UTF-8"));
            String line;
            while ((line = br.readLine()) != null) {
                if (line.contains("Display Power:")) {
                    br.close();
                    return line.contains("state=ON");
                }
            }
            br.close();
        } catch (Throwable ignored) {
        }
        return false;
    }

    private void waitForWifi(WifiManager wm, long timeoutMs) {
        long end = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < end) {
            if (wm.isWifiEnabled()
                    && wm.getConnectionInfo() != null
                    && wm.getConnectionInfo().getNetworkId() != -1) return;
            try { Thread.sleep(400); }
            catch (InterruptedException e) { Thread.currentThread().interrupt(); return; }
        }
    }

    private String httpGet(String urlStr, int timeoutMs) throws Exception {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(urlStr).openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(timeoutMs);
            conn.setReadTimeout(timeoutMs);
            conn.setInstanceFollowRedirects(false);
            int code = conn.getResponseCode();
            if (code != 200) throw new Exception("HTTP " + code);
            InputStream is = conn.getInputStream();
            BufferedReader br = new BufferedReader(new InputStreamReader(is, "UTF-8"));
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) {
                sb.append(line);
                if (sb.length() > 256 * 1024) throw new Exception("response too large");
            }
            br.close();
            return sb.toString();
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    /** 解析 daemon 快照，只抽 todo widget。 */
    private static Feed parseFeed(String json) throws Exception {
        JSONObject root = new JSONObject(json);
        int rev = root.optInt("rev", -1);
        JSONArray widgets = root.optJSONArray("widgets");
        if (widgets == null) return null;
        List<Task> out = new ArrayList<Task>();
        StringBuilder sig = new StringBuilder();
        for (int i = 0; i < widgets.length(); i++) {
            JSONObject w = widgets.getJSONObject(i);
            if (!"todo".equals(w.optString("type"))) continue;
            JSONObject data = w.optJSONObject("data");
            if (data == null) continue;
            sig.append(w.optString("slot")).append('|').append(data.toString());
            JSONArray items = data.optJSONArray("items");
            if (items == null) continue;
            for (int j = 0; j < items.length(); j++) {
                JSONObject it = items.getJSONObject(j);
                String text = it.optString("text", "").trim();
                if (text.isEmpty()) continue;
                String due = it.optString("due", "");
                String tag = it.optString("tag", "");
                if (due.isEmpty() && !tag.isEmpty()) due = tagLabel(tag);
                out.add(new Task(text, due, tag, it.optString("status", "")));
            }
        }
        if (out.isEmpty()) return null;   // 空 todo 不清屏
        return new Feed(rev, sig.toString(), out);
    }

    private static String tagLabel(String tag) {
        if ("today".equals(tag)) return "今天";
        if ("tomorrow".equals(tag)) return "明天";
        if ("this-week".equals(tag)) return "本周";
        if ("overdue".equals(tag)) return "已逾期";
        if ("later".equals(tag)) return "稍后";
        return "";
    }

    /** 从 assets/daemon.txt 读配置：第一段 URL + 可选 keep_wifi=1 行。 */
    static Config readConfig(Context ctx) {
        String url = null;
        boolean keepWifi = false;
        try {
            BufferedReader br = new BufferedReader(new InputStreamReader(
                    ctx.getAssets().open("daemon.txt"), "UTF-8"));
            String line;
            while ((line = br.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty() || line.startsWith("#")) continue;
                if (line.startsWith("keep_wifi=")) {
                    keepWifi = "1".equals(line.substring("keep_wifi=".length()).trim());
                } else if (url == null && line.startsWith("http")) {
                    url = line.replaceAll("/+$", "");
                }
            }
            br.close();
        } catch (Exception ignored) {
        }
        return new Config(url, keepWifi);
    }

    static final class Config {
        final String daemon;
        final boolean keepWifi;
        Config(String daemon, boolean keepWifi) {
            this.daemon = daemon; this.keepWifi = keepWifi;
        }
    }

    private static final class Feed {
        final int rev;
        final String sig;
        final List<Task> tasks;
        Feed(int rev, String sig, List<Task> tasks) {
            this.rev = rev; this.sig = sig; this.tasks = tasks;
        }
    }
}
