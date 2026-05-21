#!/usr/bin/env python3
"""ai-desk-card 纯 Python fallback 刷新器 — 不调 AI，0 token 成本。

只刷三个本地能算的 widget：
  - weather    via wttr.in
  - system     via psutil (or `vm_stat`/`df` fallbacks)
  - git-status if a configured repo path is dirty/has commits

配置文件 ~/.card-refresh.yaml（可选）：
    location: "Beijing"
    repo_path: "/Users/me/code/main-project"

如果没配置文件就用默认：location=北京、跳过 git。
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

DAEMON = os.environ.get("CARD_DAEMON_URL", "http://127.0.0.1:9877")
CONFIG_PATH = Path.home() / ".card-refresh.yaml"


def log(*a): print(*a, file=sys.stderr, flush=True)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"location": "Beijing"}
    try:
        try:
            import yaml
        except ImportError:
            # Tiny YAML key:value parser — only handles flat strings, no nesting.
            cfg = {}
            for line in CONFIG_PATH.read_text().splitlines():
                line = line.split("#", 1)[0].strip()
                if ":" in line:
                    k, v = line.split(":", 1)
                    cfg[k.strip()] = v.strip().strip("\"'")
            return cfg
        with CONFIG_PATH.open() as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        log(f"[config] failed: {e}; using defaults")
        return {"location": "Beijing"}


def push(typ: str, slot: str, data: dict, ttl: int = 7800):
    body = json.dumps({"type": typ, "slot": slot, "data": data,
                       "ttl": ttl}).encode()
    try:
        req = urllib.request.Request(f"{DAEMON}/widget", data=body,
                                      method="POST",
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=4) as r:
            log(f"[push] {typ}@{slot} → {r.status}")
    except urllib.error.HTTPError as e:
        log(f"[push] {typ} fail: HTTP {e.code} {e.read().decode()!r}")
    except Exception as e:
        log(f"[push] {typ} fail: {e!r}")


def current_widgets() -> list[dict]:
    """Snapshot of which widgets are currently in which slots — so we only
    refresh the ones the user actually has on the card."""
    try:
        with urllib.request.urlopen(f"{DAEMON}/widget", timeout=4) as r:
            return (json.load(r) or {}).get("widgets", [])
    except Exception as e:
        log(f"[snapshot] {e}"); return []


def refresh_weather(slot: str, location: str):
    url = f"https://wttr.in/{urllib.parse.quote(location)}?format=j1"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            d = json.load(r)
    except Exception as e:
        log(f"[weather] fetch fail: {e}"); return
    try:
        cur = d["current_condition"][0]
        days = d["weather"][:2]
        data = {
            "location": location,
            "temp": int(cur["temp_C"]),
            "condition": cur["lang_zh"][0]["value"] if cur.get("lang_zh") else cur["weatherDesc"][0]["value"],
            "high": int(days[0]["maxtempC"]),
            "low":  int(days[0]["mintempC"]),
            "forecast": [
                {"day": "明" if i == 0 else "后",
                 "temp_high": int(days[i + 1]["maxtempC"]),
                 "temp_low":  int(days[i + 1]["mintempC"]),
                 "condition": days[i + 1]["hourly"][4]["lang_zh"][0]["value"]
                              if days[i + 1]["hourly"][4].get("lang_zh") else "晴"}
                for i in range(min(1, len(days) - 1))
            ],
        }
        push("weather", slot, data)
    except (KeyError, IndexError, TypeError) as e:
        log(f"[weather] parse fail: {e}")


def refresh_system(slot: str):
    try:
        import psutil
        cpu  = int(psutil.cpu_percent(interval=0.4))
        mem  = int(psutil.virtual_memory().percent)
        disk = int(psutil.disk_usage("/").percent)
        bat  = psutil.sensors_battery()
        bat_pct = int(bat.percent) if bat else None
        data = {"cpu_pct": cpu, "mem_pct": mem, "disk_pct": disk}
        if bat_pct is not None: data["battery_pct"] = bat_pct
        push("system", slot, data)
    except ImportError:
        log("[system] psutil not installed — skipping")
    except Exception as e:
        log(f"[system] fail: {e}")


def refresh_git_status(slot: str, repo: str):
    if not os.path.isdir(repo):
        log(f"[git] not a dir: {repo}"); return
    try:
        branch = subprocess.check_output(
            ["git", "-C", repo, "rev-parse", "--abbrev-ref", "HEAD"],
            timeout=3, text=True).strip()
        porc = subprocess.check_output(
            ["git", "-C", repo, "status", "--porcelain"],
            timeout=3, text=True).splitlines()
        dirty = sum(1 for l in porc if l.strip())
        last = subprocess.check_output(
            ["git", "-C", repo, "log", "-1", "--pretty=%s"],
            timeout=3, text=True).strip()
        push("git-status", slot, {
            "branch": branch, "dirty": dirty,
            "last_commit": last[:48],
        })
    except subprocess.CalledProcessError as e:
        log(f"[git] {e}")
    except Exception as e:
        log(f"[git] fail: {e}")


def main():
    cfg = load_config()
    widgets = current_widgets()
    if not widgets:
        log("[main] no widgets currently on card; nothing to refresh")
        return

    # 只刷已有的 widget，按它们当前所在的 slot。
    type_to_slot = {w["type"]: w["slot"] for w in widgets}

    if "weather" in type_to_slot:
        refresh_weather(type_to_slot["weather"], cfg.get("location", "Beijing"))
    if "system" in type_to_slot:
        refresh_system(type_to_slot["system"])
    if "git-status" in type_to_slot and cfg.get("repo_path"):
        refresh_git_status(type_to_slot["git-status"], cfg["repo_path"])

    # 其他类型 (calendar / messages / inbox / ...) 需要 OAuth 或更多
    # 数据源整合 — fallback 版不处理。
    skipped = [t for t in type_to_slot if t not in ("weather", "system", "git-status")]
    if skipped:
        log(f"[main] skipped (needs AI/auth): {','.join(skipped)}")


if __name__ == "__main__":
    main()
