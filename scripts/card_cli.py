#!/usr/bin/env python3
"""Profile-aware local workflow wrapper for ai-desk-card.

This is intentionally thin: it builds the same PlatformIO and daemon/demo
commands users already run by hand, while reading env/profile names from the
shared device profile config.
"""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import card_profiles


def platformio_executable(root: str = ROOT) -> str:
    exe = os.path.join(root, ".pio-venv", "Scripts", "pio.exe")
    return exe if os.path.exists(exe) else "pio"


def python_executable(root: str = ROOT) -> str:
    exe = os.path.join(root, ".pio-venv", "Scripts", "python.exe")
    return exe if os.path.exists(exe) else sys.executable


def platformio_command(profile: dict, action: str, *,
                       root: str = ROOT, port: str | None = None) -> list[str]:
    env = profile["platformio_env"]
    pio = platformio_executable(root)
    if action == "build":
        return [pio, "run", "-e", env]
    if action == "upload":
        cmd = [pio, "run", "-e", env, "-t", "upload"]
        if port:
            cmd.append(f"--upload-port={port}")
        return cmd
    if action == "monitor":
        cmd = [pio, "device", "monitor", "--environment", env]
        if port:
            cmd.extend(["--port", port])
        cmd.append("--baud=115200")
        return cmd
    raise ValueError(f"unknown PlatformIO action {action!r}")


def daemon_command(profile: dict, *, root: str = ROOT,
                   transport: str | None = None,
                   port: str | None = None,
                   host: str | None = None,
                   wifi_port: int | None = None,
                   http_host: str | None = None) -> list[str]:
    cmd = [
        python_executable(root),
        os.path.join(root, "daemon", "card_daemon.py"),
        "--profile", profile["name"],
    ]
    if transport:
        cmd.extend(["--transport", transport])
    if port:
        cmd.extend(["--port", port])
    if host:
        cmd.extend(["--host", host])
    if wifi_port:
        cmd.extend(["--wifi-port", str(int(wifi_port))])
    if http_host:
        cmd.extend(["--http-host", http_host])
    return cmd


def demo_command(profile: dict, widget: str, *, root: str = ROOT) -> list[str]:
    return [
        python_executable(root),
        os.path.join(root, "scripts", "demo_papers3_widgets.py"),
        "--profile", profile["name"],
        "--widget", widget,
    ]


def configured_dashboard_command(profile: dict, *, root: str = ROOT,
                                 interests: str | None = None) -> list[str]:
    cmd = [
        python_executable(root),
        os.path.join(root, "scripts", "push_configured_dashboard.py"),
    ]
    if interests:
        cmd.extend(["--interests", interests])
    return cmd


def profile_command(profile: dict, *, root: str = ROOT,
                    output: str | None = None,
                    name: str | None = None,
                    tagline: str | None = None,
                    bio: str | None = None,
                    city: str | None = None,
                    link: str | None = None,
                    qr_label: str | None = None,
                    footer: str | None = None,
                    non_interactive: bool = False) -> list[str]:
    cmd = [
        python_executable(root),
        os.path.join(root, "scripts", "configure_profile.py"),
    ]
    if output:
        cmd.extend(["--output", output])
    if name:
        cmd.extend(["--name", name])
    if tagline:
        cmd.extend(["--tagline", tagline])
    if bio:
        cmd.extend(["--bio", bio])
    if city:
        cmd.extend(["--city", city])
    if link:
        cmd.extend(["--link", link])
    if qr_label:
        cmd.extend(["--qr-label", qr_label])
    if footer:
        cmd.extend(["--footer", footer])
    if non_interactive:
        cmd.append("--non-interactive")
    return cmd


