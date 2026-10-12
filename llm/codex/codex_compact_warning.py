#!/usr/bin/env python3
"""Warn when a large Codex thread is close to a quota stop."""

from __future__ import annotations

import json
import mmap
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

CONTEXT_THRESHOLD = 120_000
REMAINING_THRESHOLD = 15.0
IDLE_GAP = 30 * 60


def latest_snapshot(path: Path) -> tuple[int, list[tuple[float, int | None]], float] | None:
    try:
        with path.open("rb") as stream:
            if stream.seek(0, os.SEEK_END) == 0:
                return None
            with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
                end = len(data)
                while end:
                    start = data.rfind(b"\n", 0, max(0, end - 1)) + 1
                    raw = data[start:end].strip()
                    end = start
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    payload = event.get("payload", {})
                    limits = payload.get("rate_limits", {})
                    if (
                        event.get("type") != "event_msg"
                        or payload.get("type") != "token_count"
                        or limits.get("limit_id") != "codex"
                    ):
                        continue
                    usage = payload.get("info", {}).get("last_token_usage", {})
                    context = usage.get("input_tokens")
                    if not isinstance(context, int):
                        return None
                    windows = []
                    for name in ("primary", "secondary"):
                        window = limits.get(name)
                        if isinstance(window, dict) and isinstance(window.get("used_percent"), int | float):
                            windows.append((100.0 - float(window["used_percent"]), window.get("resets_at")))
                    try:
                        at = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).timestamp()
                    except (KeyError, AttributeError, ValueError):
                        at = 0.0
                    return context, windows, at
    except (OSError, ValueError):
        return None
    return None


def warning(snapshot: tuple[int, list[tuple[float, int | None]], float], now: float) -> str | None:
    context, windows, _ = snapshot
    active = [remaining for remaining, reset in windows if reset is None or reset > now]
    if context < CONTEXT_THRESHOLD or not active or min(active) > REMAINING_THRESHOLD:
        return None
    return (
        f"Large Codex context ({context:,} input tokens) and only {min(active):.0f}% "
        "quota remaining. If a long pause is likely, run /compact now, then resume "
        "this same thread after reset."
    )


def main() -> int:
    try:
        hook = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    transcript = hook.get("transcript_path")
    session_id = hook.get("session_id")
    if not isinstance(transcript, str) or not isinstance(session_id, str):
        return 0

    now = time.time()
    snapshot = latest_snapshot(Path(transcript)) or (0, [], 0.0)
    message = warning(snapshot, now)
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    marker = state / "codex-compact-warning" / f"{session_id}.active"
    if message is None:
        marker.unlink(missing_ok=True)
        return 0
    if marker.exists():
        return 0
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    if now - snapshot[2] < IDLE_GAP or os.environ.get("IDLE_COMPACT") == "off":
        print(json.dumps({"systemMessage": message}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
