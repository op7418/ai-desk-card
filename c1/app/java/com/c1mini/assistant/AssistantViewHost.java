package com.c1mini.assistant;

import android.app.Dialog;
import android.content.Context;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.Drawable;
import android.os.Handler;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.ImageView;

import com.c1mini.core.Eink;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

/**
 * 共用窗口宿主：Activity 和 DreamService 都委托它管理"立绘 + 任务浮层"。
 *
 * 两层窗口波形隔离（真机已验证 readback=1026）：
 *   主窗口   → GL16 彩色立绘，首帧全刷清残影后永不重绘
 *   Dialog   → DU|RECT 黑白任务，只有内容变化才局刷
 * 本类不联网、不解析数据 —— 那是 SyncScheduler 的事。
 */
final class AssistantViewHost {
    private static final String TAG = "C1ViewHost";
    /** 立绘栏占屏宽比例：0.52，人像醒目、抬手指右 */
    private static final float AVATAR_W_FRAC = 0.52f;
    /**
     * 任务浮层窗口起点占屏宽比例：略小于立绘栏，让文字贴着引导手。
     * 手尖在 0.498*w 处（实测 x=534），窗口白底左边界取 0.510*w（x≈546），
     * 留 ~12px 不盖彩色手；文字 PAD 再收紧，整体贴手又不截断。
     */
    private static final float PANEL_X_FRAC = 0.510f;
    /** 眼睛贴图在立绘素材(650×1460)内的位置与尺寸，由 gen_blink_assets.py 标定 */
    private static final int AVATAR_SRC_W = 650, AVATAR_SRC_H = 1460;
    private static final int EYE_SRC_X = 122, EYE_SRC_Y = 145;
    private static final int EYE_SRC_W = 206, EYE_SRC_H = 33;

    private final Context ctx;
    private final Handler handler = new Handler();
    private Dialog taskDialog;
    private TaskView taskView;
    private List<Task> tasks;

    // 眨眼：独立 GL16 小窗，只刷眼睛那一小块
    private Dialog blinkDialog;
    private BlinkView blinkView;
    private final Runnable blinkClose = new Runnable() {
        @Override public void run() {
            if (blinkView != null) blinkView.setBlinking(true);
            handler.postDelayed(blinkOpen, 200);   // 闭眼 200ms：自然眨眼节奏
        }
    };
    private final Runnable blinkOpen = new Runnable() {
        @Override public void run() {
            if (blinkView != null) blinkView.setBlinking(false);
            scheduleBlink();                        // 排下一次
        }
    };

    AssistantViewHost(Context ctx, List<Task> initialTasks) {
        this.ctx = ctx;
        this.tasks = initialTasks;
    }

    /** 宿主 content view 就绪后调用：给立绘设图、建任务浮层、首帧全刷。 */
    void setup(View root, final Runnable onReady) {
        final ImageView avatar = (ImageView) root.findViewById(R.id.avatar);
        avatar.setImageDrawable(loadAvatar());

        taskView = new TaskView(ctx, tasks, new Runnable() {
            @Override public void run() { onTaskAdvanced(); }
        });

        // 等布局完成再按真实尺寸定位浮层（Dream/Activity 都一样）
        avatar.post(new Runnable() {
            @Override public void run() {
                // 关键：先开彩色面板输出，再做首帧全刷。C1 的 sys.use.color 默认
                // 为 0（灰阶），不先设 1，HWC 会把彩色立绘按黑白刷到面板 ——
                // framebuffer 是彩色的但物理屏是纯黑剪影（2026-11-19 真机根因）。
                ColorMode.enableColor();
                showTaskWindow(root);
                // 首帧 GC16 全刷：清掉上一个 app 留在墨水屏上的残影，
                // 也覆盖状态栏区域（宿主要求全屏，见各入口）。
                Window mainWin = mainWindow();
                if (mainWin != null) {
                    Eink.refreshAll(mainWin, root, 900);
                }
                if (onReady != null) onReady.run();
            }
        });
    }

