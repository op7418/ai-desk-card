#!/usr/bin/env python3
"""Push a dashboard built from the user's configured interests."""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


DEFAULT_DAEMON_URL = os.environ.get("CARD_DAEMON_URL", "http://127.0.0.1:9877")
SLOT_ORDER = ("top-left", "top-right", "middle", "bottom")
KNOWN_WEATHER_COORDS = {
    "上海徐汇": (31.1885, 121.4365),
}
WEATHER_CODES = {
    0: "clear",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "rime fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    80: "rain showers",
    81: "rain showers",
    82: "heavy showers",
    95: "thunderstorm",
}


def default_interests_path() -> str:
    return str(Path.home() / ".ai-desk-card" / "interests.yaml")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return value


def _load_interests(path: str | None) -> dict:
    interests_path = Path(path or default_interests_path()).expanduser()
    if not interests_path.exists():
        raise SystemExit(f"interests file not found: {interests_path}")

    result = {"slots": {}, "data_sources": {}}
    section = None
    source = None
    for raw in interests_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line:
            continue
        if not raw.startswith(" "):
            key = line.rstrip(":")
            section = key if key in {"slots", "data_sources"} else None
            source = None
            continue
        if section == "slots" and line.startswith("  ") and ":" in line:
            slot, widget = [part.strip() for part in line.split(":", 1)]
            result["slots"][slot] = _unquote(widget)
            continue
        if section == "data_sources":
            if raw.startswith("  ") and not raw.startswith("    ") and line.endswith(":"):
                source = line.rstrip(":").strip()
                result["data_sources"].setdefault(source, {})
            elif raw.startswith("    ") and source and ":" in line:
                key, value = [part.strip() for part in line.split(":", 1)]
                result["data_sources"][source][key] = _unquote(value)
    return result


def _weather_payload(slot: str, sources: dict, *, require_live: bool = False) -> dict | None:
    weather = sources.get("weather") or {}
    city = weather.get("city") or "Unknown"
    live = _open_meteo_weather(city)
    if live:
        return {
            "slot": slot,
            "type": "weather",
            "data": live,
        }
    if require_live:
        return None
    return {
        "slot": slot,
        "type": "weather",
        "data": {
            "location": city[:20],
            "current": {"condition": "Location set"},
            "forecast": [],
        },
    }


def _weather_condition(code) -> str:
    try:
        return WEATHER_CODES.get(int(code), f"weather {code}")
    except (TypeError, ValueError):
        return ""


