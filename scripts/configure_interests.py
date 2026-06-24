#!/usr/bin/env python3
"""Write ~/.ai-desk-card/interests.yaml for ai-desk-card refresh flows."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


M5PAPER_V11_DEFAULT_SLOTS = {
    "top-left": "weather",
    "top-right": "calendar",
    "middle": "todo",
    "bottom": "inbox",
}
PAPER_S3_DEFAULT_SLOTS = {
    "top-left": "weather",
    "top-right": "ai-status",
    "middle": "calendar",
    "bottom": "todo",
}
VALID_SLOTS = set(M5PAPER_V11_DEFAULT_SLOTS)
VALID_WIDGETS = {
    "weather",
    "calendar",
    "todo",
    "focus",
    "inbox",
    "pr-queue",
    "ai-status",
    "git-status",
    "system",
    "next-meeting",
    "deadlines",
    "break-reminder",
    "now-playing",
    "messages",
    "scratch",
    "ai-tasks",
}


def default_output_path() -> str:
    return str(Path.home() / ".ai-desk-card" / "interests.yaml")


def default_slots_for_profile(profile: str) -> dict[str, str]:
    if profile == "paper-s3":
        return dict(PAPER_S3_DEFAULT_SLOTS)
    return dict(M5PAPER_V11_DEFAULT_SLOTS)


def parse_slots(value: str | None, profile: str = "m5paper-v1.1") -> dict[str, str]:
    if not value:
        return default_slots_for_profile(profile)
    slots: dict[str, str] = {}
    for part in value.split(","):
        if "=" not in part:
            raise SystemExit(f"invalid slot mapping {part!r}; use slot=widget")
        slot, widget = [piece.strip() for piece in part.split("=", 1)]
        if slot not in VALID_SLOTS:
            raise SystemExit(f"invalid slot {slot!r}; choose one of {sorted(VALID_SLOTS)}")
        if widget not in VALID_WIDGETS:
            raise SystemExit(f"invalid widget {widget!r}; choose one of {sorted(VALID_WIDGETS)}")
        slots[slot] = widget
    missing = VALID_SLOTS - set(slots)
    if missing:
        raise SystemExit(f"missing slot mappings for {sorted(missing)}")
    return slots


def _yaml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def resolve_inputs(args: argparse.Namespace, *, input_func=input) -> None:
    if args.require_weather_location and not args.city:
        if args.non_interactive:
            raise SystemExit("--city is required when --require-weather-location is set")
        args.city = input_func("Weather location / city: ").strip()
        if not args.city:
            raise SystemExit("weather location is required")
    if not args.city:
        args.city = "Beijing"


def build_yaml(args: argparse.Namespace) -> str:
    if not getattr(args, "city", None):
        args.city = "Beijing"
    slots = parse_slots(args.slots, args.profile)
    lines = [
        "# ai-desk-card interests. The agent reads this on each refresh tick.",
        "version: 1",
        "",
        "slots:",
    ]
    for slot in ("top-left", "top-right", "middle", "bottom"):
        lines.append(f"  {slot}: {slots[slot]}")
    lines.extend([
        "",
        "schedule:",
        f"  cadence: {_yaml_string(args.cadence)}",
        f"  hours: {_yaml_string(args.hours)}",
        f"  days: {_yaml_string(args.days)}",
        f"  timezone: {_yaml_string(args.timezone)}",
        "",
        "data_sources:",
        "  weather:",
        f"    city: {_yaml_string(args.city)}",
        "  calendar:",
        f"    source: {_yaml_string(args.calendar_source)}",
        "  todo:",
        f"    source: {_yaml_string(args.todo_source)}",
        "  inbox:",
        f"    source: {_yaml_string(args.inbox_source)}",
        "  ai-status:",
        f"    source: {_yaml_string(args.ai_status_source)}",
        "  git_status:",
        f"    repo: {_yaml_string(args.git_repo)}",
        "",
        "quiet_hours:",
        f"  enabled: {'true' if args.quiet_hours else 'false'}",
        f"  start: {_yaml_string(args.quiet_start)}",
        f"  end: {_yaml_string(args.quiet_end)}",
        "",
    ])
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    resolve_inputs(args)
    text = build_yaml(args)
    if args.dry_run:
        print(text, end="")
        return 0
    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"[interests] wrote {out}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write ai-desk-card interests.yaml.")
    parser.add_argument(
        "--profile",
        default="m5paper-v1.1",
        choices=("m5paper-v1.1", "paper-s3"),
        help="Select profile-specific default slots.",
    )
    parser.add_argument("--output", default=default_output_path())
    parser.add_argument(
        "--slots",
        help="Comma-separated slot=widget map. Defaults are profile-specific.",
    )
    parser.add_argument("--cadence", default="30m")
    parser.add_argument("--hours", default="08-22")
    parser.add_argument("--days", default="mon-fri")
    parser.add_argument("--timezone", default=os.environ.get("TZ", "Asia/Shanghai"))
    parser.add_argument("--city")
    parser.add_argument("--calendar-source", default="macos")
    parser.add_argument("--todo-source", default="reminders")
    parser.add_argument("--inbox-source", default="mail.app")
    parser.add_argument("--ai-status-source", default="codex")
    parser.add_argument("--git-repo", default="")
    parser.add_argument("--quiet-hours", action="store_true")
    parser.add_argument("--quiet-start", default="23:00")
    parser.add_argument("--quiet-end", default="07:00")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--require-weather-location", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
