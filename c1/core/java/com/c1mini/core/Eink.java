package com.c1mini.core;

import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;

import java.lang.reflect.Method;

/**
 * 墨水屏刷新控制。
 *
 * 这台 C1（全志 virgo 平台）的 ROM 在 framework 里塞了一套 per-window 刷新模式 API，
 * 都是 public 方法但不在标准 android.jar 里，只能反射调用：
 *
 *   Window.setRefreshMode(int) / getRefreshMode()
 *   Window.setGu16RefreshLimit(int)      // 残影债务上限：连刷 N 帧后强制一次 GC16
 *   Window.forceGlobalRefresh(boolean)   // 整屏全刷，清残影
 *
 * 真机实测：设 A2 后 HWC 立刻从 EINK_GU16_MODE 切到 EINK_A2_MODE，且只影响本窗口的主 layer，
 * 别的窗口仍是 GU16 —— 所以两个 APK 各管各的，互不干扰。
 *
 * 找不到这些方法时（换机型 / 原厂 ROM）全部静默降级，界面照常工作，只是刷新走系统默认。
 */
public final class Eink {

    private static final String TAG = "C1Eink";

    // ---- 波形常量，真机反射 EINK_SHOW_MODE_* 读出 ----
    /** 初始化/清屏 */
    public static final int INIT = 1;
    /** Direct Update：只刷变化像素，最快，有轻微残影，适合翻页 */
    public static final int DU = 2;
    /** 16 级灰度全刷：无残影，会黑白闪一下，适合清残/换页 */
    public static final int GC16 = 4;
    /** 4 级灰度快刷 */
    public static final int GC4 = 8;
    /** 1 位黑白极速刷：最快，文字会发虚/锯齿，适合滚动和动画 */
    public static final int A2 = 16;
    /** 16 级灰度局部快刷，残影比 DU 略重但对比更稳 */
    public static final int GL16 = 32;
    public static final int GLR16 = 64;
    public static final int GLD16 = 128;
    /** 灰度更新：介于快刷和全刷之间，菜单/对话框用这个最舒服 */
    public static final int GU16 = 132;
    public static final int RUBBER = 136;
    /** 逐区域刷新的开关位，与上面的波形按位或组合 */
    public static final int RECT = 1024;
    public static final int AUTO = 32768;

    // ---------------- 翻页档位（对用户只暴露一个「翻页显示」） ----------------

    /**
     * 稳定（默认）：**DU|RECT 真局部刷新**。
     *
     * 这是 FlyEinkReader 那种「底部/顶部不动」效果的等价做法（它用的是私有
     * EpdController 区域刷新，我们调不到；DU|RECT 是框架给我们的、真能只刷变化区的波形）。
     *
     * DU 只有 2 级灰度、按「像素差分」刷新：上一页黑字 vs 这一页白底 → 差分非零 →
     * 被驱回白；这一页才有的字 → 被驱成黑。所以**只有真的变了的区域会被重驱**，
     * 没变的区域（系统导航栏、顶部没换的章节名）压根不参与刷新 → 不跳。
     * 像素对比实测：DU|RECT 翻页时顶部章节名 max=0、底部导航 max=0（完全没重绘），
     * 而 GL16/GLR16 整窗刷会把整片连同没变区一起重驱 → 那才是「完全不变也跳」。
     *
     * 前提：PageView 每帧先 drawColor 清白底 —— 旧页黑字在新一帧里是白、差分非零，
     * 才会被驱回白；不清白底就会叠字（这是 11-12 的坑，别删那句 drawColor）。
     * 代价：DU 2 级驱动本身不彻底，连翻会攒一点淡灰残影。
     * 解决：needsPeriodicClean() 为真时，阅读页每隔 cleanEvery() 页把「翻页那一帧」
     * 直接换成 GC16 整窗全刷清掉残影（全刷和新内容同一帧上屏，不是事后补刷），
     * 以及换章、用户点「全刷」时清一次。这是标准墨水屏行为，像 Kindle 隔几页闪一下。
     */
    public static final int TURN_STABLE = 0;
    /** 最干净：GLR16（Regal），16 级灰度、字最顺、残影最少，但整窗刷、翻页会闪 */
    public static final int TURN_CLEAN = 1;
    /** 对照档：GL16 整窗一帧，字最干净无残影，但翻页整片重驱、顶/底会跳 */
    public static final int TURN_FAST = 2;

    /** 深清波形：GC16，会黑白闪。只把「该深清的那一页」这一帧换成它，不额外插帧 */
    public static final int CLEAN_DEEP = GC16;

    public static int turnStyle() {
        int v = Prefs.i("turn_style", -1);
        return (v >= 0 && v <= TURN_FAST) ? v : TURN_STABLE;
    }