def _open_meteo_weather(city: str) -> dict | None:
    coords = KNOWN_WEATHER_COORDS.get(city)
    if not coords:
        return None
    latitude, longitude = coords
    params = urllib.parse.urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code",
        "timezone": "Asia/Shanghai",
        "forecast_days": 2,
    })
    url = f"https://api.open-meteo.com/v1/forecast?{params}"
    try:
        with urllib.request.urlopen(url, timeout=20) as res:
            data = json.loads(res.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None

    current = data.get("current") or {}
    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    codes = daily.get("weather_code") or []

    forecast = []
    for index, day in enumerate(dates[:2]):
        forecast.append({
            "day": "today" if index == 0 else day[5:],
            "high": round(highs[index]) if index < len(highs) and highs[index] is not None else "-",
            "low": round(lows[index]) if index < len(lows) and lows[index] is not None else "-",
            "condition": _weather_condition(codes[index] if index < len(codes) else None),
        })

    return {
        "location": city[:20],
        "current": {
            "temp_c": round(current["temperature_2m"]) if current.get("temperature_2m") is not None else None,
            "condition": _weather_condition(current.get("weather_code")),
        },
        "forecast": forecast,
    }


def _calendar_payload(slot: str, sources: dict, now_iso: str) -> dict:
    source = (sources.get("calendar") or {}).get("source") or "calendar"
    return {
        "slot": slot,
        "type": "calendar",
        "data": {
            "now_iso": now_iso,
            "events": [
                {"start": "", "title": f"Source: {source}"[:48]},
            ],
        },
    }


def _todo_payload(slot: str, sources: dict) -> dict:
    source = (sources.get("todo") or {}).get("source") or "todo"
    return {
        "slot": slot,
        "type": "todo",
        "data": {
            "title": source[:28],
            "items": [],
        },
    }


def _load_codex_usage() -> dict:
    try:
        import push_codex_ai_status as codex
        usage = codex.load_app_server_usage()
    except Exception:
        return {}
    return usage if codex.has_quota(usage) else {}


def _ai_status_payload(slot: str, sources: dict, codex_usage: dict | None = None,
                       *, require_live: bool = False) -> dict | None:
    source = (sources.get("ai-status") or {}).get("source") or "codex"
    if source == "codex" and codex_usage:
        import push_codex_ai_status as codex
        return codex.build_payload(
            slot=slot,
            session_name="codex",
            task="Codex usage remaining",
            usage=codex_usage,
        )
    if require_live and source == "codex":
        return None
    return {
        "slot": slot,
        "type": "ai-status",
        "data": {
            "session_name": source[:28],
            "task": f"AI status source: {source}"[:60],
        },
    }


def _scratch_payload(slot: str, widget: str) -> dict:
    return {
        "slot": slot,
        "type": "scratch",
        "data": {
            "title": widget[:28],
            "source": "configured",
            "age": "now",
            "text": f"{widget} is selected for this slot.",
        },
    }


def build_payloads(interests_path: str | None = None,
                   now_iso: str | None = None,
                   codex_usage_loader=None,
                   only_widgets: set[str] | None = None,
                   require_live: bool = False) -> list[dict]:
    config = _load_interests(interests_path)
    slots = config["slots"]
    sources = config["data_sources"]
    now_iso = now_iso or datetime.now().replace(microsecond=0).isoformat()
    codex_usage = codex_usage_loader() if codex_usage_loader else None

    payloads = []
    for slot in SLOT_ORDER:
        widget = slots.get(slot)
        if not widget:
            continue
        if only_widgets and widget not in only_widgets:
            continue
        if widget == "weather":
            payload = _weather_payload(slot, sources, require_live=require_live)
        elif widget == "calendar":
            payload = _calendar_payload(slot, sources, now_iso)
        elif widget == "todo":
            payload = _todo_payload(slot, sources)
        elif widget == "ai-status":
            payload = _ai_status_payload(slot, sources, codex_usage, require_live=require_live)
        else:
            payload = _scratch_payload(slot, widget)
        if payload:
            payloads.append(payload)
    return payloads


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


def _ensure_widget_view(daemon_url: str, before: dict,
                        timeout_s: float, poll_s: float) -> dict:
    if before.get("selected_view") != "status":
        return before

    print("[dashboard] leave status page before posting configured widgets")
    code, body = _request_json("POST", daemon_url, "/back", {})
    if code < 200 or code >= 300:
        raise RuntimeError(f"back request failed: {body}")
    status = _wait_for_frame(daemon_url, before, timeout_s, poll_s)
    if status.get("result") not in {"ok", "noop"}:
        raise RuntimeError(f"back request did not complete cleanly: {status}")
    return status


def run(args: argparse.Namespace) -> int:
    daemon_url = args.daemon_url.rstrip("/")
    only_widgets = _parse_only_widgets(args.only)
    payloads = build_payloads(
        args.interests,
        codex_usage_loader=_load_codex_usage,
        only_widgets=only_widgets,
        require_live=bool(only_widgets),
    )
    if only_widgets:
        args.no_clear = True

    print(f"[dashboard] daemon={daemon_url}")
    print(f"[dashboard] interests={Path(args.interests).expanduser()}")
    for payload in payloads:
        print(f"[dashboard] configured widget type={payload['type']} slot={payload['slot']}")
    if not payloads:
        print("[dashboard] no live widget data; leaving current card unchanged")
        return 0

    if args.dry_run:
        print(json.dumps(payloads, ensure_ascii=False, indent=2))
        return 0

    code, pair = _request_json("GET", daemon_url, "/pair-status")
    if code != 200 or not pair.get("connected"):
        heartbeat_code, heartbeat = _request_json("GET", daemon_url, "/heartbeat")
        if heartbeat_code != 200 or not heartbeat.get("alive"):
            print(f"[dashboard] daemon/device not connected: {pair}")
            return 2
        print("[dashboard] pair-status disconnected but heartbeat is alive; attempting refresh")

    code, before = _request_json("GET", daemon_url, "/frame-status")
    if code != 200:
        before = {"render_id": 0}

    try:
        before = _ensure_widget_view(daemon_url, before, args.timeout, args.poll)
    except RuntimeError as exc:
        print(f"[dashboard] widget view setup failed: {exc}")
        return 3

    if not args.no_clear:
        _request_json("DELETE", daemon_url, "/widget")
    for payload in payloads:
        code, body = _request_json("POST", daemon_url, "/widget", payload)
        if code < 200 or code >= 300:
            print(f"[dashboard] widget post failed: {body}")
            return 3

    status = _wait_for_frame(daemon_url, before, args.timeout, args.poll)
    transfer = status.get("transfer") or {}
    print(
        f"[dashboard] render result={status.get('result')} "
        f"profile={status.get('selected_profile')} "
        f"widgets={status.get('selected_widgets')}"
    )
    print(
        f"[dashboard] transfer method={transfer.get('method')} "
        f"target={transfer.get('target')} bytes={transfer.get('bytes')}"
    )
    if status.get("result") not in {"ok", "noop"}:
        print(f"[dashboard] error={status.get('error') or status}")
        return 4
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Push a dashboard from interests.yaml.")
    parser.add_argument("--daemon-url", default=DEFAULT_DAEMON_URL)
    parser.add_argument("--interests", default=default_interests_path())
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--poll", type=float, default=0.5)
    parser.add_argument("--only", default="", help="Comma-separated widget types to update, e.g. weather,ai-status.")
    parser.add_argument("--no-clear", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _parse_only_widgets(value: str) -> set[str] | None:
    widgets = {part.strip() for part in value.split(",") if part.strip()}
    return widgets or None


def main(argv: list[str] | None = None) -> int:
    return run(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
