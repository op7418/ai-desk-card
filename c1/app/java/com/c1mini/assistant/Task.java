package com.c1mini.assistant;

/** 一条待办。done 划线 / doing 三角 / 其余方框，TaskView 据此绘制。 */
final class Task {
    final String text, due, tag;
    boolean done, doing;

    /** demo 用：只有 doing 状态。 */
    Task(String text, String due, boolean doing) {
        this.text = text; this.due = due; this.tag = "";
        this.doing = doing; this.done = false;
    }

    /** daemon 用：done/completed → ✓；doing/in_progress → ▶；其余 □。 */
    Task(String text, String due, String tag, String status) {
        this.text = text; this.due = due; this.tag = tag;
        this.done = "done".equalsIgnoreCase(status)
                || "completed".equalsIgnoreCase(status);
        this.doing = !this.done && ("doing".equalsIgnoreCase(status)
                || "in_progress".equalsIgnoreCase(status));
    }
}
