#!/usr/bin/env python3
"""Collect a redacted PaperS3 Wi-Fi diagnostic report."""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import card_cli
import card_profiles


DEFAULT_DAEMON_URL = os.environ.get("CARD_DAEMON_URL", "http://127.0.0.1:9877")
DEFAULT_WIFI_PORT = 9880
SENSITIVE_KEY_PARTS = ("password", "token", "secret", "api_key", "private_key")


def mask_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    return text[:3] + "***"


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    return any(part in lower for part in SENSITIVE_KEY_PARTS)


def _redact(value: Any, key: str = "") -> Any:
    if _is_sensitive_key(key):
        return "[redacted]"
    if key.lower() == "ssid":
        return mask_value(value)
    if isinstance(value, dict):
        return {k: _redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _scalar(value: Any, default: str = "unknown") -> str:
    if value is None or value == "":
        return default
    return str(value)


def _json_block(value: Any) -> list[str]:
    redacted = _redact(value)
    text = json.dumps(redacted, indent=2, sort_keys=True, ensure_ascii=False)
    return ["```json", text, "```"]


def _wifi_from_status(status: dict[str, Any]) -> dict[str, Any]:
    wifi = status.get("wifi")
    if isinstance(wifi, dict):
        return wifi
    return status


def build_report(data: dict[str, Any]) -> str:
    profile = _scalar(data.get("profile"), "paper-s3")
    transport = _scalar(data.get("transport"), "wifi")
    host = _scalar(data.get("host"), "")
    wifi_status = _wifi_from_status(data.get("wifi_status") or data.get("device_status") or {})
    daemon = data.get("daemon") or {}
    frame = data.get("frame") or {}
    tools = data.get("tools") or {}

    lines = [
        "# PaperS3 Wi-Fi Diagnostic Report",
        "",
        "## Summary",
        f"- git commit: {_scalar(data.get('git'))}",
        f"- selected profile: {profile}",
        f"- selected transport: {transport}",
        f"- PaperS3 host: {host}",
        f"- Wi-Fi port: {_scalar(data.get('wifi_port'), str(DEFAULT_WIFI_PORT))}",
        f"- daemon URL: {_scalar(data.get('daemon_url'), DEFAULT_DAEMON_URL)}",
        "",
        "## Wi-Fi",
        f"- state: {_scalar(wifi_status.get('state') or wifi_status.get('wifi_state'))}",
        f"- ssid: {mask_value(wifi_status.get('ssid') or wifi_status.get('wifi_ssid'))}",
        f"- ip: {_scalar(wifi_status.get('ip') or wifi_status.get('wifi_ip'))}",
        f"- rssi: {_scalar(wifi_status.get('rssi') or wifi_status.get('wifi_rssi'))}",
        f"- last_error: {_scalar(wifi_status.get('last_error') or wifi_status.get('error') or wifi_status.get('wifi_error'), 'none')}",
        "",
        "## Daemon",
        f"- pair connected: {_scalar((daemon.get('pair_status') or {}).get('connected'))}",
        f"- pair transport: {_scalar((daemon.get('pair_status') or {}).get('transport'))}",
        f"- heartbeat state: {_scalar((daemon.get('heartbeat') or {}).get('state'))}",
        "",
        "## Frame",
        f"- last frame result: {_scalar(frame.get('result'))}",
        f"- selected profile: {_scalar(frame.get('selected_profile'))}",
        f"- selected view: {_scalar(frame.get('selected_view'))}",
        f"- transfer method: {_scalar((frame.get('transfer') or {}).get('method'))}",
        f"- transfer target: {_scalar((frame.get('transfer') or {}).get('target'))}",
        f"- transfer bytes: {_scalar((frame.get('transfer') or {}).get('bytes'))}",
        f"- error: {_scalar(frame.get('error') or frame.get('wifi_error'), 'none')}",
        "",
        "## Local Tools",
        f"- OS: {_scalar(tools.get('os'))}",
        f"- Python: {_scalar(tools.get('python'))}",
        f"- PlatformIO: {_scalar(tools.get('platformio'))}",
        f"- serial ports: {_scalar(', '.join(tools.get('serial_ports') or []), 'none detected')}",
    ]

    raw_sections = {
        "PaperS3 /status": data.get("device_status"),
        "daemon /pair-status": daemon.get("pair_status"),
        "daemon /frame-status": frame,
        "daemon /heartbeat": daemon.get("heartbeat"),
    }
    for title, value in raw_sections.items():
        if value:
            lines.extend(["", f"## Raw {title}", *_json_block(value)])

    return "\n".join(lines).rstrip() + "\n"


def _run_text(cmd: list[str], timeout: float = 5.0) -> str:
    try:
        result = subprocess.run(
            cmd,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return f"unavailable: {exc}"
    text = (result.stdout or result.stderr).strip()
    return text or f"exit {result.returncode}"


def _request_json(url: str, timeout: float = 4.0) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            raw = res.read().decode("utf-8") or "{}"
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        try:
            return {"error": json.loads(exc.read().decode("utf-8"))}
        except Exception:
            return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}


def collect(args: argparse.Namespace) -> dict[str, Any]:
    profile = card_profiles.get_profile(args.profile)
    daemon_url = args.daemon_url.rstrip("/")
    tools = {
        "os": f"{platform.system()} {platform.release()}",
        "python": sys.version.split()[0],
        "platformio": _run_text([card_cli.platformio_executable(ROOT), "--version"]),
        "serial_ports": card_cli.list_serial_ports(),
    }
    data: dict[str, Any] = {
        "git": _run_text(["git", "rev-parse", "--short", "HEAD"]),
        "profile": profile["name"],
        "transport": args.transport,
        "host": args.host or "",
        "wifi_port": args.wifi_port,
        "daemon_url": daemon_url,
        "tools": tools,
        "daemon": {
            "pair_status": _request_json(daemon_url + "/pair-status"),
            "heartbeat": _request_json(daemon_url + "/heartbeat"),
        },
        "frame": _request_json(daemon_url + "/frame-status"),
    }
    if args.host:
        data["device_status"] = _request_json(f"http://{args.host}:{args.wifi_port}/status")
        data["wifi_status"] = data["device_status"]
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect a redacted PaperS3 Wi-Fi diagnostic report.")
    parser.add_argument("--profile", default="paper-s3", choices=card_profiles.profile_choices())
    parser.add_argument("--transport", default="wifi", choices=("auto", "serial", "ble", "wifi"))
    parser.add_argument("--host")
    parser.add_argument("--wifi-port", type=int, default=DEFAULT_WIFI_PORT)
    parser.add_argument("--daemon-url", default=DEFAULT_DAEMON_URL)
    args = parser.parse_args(argv)
    print(build_report(collect(args)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
