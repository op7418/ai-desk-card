#!/usr/bin/env python3
"""Fetch open items from macOS Reminders.app → todo.data JSON.

Same logic as the parent buddy plugin's helper, but caps to 4 items
(ai-desk-card is glance-distance and the firmware schema limits to 4).
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from datetime import datetime, timedelta

APPLESCRIPT = r'''
on escape(s)
    set s to my replace(s, "\\", "\\\\")
    set s to my replace(s, "\"", "\\\"")
    set s to my replace(s, return, "\\n")
    set s to my replace(s, ASCII character 10, "\\n")
    return s
end escape

on replace(t, search, repl)
    set AppleScript's text item delimiters to search
    set tList to text items of t
    set AppleScript's text item delimiters to repl
    set t to tList as text
    set AppleScript's text item delimiters to ""
    return t
end replace

on iso(theDate)
    set y to year of theDate
    set m to (month of theDate as integer)
    set d to day of theDate
    set hh to hours of theDate
    set mm to minutes of theDate
    set s to (y as string)
    if m < 10 then set s to s & "-0" & m else set s to s & "-" & m
    if d < 10 then set s to s & "-0" & d else set s to s & "-" & d
    set s to s & "T"
    if hh < 10 then set s to s & "0" & hh else set s to s & hh
    if mm < 10 then set s to s & ":0" & mm else set s to s & ":" & mm
    return s
end iso

on run argv
    set listName to ""
    if (count of argv) > 0 then set listName to item 1 of argv
    tell application "Reminders"
        if listName is "" then
            set theList to first list
        else
            set theList to list listName
        end if
        set theItems to (every reminder in theList whose completed is false)
        set out to "{\"items\":["
        set first_item to true
        repeat with r in theItems
            if first_item then
                set first_item to false
            else
                set out to out & ","
            end if
            set out to out & "{\"text\":\"" & my escape(name of r) & "\""
            try
                set out to out & ",\"due\":\"" & my iso(due date of r) & "\""
            on error
                set out to out & ",\"due\":\"\""
            end try
            set out to out & "}"
        end repeat
        return out & "]}"
    end tell
end run
'''


def tag_for(due_iso: str, now: datetime) -> str:
    if not due_iso: return ""
    try: d = datetime.fromisoformat(due_iso)
    except ValueError: return ""
    today = now.date()
    if d < now: return "overdue"
    if d.date() == today: return "today"
    if d.date() == today + timedelta(days=1): return "tomorrow"
    if d.date() <= today + timedelta(days=7): return "this-week"
    return "later"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", dest="list_name", default="")
    ap.add_argument("--title", default="")
    args = ap.parse_args()

    cmd = ["osascript", "-e", APPLESCRIPT]
    if args.list_name: cmd.extend(["--", args.list_name])
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if res.returncode != 0:
        print(f"osascript: {res.stderr}", file=sys.stderr); return 1

    raw = json.loads(res.stdout.strip())
    now = datetime.now()
    items = []
    for it in raw.get("items", []):
        items.append({"text": it["text"], "due": it.get("due", ""),
                       "tag": tag_for(it.get("due", ""), now)})

    order = {"overdue": 0, "today": 1, "tomorrow": 2, "this-week": 3, "later": 4, "": 5}
    items.sort(key=lambda i: (order.get(i["tag"], 9), i.get("due") or "zzz"))

    out = {"items": items[:4]}
    out["title"] = args.title or (args.list_name or "Todo")
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__": sys.exit(main())