    /** 由宿主提供主窗口（Activity.getWindow() / DreamService.getWindow()）。 */
    private Window mainWindow() {
        if (ctx instanceof android.app.Activity)
            return ((android.app.Activity) ctx).getWindow();
        if (ctx instanceof android.service.dreams.DreamService)
            return ((android.service.dreams.DreamService) ctx).getWindow();
        return null;
    }

    private Drawable loadAvatar() {
        InputStream is = null;
        try {
            is = ctx.getAssets().open("assistant.png");
            android.graphics.Bitmap bmp = android.graphics.BitmapFactory.decodeStream(is);
            // 关键：C1 density=300。若按默认 mdpi 解释，intrinsic 会被放大 1.875×，
            // fitEnd 于是把人缩得很小。显式设为设备 density，intrinsic=像素尺寸，
            // 才能按 showBlinkWindow 里的 scale 精确铺满 557×1107。
            bmp.setDensity(ctx.getResources().getDisplayMetrics().densityDpi);
            BitmapDrawable d = new BitmapDrawable(ctx.getResources(), bmp);
            DebugLog.i(TAG, "avatar bitmap " + bmp.getWidth() + "x" + bmp.getHeight()
                    + " density=" + bmp.getDensity());
            return d;
        } catch (Exception e) {
            Log.e(TAG, "load avatar failed", e);
            return new BitmapDrawable(ctx.getResources());
        } finally {
            if (is != null) try { is.close(); } catch (Exception ignored) {}
        }
    }

    private void showTaskWindow(View root) {
        int w = root.getWidth();
        int h = root.getHeight();
        if (w <= 0 || h <= 0) {
            Log.w(TAG, "root not laid out yet, skip task window");
            return;
        }
        int avatarX = (int) (w * AVATAR_W_FRAC);   // 立绘栏宽（手的位置由它决定）
        int taskX = (int) (w * PANEL_X_FRAC);      // 任务窗起点（贴手，白底不盖手尖）
        int taskW = w - taskX;

        // 立绘宽度 = 左侧 AVATAR_W_FRAC，手的位置不变。
        ImageView avatar = (ImageView) root.findViewById(R.id.avatar);
        FrameLayout.LayoutParams alp = (FrameLayout.LayoutParams) avatar.getLayoutParams();
        alp.width = avatarX;
        avatar.setLayoutParams(alp);

        // 用 content view 的 Context（带窗口 token）：Activity/Dream 都适用。
        // 直接传 Service Context 在部分 ROM 上会 BadTokenException。
        Context dlgCtx = root.getContext();

        // 眼睛窗口：按立绘栏实际宽度（avatarX）算 fitEnd 落点，与任务窗起点无关。
        showBlinkWindow(dlgCtx, avatarX, h);
        taskDialog = new Dialog(dlgCtx, R.style.AssistantDialogTheme);
        taskDialog.setContentView(taskView);
        taskDialog.setCancelable(false);
        taskDialog.setCanceledOnTouchOutside(false);
        Window tw = taskDialog.getWindow();   // 公开 API，iFlytek ROM 可靠
        if (tw != null) {
            WindowManager.LayoutParams lp = tw.getAttributes();
            lp.width = taskW;
            lp.height = h;
            lp.gravity = Gravity.TOP | Gravity.LEFT;
            lp.x = taskX;
            lp.y = 0;
            lp.flags |= WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE;
            tw.setAttributes(lp);
            boolean ok = Eink.set(tw, Eink.DU | Eink.RECT);
            Eink.setGu16Limit(tw, 0);
            DebugLog.i(TAG, "task dialog set DU|RECT ok=" + ok + " readback=" + Eink.get(tw));
        }
        taskDialog.show();
    }

