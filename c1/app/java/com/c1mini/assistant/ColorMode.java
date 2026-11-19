package com.c1mini.assistant;

import android.util.Log;

import java.lang.reflect.Method;

/**
 * C1 彩色开关。
 *
 * 真机根因（2026-11-19）：这台 C1 的系统属性 sys.use.color 默认为 0，
 * HWC 的 displayToScreen 会把彩色内容按灰阶刷到墨水屏面板 ——
 * framebuffer 截图（adb screencap）是彩色的，但物理面板显示纯黑剪影。
 * setprop sys.use.color 1 后，下一帧日志 use_color:1，颜色恢复正常。
 *
 * 本机是 userdebug + SELinux Permissive，App 反射 SystemProperties.set 即可设；
 * 量产 Enforcing 机上会失败，静默降级（保持系统默认黑白），不影响其它功能。
 *
 * 调用时机：立绘首帧上屏前（屏幕刚灭、系统可能把该属性压回 0 之后再设），
 * 以及每次进屏保时再设一次，确保彩色立绘按彩色波形上屏。
 */
final class ColorMode {
    private static final String TAG = "C1Color";
    private static Method sSet;
    private static Method sGet;
    private static boolean sProbed;

    private ColorMode() {}

    /** 打开彩色面板输出。返回是否设置成功（失败不影响主流程）。 */
    static boolean enableColor() {
        try {
            probe();
            if (sSet == null) {
                DebugLog.i(TAG, "SystemProperties.set unavailable → skip (ROM default)");
                return false;
            }
            String before = get();
            sSet.invoke(null, "sys.use.color", "1");
            String after = get();
            DebugLog.i(TAG, "sys.use.color " + before + " → " + after);
            return "1".equals(after);
        } catch (Throwable t) {
            DebugLog.i(TAG, "enableColor failed: " + t);
            return false;
        }
    }

    private static void probe() {
        if (sProbed) return;
        sProbed = true;
        try {
            Class<?> sp = Class.forName("android.os.SystemProperties");
            sSet = sp.getDeclaredMethod("set", String.class, String.class);
            sSet.setAccessible(true);
            sGet = sp.getDeclaredMethod("get", String.class);
            sGet.setAccessible(true);
        } catch (Throwable t) {
            DebugLog.i(TAG, "SystemProperties reflect failed: " + t);
        }
    }

    private static String get() {
        try {
            if (sGet == null) return "?";
            Object v = sGet.invoke(null, "sys.use.color");
            return v instanceof String ? (String) v : "?";
        } catch (Throwable t) {
            return "?";
        }
    }
}