    /**
     * 正文翻页的**完整模式值**（已含是否带 RECT，调用方直接 setMode，不要再按位或）。
     * 默认 DU|RECT：真局部、顶/底不重驱、不跳；隔几页顺手 GC16 清一次残影。
     * 另两档是整窗 16 级灰度，字更顺/更干净，但翻页会整片重驱（顶/底会闪）。
     */
    public static int turnMode() {
        switch (turnStyle()) {
            case TURN_CLEAN: return GLR16;
            case TURN_FAST:  return GL16;
            default:         return DU | RECT;
        }
    }

    public static String turnName() {
        switch (turnStyle()) {
            case TURN_CLEAN: return "最干净（Regal，字最顺但翻页会闪）";
            case TURN_FAST:  return "标准（GL16，最干净但翻页会闪）";
            default: return "稳定（推荐，局部刷不跳）";
        }
    }

    /** 只有 2 级快刷会累积物理残影，需要隔几页把翻页那一帧换成 GC16 全清 */
    public static boolean needsPeriodicClean() {
        return (turnMode() & ~RECT) == DU;
    }

    /**
     * 系统残影债务上限：阅读页一律关掉（0 = 不设上限）。
     *
     * 这个值是 HWC 自己的计数器：连刷 N 帧后它自己插一帧 GC16 全刷，App 拦不住。
     * 出厂 12 就是「关了所有开关还是十几页闪一次」的真凶。
     * 默认 GL16 每帧自身就是完整复位，不需要 HWC 再插一脚。
     */
    public static int gu16Limit() {
        return 0;
    }

    /**
     * 仅对照档 DU|RECT 用：每隔多少页，在「翻页那一帧」直接用 GC16 清一次物理残影。
     *
     * 0 = 不自动全刷，只靠菜单「全刷」手动清。
     * 默认的 GL16/GLR16 每页自身就把像素完整复位，不走这条路。
     */
    public static int cleanEvery() {
        int v = Prefs.i("clean_every", 8);
        return (v < 0 || v > 60) ? 8 : v;
    }

    private static Method mSet, mGet, mLimit, mGlobal, mParamSet;
    private static boolean probed;

    // ---------------- 静止界面（桌面 / 书库 / 设置页） ----------------

    /**
     * 静止界面统一波形：GL16。
     *
     * 和阅读页翻页是同一个波形、同一个理由 —— 16 级灰度、低闪，
     * 抗锯齿文字只被量化一次。界面上的任何重绘（点开关、切应用页、改设置项）
     * 都走这一种波形，中途不换，所以字上屏之后不会再「跳」。
     *
     * 为什么不是 DU：DU 只有 2 级灰度，字边会被压成硬边；桌面上一会儿 GL16
     * 一会儿 DU，同一批字来回重新量化，读者看到的就是抖动。
     */
    public static int screenMode() {
        return GL16;
    }

    /**
     * 把一个窗口调成「静止界面」：单一波形 + 不设残影债务上限。
     * 每个 Activity 在 onResume 调一次即可，之后不要再临时换波形 ——
     * 换一次就把整屏字重画一遍，那是抖动的唯一来源。
     */
    public static void applyScreen(Window win) {
        int want = screenMode();
        // setRefreshMode() 本身会让窗口重绘一帧，所以值没变就别设。
        // 每次 onResume 都无条件 set 的话，从别的应用回来会白刷一帧。
        if (get(win) != want) set(win, want);
        setGu16Limit(win, 0);
        Log.i(TAG, "applyScreen mode=" + modeName(want)
                + " readback=" + get(win) + " limit=" + gu16Limit());
    }

    /** 手动全刷之后回到静止界面波形（供 refreshAll 内部回调） */
    private static void backToScreen(Window win) {
        set(win, screenMode());
    }

    private Eink() {
    }

    private static synchronized void probe() {
        if (probed) return;
        probed = true;
        try {
            Class<?> w = Class.forName("android.view.Window");
            mSet = find(w, "setRefreshMode", int.class);
            mGet = find(w, "getRefreshMode");
            mLimit = find(w, "setGu16RefreshLimit", int.class);
            mGlobal = find(w, "forceGlobalRefresh", boolean.class);
        } catch (Throwable ignored) {
        }
        try {
            Class<?> lp = Class.forName("android.view.WindowManager$LayoutParams");
            mParamSet = find(lp, "setRefreshMode", int.class);
        } catch (Throwable ignored) {
        }
        Log.i(TAG, "per-window refresh api: set=" + (mSet != null)
                + " get=" + (mGet != null) + " limit=" + (mLimit != null)
                + " global=" + (mGlobal != null) + " param=" + (mParamSet != null));
    }

    private static Method find(Class<?> c, String name, Class<?>... types) {
        try {
            Method m = c.getMethod(name, types);
            m.setAccessible(true);
            return m;
        } catch (Throwable e) {
            return null;
        }
    }

    /** 当前 ROM 是否支持控制刷新波形 */
    public static boolean supported() {
        probe();
        return mSet != null;
    }

    /** 设置本窗口的刷新波形，mode 可用 {@link #RECT} 按位或。失败返回 false */
    public static boolean set(Window win, int mode) {
        probe();
        if (win == null || mSet == null) return false;
        try {
            mSet.invoke(win, mode);
            return true;
        } catch (Throwable e) {
            Log.w(TAG, "setRefreshMode(" + mode + ") failed: " + e);
            return false;
        }
    }

