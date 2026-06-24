#!/usr/bin/env python3
"""Push a Codex AI status card from local, explicit usage data.

This script intentionally avoids reading Codex auth tokens or private ChatGPT
endpoints. Provide real quota values via environment variables or a local JSON
file, then it pushes an ai-status widget through the existing daemon API.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

DEFAULT_DAEMON_URL = os.environ.get("CARD_DAEMON_URL", "http://127.0.0.1:9877")
DEFAULT_STATE_FILE = os.path.expanduser(r"~\.codex\ai-desk-card-usage.json")
APP_SERVER_TIMEOUT_S = 20.0


def _read_json(path: str) -> dict:
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _first(env: dict, *names: str) -> str:
    for name in names:
        value = env.get(name)
        if value:
            return str(value)
    return ""


def _clean_status_line(line: str) -> str:
    return line.strip().strip("│").strip()


def _compact_reset(reset: str) -> str:
    reset = reset.strip()
    match = re.fullmatch(r"(\d{1,2}:\d{2})\s+on\s+(.+)", reset)
    if match:
        return f"{match.group(2)} {match.group(1)}"
    return reset


def _parse_limit_line(line: str, label: str) -> tuple[str, str]:
    pattern = rf"\b{re.escape(label)}\s+limit:\s*(?:\[[^\]]+\]\s*)?(.*)"
    match = re.search(pattern, line, flags=re.IGNORECASE)
    if not match:
        return "", ""
    rest = match.group(1).strip()
    rest = re.sub(r"\s*│\s*$", "", rest).strip()

    remaining = ""
    remaining_match = re.search(r"(\d+%\s+left)", rest, flags=re.IGNORECASE)
    if remaining_match:
        remaining = remaining_match.group(1)

    reset = ""
    reset_match = re.search(r"\(resets\s+([^)]+)\)", rest, flags=re.IGNORECASE)
    if reset_match:
        reset = _compact_reset(reset_match.group(1))
    return remaining, reset


def parse_status_text(text: str) -> dict:
    """Parse the human-readable Codex /status block copied from CLI or app."""
    usage = {}
    five_hour_reset = ""
    weekly_reset = ""
    for raw_line in text.splitlines():
        line = _clean_status_line(raw_line)
        model_match = re.search(r"\bModel:\s*([^\s(│]+)", line)
        if model_match:
            usage["model"] = model_match.group(1)

        remaining, reset = _parse_limit_line(line, "5h")
        if remaining:
            usage["five_hour_remaining"] = remaining
        if reset:
            five_hour_reset = reset

        remaining, reset = _parse_limit_line(line, "Weekly")
        if remaining:
            usage["weekly_remaining"] = remaining
        if reset:
            weekly_reset = reset

    reset_parts = []
    if five_hour_reset:
        reset_parts.append(f"5h {five_hour_reset}")
    if weekly_reset:
        reset_parts.append(f"wk {weekly_reset}")
    if reset_parts:
        usage["reset_hint"] = " / ".join(reset_parts)
    return usage


def _local_time(timestamp: int | None) -> datetime | None:
    if not timestamp:
        return None
    try:
        return datetime.fromtimestamp(int(timestamp))
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def _format_reset(timestamp: int | None, *, weekly: bool = False) -> str:
    dt = _local_time(timestamp)
    if not dt:
        return ""
    return dt.strftime("%d %b %H:%M") if weekly else dt.strftime("%H:%M")


def _remaining_text(window: dict | None) -> str:
    if not isinstance(window, dict):
        return ""
    used = window.get("usedPercent")
    if used is None:
        return ""
    try:
        remaining = max(0, min(100, 100 - int(used)))
    except (TypeError, ValueError):
        return ""
    return f"{remaining}% left"


def rate_limits_to_usage(rate_limits: dict, model: str = "") -> dict:
    primary = rate_limits.get("primary") if isinstance(rate_limits, dict) else {}
    secondary = rate_limits.get("secondary") if isinstance(rate_limits, dict) else {}
    usage = {}
    if model:
        usage["model"] = model

    five_hour = _remaining_text(primary)
    weekly = _remaining_text(secondary)
    if five_hour:
        usage["five_hour_remaining"] = five_hour
    if weekly:
        usage["weekly_remaining"] = weekly

    reset_parts = []
    reset_5h = _format_reset(primary.get("resetsAt") if isinstance(primary, dict) else None)
    reset_weekly = _format_reset(
        secondary.get("resetsAt") if isinstance(secondary, dict) else None,
        weekly=True,
    )
    if reset_5h:
        reset_parts.append(f"5h {reset_5h}")
    if reset_weekly:
        reset_parts.append(f"wk {reset_weekly}")
    if reset_parts:
        usage["reset_hint"] = " / ".join(reset_parts)
    return usage


def _codex_app_server_command() -> list[str]:
    if os.name == "nt":
        powershell = os.path.join(
            os.environ.get("SystemRoot", r"C:\WINDOWS"),
            "System32",
            "WindowsPowerShell",
            "v1.0",
            "powershell.exe",
        )
        return [powershell, "-NoProfile", "-Command", "codex app-server --stdio"]
    return ["codex", "app-server", "--stdio"]


def _read_app_server_stdout(proc, out_queue: queue.Queue) -> None:
    for line in proc.stdout:
        out_queue.put(line.rstrip("\n"))


def _drain_stream(stream, sink: list[str]) -> None:
    for line in stream:
        sink.append(line)


def app_server_request(methods: list[tuple[int, str, object]], timeout_s: float = APP_SERVER_TIMEOUT_S) -> dict[int, dict]:
    """Run a short-lived Codex app-server stdio session and return responses."""
    proc = subprocess.Popen(
        _codex_app_server_command(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    out_queue: queue.Queue = queue.Queue()
    stderr_lines: list[str] = []
    threading.Thread(target=_read_app_server_stdout, args=(proc, out_queue), daemon=True).start()
    threading.Thread(target=_drain_stream, args=(proc.stderr, stderr_lines), daemon=True).start()

    def send(message: dict) -> None:
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()

    try:
        send({
            "id": 1,
            "method": "initialize",
            "params": {
                "clientInfo": {
                    "name": "ai-desk-card",
                    "title": "AI Desk Card",
                    "version": "0.8",
                },
                "capabilities": {"experimentalApi": True},
            },
        })
        send({"method": "initialized", "params": {}})
        wanted = {1}
        for req_id, method, params in methods:
            send({"id": req_id, "method": method, "params": params})
            wanted.add(req_id)

        responses: dict[int, dict] = {}
        deadline = time.time() + timeout_s
        while time.time() < deadline and not wanted.issubset(responses):
            try:
                line = out_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" not in message:
                continue
            responses[message["id"]] = message
        missing = wanted - set(responses)
        if missing:
            tail = "".join(stderr_lines[-5:]).strip()
            detail = f" missing response id(s): {sorted(missing)}"
            if tail:
                detail += f"; stderr: {tail[:500]}"
            raise RuntimeError(detail)
        return responses
    finally:
        try:
            proc.kill()
        except Exception:
            pass


def load_app_server_usage(cwd: str | None = None) -> dict:
    responses = app_server_request([
        (2, "account/rateLimits/read", None),
        (3, "config/read", {"cwd": cwd or os.getcwd(), "includeLayers": False}),
    ])
    rate_response = responses.get(2, {})
    config_response = responses.get(3, {})
    if "error" in rate_response:
        raise RuntimeError(rate_response["error"].get("message", rate_response["error"]))

    config = ((config_response.get("result") or {}).get("config") or {})
    model = config.get("model") or ""
    rate_result = rate_response.get("result") or {}
    rate_limits = rate_result.get("rateLimits") or {}
    return rate_limits_to_usage(rate_limits, model=model)


def load_usage(state_file: str = DEFAULT_STATE_FILE, env: dict | None = None) -> dict:
    """Load usage data from JSON, then override with explicit env vars."""
    env = env if env is not None else os.environ
    state = _read_json(state_file)
    nested_usage = state.get("usage") if isinstance(state.get("usage"), dict) else {}

    usage = {
        "model": state.get("model") or state.get("codex_model") or "",
        "five_hour_remaining": (
            state.get("five_hour_remaining")
            or state.get("five_h_remaining")
            or nested_usage.get("five_hour_remaining")
            or nested_usage.get("five_h_remaining")
            or ""
        ),
        "weekly_remaining": (
            state.get("weekly_remaining")
            or nested_usage.get("weekly_remaining")
            or ""
        ),
        "reset_hint": state.get("reset_hint") or nested_usage.get("reset_hint") or "",
    }

    env_model = _first(env, "CODEX_MODEL", "CODEX_AI_MODEL")
    env_5h = _first(env, "CODEX_5H_REMAINING", "CODEX_FIVE_HOUR_REMAINING")
    env_weekly = _first(env, "CODEX_WEEKLY_REMAINING")
    env_reset = _first(env, "CODEX_USAGE_RESET_HINT")
    if env_model:
        usage["model"] = env_model
    if env_5h:
        usage["five_hour_remaining"] = env_5h
    if env_weekly:
        usage["weekly_remaining"] = env_weekly
    if env_reset:
        usage["reset_hint"] = env_reset

    return {k: v for k, v in usage.items() if v}


def has_quota(usage: dict) -> bool:
    return bool(usage.get("five_hour_remaining") or usage.get("weekly_remaining"))


def build_payload(*, slot: str, session_name: str, task: str, usage: dict) -> dict:
    usage_payload = {}
    for key in ("five_hour_remaining", "weekly_remaining", "reset_hint"):
        if usage.get(key):
            usage_payload[key] = usage[key]

    return {
        "type": "ai-status",
        "slot": slot,
        "data": {
            "session_name": session_name,
            "model": usage.get("model", "Codex"),
            "task": task,
            "usage": usage_payload,
        },
    }


def request_json(method: str, daemon_url: str, path: str,
                 payload: dict | None = None, timeout: float = 4.0) -> tuple[int, dict]:
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        daemon_url.rstrip("/") + path,
        data=body,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8") or "{}"
            return res.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, {"error": str(exc)}
    except urllib.error.URLError as exc:
        return 0, {"error": f"daemon unreachable: {exc.reason}"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Push a Codex model + 5h/weekly usage ai-status card."
    )
    parser.add_argument("--daemon-url", default=DEFAULT_DAEMON_URL)
    parser.add_argument("--state-file", default=DEFAULT_STATE_FILE)
    parser.add_argument("--slot", default="top-right",
                        choices=("top-left", "top-right", "middle", "bottom", "full"))
    parser.add_argument("--session-name", default="")
    parser.add_argument("--task", default="Codex usage remaining")
    parser.add_argument("--model", default="")
    parser.add_argument("--five-hour-remaining", default="")
    parser.add_argument("--weekly-remaining", default="")
    parser.add_argument("--reset-hint", default="")
    parser.add_argument("--source", choices=("auto", "app-server", "local"),
                        default="auto",
                        help="auto/app-server reads real Codex quota through codex app-server; local uses env/JSON/status text only.")
    parser.add_argument("--status-text-file", default="",
                        help="Parse a copied Codex /status block from this text file.")
    parser.add_argument("--status-stdin", action="store_true",
                        help="Read a copied Codex /status block from stdin.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    usage = {}
    if args.source in ("auto", "app-server"):
        try:
            usage.update(load_app_server_usage())
            print("[codex-ai-status] source=app-server")
        except Exception as exc:
            if args.source == "app-server":
                print(f"[codex-ai-status] app-server read failed: {exc}", file=sys.stderr)
                return 1
            print(f"[codex-ai-status] app-server unavailable, falling back to local sources: {exc}", file=sys.stderr)

    local_usage = load_usage(args.state_file)
    usage.update({k: v for k, v in local_usage.items() if v})
    status_text = ""
    if args.status_text_file:
        with open(args.status_text_file, "r", encoding="utf-8") as f:
            status_text = f.read()
    if args.status_stdin:
        status_text = sys.stdin.read()
    if status_text:
        usage.update(parse_status_text(status_text))
    if args.model:
        usage["model"] = args.model
    if args.five_hour_remaining:
        usage["five_hour_remaining"] = args.five_hour_remaining
    if args.weekly_remaining:
        usage["weekly_remaining"] = args.weekly_remaining
    if args.reset_hint:
        usage["reset_hint"] = args.reset_hint

    if not has_quota(usage):
        print("[codex-ai-status] no 5h/weekly usage value found", file=sys.stderr)
        print("[codex-ai-status] set CODEX_5H_REMAINING and/or CODEX_WEEKLY_REMAINING", file=sys.stderr)
        print(f"[codex-ai-status] or create JSON: {args.state_file}", file=sys.stderr)
        return 1

    session_name = args.session_name or "codex"
    payload = build_payload(
        slot=args.slot,
        session_name=session_name,
        task=args.task,
        usage=usage,
    )
    print(f"[codex-ai-status] model={payload['data'].get('model')}")
    print(f"[codex-ai-status] 5h={payload['data']['usage'].get('five_hour_remaining', '')}")
    print(f"[codex-ai-status] weekly={payload['data']['usage'].get('weekly_remaining', '')}")
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    code, body = request_json("POST", args.daemon_url, "/widget", payload)
    print(json.dumps(body, ensure_ascii=False))
    if code < 200 or code >= 300:
        print(f"[codex-ai-status] push failed HTTP={code}", file=sys.stderr)
        return 2 if code == 0 else 3
    print("[codex-ai-status] success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
