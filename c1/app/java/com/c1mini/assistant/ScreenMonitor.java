package com.c1mini.assistant;

import android.app.ActivityManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.wifi.WifiManager;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * 屏幕亮灭监控器 —— 动态注册 SCREEN_OFF/SCREEN_ON（静态注册在 C1 上投递不到）。
 *
 * 真机结论（C1 / iFlytek ROM）：
 *   - SCREEN_OFF 是受保护广播，三方连 adb shell 都发不了；系统真实灭屏时静态
 *     receiver 收不到，动态注册的能收到。
 *   - PowerManager.isScreenOn() / Display.getState() 在 C1 上都不可靠（抖动 / 恒 OFF）。
 *   - C1 ROM 对一次电源键会连发多轮 SCREEN_OFF/SCREEN_ON，需按状态去重。
 *
 * 状态机完全自维护（screenOff 由广播驱动），不依赖 Activity 生命周期：
 *   SCREEN_OFF（screenOff false→true）→ 拉起全屏 overlay 盖住系统 showSuspendLogo
 *   SCREEN_ON （screenOff true→false）→ finish 掉 overlay，回桌面
 * 同一状态的重复广播直接忽略。
 */
final class ScreenMonitor {
    private static final String TAG = "C1Screen";
    /** 轮询周期：2s。墨水屏无背光，CPU 唤醒开销极小；2s 足够快地兜住"广播丢了"的情况。 */
    private static final long POLL_MS = 2_000L;
    private static final boolean DIAG_POLL = true;   // 诊断轮询，只记日志

    private static volatile ScreenMonitor instance;

    private final Context ctx;
    private final PowerManager pm;
    private ScheduledExecutorService diagWorker;
    private volatile boolean running;
    private volatile boolean receiverRegistered;
    /** 息屏期间持有的 WifiLock，防止系统深度睡眠时断掉 WiFi 连接 */
    private WifiManager.WifiLock wifiLock;
    /** 主线程 handler，用于延时释放 WifiLock */
    private final Handler handler = new Handler(Looper.getMainLooper());

    // 状态机：由广播驱动，初值 false（认为当前亮屏）
    private volatile boolean screenOff = false;

    private final BroadcastReceiver sysReceiver = new BroadcastReceiver() {
        @Override public void onReceive(Context c, Intent intent) {
            String a = intent == null ? null : intent.getAction();
            DebugLog.i(TAG, "SYS_BROADCAST " + a + " screenOff=" + screenOff);
            if (Intent.ACTION_SCREEN_OFF.equals(a)) {
                if (screenOff) {
                    DebugLog.i(TAG, "SCREEN_OFF ignored: already off");
                    return;
                }
                screenOff = true;
                // 灭屏瞬间系统即将冻结进程，持短锁保证 startActivity 能完成
                PowerManager.WakeLock wl = pm.newWakeLock(
                        PowerManager.PARTIAL_WAKE_LOCK, "C1Screen:off");
                try {
                    wl.acquire(8_000L);
                    onScreenOff();
                } catch (Throwable t) {
                    DebugLog.e(TAG, "onScreenOff CRASH", t);
                } finally {
                    if (wl.isHeld()) wl.release();
                }
            } else if (Intent.ACTION_SCREEN_ON.equals(a)) {
                if (!screenOff) {
                    DebugLog.i(TAG, "SCREEN_ON ignored: not in off state");
                    return;
                }
                screenOff = false;
                onScreenOn();
            }
        }
    };

    static ScreenMonitor get(Context ctx) {
        if (instance == null) {
            synchronized (ScreenMonitor.class) {
                if (instance == null) instance = new ScreenMonitor(ctx);
            }
        }
        return instance;
    }

    private ScreenMonitor(Context ctx) {
        this.ctx = ctx.getApplicationContext();
        this.pm = (PowerManager) ctx.getSystemService(Context.POWER_SERVICE);
    }

    void start() {
        if (running) return;
        running = true;
        DebugLog.i(TAG, "started");
        try {
            IntentFilter f = new IntentFilter();
            f.addAction(Intent.ACTION_SCREEN_OFF);
            f.addAction(Intent.ACTION_SCREEN_ON);
            f.setPriority(1000);
            ctx.registerReceiver(sysReceiver, f);
            receiverRegistered = true;
            DebugLog.i(TAG, "dynamic SCREEN_OFF/ON receiver registered");
        } catch (Throwable t) {
            DebugLog.e(TAG, "register receiver CRASH", t);
        }
        if (DIAG_POLL) {
            diagWorker = Executors.newSingleThreadScheduledExecutor();
            diagWorker.scheduleAtFixedRate(new Runnable() {
                @Override public void run() {
                    if (!running) return;
                    // 兜底：不依赖 SCREEN_ON 广播，直接读电源服务的真实显示状态。
                    // 广播收不到时（overlay 持有 display blocker 的场景），这是唯一
                    // 能发现"用户已经醒了"的途径 —— 顺带把 WiFi 恢复掉。
                    if (screenOff && displayIsOn()) {
                        DebugLog.i(TAG, "poll detected display ON (broadcast missed) → recover");
                        screenOff = false;
                        restoreWifi();
                        ctx.sendBroadcast(new Intent("com.c1mini.assistant.DISMISS_OVERLAY")
                                .setPackage(ctx.getPackageName()));
                        return;
                    }
                    DebugLog.i(TAG, "diag screenOff=" + screenOff
                            + " isScreenOn=" + pm.isScreenOn());
                }
            }, POLL_MS, POLL_MS, TimeUnit.MILLISECONDS);
        }
    }

