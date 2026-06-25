#!/usr/bin/env python3
"""Claude Code statusline sink for ai-desk-card usage panels.

Claude Code pipes statusline JSON to stdin. This script extracts model and
rate-limit fields, writes a small cache for push_claude_ai_status.py, and
prints a compact statusline back to Claude Code.
"""
from __future__ import annotations

import json
import sys

import push_claude_ai_status as claude_usage


def main() -> int:
    try:
        statusline = json.loads(sys.stdin.read() or "{}")
        usage = claude_usage.write_usage_cache(statusline)
        print(claude_usage.format_statusline(usage))
    except Exception:
        print("Claude | quota pending")
    return 0


if __name__ == "__main__":
    sys.exit(main())
