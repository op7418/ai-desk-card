#!/usr/bin/env python3
"""Push one widget to the claude-card daemon.

Usage:
    push_widget.py <type> --slot <slot> --data-file <path>
    push_widget.py <type> --slot <slot> --data-stdin
    push_widget.py --clear --slot <slot>
    push_widget.py --clear   # clears all slots
"""
from __future__ import annotations
import argparse, json, os, sys, urllib.error, urllib.request

DAEMON = os.environ.get("CARD_DAEMON_URL", "http://127.0.0.1:9877")
SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "schemas")
TYPES = ("weather", "todo", "calendar", "messages",
         "ai-status", "ai-tasks",
         "scratch", "focus", "now-playing", "git-status", "system",
         "inbox", "next-meeting", "pr-queue",
         "break-reminder", "deadlines")
SLOTS = ("top-left", "top-right", "middle", "bottom", "full")


def load_schema(t):
    p = os.path.join(SCHEMA_DIR, f"{t}.schema.json")
    if not os.path.exists(p): return None
    with open(p) as f: return json.load(f)


def validate(t, data):
    schema = load_schema(t)
    if schema is None: return True, ""
    try:
        import jsonschema
        try:
            jsonschema.validate(data, schema); return True, ""
        except jsonschema.ValidationError as e:
            return False, e.message
    except ImportError:
        return isinstance(data, dict), "" if isinstance(data, dict) else "data must be object"


def post(path, payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(DAEMON + path, data=body, method="POST",
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, str(e)
    except urllib.error.URLError as e:
        return 0, f"unreachable: {e.reason}"


def delete(slot):
    url = f"{DAEMON}/widget" + (f"?slot={slot}" if slot else "")
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.URLError as e: return 0, f"unreachable: {e.reason}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("widget_type", nargs="?", choices=TYPES)
    ap.add_argument("--slot", choices=SLOTS)
    ap.add_argument("--data-file")
    ap.add_argument("--data-stdin", action="store_true")
    ap.add_argument("--ttl", type=int, default=0)
    ap.add_argument("--stale-after", type=int, default=0)
    ap.add_argument("--theme", default="")
    ap.add_argument("--clear", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.clear:
        code, body = delete(args.slot)
        print(json.dumps(body, ensure_ascii=False))
        return 0 if 200 <= code < 300 else 2

    if not args.widget_type or not args.slot:
        ap.error("widget_type + --slot required (or use --clear)")

    if args.data_stdin:
        data = json.load(sys.stdin)
    elif args.data_file:
        with open(args.data_file) as f: data = json.load(f)
    else:
        ap.error("--data-stdin or --data-file required")

    ok, err = validate(args.widget_type, data)
    if not ok:
        print(f"validation: {err}", file=sys.stderr); return 1

    payload = {"type": args.widget_type, "slot": args.slot, "data": data,
               "ttl": args.ttl, "stale_after": args.stale_after, "theme": args.theme}
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2)); return 0

    code, body = post("/widget", payload)
    print(json.dumps(body, ensure_ascii=False))
    return 0 if 200 <= code < 300 else (2 if code == 0 else 3)


if __name__ == "__main__": sys.exit(main())
