"""Shared ai-desk-card device profile metadata.

The JSON file is the source of truth. Scripts and the daemon import this
helper so PaperS3 support does not depend on scattered hard-coded env names.
"""
from __future__ import annotations

import copy
import json
import os
from functools import lru_cache
from typing import Any


ROOT = os.path.dirname(os.path.abspath(__file__))
PROFILE_CONFIG_PATH = os.path.join(ROOT, "config", "device_profiles.json")


@lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    with open(PROFILE_CONFIG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data.get("profiles"), dict):
        raise ValueError("device profile config is missing profiles")
    return data


def load_profiles() -> dict[str, dict[str, Any]]:
    return copy.deepcopy(_config()["profiles"])


def default_profile_name() -> str:
    return str(_config().get("default_profile") or "m5paper-v1.1")


def normalize_profile_name(name: str | None) -> str:
    if not name or str(name).lower() == "auto":
        return default_profile_name()
    target = str(name).strip()
    target_lower = target.lower()
    profiles = _config()["profiles"]
    if target in profiles:
        return target
    for profile_name, profile in profiles.items():
        aliases = [profile_name] + list(profile.get("aliases") or [])
        if any(str(alias).lower() == target_lower for alias in aliases):
            return profile_name
    raise KeyError(f"unknown device profile {name!r}")


def profile_choices(include_auto: bool = False) -> tuple[str, ...]:
    names = tuple(_config()["profiles"].keys())
    return (("auto",) + names) if include_auto else names


def get_profile(name: str | None = None) -> dict[str, Any]:
    profile_name = normalize_profile_name(name)
    profile = copy.deepcopy(_config()["profiles"][profile_name])
    profile["name"] = profile_name
    profile["frame_bytes"] = int(profile["logical_width"]) * int(profile["logical_height"]) // 2
    return profile


def detect_profile_from_status(status: dict[str, Any] | None) -> str | None:
    """Return a canonical profile from daemon/device status when safe.

    Detection is intentionally conservative. Generic firmware like "0.10.1"
    is not enough to call the device M5Paper V1.1; the caller can fall back
    to the default or ask the user.
    """
    if not isinstance(status, dict):
        return None

    explicit = status.get("selected_profile") or status.get("profile")
    if explicit:
        try:
            return normalize_profile_name(str(explicit))
        except KeyError:
            pass

    haystack = " ".join(
        str(status.get(key) or "")
        for key in ("device", "device_name", "firmware", "fw", "model")
    ).lower()
    if not haystack:
        return None

    for profile_name, profile in _config()["profiles"].items():
        tokens = list(profile.get("firmware_tokens") or [])
        if profile_name == "paper-s3":
            tokens.extend(["papers3", "paper s3", "m5stack papers3"])
        for token in tokens:
            if str(token).lower() and str(token).lower() in haystack:
                return profile_name
    return None
