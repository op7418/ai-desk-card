#!/usr/bin/env python3
"""Write assets/profile.yaml for the sleep-card business card."""
from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def default_output_path() -> str:
    return str(ROOT / "assets" / "profile.yaml")


def _prompt(args: argparse.Namespace, attr: str, prompt: str) -> None:
    if getattr(args, attr):
        return
    value = input(prompt).strip()
    if value:
        setattr(args, attr, value)


def resolve_inputs(args: argparse.Namespace) -> None:
    if args.non_interactive:
        if not args.name:
            raise SystemExit("--name is required in --non-interactive mode")
        return

    _prompt(args, "name", "Business card name: ")
    if not args.name:
        raise SystemExit("business card name is required")
    _prompt(args, "tagline", "Tagline: ")
    _prompt(args, "bio", "Bio lines, separated by |: ")
    _prompt(args, "city", "City tag: ")
    _prompt(args, "link", "Web/link tag: ")
    _prompt(args, "qr_label", "QR label: ")
    _prompt(args, "footer", "Footer: ")


def _yaml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _bio_lines(value: str | None) -> list[str]:
    if not value:
        return []
    return [line.strip() for line in value.split("|") if line.strip()]


def build_yaml(args: argparse.Namespace) -> str:
    tags: list[tuple[str, str]] = []
    if args.city:
        tags.append(("City", args.city))
    if args.link:
        tags.append(("Web", args.link))

    lines = [
        "# ai-desk-card sleep-frame profile. Rendered by the sleep-card flow.",
        f"name: {_yaml_string(args.name)}",
        f"tagline: {_yaml_string(args.tagline or '')}",
        "",
        "bio_lines:",
    ]
    bios = _bio_lines(args.bio)
    if bios:
        for line in bios:
            lines.append(f"  - {_yaml_string(line)}")
    else:
        lines.append("  - \"\"")

    lines.extend(["", "tags:"])
    if tags:
        for icon, text in tags:
            lines.append(f"  - icon: {_yaml_string(icon)}")
            lines.append(f"    text: {_yaml_string(text)}")
    else:
        lines.append("  []")

    lines.extend([
        "",
        "qr_image: \"qr.png\"",
        f"qr_label: {_yaml_string(args.qr_label or '')}",
        "avatar_image: \"avatar.png\"",
        f"footer: {_yaml_string(args.footer or 'ai-desk-card sleeping')}",
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
    print(f"[profile] wrote {out}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write ai-desk-card sleep-card profile.yaml.")
    parser.add_argument("--output", default=default_output_path())
    parser.add_argument("--name")
    parser.add_argument("--tagline")
    parser.add_argument("--bio", help="Use | to separate multiple bio lines.")
    parser.add_argument("--city")
    parser.add_argument("--link")
    parser.add_argument("--qr-label")
    parser.add_argument("--footer")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    return run(build_arg_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
