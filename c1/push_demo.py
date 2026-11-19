#!/usr/bin/env python3
"""模拟 AI Agent 推任务到 C1 助理的数据桥。

等价于骨架 agent skill 的 `POST /widget {slot,type,data}`，只是额外带了一个
C1 用的可选字段 items[].status（done/doing/todo）——bridge 不校验 schema，
APK 会把它映射成划线(✓)/进行中(▶)/待办(□)。不带 status 也正常显示。

用法：
    python3 push_demo.py                          # 推内置示例到 127.0.0.1:9877
    python3 push_demo.py --daemon http://192.168.1.5:9877
    echo '{"slot":"bottom","type":"todo","data":{...}}' | python3 push_demo.py --stdin
    python3 push_demo.py --clear                  # 清空全部 widget
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

SAMPLE = {
    "slot": "bottom",
    "type": "todo",
    "data": {
        "title": "未来 3 天",
        "items": [
            {"text": "审阅 Q4 架构方案", "due": "今天 14:00",
             "tag": "today", "status": "doing"},
            {"text": "回复设计评审意见", "due": "今天 17:30",
             "tag": "today", "status": "todo"},
            {"text": "整理墨水屏调研笔记", "tag": "this-week", "status": "todo"},
            {"text": "预约周五的体检", "due": "本周五",
             "tag": "this-week", "status": "done"},
        ],
    },
    "theme": "",
}


def request(url: str, method: str, obj=None):
    data = None
    headers = {}
    if obj is not None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def main():
    ap = argparse.ArgumentParser(description="push todo widget to C1 bridge")
    ap.add_argument("--daemon", default="http://127.0.0.1:9877",
                    help="bridge base url (default http://127.0.0.1:9877)")
    ap.add_argument("--stdin", action="store_true",
                    help="read widget JSON from stdin instead of built-in sample")
    ap.add_argument("--clear", action="store_true", help="clear all widgets")
    ap.add_argument("--complete", metavar="TEXT",
                    help="push sample again with one item's status set to done")
    args = ap.parse_args()

    base = args.daemon.rstrip("/")
    if args.clear:
        print(json.dumps(request(base + "/widget", "DELETE"), ensure_ascii=False))
        return

    if args.stdin:
        payload = json.load(sys.stdin)
    else:
        payload = json.loads(json.dumps(SAMPLE))
        if args.complete:
            hit = False
            for it in payload["data"]["items"]:
                if args.complete in it["text"]:
                    it["status"] = "done"
                    hit = True
            if not hit:
                print(f"[warn] no item matched {args.complete!r}", file=sys.stderr)

    reply = request(base + "/widget", "POST", payload)
    print(json.dumps(reply, ensure_ascii=False))
    print(f"→ C1 will refresh only if todo content signature changed "
          f"(rev={reply.get('rev')})")


if __name__ == "__main__":
    main()
