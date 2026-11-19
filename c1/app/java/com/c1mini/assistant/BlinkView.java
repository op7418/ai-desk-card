package com.c1mini.assistant;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.drawable.Drawable;
import android.util.AttributeSet;
import android.view.View;

import com.c1mini.core.Eink;

/**
 * 眼睛窗口：在立绘双眼位置叠一个极小的 GL16 窗口，
 * 平时画 eyes_open（与底图像素一致，看不出叠加），定时切 eyes_closed 眨一下。
 *
 * 为什么不直接重绘立绘：
 *   立绘是主窗口 GL16 常驻，整窗刷一次全屏重驱、闪且耗电。
 *   眼睛窗只有 119×52px，GL16 只刷这一小块，人眼几乎无感。
 *
 * 波形：GL16（16 级灰度、低闪、彩色）—— 彩色贴图只有 GL16/GC16 能正确上屏；
 *       DU 是 2 级黑白，会把彩色眼睛压成色块，绝不能用。
 */
public class BlinkView extends View {
    private Drawable open, closed;
    private boolean blinking;

    public BlinkView(Context c) {
        super(c);
        open = load("eyes_open.png");
        closed = load("eyes_closed.png");
    }
    public BlinkView(Context c, AttributeSet a) { this(c); }

    private Drawable load(String name) {
        try {
            return Drawable.createFromStream(getContext().getAssets().open(name), name);
        } catch (Exception e) {
            DebugLog.e("C1Blink", "load " + name + " failed", e);
            return null;
        }
    }

    /** 由调度器调用：true=闭眼帧，false=睁眼帧。主线程调用。 */
    void setBlinking(boolean on) {
        if (blinking == on) return;
        blinking = on;
        DebugLog.i("C1Blink", on ? "眨眼:闭" : "眨眼:睁");
        invalidate();
    }

    @Override
    protected void onDraw(Canvas c) {
        Drawable d = blinking ? closed : open;
        if (d == null) return;
        d.setBounds(0, 0, getWidth(), getHeight());
        d.draw(c);
    }
}
