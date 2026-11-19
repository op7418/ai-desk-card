package com.c1mini.assistant;

import android.service.dreams.DreamService;
import android.util.Log;
import android.view.Window;
import android.view.WindowManager;

import com.c1mini.core.Eink;

import java.util.List;

/**
 * C1 桌面助理 —— 屏保入口（替换系统默认 deskclock 屏保）。
 *
 * 系统睡眠时自动进入（screensaver_activate_on_sleep=1），全屏常驻：
 *   - 立绘 GL16 首帧全刷后不动；任务 Dialog DU|RECT 局刷
 *   - SyncScheduler 每 30s 拉一次（拉时开 WiFi、拉完关），内容不变零刷屏
 *   - 其余时间 CPU 睡（进程内定时 + 短时 WakeLock；iFlytek ROM 禁用了三方 AlarmManager）
 * 触摸/按键 → 系统自动结束屏保（setInteractive(false) 默认行为）。
 *
 * 替换默认屏保：
 *   adb shell settings put secure screensaver_components \
 *       com.c1mini.assistant/com.c1mini.assistant.AssistantDream
 *   adb shell settings put secure screensaver_enabled 1
 * 恢复默认：
 *   adb shell settings put secure screensaver_components \
 *       com.android.deskclock/com.android.deskclock.Screensaver
 */
public class AssistantDream extends DreamService {
    private static final String TAG = "C1Dream";

    private AssistantViewHost viewHost;
    private SyncScheduler sync;

    @Override
    public void onDreamingStarted() {
        super.onDreamingStarted();
        DebugLog.i(TAG, "onDreamingStarted ENTER");
        try {
            // 屏保默认全屏，但仍显式声明，确保 GC16 全刷能覆盖整屏。
            Window win = getWindow();
            DebugLog.i(TAG, "got window=" + (win != null));
            if (win == null) { DebugLog.w(TAG, "null window, abort view setup"); return; }
            win.addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN
                    | WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD);
            Eink.applyScreen(win);

            // 非交互屏保：触摸/按键直接退出（省电语义："没操作就睡，有操作就醒"）
            setInteractive(false);
            setFullscreen(true);

            setContentView(R.layout.assistant_main);
            DebugLog.i(TAG, "setContentView done");

            viewHost = new AssistantViewHost(this, AssistantViewHost.demoTasks());
            viewHost.setup(findViewById(android.R.id.content), new Runnable() {
                @Override public void run() {
                    DebugLog.i(TAG, "viewHost ready → startSync");
                    startSync();
                }
            });
            DebugLog.i(TAG, "onDreamingStarted OK");
        } catch (Throwable t) {
            DebugLog.e(TAG, "onDreamingStarted CRASH", t);
        }
    }

    private void startSync() {
        SyncScheduler.Config cfg = SyncScheduler.readConfig(this);
        if (cfg.daemon == null) {
            DebugLog.i(TAG, "no daemon configured → demo tasks only");
            return;
        }
        try {
            sync = new SyncScheduler(this, cfg.daemon, cfg.keepWifi,
                    new SyncScheduler.Callback() {
                        @Override public void onTasksChanged(List<Task> tasks) {
                            DebugLog.i(TAG, "callback → " + tasks.size() + " tasks");
                            viewHost.onTasksChanged(tasks);
                        }
                    });
            sync.start();
            DebugLog.i(TAG, "sync started → " + cfg.daemon);
        } catch (Throwable t) {
            DebugLog.e(TAG, "startSync CRASH", t);
        }
    }

    @Override
    public void onDreamingStopped() {
        DebugLog.i(TAG, "onDreamingStopped");
        try {
            if (sync != null) { sync.stop(); sync = null; }
            if (viewHost != null) { viewHost.destroy(); viewHost = null; }
        } catch (Throwable t) {
            DebugLog.e(TAG, "onDreamingStopped CRASH", t);
        }
        super.onDreamingStopped();
    }
}
