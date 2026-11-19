package com.c1mini.assistant;

import android.util.Log;

import java.io.File;
import java.io.FileWriter;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * 落盘调试日志：C1 睡眠期间 logcat buffer 会被清空，远程 adb 又断，
 * 只有写进文件能在唤醒后读到。屏保验证全靠它。
 *
 * 双写：
 *   1) /sdcard/c1_assistant.log —— 需要 WRITE_EXTERNAL_STORAGE，adb 直接 cat
 *   2) /data/data/<pkg>/files/c1_assistant.log —— app 私有目录，无条件可写，
 *      debuggable=true 后 adb shell run-as 也能读（sdcard 权限失败时的兜底）
 * 同时仍写 logcat，方便前台调试。
 */
final class DebugLog {
    private static final String SD_PATH = "/sdcard/c1_assistant.log";
    private static final String PRIVATE_PATH =
            "/data/data/com.c1mini.assistant/files/c1_assistant.log";
    private static final SimpleDateFormat FMT =
            new SimpleDateFormat("MM-dd HH:mm:ss.SSS", Locale.US);

    static void i(String tag, String msg) { write("I", tag, msg, null); }
    static void w(String tag, String msg) { write("W", tag, msg, null); }
    static void e(String tag, String msg, Throwable t) { write("E", tag, msg, t); }

    private static void write(String lv, String tag, String msg, Throwable t) {
        String full = msg;
        if (t != null) full += "\n" + Log.getStackTraceString(t);
        final String line;
        synchronized (FMT) {
            line = FMT.format(new Date()) + " " + lv + "/" + tag + ": " + full + "\n";
        }
        append(SD_PATH, line);
        append(PRIVATE_PATH, line);
        if ("E".equals(lv)) Log.e(tag, msg, t);
        else if ("W".equals(lv)) Log.w(tag, msg);
        else Log.i(tag, msg);
    }

    private static void append(String path, String line) {
        try {
            File f = new File(path);
            File parent = f.getParentFile();
            if (parent != null && !parent.exists()) parent.mkdirs();
            FileWriter fw = new FileWriter(f, true);
            try {
                fw.write(line);
            } finally {
                fw.close();
            }
        } catch (Throwable ignored) {
            // 单个路径不可写时静默降级，不影响另一路径与功能
        }
    }
}
