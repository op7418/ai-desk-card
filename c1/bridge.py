#!/usr/bin/env python3
"""C1 桌面助理 —— 轻量 widget 数据桥。

它替换 ai-desk-card 的 color_daemon.py / card_daemon.py 作为 C1 的数据源：
那两个 daemon 是给 M5Paper 推 RGB565 像素帧的（600x400、peer 白名单、
绑 --device-ip），C1 有自己的原生渲染与 DU|RECT 局刷，只需要 JSON 数据。

数据模型完全沿用骨架，AI Agent 侧 skill 无需改动：
    POST /widget   body {slot, type, data, theme?}   ← agent 推
    GET  /widget   → {widgets: [...], rev: N}        ← C1 拉
    GET  /status   → {daemon, rev, widget_count, ...}
    DELETE /widget [?slot=xxx]                       ← 清空 / 删单个

与骨架的关键差异：
  * 监听 0.0.0.0，同网段 C1 可访问（骨架绑 127.0.0.1 只给本机 agent）。
  * 不 render、不 push 像素帧、不限制 peer —— C1 自己画。
  * 每次写递增 rev，C1 轮询时 rev 不变就完全不刷屏（省电关键）。
  * 状态落盘 JSON，daemon 重启后任务不丢。

安全：无鉴权，仅用于可信局域网。要挂公网请在前面加反向代理 + token。

运行：
    python3 bridge.py                            # 0.0.0.0:9877
    python3 bridge.py --port 9881 --no-persist
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))

# slot -> {type, data, theme, written_at}
WIDGET_CACHE: dict = {}
LOCK = threading.Lock()
REV = 0
START_TS = time.time()
STATE_PATH = ""
MAX_BODY = 64 * 1024


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_state(path: str):
    """启动时恢复缓存与 rev；文件不存在/损坏就当空缓存启动。"""
    global WIDGET_CACHE, REV
    if not path or not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            st = json.load(f)
        with LOCK:
            WIDGET_CACHE = st.get("widgets") or {}
            REV = int(st.get("rev") or 0)
        log(f"[state] loaded {len(WIDGET_CACHE)} widgets, rev={REV} from {path}")
    except Exception as e:
        log(f"[state] load failed ({e!r}), starting empty")


def save_state():
    """调用方必须已持 LOCK。tmp+replace 保证原子写，防半截文件。"""
    if not STATE_PATH:
        return
    try:
        payload = json.dumps(
            {"rev": REV, "widgets": WIDGET_CACHE},
            ensure_ascii=False, indent=2).encode("utf-8")
        d = os.path.dirname(STATE_PATH) or "."
        fd, tmp = tempfile.mkstemp(prefix=".c1bridge-", dir=d)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
            os.replace(tmp, STATE_PATH)
        except Exception:
            try: os.unlink(tmp)
            except OSError: pass
            raise
    except Exception as e:
        log(f"[state] save failed: {e!r}")


def snapshot():
    with LOCK:
        widgets = [{"slot": s, **dict(v)}
                   for s, v in sorted(WIDGET_CACHE.items())]
        return widgets, REV


class Handler(BaseHTTPRequestHandler):
    # 局域网轮询问得频繁，关掉 access log 免刷屏
    def log_message(self, *args):
        pass

    def _reply(self, code: int, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or "0")
        if n > MAX_BODY:
            raise ValueError(f"body too large: {n} > {MAX_BODY}")
        raw = self.rfile.read(n) if n > 0 else b""
        return json.loads(raw.decode("utf-8")) if raw else {}

    def do_GET(self):
        global REV
        path = urlparse(self.path).path
        if path == "/widget":
            widgets, rev = snapshot()
            return self._reply(200, {"widgets": widgets, "rev": rev})
        if path == "/status":
            widgets, rev = snapshot()
            return self._reply(200, {
                "daemon": "c1-bridge/0.1.0",
                "rev": rev,
                "widget_count": len(widgets),
                "uptime_s": int(time.time() - START_TS),
                "state_path": STATE_PATH or None,
                "now": datetime.now().strftime("%H:%M:%S"),
            })
        if path == "/health":
            return self._reply(200, {"ok": True})
        return self._reply(404, {"error": f"unknown GET {path}"})

    def do_POST(self):
        global REV
        path = urlparse(self.path).path
        if path != "/widget":
            return self._reply(404, {"error": f"unknown POST {path}"})
        try:
            payload = self._read_json()
        except Exception as e:
            return self._reply(400, {"error": f"bad json: {e}"})

        slot = payload.get("slot")
        if not isinstance(slot, str) or not slot or len(slot) > 32:
            return self._reply(400, {"error": "slot must be 1..32 chars"})
        wtype = payload.get("type") or ""
        data = payload.get("data")
        if not isinstance(data, dict):
            return self._reply(400, {"error": "data must be an object"})

        with LOCK:
            WIDGET_CACHE[slot] = {
                "type": wtype,
                "data": data,
                "theme": payload.get("theme") or "",
                "written_at": time.time(),
            }
            REV += 1
            rev = REV
            save_state()
        log(f"[widget] {slot} <- {wtype}  rev={rev}")
        return self._reply(200, {"ok": True, "slot": slot,
                                 "type": wtype, "rev": rev})

    def do_DELETE(self):
        global REV
        path = urlparse(self.path).path
        if path != "/widget":
            return self._reply(404, {"error": f"unknown DELETE {path}"})
        slot = (parse_qs(urlparse(self.path).query).get("slot") or [None])[0]
        with LOCK:
            if slot:
                removed = WIDGET_CACHE.pop(slot, None) is not None
            else:
                removed = bool(WIDGET_CACHE)
                WIDGET_CACHE.clear()
            if removed:
                REV += 1
            rev = REV
            save_state()
        log(f"[widget] deleted {slot or 'all'}  rev={rev}")
        return self._reply(200, {"ok": True, "rev": rev, "removed": removed})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main():
    global STATE_PATH
    ap = argparse.ArgumentParser(description="C1 assistant widget bridge")
    ap.add_argument("--host", default="0.0.0.0",
                    help="bind address (default 0.0.0.0 so C1 on LAN can reach it)")
    ap.add_argument("--port", type=int, default=9877,
                    help="HTTP port (default 9877, same as upstream daemon)")
    ap.add_argument("--state", default=os.path.join(HERE, "widget_state.json"),
                    help="state file for widget cache + rev")
    ap.add_argument("--no-persist", action="store_true",
                    help="don't load/save state file")
    args = ap.parse_args()

    STATE_PATH = "" if args.no_persist else os.path.abspath(args.state)
    load_state(STATE_PATH)

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    log(f"[bridge] listening http://{args.host}:{args.port}  "
        f"persist={'off' if args.no_persist else STATE_PATH}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("[bridge] stopped")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