    /**
     * 眼睛窗口：在立绘双眼像素上叠一个极小的 GL16 窗口做眨眼。
     * 坐标按 ImageView 的 fitEnd 缩放推算，和 showTaskWindow 用同一套 taskX/h。
     */
    private void showBlinkWindow(Context dlgCtx, int ivW, int ivH) {
        float scale = Math.min(ivW / (float) AVATAR_SRC_W, ivH / (float) AVATAR_SRC_H);
        int dw = Math.round(AVATAR_SRC_W * scale);
        int dh = Math.round(AVATAR_SRC_H * scale);
        int offsetX = (ivW - dw) / 2;          // fitEnd：水平居中
        int offsetY = ivH - dh;                 // fitEnd：贴底
        int eyeX = offsetX + Math.round(EYE_SRC_X * scale);
        int eyeY = offsetY + Math.round(EYE_SRC_Y * scale);
        int eyeW = Math.round(EYE_SRC_W * scale);
        int eyeH = Math.round(EYE_SRC_H * scale);

        blinkView = new BlinkView(dlgCtx);
        blinkDialog = new Dialog(dlgCtx, R.style.AssistantDialogTheme);
        blinkDialog.setContentView(blinkView);
        blinkDialog.setCancelable(false);
        blinkDialog.setCanceledOnTouchOutside(false);
        Window bw = blinkDialog.getWindow();
        if (bw != null) {
            WindowManager.LayoutParams lp = bw.getAttributes();
            lp.width = eyeW;
            lp.height = eyeH;
            lp.gravity = Gravity.TOP | Gravity.LEFT;
            lp.x = eyeX;
            lp.y = eyeY;
            lp.flags |= WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE;
            bw.setAttributes(lp);
            // 彩色眼睛必须 GL16；DU 是 2 级黑白会把彩色压成色块。
            boolean ok = Eink.set(bw, Eink.GL16);
            Eink.setGu16Limit(bw, 0);
            DebugLog.i(TAG, "blink window " + eyeW + "x" + eyeH + "@(" + eyeX + "," + eyeY
                    + ") GL16 ok=" + ok + " readback=" + Eink.get(bw));
        }
        try { blinkDialog.show(); }
        catch (Throwable t) { DebugLog.e(TAG, "blink dialog show CRASH", t); }
        scheduleBlink();
    }

    /** 低频眨眼：5~11 秒随机一次，闭 140ms。频率压低既自然又省电。 */
    private void scheduleBlink() {
        long delay = 5000L + (long) (Math.random() * 6000L);
        handler.postDelayed(blinkClose, delay);
    }
    void onTasksChanged(List<Task> fresh) {
        if (fresh == null || fresh.isEmpty()) return;
        tasks = fresh;
        if (taskView != null) taskView.setTasks(fresh);
        onTaskAdvanced();
        DebugLog.i(TAG, "tasks changed → " + fresh.size() + " (avatar untouched)");
    }

    /** 局刷 + 每 8 次插 GC16 清残影（复用 c1 阅读页 cleanEvery 结论）。 */
    private void onTaskAdvanced() {
        Window tw = taskDialog != null ? taskDialog.getWindow() : null;
        if (tw == null) {
            if (taskView != null) taskView.invalidate();
            return;
        }
        if (taskView.pushCount() % 8 == 0 && taskView.pushCount() > 0) {
            Eink.set(tw, Eink.GC16);
            taskView.invalidate();
            handler.postDelayed(new Runnable() {
                @Override public void run() {
                    Window w = taskDialog != null ? taskDialog.getWindow() : null;
                    if (w != null) Eink.set(w, Eink.DU | Eink.RECT);
                }
            }, 520);
            return;
        }
        taskView.invalidate();
    }

    /** 宿主销毁/退出屏保时调：关浮层，停眨眼。 */
    void destroy() {
        handler.removeCallbacks(blinkClose);
        handler.removeCallbacks(blinkOpen);
        blinkView = null;
        if (blinkDialog != null && blinkDialog.isShowing()) blinkDialog.dismiss();
        blinkDialog = null;
        if (taskDialog != null && taskDialog.isShowing()) taskDialog.dismiss();
        taskDialog = null;
    }

    /** 首屏占位任务（daemon 未配置/未拉到时用）。 */
    static List<Task> demoTasks() {
        List<Task> l = new ArrayList<Task>();
        l.add(new Task("审阅 Q4 架构方案", "今天 14:00", true));
        l.add(new Task("回复设计评审意见", "今天 17:30", false));
        l.add(new Task("整理墨水屏调研笔记", "本周", false));
        l.add(new Task("预约周五的体检", "本周五", false));
        return l;
    }
}
