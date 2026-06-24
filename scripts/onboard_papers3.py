#!/usr/bin/env python3
"""PaperS3 first-run workflow wrapper.

This is intentionally a thin orchestrator around the commands that already
exist in the repo. It does not render dashboard frames itself; it starts the
daemon, delegates flow 04 setup to ``configure_interests.py`` and
``configure_profile.py``, then asks ``push_configured_dashboard.py`` to push a
first dashboard from those user settings.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
import tempfile
import time
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


def _log_step(message: str) -> None:
    print(f"[onboard] {message}", flush=True)


def _run_command(label: str, cmd: list[str], *,
                 dry_run: bool,
                 call=subprocess.call) -> int:
    _log_step(f"{label}: {card_cli.format_command(cmd)}")
    if dry_run:
        return 0
    return int(call(cmd, cwd=ROOT))


def _daemon_log_path(label: str, log_dir: str | None) -> str:
    base = log_dir or tempfile.gettempdir()
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"ai-desk-card-{label}.log")


def _start_daemon(label: str, cmd: list[str], *,
                  dry_run: bool,
                  log_dir: str | None,
                  popen=subprocess.Popen):
    log_path = _daemon_log_path(label, log_dir)
    _log_step(f"start {label} daemon: {card_cli.format_command(cmd)}")
    _log_step(f"{label} daemon log: {log_path}")
    if dry_run:
        return None
    log_file = open(log_path, "ab", buffering=0)
    kwargs = {
        "cwd": ROOT,
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        return popen(cmd, **kwargs)
    finally:
        log_file.close()


def _stop_daemon(proc, label: str) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    _log_step(f"stop {label} daemon")
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _wait_for_daemon(daemon_url: str, timeout_s: float, *,
                     request_json=_request_json,
                     sleep=time.sleep) -> dict:
    deadline = time.monotonic() + timeout_s
    last = {}
    while time.monotonic() < deadline:
        code, body = request_json("GET", daemon_url, "/pair-status")
        last = body
        if code == 200 and body.get("connected"):
            return body
        sleep(0.5)
    return last


def _wait_for_wifi_ip(daemon_url: str, timeout_s: float, *,
                      request_json=_request_json,
                      sleep=time.sleep) -> str | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for path in ("/heartbeat", "/frame-status"):
            code, body = request_json("GET", daemon_url, path)
            if code == 200 and body.get("wifi_ip"):
                return str(body["wifi_ip"])
        sleep(1.0)
    return None


def resolve_wifi_credentials(args: argparse.Namespace) -> tuple[str, str] | None:
    if args.no_wifi:
        return None
    ssid = (args.wifi_ssid or "").strip()
    if not ssid:
        if args.non_interactive:
            raise SystemExit("--wifi-ssid is required in --non-interactive mode")
        ssid = input("Wi-Fi SSID: ").strip()
    password = args.wifi_password
    if password is None and args.wifi_password_env:
        password = os.environ.get(args.wifi_password_env)
    if password is None:
        if args.non_interactive:
            raise SystemExit("--wifi-password or CARD_WIFI_PASSWORD is required in --non-interactive mode")
        password = getpass.getpass("Wi-Fi password: ")
    return ssid, password


def _prompt_optional(args: argparse.Namespace, attr: str, prompt: str) -> None:
    if getattr(args, attr):
        return
    if not sys.stdin.isatty():
        return
    try:
        value = input(prompt).strip()
    except EOFError:
        return
    if value:
        setattr(args, attr, value)


def resolve_flow04_inputs(args: argparse.Namespace) -> None:
    if not args.skip_interests and not args.city:
        if args.non_interactive:
            raise SystemExit("--city is required for PaperS3 onboard flow 04 weather setup")
        args.city = input("Weather location / city: ").strip()
        if not args.city:
            raise SystemExit("weather location is required for PaperS3 onboard flow 04")

    if args.skip_card_profile:
        return

    if not args.card_name:
        if args.non_interactive:
            raise SystemExit("--card-name is required for PaperS3 onboard flow 04 sleep-card setup")
        args.card_name = input("Sleep-card name: ").strip()
        if not args.card_name:
            raise SystemExit("sleep-card name is required for PaperS3 onboard flow 04")

    if args.city and not args.card_city:
        args.card_city = args.city

    if not args.non_interactive:
        _prompt_optional(args, "card_tagline", "Sleep-card tagline: ")
        _prompt_optional(args, "card_bio", "Sleep-card bio lines, separated by |: ")
        _prompt_optional(args, "card_city", "Sleep-card city tag: ")
        _prompt_optional(args, "card_link", "Sleep-card web/link tag: ")
        _prompt_optional(args, "card_qr_label", "Sleep-card QR label: ")
        _prompt_optional(args, "card_footer", "Sleep-card footer: ")


def _probe_current_state(daemon_url: str, request_json=_request_json) -> dict:
    ports = card_cli.list_serial_ports()
    state = {"ports": ports, "pair": {}, "heartbeat": {}}
    _log_step(f"serial ports={ports or 'none detected'}")
    code, pair = request_json("GET", daemon_url, "/pair-status")
    if code == 200:
        state["pair"] = pair
        _log_step(f"daemon connected={pair.get('connected')} transport={pair.get('transport')}")
    else:
        _log_step(f"daemon not reachable yet: {pair.get('error', pair)}")
    code, heartbeat = request_json("GET", daemon_url, "/heartbeat")
    if code == 200:
        state["heartbeat"] = heartbeat
        _log_step(
            "heartbeat "
            f"alive={heartbeat.get('alive')} "
            f"wifi_ip={heartbeat.get('wifi_ip')} "
            f"profile={heartbeat.get('selected_profile')}"
        )
    return state


def _profile() -> dict:
    return card_profiles.get_profile("paper-s3")


def run(args: argparse.Namespace, *,
        call=subprocess.call,
        popen=subprocess.Popen,
        request_json=_request_json,
        sleep=time.sleep) -> int:
    if args.profile != "paper-s3":
        raise SystemExit("PaperS3 onboarding requires --profile paper-s3")

    profile = _profile()
    daemon_url = args.daemon_url.rstrip("/")
    os.environ.setdefault("PLATFORMIO_CORE_DIR", ".pio-core")

    _log_step(f"profile={profile['name']} device={profile['device_name']}")
    _log_step("probe current state")
    state = _probe_current_state(daemon_url, request_json=request_json)

    if not args.skip_build:
        code = _run_command(
            "build firmware",
            card_cli.platformio_command(profile, "build", root=ROOT),
            dry_run=args.dry_run,
            call=call,
        )
        if code != 0:
            return code
    else:
        _log_step("build firmware: skipped")

    if not args.skip_upload:
        code = _run_command(
            "upload firmware",
            card_cli.platformio_command(profile, "upload", root=ROOT, port=args.port),
            dry_run=args.dry_run,
            call=call,
        )
        if code != 0:
            return code
    else:
        _log_step("upload firmware: skipped")

    _log_step("PaperS3 renders CJK on the host; M5Paper V1.1 uploadfs is not used for this profile")
    pair_state = state.get("pair") or {}
    heartbeat_state = state.get("heartbeat") or {}
    host = args.host or heartbeat_state.get("wifi_ip")
    existing_transport = str(pair_state.get("transport") or "")
    use_existing_wifi_daemon = bool(pair_state.get("connected") and host and "WiFi" in existing_transport)

    serial_proc = None
    if use_existing_wifi_daemon:
        _log_step(f"reuse existing Wi-Fi daemon host={host}")
    else:
        serial_proc = _start_daemon(
            "papers3-serial",
            card_cli.daemon_command(profile, root=ROOT, transport="serial", port=args.port),
            dry_run=args.dry_run,
            log_dir=args.log_dir,
            popen=popen,
        )
        if not args.dry_run:
            pair = _wait_for_daemon(
                daemon_url,
                args.daemon_timeout,
                request_json=request_json,
                sleep=sleep,
            )
            if not pair.get("connected"):
                _log_step(f"serial daemon did not connect: {pair}")
                return 2

    can_skip_reprovision = (
        args.dry_run
        or (
            bool(args.host)
            and not args.wifi_ssid
            and args.wifi_password is None
            and not os.environ.get(args.wifi_password_env or "")
        )
    )
    if can_skip_reprovision:
        credentials = None
        if args.dry_run:
            _log_step("dry run; skip credential provisioning")
        else:
            _log_step("Wi-Fi host supplied; skip credential provisioning")
    else:
        credentials = resolve_wifi_credentials(args)
    if credentials:
        ssid, password = credentials
        _log_step(f"provision Wi-Fi ssid={ssid!r} password=<redacted>")
        if not args.dry_run:
            code, body = request_json(
                "POST",
                daemon_url,
                "/provision-wifi",
                {"ssid": ssid, "password": password},
            )
            if code < 200 or code >= 300:
                _log_step(f"provision failed: {body}")
                return 3
        if not host and not args.dry_run:
            host = _wait_for_wifi_ip(
                daemon_url,
                args.wifi_timeout,
                request_json=request_json,
                sleep=sleep,
            )
            if not host:
                _log_step("PaperS3 did not report a Wi-Fi IP before timeout")
                return 4

    wifi_proc = None
    if host:
        if use_existing_wifi_daemon:
            _log_step("existing Wi-Fi daemon will receive the dashboard push")
        else:
            _stop_daemon(serial_proc, "serial")
            serial_proc = None
            wifi_proc = _start_daemon(
                "papers3-wifi",
                card_cli.daemon_command(
                    profile,
                    root=ROOT,
                    transport="wifi",
                    host=host,
                    wifi_port=args.wifi_port,
                    http_host=args.http_host,
                ),
                dry_run=args.dry_run,
                log_dir=args.log_dir,
                popen=popen,
            )
            if not args.dry_run:
                pair = _wait_for_daemon(
                    daemon_url,
                    args.daemon_timeout,
                    request_json=request_json,
                    sleep=sleep,
                )
                if not pair.get("connected"):
                    _log_step(f"Wi-Fi daemon did not connect: {pair}")
                    return 5
    else:
        _log_step("no Wi-Fi host known; keeping serial daemon for first dashboard push")

    resolve_flow04_inputs(args)

    if args.skip_interests:
        _log_step("flow 04 interests: skipped")
    else:
        code = _run_command(
            "flow 04 configure interests",
            card_cli.interests_command(
                profile,
                root=ROOT,
                output=args.interests_output,
                slots=args.interests_slots,
                cadence=args.cadence,
                hours=args.hours,
                days=args.days,
                timezone=args.timezone,
                city=args.city,
                non_interactive=args.non_interactive,
                require_weather_location=True,
            ),
            dry_run=args.dry_run,
            call=call,
        )
        if code != 0:
            return code

    if args.skip_card_profile:
        _log_step("flow 04 sleep-card profile: skipped")
    else:
        code = _run_command(
            "flow 04 configure sleep-card profile",
            card_cli.profile_command(
                profile,
                root=ROOT,
                name=args.card_name,
                tagline=args.card_tagline,
                bio=args.card_bio,
                city=args.card_city,
                link=args.card_link,
                qr_label=args.card_qr_label,
                footer=args.card_footer,
                non_interactive=args.non_interactive,
            ),
            dry_run=args.dry_run,
            call=call,
        )
        if code != 0:
            return code

    code = _run_command(
        "push configured dashboard",
        card_cli.configured_dashboard_command(profile, root=ROOT, interests=args.interests_output),
        dry_run=args.dry_run,
        call=call,
    )
    if code != 0:
        return code

    if args.skip_schedule:
        _log_step("flow 06 schedule handoff: skipped")
    else:
        _log_step(
            "flow 06 schedule handoff: register an agent loop using "
            "~/.ai-desk-card/interests.yaml"
        )

    _log_step("sleep-card profile is assets/profile.yaml; dashboard remains on screen after onboarding")
    if args.push_sleep_card and not args.dry_run:
        code, body = request_json("POST", daemon_url, "/sleep", {})
        if code < 200 or code >= 300:
            _log_step(f"sleep-card push failed: {body}")
            return 6
        _log_step(f"sleep-card response={body}")

    if wifi_proc is not None:
        _log_step(f"Wi-Fi daemon left running for PaperS3 host={host}")
    elif serial_proc is not None:
        _log_step("serial daemon left running for PaperS3 fallback")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Onboard PaperS3 and push the configured first dashboard.")
    parser.add_argument("--profile", default="paper-s3", choices=("paper-s3",))
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--host", help="Known PaperS3 Wi-Fi IP; skips waiting for reported IP.")
    parser.add_argument("--wifi-port", type=int, default=9880)
    parser.add_argument("--http-host", default="0.0.0.0")
    parser.add_argument("--daemon-url", default=DEFAULT_DAEMON_URL)
    parser.add_argument("--wifi-ssid")
    parser.add_argument("--wifi-password")
    parser.add_argument("--wifi-password-env", default="CARD_WIFI_PASSWORD")
    parser.add_argument("--no-wifi", action="store_true")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument("--skip-interests", action="store_true")
    parser.add_argument("--skip-card-profile", action="store_true")
    parser.add_argument("--skip-schedule", action="store_true")
    parser.add_argument("--interests-output")
    parser.add_argument("--interests-slots")
    parser.add_argument("--cadence", default="30m")
    parser.add_argument("--hours", default="08-22")
    parser.add_argument("--days", default="mon-fri")
    parser.add_argument("--timezone")
    parser.add_argument("--city")
    parser.add_argument("--card-name")
    parser.add_argument("--card-tagline")
    parser.add_argument("--card-bio")
    parser.add_argument("--card-city")
    parser.add_argument("--card-link")
    parser.add_argument("--card-qr-label")
    parser.add_argument("--card-footer")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-dir")
    parser.add_argument("--daemon-timeout", type=float, default=30.0)
    parser.add_argument("--wifi-timeout", type=float, default=45.0)
    parser.add_argument("--push-sleep-card", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
