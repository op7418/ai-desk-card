package com.c1mini.assistant;

import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.Window;
import android.view.WindowManager;

import com.c1mini.core.Eink;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.List;

/**
 * C1 桌面助理 —— 手动入口 + 休眠覆盖层（替代系统 showSuspendLogo 屏保）。
 *
 * 波形隔离：主窗口 GL16 彩色立绘首帧全刷后不动；Dialog 浮层 DU|RECT 局刷任务。
 * 数据：SyncScheduler 每 30s 拉一次，拉时开 WiFi、拉完关，内容不变零刷屏。
 *
 * overlay 模式（ScreenOffReceiver 在 ACTION_SCREEN_OFF 时拉起）：
 *   - 高 z-order 盖住 PowerManagerService 画的静态 Logo
 *   - 注册 SCREEN_ON，唤醒即 finish，不留残影
 */
public class AssistantActivity extends Activity {
    private static final String TAG = "C1Assistant";

    private AssistantViewHost viewHost;
    private SyncScheduler sync;
    private boolean overlayMode;
    private boolean dismissRegistered;
    private final BroadcastReceiver dismissReceiver = new BroadcastReceiver() {
        @Override public void onReceive(Context ctx, Intent intent) {
            DebugLog.i(TAG, "DISMISS_OVERLAY received → finish");
            finish();
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        overlayMode = getIntent().getBooleanExtra("overlay", false);
        DebugLog.i(TAG, "onCreate overlay=" + overlayMode);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        // 屏保要铺满整屏：隐藏状态栏，否则顶部归系统窗口，GC16 刷不到露残影。
        Window win = getWindow();
        win.addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
        if (overlayMode) {
            // 盖住 PowerManagerService.showSuspendLogo 的全屏 ImageView。
            // 关键：绝不加 FLAG_KEEP_SCREEN_ON —— 它会占住 Display suspend blocker，
            // 让系统卡在亮屏态、SCREEN_ON 广播不再发出，overlay 就退不掉了。
            // 墨水屏画面断电后静态保持，本来也不需要常亮。
            // 同理不加 FLAG_DISMISS_KEYGUARD —— 别打断系统 keyguard 状态机。
            //
            // 窗口类型（2026-11-19 真机修正）：原来设 TYPE_KEYGUARD_DIALOG，
            // 但 dumpsys window 显示实际 ty=2(TYPE_APPLICATION) —— Activity 的类型
            // 在 setContentView 之后已由 WMS 敲定，setType 根本没生效。
            // 结果是普通应用窗口一直可见 → 持有 Display suspend blocker
            // （mHoldingDisplaySuspendBlocker=true）→ 系统认定"屏幕正被应用使用"
            // → 永远不再发 SCREEN_ON → 唤醒广播收不到 → overlay 退不掉，
            // 用户醒来看到的还是屏保（真机 10:41 卡死现场）。
            //
            // 改用 TYPE_SYSTEM_ALERT：系统窗口，不参与 keyguard 状态机，
            // 也不像应用窗口那样被算作"正在使用屏幕"，SCREEN_ON 能正常收到。
            win.setType(WindowManager.LayoutParams.TYPE_SYSTEM_ALERT);
            win.addFlags(WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED);
            // 不需要输入焦点：屏保期间只要画面，别抢键盘/输入法。
            win.addFlags(WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE);
            DebugLog.i(TAG, "overlay window type=SYSTEM_ALERT (no KEEP_SCREEN_ON)");
        }
        Eink.applyScreen(win);

        setContentView(R.layout.assistant_main);
        findViewById(android.R.id.content).setSystemUiVisibility(
                android.view.View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | android.view.View.SYSTEM_UI_FLAG_FULLSCREEN
                        | android.view.View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);

        viewHost = new AssistantViewHost(this, AssistantViewHost.demoTasks());
        viewHost.setup(findViewById(android.R.id.content), new Runnable() {
            @Override public void run() { startSync(); }
        });

        // 屏幕亮灭监控：替代收不到的 SCREEN_OFF/SCREEN_ON 广播
        ScreenMonitor.get(this).start();
        // overlay 监听唤醒退出广播（比 Activity 引用可靠）
        if (overlayMode) {
            try {
                registerReceiver(dismissReceiver,
                        new IntentFilter("com.c1mini.assistant.DISMISS_OVERLAY"));
                dismissRegistered = true;
                DebugLog.i(TAG, "DISMISS_OVERLAY receiver registered");
            } catch (Throwable t) {
                DebugLog.e(TAG, "register DISMISS CRASH", t);
            }
            startSelfCheck();
        }
    }

    /**
     * 屏保自救检测：不依赖 SCREEN_ON 广播，周期性看显示电源状态。
     *
     * 背景（2026-11-19 真机 10:41 卡死）：overlay 若持有 Display suspend blocker，
     * 系统就认定"屏幕正被应用使用"，永远不再发 SCREEN_ON —— 广播这条路直接断掉，
     * 用户醒来看到的还是屏保。
     *
     * Display Power: state=ON / mWakefulness=Awake 是电源服务的真实状态，
     * 不像 isScreenOn() 在这台 ROM 上会抖。它能独立判断"用户是不是已经醒了"。
     * 一旦发现屏幕已亮且用户没在交互（比如 2 次连续检测都为 ON），
     * 就自己 finish 掉 overlay，把屏幕还给用户。
     *
     * 频率 2s：墨水屏无背光，CPU 唤醒开销极小；且这是"用户醒来却看到屏保"
     * 这种严重体验问题的唯一兜底，值得这点功耗。
     */
    private void startSelfCheck() {
        final Handler handler = new Handler(Looper.getMainLooper());
        handler.postDelayed(new Runnable() {
            @Override public void run() {
                if (isFinishing()) return;
                String power = readDisplayPowerState();
                if (power != null && power.contains("state=ON")) {
                    onAwakeDetected();
                    return;
                }
                handler.postDelayed(this, 2000L);
            }
        }, 2000L);
    }

    /** 读 dumpsys power 里的 Display Power 状态；失败返回 null。 */
    private String readDisplayPowerState() {
        try {
            Process p = Runtime.getRuntime().exec(new String[]{"dumpsys", "power"});
            BufferedReader br = new BufferedReader(
                    new InputStreamReader(p.getInputStream(), "UTF-8"));
            String line;
            while ((line = br.readLine()) != null) {
                if (line.contains("Display Power:")) {
                    br.close();
                    return line.trim();
                }
            }
            br.close();
        } catch (Throwable t) {
            DebugLog.i(TAG, "readDisplayPowerState failed: " + t);
        }
        return null;
    }

    /** 检测到屏幕已亮：退掉屏保，把屏幕还给用户。 */
    private void onAwakeDetected() {
        DebugLog.i(TAG, "display power ON while overlay active → self-dismiss");
        try {
            Intent done = new Intent("com.c1mini.assistant.DISMISS_OVERLAY");
            done.setPackage(getPackageName());
            sendBroadcast(done);
        } catch (Throwable t) {
            DebugLog.e(TAG, "self-dismiss CRASH", t);
            finish();
        }
    }

    private void startSync() {
        SyncScheduler.Config cfg = SyncScheduler.readConfig(this);
        String url = getIntent().getStringExtra("daemon");
        if (url != null && !url.trim().isEmpty()) cfg = new SyncScheduler.Config(
                url.trim().replaceAll("/+$", ""), cfg.keepWifi);
        if (cfg.daemon == null) {
            Log.i(TAG, "no daemon configured → demo tasks only");
            return;
        }
        final SyncScheduler.Config use = cfg;
        sync = new SyncScheduler(this, use.daemon, use.keepWifi,
                new SyncScheduler.Callback() {
                    @Override public void onTasksChanged(List<Task> tasks) {
                        viewHost.onTasksChanged(tasks);
                    }
                });
        sync.start();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (dismissRegistered) {
            try { unregisterReceiver(dismissReceiver); } catch (Throwable ignored) {}
            dismissRegistered = false;
        }
        if (sync != null) sync.stop();
        if (viewHost != null) viewHost.destroy();
        DebugLog.i(TAG, "onDestroy overlay=" + overlayMode);
    }
}
