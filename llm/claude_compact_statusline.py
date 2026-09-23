#!/usr/bin/env python3
"""Show Claude context, quota, cache state, and a proactive /compact warning."""

from __future__ import annotations

import json
import sys
from typing import Any

CONTEXT_THRESHOLD = 120_000
QUOTA_USED_THRESHOLD = 85.0


def render(data: dict[str, Any]) -> str:
    context = data.get("context_window", {})
    input_tokens = context.get("total_input_tokens")
    used = context.get("used_percentage")
    parts = [
        f"context {used:.0f}% ({input_tokens / 1000:.0f}k)"
        if isinstance(used, int | float) and isinstance(input_tokens, int | float)
        else "context --"
    ]

    quota_used = []
    for label, key in (("5h", "five_hour"), ("7d", "seven_day")):
        value = data.get("rate_limits", {}).get(key, {}).get("used_percentage")
        if isinstance(value, int | float):
            quota_used.append(float(value))
            parts.append(f"{label} {value:.0f}%")

    cache = data.get("prompt_cache", {})
    if cache.get("caching_observed"):
        parts.append("cache warm" if cache.get("warm") else "cache cold")

    if (
        isinstance(input_tokens, int | float)
        and input_tokens >= CONTEXT_THRESHOLD
        and quota_used
        and max(quota_used) >= QUOTA_USED_THRESHOLD
    ):
        parts.append("WARNING: run /compact before a long pause or quota reset")
    return " | ".join(parts)


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
