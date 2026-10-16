#!/usr/bin/env python3
"""Claude and Codex PreToolUse hook: before a whole-file read of a large file, point the model at smart-read."""

import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path

MIN_LINES = int(os.environ.get("READ_HINT_MIN_LINES") or 80)
MAX_BYTES = 5_000_000
WHOLE_READ = {"cat", "nl", "bat"}


def bash_targets(command: str) -> list[str]:
    """Files a shell command prints whole: `cat FILE` not piped into head, sed, grep and the like."""
    targets = []
    for segment in re.split(r"&&|\|\||;|\n", command):
        if "|" in segment or "<" in segment or ">" in segment:
            continue
        try:
            words = shlex.split(segment)
        except ValueError:
            continue
        if words and words[0] in WHOLE_READ:
            targets += [w for w in words[1:] if not w.startswith("-")]
    return targets


def targets(hook: dict) -> list[str]:
    tool = hook.get("tool_input") if isinstance(hook.get("tool_input"), dict) else {}
    if hook.get("tool_name") == "Read":
        return [] if tool.get("offset") or tool.get("limit") else [str(tool.get("file_path") or "")]
    return bash_targets(str(tool.get("command") or ""))


def line_count(path: Path) -> int:
    try:
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            return 0
        return path.read_bytes().count(b"\n")
    except OSError:
        return 0


def main() -> int:
    try:
        hook = json.load(sys.stdin)
    except ValueError:
        return 0
    if not shutil.which("smart-read"):
        return 0
    cwd = Path(hook.get("cwd") or os.getcwd())
    notes = []
    for name in targets(hook):
        lines = line_count(cwd / name)
        if lines >= MIN_LINES:
            notes.append(
                f"{name} has {lines} lines. To read only what the task needs: `smart-read outline {name}` lists its "
                f'symbols with line ranges; `smart-read search "<what you need>" --path {name}` returns the relevant '
                "parts; then read just that line range."
            )
    if notes:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "\n".join(notes)}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
