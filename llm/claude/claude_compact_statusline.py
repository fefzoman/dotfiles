#!/usr/bin/env python3
"""Show Claude context, quota, cache state, and a proactive /compact warning."""

from __future__ import annotations

import json
import sys
from typing import Any

CONTEXT_THRESHOLD = 120_000
QUOTA_USED_THRESHOLD = 85.0
BOLD, RESET = "\033[1m", "\033[0m"


def color(text: str, hex_rgb: str) -> str:
    r, g, b = bytes.fromhex(hex_rgb)
    return f"\033[38;2;{r};{g};{b}m{text}\033[39m"


def percent(value: float) -> str:
    return color(f"{value:.0f}%", "21C23E" if value < 40 else "F0ED24" if value <= 75 else "E53B12")


def render(data: dict[str, Any]) -> str:
    context = data.get("context_window", {})
    input_tokens = context.get("total_input_tokens")
    used = context.get("used_percentage")
    parts = [
        f"Context {input_tokens / 1000:.0f}k/{percent(used)} used"
        if isinstance(used, int | float) and isinstance(input_tokens, int | float)
        else "Context --"
    ]

    quota_used = []
    for label, key in (("5h", "five_hour"), ("7d", "seven_day")):
        value = data.get("rate_limits", {}).get(key, {}).get("used_percentage")
        if isinstance(value, int | float):
            quota_used.append(float(value))
            parts.append(f"{label} {percent(value)}")

    cache = data.get("prompt_cache", {})
    if cache.get("caching_observed"):
        parts.append(color("cache warm", "E35812") if cache.get("warm") else color("cache cold", "4CBFD4"))

    line = BOLD + " | ".join(parts) + RESET
    if (
        isinstance(input_tokens, int | float)
        and input_tokens >= CONTEXT_THRESHOLD
        and quota_used
        and max(quota_used) >= QUOTA_USED_THRESHOLD
    ):
        line += " | " + color("WARNING: run /compact before a long pause or quota reset", "D4CB24")
    return line


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    if isinstance(data, dict):
        print(render(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
