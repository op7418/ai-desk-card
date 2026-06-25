#!/usr/bin/env python3
"""Push a Claude Code AI status card from Claude statusline quota data.

Claude Code exposes Claude.ai Pro/Max rate limits to statusline commands via
stdin JSON. This helper reads the small cache written by
claude_statusline_sink.py and pushes it as an existing ai-status widget.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_DAEMON_URL = os.environ.get("CARD_DAEMON_URL", "http://127.0.0.1:9877")
DEFAULT_STATE_FILE = os.path.expanduser(r"~\.claude\ai-desk-card-usage.json")


def _read_json(path: str) -> dict:
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _write_json(path: str, data: dict) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _first(env: dict, *names: str) -> str:
    for name in names:
        value = env.get(name)
        if value:
            return str(value)
    return ""


def _local_time(timestamp: int | float | None) -> datetime | None:
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(float(timestamp))
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def _format_reset(timestamp: int | float | None, *, weekly: bool = False) -> str:
    dt = _local_time(timestamp)
    if not dt:
        return ""
    return dt.strftime("%d %b %H:%M") if weekly else dt.strftime("%H:%M")


def _remaining_text(window: dict | None) -> str:
    if not isinstance(window, dict):
        return ""
    used = (
        window.get("used_percentage")
        if window.get("used_percentage") is not None
        else window.get("usedPercent")
    )
    if used is None:
        return ""
    try:
        remaining = int(round(100 - float(used)))
    except (TypeError, ValueError):
        return ""
    remaining = max(0, min(100, remaining))
    return f"{remaining}% left"


def _model_name(statusline: dict) -> str:
    model = statusline.get("model")
    if isinstance(model, dict):
        return str(model.get("display_name") or model.get("name") or model.get("id") or "")
    if isinstance(model, str):
        return model
    return ""


def parse_statusline_json(text: str) -> dict:
    if not text.strip():
        raise ValueError("empty Claude statusline JSON")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Claude statusline JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Claude statusline JSON must be an object")
    return data


def statusline_to_usage(statusline: dict) -> dict:
    """Convert Claude Code statusline JSON into ai-status usage fields."""
    usage = {}
    model = _model_name(statusline)
    if model:
        usage["model"] = model
    if statusline.get("session_name"):
        usage["session_name"] = str(statusline["session_name"])

    rate_limits = statusline.get("rate_limits") if isinstance(statusline, dict) else {}
    if not isinstance(rate_limits, dict):
        return usage

    five_hour = rate_limits.get("five_hour") or rate_limits.get("fiveHour") or {}
    seven_day = (
        rate_limits.get("seven_day")
        or rate_limits.get("sevenDay")
        or rate_limits.get("weekly")
        or {}
    )

    five_hour_text = _remaining_text(five_hour)
    weekly_text = _remaining_text(seven_day)
    if five_hour_text:
        usage["five_hour_remaining"] = five_hour_text
    if weekly_text:
        usage["weekly_remaining"] = weekly_text

    reset_parts = []
    reset_5h = _format_reset(five_hour.get("resets_at") if isinstance(five_hour, dict) else None)
    reset_weekly = _format_reset(
        seven_day.get("resets_at") if isinstance(seven_day, dict) else None,
        weekly=True,
    )
    if reset_5h:
        reset_parts.append(f"5h {reset_5h}")
    if reset_weekly:
        reset_parts.append(f"wk {reset_weekly}")
    if reset_parts:
        usage["reset_hint"] = " / ".join(reset_parts)
    return usage


def write_usage_cache(statusline: dict, state_file: str = DEFAULT_STATE_FILE) -> dict:
    usage = statusline_to_usage(statusline)
    cached = {
        "source": "claude-statusline",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "model": usage.get("model", ""),
        "session_name": usage.get("session_name", "Claude Code"),
        "usage": {
            key: usage[key]
            for key in ("five_hour_remaining", "weekly_remaining", "reset_hint")
            if usage.get(key)
        },
    }
    _write_json(state_file, cached)
    return usage


def load_usage(state_file: str = DEFAULT_STATE_FILE, env: dict | None = None) -> dict:
    env = env if env is not None else os.environ
    state = _read_json(state_file)
    nested_usage = state.get("usage") if isinstance(state.get("usage"), dict) else {}

    usage = {
        "model": state.get("model") or "",
        "session_name": state.get("session_name") or "",
        "five_hour_remaining": nested_usage.get("five_hour_remaining") or "",
        "weekly_remaining": nested_usage.get("weekly_remaining") or "",
        "reset_hint": nested_usage.get("reset_hint") or "",
    }

    env_model = _first(env, "CLAUDE_MODEL", "CLAUDE_AI_MODEL")
    env_5h = _first(env, "CLAUDE_5H_REMAINING", "CLAUDE_FIVE_HOUR_REMAINING")
    env_weekly = _first(env, "CLAUDE_WEEKLY_REMAINING", "CLAUDE_7D_REMAINING")
    env_reset = _first(env, "CLAUDE_USAGE_RESET_HINT")
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


def build_payload(*, slot: str, task: str, usage: dict) -> dict:
    usage_payload = {}
    for key in ("five_hour_remaining", "weekly_remaining", "reset_hint"):
        if usage.get(key):
            usage_payload[key] = usage[key]

    return {
        "type": "ai-status",
        "slot": slot,
        "data": {
            "session_name": usage.get("session_name", "Claude Code"),
            "model": usage.get("model", "Claude"),
            "task": task,
            "usage": usage_payload,
        },
    }


def format_statusline(usage: dict) -> str:
    model = usage.get("model") or "Claude"
    parts = [model]
    if usage.get("five_hour_remaining"):
        parts.append(f"5h {usage['five_hour_remaining']}")
    if usage.get("weekly_remaining"):
        parts.append(f"wk {usage['weekly_remaining']}")
    if len(parts) == 1:
        parts.append("quota pending")
    return " | ".join(parts)


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
        description="Push Claude Code model + 5h/weekly usage as an ai-status card."
    )
    parser.add_argument("--daemon-url", default=DEFAULT_DAEMON_URL)
    parser.add_argument("--state-file", default=DEFAULT_STATE_FILE)
    parser.add_argument("--slot", default="top-right",
                        choices=("top-left", "top-right", "middle", "bottom", "full"))
    parser.add_argument("--task", default="Claude usage remaining")
    parser.add_argument("--model", default="")
    parser.add_argument("--five-hour-remaining", default="")
    parser.add_argument("--weekly-remaining", default="")
    parser.add_argument("--reset-hint", default="")
    parser.add_argument("--statusline-file", default="",
                        help="Read Claude Code statusline JSON from this file and update the cache first.")
    parser.add_argument("--statusline-stdin", action="store_true",
                        help="Read Claude Code statusline JSON from stdin and update the cache first.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    usage = load_usage(args.state_file)
    statusline_text = ""
    if args.statusline_file:
        with open(args.statusline_file, "r", encoding="utf-8") as f:
            statusline_text = f.read()
    if args.statusline_stdin:
        statusline_text = sys.stdin.read()
    if statusline_text:
        try:
            statusline = parse_statusline_json(statusline_text)
        except ValueError as exc:
            print(f"[claude-ai-status] {exc}", file=sys.stderr)
            return 1
        usage.update(write_usage_cache(statusline, args.state_file))
    if args.model:
        usage["model"] = args.model
    if args.five_hour_remaining:
        usage["five_hour_remaining"] = args.five_hour_remaining
    if args.weekly_remaining:
        usage["weekly_remaining"] = args.weekly_remaining
    if args.reset_hint:
        usage["reset_hint"] = args.reset_hint

    if not has_quota(usage):
        print("[claude-ai-status] no 5h/weekly usage value found", file=sys.stderr)
        print("[claude-ai-status] configure Claude Code statusLine to run scripts\\claude_statusline_sink.py", file=sys.stderr)
        print("[claude-ai-status] rate_limits appears only after a Claude.ai Pro/Max session receives a response", file=sys.stderr)
        return 1

    payload = build_payload(slot=args.slot, task=args.task, usage=usage)
    print(f"[claude-ai-status] model={payload['data'].get('model')}")
    print(f"[claude-ai-status] 5h={payload['data']['usage'].get('five_hour_remaining', '')}")
    print(f"[claude-ai-status] weekly={payload['data']['usage'].get('weekly_remaining', '')}")
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    code, body = request_json("POST", args.daemon_url, "/widget", payload)
    print(json.dumps(body, ensure_ascii=False))
    if code < 200 or code >= 300:
        print(f"[claude-ai-status] push failed HTTP={code}", file=sys.stderr)
        return 2 if code == 0 else 3
    print("[claude-ai-status] success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
