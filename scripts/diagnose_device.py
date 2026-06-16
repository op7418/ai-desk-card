#!/usr/bin/env python3
"""Profile-aware ai-desk-card health check.

The script is safe to run from Windows PowerShell. It reads the shared device
profile config, checks local tooling and daemon status, and can send a small
demo/status card through the existing daemon API.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import card_cli
import card_profiles


DEFAULT_DAEMON_URL = os.environ.get("CARD_DAEMON_URL", "http://127.0.0.1:9877")
DAEMON_LOG_PATTERNS = ["[widget]", "[render]", "[transfer]", "[frame]", "[action]"]
DEVICE_LOG_PATTERNS = ["[rx]", "[frame]", "[display]", "[touch]"]


def build_advice(profile: dict, *, root: str = ROOT, port: str | None = None) -> dict:
    return {
        "build_command": card_cli.platformio_command(profile, "build", root=root),
        "upload_command": card_cli.platformio_command(profile, "upload", root=root, port=port),
        "monitor_command": card_cli.platformio_command(profile, "monitor", root=root, port=port),
        "daemon_command": card_cli.daemon_command(
            profile,
            root=root,
            transport="serial" if profile["name"] == "paper-s3" else "auto",
            port=port,
        ),
        "demo_status_command": card_cli.format_command(
            card_cli.demo_command(profile, "status", root=root)
        ),
        "demo_text_command": card_cli.format_command(
            card_cli.demo_command(profile, "text", root=root)
        ),
        "daemon_log_patterns": DAEMON_LOG_PATTERNS,
        "device_log_patterns": DEVICE_LOG_PATTERNS,
    }


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


def _platformio_env_exists(env_name: str, root: str = ROOT) -> bool:
    ini_path = os.path.join(root, "platformio.ini")
    if not os.path.exists(ini_path):
        return False
    marker = f"[env:{env_name}]"
    with open(ini_path, encoding="utf-8", errors="replace") as f:
        return any(line.strip() == marker for line in f)


def _run_check(name: str, cmd: list[str], *, run: bool) -> bool:
    print(f"[diagnose] {name}: {card_cli.format_command(cmd)}")
    if not run:
        print(f"[diagnose] {name}: skipped")
        return True
    try:
        result = subprocess.run(cmd, cwd=ROOT, check=False)
    except FileNotFoundError as exc:
        print(f"[diagnose] {name}: failed reason={exc}")
        return False
    ok = result.returncode == 0
    print(f"[diagnose] {name}: {'ok' if ok else 'failed'} code={result.returncode}")
    return ok


def run(args: argparse.Namespace) -> int:
    profile = card_profiles.get_profile(args.profile)
    advice = build_advice(profile, port=args.port)
    ok = True

    print(f"[diagnose] selected profile={profile['name']}")
    print(f"[diagnose] device={profile['device_name']}")
    print(f"[diagnose] preferred transport={profile['preferred_transport']}")
    print(f"[diagnose] render={profile['logical_width']}x{profile['logical_height']} {profile['display_format']}")

    pio = card_cli.platformio_executable(ROOT)
    print(f"[diagnose] PlatformIO command={pio}")
    if pio == "pio":
        print("[diagnose] if this fails, use the project venv or install PlatformIO Core CLI")
    if not _platformio_env_exists(profile["platformio_env"]):
        print(f"[diagnose] missing platformio env={profile['platformio_env']}")
        ok = False
    else:
        print(f"[diagnose] platformio env={profile['platformio_env']} found")

    ports = card_cli.list_serial_ports()
    print(f"[diagnose] serial ports={ports or 'none detected'}")
    if profile["name"] == "paper-s3" and not (args.port or ports):
        print("[diagnose] PaperS3 usually needs a COM port, for example --port COM3")
        print("[diagnose] PowerShell port check: [System.IO.Ports.SerialPort]::GetPortNames()")

    ok = _run_check("firmware build", advice["build_command"], run=not args.skip_build) and ok

    daemon_url = args.daemon_url.rstrip("/")
    code, pair = _request_json("GET", daemon_url, "/pair-status")
    if code != 200:
        print(f"[diagnose] daemon not reachable at {daemon_url}: {pair.get('error', pair)}")
        print(f"[diagnose] start daemon: {card_cli.format_command(advice['daemon_command'])}")
        ok = False
    else:
        print(f"[diagnose] daemon reachable connected={pair.get('connected')} transport={pair.get('transport')}")
        print(f"[diagnose] daemon selected_profile={pair.get('selected_profile')}")
        detected = card_profiles.detect_profile_from_status(pair)
        if detected and detected != profile["name"]:
            print(f"[diagnose] profile mismatch expected={profile['name']} daemon={detected}")
            ok = False
        code, frame = _request_json("GET", daemon_url, "/frame-status")
        if code == 200:
            transfer = frame.get("transfer") or {}
            print(f"[diagnose] last frame result={frame.get('result')} "
                  f"profile={frame.get('selected_profile')} "
                  f"method={transfer.get('method')} bytes={transfer.get('bytes')}")
        if args.send_test and pair.get("connected"):
            demo = card_cli.demo_command(profile, args.test_widget)
            ok = _run_check(f"send {args.test_widget} card", demo, run=True) and ok
        elif args.send_test:
            print("[diagnose] skip send test because daemon is not connected to a device")
            ok = False

    print("[diagnose] copy daemon log lines containing: " + ", ".join(DAEMON_LOG_PATTERNS))
    print("[diagnose] copy PaperS3 serial lines containing: " + ", ".join(DEVICE_LOG_PATTERNS))
    return 0 if ok else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose an ai-desk-card device/profile.")
    parser.add_argument("--profile", required=True, choices=card_profiles.profile_choices())
    parser.add_argument("--port")
    parser.add_argument("--daemon-url", default=DEFAULT_DAEMON_URL)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--send-test", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--test-widget", default="status", choices=(
        "status", "text", "weather-mock", "calendar-mock", "todo-mock", "ai-status", "dashboard",
    ))
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
