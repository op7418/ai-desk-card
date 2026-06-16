#!/usr/bin/env python3
"""Phase 5 PaperS3 widget demo helper.

This script talks to the existing daemon HTTP API. The daemon owns the
PaperS3 serial connection and pushes the rendered 540x960 4bpp frame.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import card_profiles

DEFAULT_DAEMON_URL = os.environ.get("CARD_DAEMON_URL", "http://127.0.0.1:9877")
WIDGET_CHOICES = (
    "text",
    "status",
    "weather-mock",
    "calendar-mock",
    "todo-mock",
    "ai-status",
    "dashboard",
)


def _hhmm(now_iso: str) -> str:
    return now_iso[11:16] if len(now_iso) >= 16 else now_iso


def _sample_payload(widget: str, slot: str, now_iso: str) -> dict:
    hhmm = _hhmm(now_iso)
    if widget == "text":
        return {
            "slot": slot,
            "type": "scratch",
            "data": {
                "title": "PaperS3 Text",
                "source": "demo",
                "age": hhmm,
                "text": (
                    "PaperS3 real widget demo\n"
                    "Multiline text wraps through the existing scratch renderer."
                ),
            },
        }
    if widget == "weather-mock":
        return {
            "slot": slot,
            "type": "weather",
            "data": {
                "location": "Desk",
                "current": {"temp_c": 24, "condition": "Sample"},
                "forecast": [
                    {"day": "Today", "high": 26, "low": 18, "condition": "Dry"},
                    {"day": "Tue", "high": 27, "low": 19, "condition": "Clouds"},
                ],
            },
        }
    if widget == "calendar-mock":
        return {
            "slot": slot,
            "type": "calendar",
            "data": {
                "now_iso": now_iso,
                "events": [
                    {"start": "09:30", "title": "PaperS3 demo check"},
                    {"start": "14:00", "end": "14:30", "title": "Widget refresh path"},
                    {"start": "17:30", "title": "Review serial logs"},
                ],
            },
        }
    if widget == "todo-mock":
        return {
            "slot": slot,
            "type": "todo",
            "data": {
                "title": "Phase 5",
                "items": [
                    {"text": "Show real text/status cards", "tag": "today"},
                    {"text": "Mock weather/calendar/todo without API keys", "tag": "today"},
                    {"text": "Tap Refresh, Status, Back, Home", "tag": "this-week"},
                ],
            },
        }
    if widget == "ai-status":
        return {
            "slot": slot,
            "type": "ai-status",
            "data": {
                "session_name": "PaperS3",
                "model": "GPT-5 Codex",
                "task": "PaperS3 dashboard demo",
                "usage": {
                    "five_hour_remaining": "3h 20m",
                    "weekly_remaining": "72%",
                },
                "elapsed_seconds": 900,
                "last_message_preview": "Rendering real daemon widgets to PaperS3.",
            },
        }
    raise ValueError(f"unknown sample widget {widget!r}")


def build_demo_selection(widget: str, now_iso: str | None = None) -> dict:
    now_iso = now_iso or datetime.now().replace(microsecond=0).isoformat()
    if widget == "status":
        return {"action": "status", "payloads": []}
    if widget == "dashboard":
        return {
            "action": "widgets",
            "payloads": [
                _sample_payload("weather-mock", "top-left", now_iso),
                _sample_payload("ai-status", "top-right", now_iso),
                _sample_payload("calendar-mock", "middle", now_iso),
                _sample_payload("todo-mock", "bottom", now_iso),
            ],
        }
    return {"action": "widgets", "payloads": [_sample_payload(widget, "full", now_iso)]}


def _request_json(method: str, daemon_url: str, path: str,
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


def frame_status_is_complete(before: dict, current: dict) -> bool:
    try:
        before_id = int(before.get("render_id") or 0)
        current_id = int(current.get("render_id") or 0)
    except (TypeError, ValueError):
        return False
    if current_id <= before_id:
        return False
    if current.get("in_progress"):
        return False
    return current.get("result") in {"ok", "noop", "failed"}


def _wait_for_frame(daemon_url: str, before: dict,
                    timeout_s: float, poll_s: float) -> dict:
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        code, status = _request_json("GET", daemon_url, "/frame-status", timeout=4)
        if code == 200:
            last = status
            if frame_status_is_complete(before, status):
                return status
        else:
            last = {"result": "failed", "error": status.get("error", f"HTTP {code}")}
        time.sleep(poll_s)
    last.setdefault("result", "failed")
    last.setdefault("error", f"timed out after {timeout_s:.1f}s waiting for frame")
    return last


def _print_frame_summary(status: dict) -> None:
    output = status.get("output") or {}
    transfer = status.get("transfer") or {}
    print(f"[demo] render result={status.get('result')} profile={status.get('selected_profile')} "
          f"view={status.get('selected_view')} widgets={status.get('selected_widgets')}")
    print(f"[demo] output width={output.get('width')} height={output.get('height')} "
          f"format={output.get('format')}")
    print(f"[demo] transfer method={transfer.get('method')} target={transfer.get('target')} "
          f"bytes={transfer.get('bytes')}")
    if status.get("error"):
        print(f"[demo] error reason={status.get('error')}")


def _resolve_profile(profile_name: str, pair_status: dict, frame_status: dict) -> dict | None:
    if profile_name != "auto":
        return card_profiles.get_profile(profile_name)
    for status in (frame_status, pair_status):
        if status.get("profile_source") == "default":
            continue
        detected = card_profiles.detect_profile_from_status(status)
        if detected:
            return card_profiles.get_profile(detected)
    return None


def _ensure_widget_view(daemon_url: str, before: dict,
                        timeout_s: float, poll_s: float) -> dict:
    if before.get("selected_view") != "status":
        return before

    print("[demo] leave status page before posting widget demo")
    code, body = _request_json("POST", daemon_url, "/back", {})
    if code < 200 or code >= 300:
        raise RuntimeError(f"back request failed: {body}")
    status = _wait_for_frame(daemon_url, before, timeout_s, poll_s)
    if status.get("result") not in {"ok", "noop"}:
        raise RuntimeError(f"back request did not complete cleanly: {status}")
    return status


def run(args: argparse.Namespace) -> int:
    daemon_url = args.daemon_url.rstrip("/")
    selection = build_demo_selection(args.widget)

    print(f"[demo] requested profile={args.profile}")
    print(f"[demo] selected widget={args.widget}")
    print(f"[demo] daemon={daemon_url}")

    code, pair = _request_json("GET", daemon_url, "/pair-status")
    if code != 200:
        print(f"[demo] daemon check failed: {pair.get('error', pair)}")
        print("[demo] start daemon first, then copy daemon stderr and PaperS3 serial logs if this repeats")
        return 2
    print(f"[demo] daemon connected={pair.get('connected')} transport={pair.get('transport')}")

    code, before = _request_json("GET", daemon_url, "/frame-status")
    if code != 200:
        before = {"render_id": 0}

    try:
        profile = _resolve_profile(args.profile, pair, before)
    except KeyError as exc:
        print(f"[demo] profile error: {exc}")
        return 2
    if profile is None:
        print("[demo] could not auto-detect profile; rerun with --profile paper-s3 or --profile m5paper-v1.1")
        return 2

    print(f"[demo] selected profile={profile['name']} device={profile['device_name']}")
    print(f"[demo] selected transport={pair.get('transport')} preferred={profile['preferred_transport']}")
    print(f"[demo] render width={profile['logical_width']} height={profile['logical_height']} "
          f"format={profile['display_format']}")

    detected = card_profiles.detect_profile_from_status(before) or card_profiles.detect_profile_from_status(pair)
    if args.profile != "auto" and detected and detected != profile["name"]:
        print(f"[demo] warning profile mismatch requested={profile['name']} daemon={detected}")

    if not pair.get("connected"):
        print(f"[demo] no {profile['device_name']} connection through daemon; close serial monitor and start daemon with --profile {profile['name']} --transport serial --port COM3")
        return 2

    if selection["action"] == "status":
        print("[demo] request status/settings page via existing /settings action")
        code, body = _request_json("POST", daemon_url, "/settings", {})
        if code < 200 or code >= 300:
            print(f"[demo] status request failed: {body}")
            return 3
    else:
        try:
            before = _ensure_widget_view(daemon_url, before, args.timeout, args.poll)
        except RuntimeError as exc:
            print(f"[demo] widget view setup failed: {exc}")
            return 3
        if not args.no_clear:
            print("[demo] clear existing widgets before demo")
            _request_json("DELETE", daemon_url, "/widget")
        for payload in selection["payloads"]:
            print(f"[demo] post widget type={payload['type']} slot={payload['slot']}")
            code, body = _request_json("POST", daemon_url, "/widget", payload)
            if code < 200 or code >= 300:
                print(f"[demo] widget post failed: {body}")
                return 3

    print(f"[demo] waiting for render/transfer up to {args.timeout:.1f}s")
    status = _wait_for_frame(daemon_url, before, args.timeout, args.poll)
    _print_frame_summary(status)
    if status.get("result") not in {"ok", "noop"}:
        print("[demo] copy these logs for debugging:")
        print("[demo] daemon: lines containing [widget], [render], [transfer], [frame], [action]")
        print("[demo] device: PaperS3 serial lines containing [rx], [frame], [display], [touch]")
        return 4
    print("[demo] success")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Push Phase 5 PaperS3 demo widgets through the daemon.")
    parser.add_argument("--daemon-url", default=DEFAULT_DAEMON_URL)
    parser.add_argument("--profile", default="paper-s3")
    parser.add_argument("--widget", default="dashboard", choices=WIDGET_CHOICES)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--poll", type=float, default=0.5)
    parser.add_argument("--no-clear", action="store_true")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