    public static int get(Window win) {
        probe();
        if (win == null || mGet == null) return -1;
        try {
            Object v = mGet.invoke(win);
            return v instanceof Integer ? (Integer) v : -1;
        } catch (Throwable e) {
            return -1;
        }
    }

    /** 残影债务上限：同一窗口连续快刷多少帧后强制一次 GC16。0 表示用系统默认 */
    private static final java.util.WeakHashMap<Window, Integer> lastGuLimit =
            new java.util.WeakHashMap<Window, Integer>();

    public static boolean setGu16Limit(Window win, int frames) {
        probe();
        if (win == null || mLimit == null) return false;
        // 同值不重复设：setRefreshMode/limit 本身会让窗口重绘一帧，
        // 每次 onResume、每次开书都无条件重设，就会白刷一帧、顶部闪一下。
        Integer prev = lastGuLimit.get(win);
        if (prev != null && prev == frames) return true;
        try {
            mLimit.invoke(win, frames);
            lastGuLimit.put(win, frames);
            return true;
        } catch (Throwable e) {
            return false;
        }
    }

    /**
     * 手动整屏刷新：用户主动点的，黑闪一下正好是反馈。
     * 默认 520ms 后自动回到静止界面波形。
     */
    public static boolean refreshAll(Window win, View view) {
        return refreshAll(win, view, 520);
    }

    /**
     * 切一帧 GC16 清残影，**不安排恢复** —— 调用方必须自己切回来。
     *
     * 阅读页用它：那边有个 curMode 缓存，恢复时要同时改缓存，
     * 交给这边统一处理会漏掉缓存，结果后面每页都全刷。
     */
    public static boolean flashGlobal(Window win, View view) {
        if (win == null) return false;
        boolean ok = set(win, GC16);
        if (view != null) view.invalidate();
        return ok;
    }

    /**
     * 手动整屏刷新（可指定恢复延迟）。
     *
     * 注意 view 参数：切波形本身会刷一帧旧内容，必须再 invalidate 一次把
     * 当前内容写实，否则全刷会拖到下一次重绘时才闪。
     *
     * delayMs 之后自动切回 {@link #screenMode()}：调用方忘了切回来会一直停在全刷，
     * 之后每次重绘都黑闪一次 —— 这个坑踩过，所以把恢复收进方法内部。
     */
    public static boolean refreshAll(Window win, View view, long delayMs) {
        boolean ok = flashGlobal(win, view);
        if (win == null) return ok;
        final Window w = win;
        new Handler(Looper.getMainLooper()).postDelayed(new Runnable() {
            @Override
            public void run() {
                backToScreen(w);
            }
        }, Math.max(200, delayMs));
        return ok;
    }

    /**
     * ⚠️ 不要用 forceGlobalRefresh 做「这一页顺便深清」。
     *
     * 真机实测（2026-11-12）：这台 ROM 的 forceGlobalRefresh(true) 是个**锁存器** ——
     * 打开之后每一帧都变成 EINK_GC16_MODE，再调 false 也解不掉，只能重建窗口。
     * 表现就是「翻一页黑闪一次」，比任何残影都难受。所以翻页路径里一次都不能碰它。
     * 这里只留一个解锁口子，给「别的版本锁住了、想当场解开」用；
     * 解不掉也没关系，退出重进阅读页就是新窗口。
     */
    public static void endDeep(Window win) {
        probe();
        if (win == null || mGlobal == null) return;
        try {
            mGlobal.invoke(win, Boolean.FALSE);
        } catch (Throwable ignored) {
        }
    }

    public static String modeName(int mode) {
        int base = mode & ~RECT;
        String n;
        switch (base) {
            case INIT: n = "INIT"; break;
            case DU: n = "DU"; break;
            case GC16: n = "GC16"; break;
            case GC4: n = "GC4"; break;
            case A2: n = "A2"; break;
            case GL16: n = "GL16"; break;
            case GLR16: n = "GLR16"; break;
            case GLD16: n = "GLD16"; break;
            case GU16: n = "GU16"; break;
            case RUBBER: n = "RUBBER"; break;
            default: n = "0x" + Integer.toHexString(base); break;
        }
        return (mode & RECT) != 0 ? n + "|RECT" : n;
    }

    /** 把这台机器的显示参数打一条日志，排障时看 logcat -s C1Eink 即可 */
    public static void logDevice() {
        probe();
        Log.i(TAG, "device=" + Build.MODEL + " sdk=" + Build.VERSION.SDK_INT
                + " platform=" + Build.HARDWARE);
    }

    /** 关掉窗口动画，墨水屏上任何过渡都是拖影来源 */
    public static void noAnimations(Window win) {
        if (win == null) return;
        try {
            WindowManager.LayoutParams lp = win.getAttributes();
            lp.windowAnimations = 0;
            win.setAttributes(lp);
        } catch (Throwable ignored) {
        }
    }
}
