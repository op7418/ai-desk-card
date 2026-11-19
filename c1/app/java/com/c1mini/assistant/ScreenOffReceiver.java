package com.c1mini.assistant;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/**
 * 休眠覆盖层入口 —— 替代这台 C1 的系统屏保（PowerManagerService.showSuspendLogo）。
 *
 * 真机证实：这台机按电源键休眠时，PowerManagerService 监听 SCREEN_OFF 广播，
 * 自己 new 一个全屏 ImageView 画一张静态 Logo（showSuspendLogo），
 * 标准 Android Dream/Screensaver 框架是空壳、永不触发。
 * 因此改为监听同一个 ACTION_SCREEN_OFF 广播，在桌面层弹全屏助理覆盖系统 Logo。
 *
 * ACTION_SCREEN_OFF 在 Android 隐式广播白名单内，可静态注册。
 */
public class ScreenOffReceiver extends BroadcastReceiver {
    private static final String TAG = "C1ScreenOff";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent == null ? null : intent.getAction();
        if (!Intent.ACTION_SCREEN_OFF.equals(action)) return;

        DebugLog.i(TAG, "ACTION_SCREEN_OFF → launch assistant overlay");
        try {
            Intent i = new Intent(context, AssistantActivity.class);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                    | Intent.FLAG_ACTIVITY_CLEAR_TOP
                    | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            i.putExtra("overlay", true);          // 覆盖模式：高 z-order + 自动退出逻辑
            context.startActivity(i);
            DebugLog.i(TAG, "startActivity(AssistantActivity overlay) OK");
        } catch (Throwable t) {
            DebugLog.e(TAG, "launch overlay CRASH", t);
        }
    }
}
