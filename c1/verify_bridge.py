#!/usr/bin/env python3
"""端到端验证：bridge 数据模型 + APK 侧解析/签名逻辑（无需真机）。

起一个临时 bridge（随机高端口、不落盘），走一遍：
  空快照 → POST → GET → 同内容再 POST → 改内容 POST → DELETE
并用与 AssistantActivity.parseFeed() 等价的 Python 逻辑解析每次快照，
验证：
  1. todo widget 被正确抽成任务列表，tag→中文 due 映射正确
  2. status=done/doing 标记正确，非 todo widget 被忽略
  3. 内容相同时签名不变 → APK 零刷屏（省电核心）
  4. 内容变化时签名改变 → APK 才走 DU|RECT 局刷
  5. rev 每次写递增，DELETE 清空
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = 19877
BASE = f"http://127.0.0.1:{PORT}"
HERE = os.path.dirname(os.path.abspath(__file__))

TAG_LABEL = {
    "today": "今天", "tomorrow": "明天", "this-week": "本周",
    "overdue": "已逾期", "later": "稍后",
}


def req(path: str, method: str = "GET", obj=None):
    data = None
    headers = {}
    if obj is not None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(r, timeout=4) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def apk_parse(widgets: list):
    """与 AssistantActivity.parseFeed() 等价的解析 + 签名。"""
    tasks, sig = [], ""
    for w in widgets:
        if w.get("type") != "todo":
            continue
        data = w.get("data") or {}
        sig += w.get("slot", "") + "|" + json.dumps(data, sort_keys=True, ensure_ascii=False)
        for it in data.get("items") or []:
            text = (it.get("text") or "").strip()
            if not text:
                continue
            due = it.get("due") or ""
            tag = it.get("tag") or ""
            if not due and tag:
                due = TAG_LABEL.get(tag, "")
            status = (it.get("status") or "").lower()
            tasks.append({
                "text": text, "due": due,
                "done": status in ("done", "completed"),
                "doing": (not status in ("done", "completed"))
                         and status in ("doing", "in_progress"),
            })
    return sig, tasks


TODO = {
    "slot": "bottom", "type": "todo",
    "data": {"title": "未来 3 天", "items": [
        {"text": "审阅 Q4 架构方案", "due": "今天 14:00", "tag": "today", "status": "doing"},
        {"text": "回复设计评审意见", "tag": "today", "status": "todo"},
        {"text": "整理墨水屏调研笔记", "tag": "this-week", "status": "done"},
    ]},
}
NOISE = {"slot": "top-left", "type": "calendar", "data": {"events": []}}


def check(cond: bool, label: str):
    mark = "OK " if cond else "FAIL"
    print(f"  [{mark}] {label}")
    if not cond:
        raise AssertionError(label)


def main():
    proc = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "bridge.py"),
         "--port", str(PORT), "--no-persist"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # 等 daemon 就绪
        for _ in range(50):
            try:
                req("/health")
                break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.1)
        else:
            raise RuntimeError("bridge failed to start")

        print("\n=== 1. 空快照 ===")
        snap = req("/widget")
        check(snap["rev"] == 0 and snap["widgets"] == [], "rev=0, widgets=[]")

        print("\n=== 2. Agent POST todo + 非 todo 噪声 ===")
        r1 = req("/widget", "POST", TODO)
        r2 = req("/widget", "POST", NOISE)
        check(r1["rev"] == 1 and r2["rev"] == 2, "写入两次 rev 递增到 2")
        snap = req("/widget")
        sig1, tasks = apk_parse(snap["widgets"])
        check(len(snap["widgets"]) == 2, "两个 widget 都在快照里")
        check(len(tasks) == 3, "APK 只抽 todo → 3 项（calendar 被忽略）")
        check(tasks[0]["text"] == "审阅 Q4 架构方案", "text 映射正确")
        check(tasks[0]["doing"] and not tasks[0]["done"], "status=doing → ▶")
        check(tasks[1]["due"] == "今天", "无 due 时 tag=today → 中文「今天」")
        check(tasks[2]["done"] and not tasks[2]["doing"], "status=done → ✓")

        print("\n=== 3. 同内容再 POST（C1 应零刷屏）===")
        req("/widget", "POST", TODO)
        snap = req("/widget")
        sig2, _ = apk_parse(snap["widgets"])
        check(snap["rev"] == 3, "rev 递增到 3")
        check(sig1 == sig2, "内容签名不变 → APK 不 invalidate（省电）")

        print("\n=== 4. 其他 widget 变化（C1 仍应零刷屏）===")
        changed_noise = dict(NOISE, data={"events": [{"start": "10:00"}]})
        req("/widget", "POST", changed_noise)
        snap = req("/widget")
        sig3, _ = apk_parse(snap["widgets"])
        check(snap["rev"] == 4, "rev 递增到 4")
        check(sig1 == sig3, "非 todo 变化不进签名 → APK 仍不刷任务区")

        print("\n=== 5. todo 内容变化（C1 才局刷）===")
        changed = json.loads(json.dumps(TODO))
        changed["data"]["items"][0]["status"] = "done"
        req("/widget", "POST", changed)
        snap = req("/widget")
        sig4, tasks2 = apk_parse(snap["widgets"])
        check(snap["rev"] == 5, "rev 递增到 5")
        check(sig1 != sig4, "签名改变 → APK 触发 DU|RECT 局刷")
        check(tasks2[0]["done"], "进度推进映射为 done → 划线")

        print("\n=== 6. DELETE 清空 ===")
        d = req("/widget", "DELETE")
        snap = req("/widget")
        check(d["removed"] and snap["rev"] == 6, "DELETE 生效，rev=6")
        check(snap["widgets"] == [], "快照清空（APK 保留最后一帧，不清屏）")

        print("\n全部通过：数据链路 + 零刷屏判定 + 局刷触发条件均符合设计。\n")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
