#!/usr/bin/env python3
"""Fetch recent macOS notifications → messages.data JSON.

v0.5 ships a MOCK implementation. Real NotificationCenter integration on
macOS 13+ requires either:
  - SQLite read of NotificationCenter's database (path varies by macOS
    version, sandboxing restricts access), OR
  - Hammerspoon / Yabai-style accessibility-API observer that we don't
    bundle here, OR
  - User installing a small companion app

For v0.5 we generate plausible mock data so the widget renders + the
end-to-end pipeline can be tested. Replace this script's main() with
a real source when ready.

Usage:
    fetch_notifications.py [--limit N] [--mock]
    fetch_notifications.py | push_widget.py messages --slot top-right --data-stdin
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timedelta


def mock_data(limit: int) -> dict:
    now = datetime.now()
    items = [
        {"sender": "Alice",    "preview": "PR review please when you get a sec",
         "age": _age(now - timedelta(minutes=2))},
        {"sender": "Slack #eng", "preview": "deploy failed on staging",
         "age": _age(now - timedelta(minutes=14))},
        {"sender": "Mom",      "preview": "晚饭 7 点你回来吗",
         "age": _age(now - timedelta(hours=1, minutes=30))},
    ][:limit]
    return {"items": items}


def _age(then: datetime) -> str:
    delta = datetime.now() - then
    secs = int(delta.total_seconds())
    if secs < 60:  return "just now"
    if secs < 3600: return f"{secs // 60}m"
    if secs < 86400: return f"{secs // 3600}h"
    return f"{secs // 86400}d"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--mock", action="store_true", default=True,
                    help="(v0.5 default) emit mock data — real NotificationCenter source TBD")
    args = ap.parse_args()
    json.dump(mock_data(args.limit), sys.stdout, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__": sys.exit(main())