def onboard_command(profile: dict, *, root: str = ROOT,
                    port: str | None = None,
                    host: str | None = None,
                    no_wifi: bool = False,
                    skip_build: bool = False,
                    skip_upload: bool = False,
                    non_interactive: bool = False,
                    skip_interests: bool = False,
                    skip_card_profile: bool = False,
                    skip_schedule: bool = False,
                    interests_output: str | None = None,
                    interests_slots: str | None = None,
                    cadence: str | None = None,
                    hours: str | None = None,
                    days: str | None = None,
                    timezone: str | None = None,
                    city: str | None = None,
                    card_name: str | None = None,
                    card_tagline: str | None = None,
                    card_bio: str | None = None,
                    card_city: str | None = None,
                    card_link: str | None = None,
                    card_qr_label: str | None = None,
                    card_footer: str | None = None) -> list[str]:
    cmd = [
        python_executable(root),
        os.path.join(root, "scripts", "onboard_papers3.py"),
        "--profile", profile["name"],
    ]
    if port:
        cmd.extend(["--port", port])
    if host:
        cmd.extend(["--host", host])
    if no_wifi:
        cmd.append("--no-wifi")
    if skip_build:
        cmd.append("--skip-build")
    if skip_upload:
        cmd.append("--skip-upload")
    if non_interactive:
        cmd.append("--non-interactive")
    if skip_interests:
        cmd.append("--skip-interests")
    if skip_card_profile:
        cmd.append("--skip-card-profile")
    if skip_schedule:
        cmd.append("--skip-schedule")
    if interests_output:
        cmd.extend(["--interests-output", interests_output])
    if interests_slots:
        cmd.extend(["--interests-slots", interests_slots])
    if cadence:
        cmd.extend(["--cadence", cadence])
    if hours:
        cmd.extend(["--hours", hours])
    if days:
        cmd.extend(["--days", days])
    if timezone:
        cmd.extend(["--timezone", timezone])
    if city:
        cmd.extend(["--city", city])
    if card_name:
        cmd.extend(["--card-name", card_name])
    if card_tagline:
        cmd.extend(["--card-tagline", card_tagline])
    if card_bio:
        cmd.extend(["--card-bio", card_bio])
    if card_city:
        cmd.extend(["--card-city", card_city])
    if card_link:
        cmd.extend(["--card-link", card_link])
    if card_qr_label:
        cmd.extend(["--card-qr-label", card_qr_label])
    if card_footer:
        cmd.extend(["--card-footer", card_footer])
    return cmd


def interests_command(profile: dict, *, root: str = ROOT,
                      output: str | None = None,
                      slots: str | None = None,
                      cadence: str | None = None,
                      hours: str | None = None,
                      days: str | None = None,
                      timezone: str | None = None,
                      city: str | None = None,
                      non_interactive: bool = False,
                      require_weather_location: bool = False) -> list[str]:
    cmd = [
        python_executable(root),
        os.path.join(root, "scripts", "configure_interests.py"),
        "--profile", profile["name"],
    ]
    if output:
        cmd.extend(["--output", output])
    if slots:
        cmd.extend(["--slots", slots])
    if cadence:
        cmd.extend(["--cadence", cadence])
    if hours:
        cmd.extend(["--hours", hours])
    if days:
        cmd.extend(["--days", days])
    if timezone:
        cmd.extend(["--timezone", timezone])
    if city:
        cmd.extend(["--city", city])
    if non_interactive:
        cmd.append("--non-interactive")
    if require_weather_location:
        cmd.append("--require-weather-location")
    return cmd


def list_serial_ports() -> list[str]:
    try:
        from serial.tools import list_ports
    except Exception:
        return []
    return [port.device for port in list_ports.comports()]


