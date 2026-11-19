package com.c1mini.assistant;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import android.view.MotionEvent;
import android.view.View;

import java.util.List;

/**
 * 任务浮层：纯黑白自绘，跑在 DU|RECT 浮层窗口里。
 *
 * 三条铁律（来自 c1 项目 docs/eink-refresh.md）：
 *  1. onDraw 第一步先 drawColor(白) 清白底 —— DU 差分靠它把旧墨驱回白，不清会叠字。
 *  2. 不抗锯齿、不渐变、无按下态 —— DU 只有 2 级灰度。
 *  3. 点击命中自己算（没有子 View），只 invalidate 变化的文字行区域。
 */
public class TaskView extends View {
    private List<Task> tasks;
    private final Runnable onAdvance;
    private final Paint ink = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint faint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint bold = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint hint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint paper = new Paint();
    private int pushCount = 0;

    private static final int PAD = 18;
    private static final int ROW_H = 150;
    // 骨架 todo schema 上限 4 项；屏高有限，超过 5 项就只画前 5 项。
    private static final int MAX_ROWS = 5;

    public TaskView(Context c, List<Task> tasks, Runnable onAdvance) {
        super(c);
        this.tasks = tasks;
        this.onAdvance = onAdvance;
        ink.setColor(Color.rgb(0x1a, 0x1a, 0x1a));
        ink.setTextSize(40);
        bold.setColor(Color.rgb(0x1a, 0x1a, 0x1a));
        bold.setTextSize(46);
        bold.setFakeBoldText(true);
        faint.setColor(Color.rgb(0x77, 0x77, 0x77));
        faint.setTextSize(30);
        hint.setColor(Color.rgb(0x1a, 0x1a, 0x1a));
        hint.setTextSize(30);
        paper.setColor(Color.WHITE);
    }

    /** daemon 推来的新任务：替换列表 + 计入局刷次数（纳入 GC16 清残影周期）。 */
    public void setTasks(List<Task> fresh) {
        if (fresh == null || fresh.isEmpty()) return;
        this.tasks = fresh;
        pushCount++;
    }

    @Override
    protected void onDraw(Canvas c) {
        // 铁律 1：先清白底。DU 差分必需，绝不删。
        c.drawColor(Color.WHITE);

        int n = Math.min(tasks.size(), MAX_ROWS);
        int y = PAD + 60;
        c.drawText("早上好，苏苏", PAD, y, bold);
        y += 34;

        // 引导气泡：随进展变化的提示语，黑框矩形（DU 2 级，纯黑白）。
        String hint = hintText();
        int bubbleH = 92;
        int bubbleW = getWidth() - PAD * 2;
        c.drawRect(new Rect(PAD, y, PAD + bubbleW, y + bubbleH), ink);
        c.drawRect(new Rect(PAD + 3, y + 3, PAD + bubbleW - 3, y + bubbleH - 3), paper);
        c.drawText(hint, PAD + 20, y + bubbleH / 2 + 11, this.hint);
        y += bubbleH + 40;

        c.drawText("今日待办 · TASK", PAD, y, faint);
        y += 24;
        c.drawLine(PAD, y, getWidth() - PAD, y, faint);
        y += 16;

        for (int i = 0; i < n; i++) {
            Task t = tasks.get(i);
            String mark = t.done ? "✓" : (t.doing ? "▶" : "□");
            c.drawText(mark, PAD, y + ROW_H - 40, t.doing ? bold : ink);
            c.drawText(t.text, PAD + 60, y + ROW_H - 40, ink);
            c.drawText(t.due, PAD + 60, y + ROW_H - 4, faint);
            if (t.done) {
                // 完成划线：一条横线覆盖文字中部
                float w = ink.measureText(t.text);
                c.drawLine(PAD + 60, y + ROW_H - 52, PAD + 60 + w, y + ROW_H - 52, faint);
            }
            y += ROW_H;
        }

        // 底部进展条
        int barY = getHeight() - 120;
        c.drawLine(PAD, barY - 20, getWidth() - PAD, barY - 20, ink);
        c.drawText("今日进展  " + done() + " / " + n, PAD, barY + 30, ink);
        Rect bar = new Rect(PAD, barY + 50, getWidth() - PAD, barY + 80);
        c.drawRect(bar, faint);
        if (n > 0) {
            Rect fill = new Rect(PAD, barY + 50,
                    PAD + (int) (bar.width() * done() / (float) n), barY + 80);
            c.drawRect(fill, ink);
        }
    }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        if (e.getAction() == MotionEvent.ACTION_UP) {
            int idx = rowAt((int) e.getY());
            if (idx >= 0 && idx < tasks.size() && !tasks.get(idx).done) {
                tasks.get(idx).done = true;
                pushCount++;
                onAdvance.run();
                return true;
            }
        }
        return super.onTouchEvent(e);
    }

    /** 任务列表第一行的顶部 y（气泡高度变化时要同步，点击命中才准）。 */
    private static int rowsTop() { return PAD + 60 + 34 + (92 + 40) + 24 + 16; }

    /** 点击行号命中：和 c1 书库 LibraryRenderer.rowAt 同一个套路。 */
    private int rowAt(int y) {
        int top = rowsTop();
        if (y < top) return -1;
        int idx = (y - top) / ROW_H;
        return idx >= 0 && idx < Math.min(tasks.size(), MAX_ROWS) ? idx : -1;
    }

    /** 只重绘某一行区域（DU|RECT 下脏矩形更小，省电更多）。 */
    public void invalidateRow(int idx) {
        int top = rowsTop() + idx * ROW_H;
        invalidate(0, top - 20, getWidth(), top + ROW_H + 20);
    }

    public int pushCount() { return pushCount; }

    /** 引导气泡文案：按完成进度给一句"手势/节奏"提示（控制在 14 字内不溢出）。 */
    private String hintText() {
        int d = done(), total = tasks.size();
        if (total == 0) return "轻点右侧任务即可完成 ✓";
        if (d == 0)    return "点右侧任务，一件件来 →";
        if (d >= total) return "今天都完成了，早点休息 ✓";
        return "已完成 " + d + "/" + total + "，继续加油 →";
    }

    private int done() {
        int n = 0;
        for (Task t : tasks) if (t.done) n++;
        return n;
    }
    private int remaining() {
        int n = 0;
        for (Task t : tasks) if (!t.done) n++;
        return n;
    }
}
