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
import socket
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
DAEMON_LOG_PATTERNS = ["[widget]", "[render]", "[transfer]", "[frame]", "[action]", "[wifi]"]
DEVICE_LOG_PATTERNS = ["[rx]", "[frame]", "[display]", "[touch]"]


def _check(status: str, name: str, detail: str = "", next_step: str = "") -> bool:
    line = f"[diagnose] {status} {name}"
    if detail:
        line += f": {detail}"
    print(line)
    if status == "FAIL" and next_step:
        print(f"[diagnose] next: {next_step}")
    return status != "FAIL"


def build_advice(profile: dict, *, root: str = ROOT,
                 port: str | None = None,
                 transport: str | None = None,
                 host: str | None = None,
                 wifi_port: int | None = None,
                 http_host: str | None = None) -> dict:
    daemon_transport = transport or ("serial" if profile["name"] == "paper-s3" else "auto")
    return {
        "build_command": card_cli.platformio_command(profile, "build", root=root),
        "upload_command": card_cli.platformio_command(profile, "upload", root=root, port=port),
        "monitor_command": card_cli.platformio_command(profile, "monitor", root=root, port=port),
        "daemon_command": card_cli.daemon_command(
            profile,
            root=root,
            transport=daemon_transport,
            port=port,
            host=host,
            wifi_port=wifi_port,
            http_host=http_host,
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


def _first_present(*values):
    for value in values:
        if value is not None and value != "":
            return value
    return None


def build_power_section(profile: dict, *,
                        frame_status: dict | None = None,
                        device_status: dict | None = None) -> dict:
    frame_status = frame_status or {}
    device_status = device_status or {}
    profile_power = profile.get("power") or {}
    frame_power = frame_status.get("power") or {}
    device_power = device_status.get("power") or {}
    deep_sleep = profile_power.get("deep_sleep") or {}
    ble = profile_power.get("ble") or {}

    return {
        "power_mode": _first_present(
            frame_power.get("mode"),
            device_power.get("mode"),
            device_status.get("power_mode"),
            profile_power.get("default_mode"),
            "always-on",
        ),
        "supported_modes": list(profile_power.get("supported_modes") or ["always-on"]),
        "idle_timeout_minutes": int(profile_power.get("idle_timeout_minutes") or 0),
        "power_source": _first_present(
            frame_power.get("power_source"),
            device_power.get("source"),
            device_status.get("power_source"),
            "unknown",
        ),
        "battery_pct": _first_present(
            frame_power.get("battery_pct"),
            device_power.get("battery_pct"),
            device_status.get("battery_pct"),
        ),
        "battery_mv": _first_present(
            frame_power.get("battery_mv"),
            device_power.get("battery_mv"),
            device_status.get("battery_mv"),
        ),
        "vbus_mv": _first_present(
            frame_power.get("vbus_mv"),
            device_power.get("vbus_mv"),
            device_status.get("vbus_mv"),
        ),
        "on_usb": _first_present(
            frame_power.get("on_usb"),
            device_power.get("on_usb"),
            device_status.get("on_usb"),
        ),
        "charging": _first_present(
            frame_power.get("charging"),
            device_power.get("charging"),
            device_status.get("charging"),
        ),
        "deep_sleep_enabled": bool(deep_sleep.get("enabled")),
        "deep_sleep_status": str(deep_sleep.get("status") or "unsupported"),
        "ble_status": str(ble.get("status") or "unsupported"),
        "wake_sources": list(profile_power.get("wake_sources") or []),
        "last_wake_reason": _first_present(
            frame_power.get("last_wake_reason"),
            device_power.get("wake_reason"),
            device_status.get("wake_reason"),
            "unknown",
        ),
        "last_wake_recovery": _first_present(
            frame_power.get("last_wake_recovery"),
            profile_power.get("wake_recovery"),
            "unknown",
        ),
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


def _tcp_reachable(host: str, port: int, timeout: float = 2.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "tcp connect ok"
    except OSError as exc:
        return False, str(exc)


def _device_status(host: str, port: int) -> tuple[int, dict]:
    url = f"http://{host}:{port}/status"
    try:
        with urllib.request.urlopen(url, timeout=4) as res:
            return res.status, json.loads(res.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, {"error": str(exc)}
    except Exception as exc:
        return 0, {"error": str(exc)}


def run(args: argparse.Namespace) -> int:
    profile = card_profiles.get_profile(args.profile)
    advice = build_advice(
        profile,
        port=args.port,
        transport=args.transport,
        host=args.host,
        wifi_port=args.wifi_port,
        http_host=args.http_host,
    )
    ok = True

    print(f"[diagnose] selected profile={profile['name']}")
    print(f"[diagnose] device={profile['device_name']}")
    print(f"[diagnose] preferred transport={profile['preferred_transport']}")
    print(f"[diagnose] render={profile['logical_width']}x{profile['logical_height']} {profile['display_format']}")
    _check("PASS", "python", sys.version.split()[0])

    pio = card_cli.platformio_executable(ROOT)
    print(f"[diagnose] PlatformIO command={pio}")
    if pio == "pio":
        print("[diagnose] if this fails, use the project venv or install PlatformIO Core CLI")
    if not _platformio_env_exists(profile["platformio_env"]):
        ok = _check("FAIL", "platformio env",
                    f"missing env={profile['platformio_env']}",
                    "check platformio.ini or rerun from the repo root") and ok
    else:
        _check("PASS", "platformio env", profile["platformio_env"])

    ports = card_cli.list_serial_ports()
    print(f"[diagnose] serial ports={ports or 'none detected'}")
    if profile["name"] == "paper-s3" and not (args.port or ports):
        _check("WARN", "serial port",
               "PaperS3 serial fallback/provisioning usually needs COM3",
               "PowerShell: [System.IO.Ports.SerialPort]::GetPortNames()")
    elif ports or args.port:
        _check("PASS", "serial port", args.port or ", ".join(ports))

    device_status_payload = {}
    if profile["name"] == "paper-s3":
        if args.transport == "wifi":
            if not args.host:
                ok = _check("FAIL", "PaperS3 Wi-Fi host",
                            "missing --host <PaperS3-IP>",
                            "read the IP from serial logs or the status card") and ok
            else:
                port = int(args.wifi_port or 9880)
                reachable, detail = _tcp_reachable(args.host, port)
                ok = _check("PASS" if reachable else "FAIL",
                            "PaperS3 host/port",
                            f"{args.host}:{port} {detail}",
                            "check IP, LAN, firewall, and --wifi-port") and ok
                code, device_status = _device_status(args.host, port)
                if code == 200:
                    device_status_payload = device_status
                    wifi = device_status.get("wifi") or {}
                    _check("PASS", "firmware /status",
                           f"wifi={wifi.get('state')} ip={wifi.get('ip')} rssi={wifi.get('rssi')} error={wifi.get('last_error') or 'none'}")
                else:
                    ok = _check("FAIL", "firmware /status",
                                device_status.get("error", f"HTTP {code}"),
                                "copy PaperS3 [http] and [wifi] logs") and ok
        else:
            _check("WARN", "PaperS3 Wi-Fi transport",
                   "diagnose is not using --transport wifi",
                   "after provisioning, rerun with --transport wifi --host <PaperS3-IP> --wifi-port 9880 --http-host 0.0.0.0")

    ok = _run_check("firmware build", advice["build_command"], run=not args.skip_build) and ok

    daemon_url = args.daemon_url.rstrip("/")
    code, pair = _request_json("GET", daemon_url, "/pair-status")
    if code != 200:
        ok = _check("FAIL", "daemon reachable",
                    f"{daemon_url}: {pair.get('error', pair)}",
                    f"start daemon: {card_cli.format_command(advice['daemon_command'])}") and ok
    else:
        _check("PASS", "daemon reachable",
               f"connected={pair.get('connected')} transport={pair.get('transport')}")
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
            if frame.get("wifi_error"):
                _check("WARN", "latest Wi-Fi error", str(frame.get("wifi_error")))
            if frame.get("error"):
                _check("WARN", "latest frame error", str(frame.get("error")))
            power = build_power_section(
                profile,
                frame_status=frame,
                device_status=device_status_payload,
            )
            print("[diagnose] power:")
            print(f"[diagnose]   mode={power['power_mode']} source={power['power_source']} "
                  f"on_usb={power['on_usb']} charging={power['charging']}")
            print(f"[diagnose]   battery_pct={power['battery_pct']} "
                  f"battery_mv={power['battery_mv']} vbus_mv={power['vbus_mv']}")
            print(f"[diagnose]   deep_sleep={power['deep_sleep_status']} "
                  f"enabled={power['deep_sleep_enabled']} ble={power['ble_status']}")
            print(f"[diagnose]   wake_reason={power['last_wake_reason']} "
                  f"wake_sources={','.join(power['wake_sources']) or 'none'}")
        if args.send_test and pair.get("connected"):
            demo = card_cli.demo_command(profile, args.test_widget)
            ok = _run_check(f"send {args.test_widget} card", demo, run=True) and ok
        elif args.send_test:
            print("[diagnose] skip send test because daemon is not connected to a device")
            ok = False

    print("[diagnose] diagnostic summary:")
    print(f"[diagnose]   profile={profile['name']} transport={args.transport or 'default'} host={args.host or ''} wifi_port={args.wifi_port or 9880} http_host={args.http_host or 'default'}")
    print("[diagnose]   copy daemon log lines containing: " + ", ".join(DAEMON_LOG_PATTERNS))
    print("[diagnose]   copy PaperS3 serial lines containing: " + ", ".join(DEVICE_LOG_PATTERNS + ["[wifi]", "[http]", "[mdns]"]))
    return 0 if ok else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose an ai-desk-card device/profile.")
    parser.add_argument("--profile", required=True, choices=card_profiles.profile_choices())
    parser.add_argument("--port")
    parser.add_argument("--transport", choices=("auto", "serial", "ble", "wifi"))
    parser.add_argument("--host")
    parser.add_argument("--wifi-port", type=int)
    parser.add_argument("--http-host")
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