def format_command(cmd: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(cmd)
    return shlex.join(cmd)


def _run_or_print(cmd: list[str], dry_run: bool) -> int:
    print(format_command(cmd))
    if dry_run:
        return 0
    return subprocess.call(cmd, cwd=ROOT)


def _profile(name: str) -> dict:
    return card_profiles.get_profile(name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile-aware ai-desk-card workflow helper.")
    sub = parser.add_subparsers(dest="command", required=True)
    choices = card_profiles.profile_choices()

    def add_profile(p):
        p.add_argument("--profile", required=True, choices=choices)
        p.add_argument("--dry-run", action="store_true")

    p_build = sub.add_parser("build", help="Build firmware for a profile.")
    add_profile(p_build)

    p_upload = sub.add_parser("upload", help="Upload firmware for a profile.")
    add_profile(p_upload)
    p_upload.add_argument("--port")

    p_monitor = sub.add_parser("monitor", help="Open PlatformIO serial monitor.")
    add_profile(p_monitor)
    p_monitor.add_argument("--port")

    p_daemon = sub.add_parser("daemon", help="Run the daemon in the foreground.")
    add_profile(p_daemon)
    p_daemon.add_argument("--transport", choices=("auto", "serial", "ble", "wifi"))
    p_daemon.add_argument("--port")
    p_daemon.add_argument("--host")
    p_daemon.add_argument("--wifi-port", type=int)
    p_daemon.add_argument("--http-host")

    p_demo = sub.add_parser("demo", help="Push a demo widget through the daemon.")
    add_profile(p_demo)
    p_demo.add_argument("--widget", default="dashboard", choices=(
        "text", "status", "weather-mock", "calendar-mock",
        "todo-mock", "ai-status", "dashboard",
    ))

    p_onboard = sub.add_parser("onboard", help="Run the PaperS3 first-run wrapper.")
    add_profile(p_onboard)
    p_onboard.add_argument("--port", default="COM3")
    p_onboard.add_argument("--host")
    p_onboard.add_argument("--no-wifi", action="store_true")
    p_onboard.add_argument("--skip-build", action="store_true")
    p_onboard.add_argument("--skip-upload", action="store_true")
    p_onboard.add_argument("--non-interactive", action="store_true")
    p_onboard.add_argument("--skip-interests", action="store_true")
    p_onboard.add_argument("--skip-card-profile", action="store_true")
    p_onboard.add_argument("--skip-schedule", action="store_true")
    p_onboard.add_argument("--interests-output")
    p_onboard.add_argument("--interests-slots")
    p_onboard.add_argument("--cadence")
    p_onboard.add_argument("--hours")
    p_onboard.add_argument("--days")
    p_onboard.add_argument("--timezone")
    p_onboard.add_argument("--city")
    p_onboard.add_argument("--card-name")
    p_onboard.add_argument("--card-tagline")
    p_onboard.add_argument("--card-bio")
    p_onboard.add_argument("--card-city")
    p_onboard.add_argument("--card-link")
    p_onboard.add_argument("--card-qr-label")
    p_onboard.add_argument("--card-footer")

    p_interests = sub.add_parser("interests", help="Write ~/.ai-desk-card/interests.yaml.")
    add_profile(p_interests)
    p_interests.add_argument("--output")
    p_interests.add_argument("--slots")
    p_interests.add_argument("--cadence")
    p_interests.add_argument("--hours")
    p_interests.add_argument("--days")
    p_interests.add_argument("--timezone")
    p_interests.add_argument("--city")

    p_ports = sub.add_parser("ports", help="List visible serial ports.")
    p_ports.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "ports":
        ports = list_serial_ports()
        if ports:
            for port in ports:
                print(port)
        else:
            print("No serial ports found. In PowerShell, try:")
            print("[System.IO.Ports.SerialPort]::GetPortNames()")
        return 0

    profile = _profile(args.profile)
    print(f"[card-cli] selected profile={profile['name']} device={profile['device_name']}")
    print(f"[card-cli] preferred transport={profile['preferred_transport']}")

    if args.command in {"build", "upload", "monitor"}:
        cmd = platformio_command(profile, args.command, port=getattr(args, "port", None))
    elif args.command == "daemon":
        cmd = daemon_command(
            profile,
            transport=args.transport,
            port=args.port,
            host=args.host,
            wifi_port=args.wifi_port,
            http_host=args.http_host,
        )
    elif args.command == "demo":
        cmd = demo_command(profile, args.widget)
    elif args.command == "onboard":
        if profile["name"] != "paper-s3":
            parser.error("onboard is currently implemented for --profile paper-s3")
        cmd = onboard_command(
            profile,
            port=args.port,
            host=args.host,
            no_wifi=args.no_wifi,
            skip_build=args.skip_build,
            skip_upload=args.skip_upload,
            non_interactive=args.non_interactive,
            skip_interests=args.skip_interests,
            skip_card_profile=args.skip_card_profile,
            skip_schedule=args.skip_schedule,
            interests_output=args.interests_output,
            interests_slots=args.interests_slots,
            cadence=args.cadence,
            hours=args.hours,
            days=args.days,
            timezone=args.timezone,
            city=args.city,
            card_name=args.card_name,
            card_tagline=args.card_tagline,
            card_bio=args.card_bio,
            card_city=args.card_city,
            card_link=args.card_link,
            card_qr_label=args.card_qr_label,
            card_footer=args.card_footer,
        )
    elif args.command == "interests":
        cmd = interests_command(
            profile,
            output=args.output,
            slots=args.slots,
            cadence=args.cadence,
            hours=args.hours,
            days=args.days,
            timezone=args.timezone,
            city=args.city,
        )
    else:
        parser.error(f"unknown command {args.command}")
    return _run_or_print(cmd, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