    /**
     * 读电源服务里的显示电源状态（Display Power: state=ON/OFF）。
     * 不依赖 isScreenOn()（这台 ROM 上会抖），也不依赖 SCREEN_ON 广播。
     */
    private boolean displayIsOn() {
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
        } catch (Throwable t) {
            // 读不到就当没亮，等下一次轮询
        }
        return false;
    }

    /**
     * 恢复 WiFi：屏保期间 SyncScheduler 为了省电，每次拉取后会把「本次临时开的」
     * WiFi 关掉；若不在唤醒时恢复，用户醒来就是断网态（真机反馈 2026-11-19）。
     * 只开不关，后续省电交给系统。
     */
    private void restoreWifi() {
        try {
            WifiManager wm = (WifiManager) ctx.getSystemService(Context.WIFI_SERVICE);
            if (wm != null && !wm.isWifiEnabled()) {
                wm.setWifiEnabled(true);
                DebugLog.i(TAG, "wifi re-enabled on wake");
            } else {
                DebugLog.i(TAG, "wifi already on, skip re-enable");
            }
        } catch (Throwable t) {
            DebugLog.e(TAG, "wifi re-enable CRASH", t);
        }
        // 唤醒后不立刻释放 WifiLock：此刻 WiFi 连接还没恢复（实测锁屏期间
        // 同步全是 "Failed to connect"）。过早释放会让系统马上断连。
        // 延后 20s 再放，期间保证连接活着，数据也能拉下来。
        handler.postDelayed(new Runnable() {
            @Override public void run() {
                releaseWifiLock();
            }
        }, 20_000L);
    }

    /** 息屏期间持 WifiLock，防止系统深度睡眠时断掉 WiFi 连接。 */
    private void acquireWifiLock() {
        try {
            if (wifiLock != null && wifiLock.isHeld()) return;
            WifiManager wm = (WifiManager) ctx.getSystemService(Context.WIFI_SERVICE);
            if (wm == null) return;
            wifiLock = wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF,
                    "C1Assistant:screen-off");
            wifiLock.setReferenceCounted(false);
            wifiLock.acquire();
            DebugLog.i(TAG, "WifiLock acquired (keep connection alive while screen off)");
        } catch (Throwable t) {
            DebugLog.e(TAG, "WifiLock acquire CRASH", t);
        }
    }

    private void releaseWifiLock() {
        try {
            if (wifiLock != null && wifiLock.isHeld()) {
                wifiLock.release();
                DebugLog.i(TAG, "WifiLock released");
            }
        } catch (Throwable t) {
            DebugLog.e(TAG, "WifiLock release CRASH", t);
        }
    }

    void stop() {
        if (!running) return;
        running = false;
        if (receiverRegistered) {
            try { ctx.unregisterReceiver(sysReceiver); } catch (Throwable ignored) {}
            receiverRegistered = false;
        }
        if (diagWorker != null) {
            diagWorker.shutdownNow();
            diagWorker = null;
        }
        DebugLog.i(TAG, "stopped");
    }

    private void onScreenOff() {
        DebugLog.i(TAG, "screen OFF → launch assistant overlay");
        // 息屏时持 WifiLock：防止系统为了省电在深度睡眠里把 WiFi **连接**断掉。
        //
        // 真机实测（2026-11-19）：息屏后 adb 断连，但 wifi_on 开关仍是 1 ——
        // 说明断的是 radio 层连接，不是开关。这种"开关开着但连不上"的状态，
        // setWifiEnabled(true) 唤不醒（本来就是 true），只有 WifiLock 能压住。
        // 顺带好处：屏保期间要每 30s 同步数据，WiFi 断了本来就拉不到。
        acquireWifiLock();
        try {
            Intent i = new Intent(ctx, AssistantActivity.class);
            // CLEAR_TASK 保证每次锁屏都新建实例、走 onCreate、intent 正确；
            // 不用 SINGLE_TOP（会复用主 Activity 导致 intent 不更新、标志卡死）
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                    | Intent.FLAG_ACTIVITY_CLEAR_TASK);
            i.putExtra("overlay", true);
            ctx.startActivity(i);
            DebugLog.i(TAG, "startActivity(overlay) OK");
        } catch (Throwable t) {
            DebugLog.e(TAG, "launch overlay CRASH", t);
        }
    }

    private void onScreenOn() {
        DebugLog.i(TAG, "screen ON → dismiss overlay");
        restoreWifi();
        // 不依赖 attach 的引用（Activity 可能还在创建中），直接从 ActivityManager
        // 结束栈顶的 AssistantActivity overlay。
        try {
            ActivityManager am = (ActivityManager) ctx.getSystemService(Context.ACTIVITY_SERVICE);
            List<ActivityManager.RunningTaskInfo> tasks = am.getRunningTasks(1);
            if (tasks != null && !tasks.isEmpty()) {
                ActivityManager.RunningTaskInfo top = tasks.get(0);
                DebugLog.i(TAG, "top task=" + (top.topActivity == null ? "null" : top.topActivity.getClassName()));
            }
        } catch (Throwable t) {
            DebugLog.i(TAG, "getRunningTasks unavailable: " + t.getMessage());
        }
        // 通过广播让 Activity 自己 finish（最可靠，不依赖引用/权限）
        Intent done = new Intent("com.c1mini.assistant.DISMISS_OVERLAY");
        done.setPackage(ctx.getPackageName());
        ctx.sendBroadcast(done);
        DebugLog.i(TAG, "DISMISS_OVERLAY broadcast sent");
    }
}
