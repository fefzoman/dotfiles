#!/usr/bin/env python3
"""Claude and Codex PreToolUse hook: before a whole-file read of a large file, point the model at smart-read.

A very large file's first whole read in a session is denied; repeating the call goes through."""

import json
import os
import re
import shlex
import shutil
import sys
import tempfile
from pathlib import Path

MIN_LINES = int(os.environ.get("READ_HINT_MIN_LINES") or 80)
BLOCK_LINES = int(os.environ.get("READ_HINT_BLOCK_LINES") or 300)
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
    session = str(hook.get("session_id") or "")
    seen = Path(tempfile.gettempdir()) / f"read-hint-{session}" if re.fullmatch(r"[A-Za-z0-9_-]+", session) else None
    denied = set(seen.read_text().splitlines()) if seen and seen.exists() else set()
    notes, blocked = [], []
    for name in targets(hook):
        path = cwd / name
        lines = line_count(path)
        if lines >= MIN_LINES:
            notes.append(
                f"{name} has {lines} lines. To read only what the task needs: `smart-read outline {name}` lists its "
                f'symbols with line ranges; `smart-read search "<what you need>" --path {name}` returns the relevant '
                "parts; then read just that line range."
            )
        if seen and lines >= BLOCK_LINES and str(path.resolve()) not in denied:
            blocked.append(str(path.resolve()))
    if blocked:
        seen.write_text("".join(f"{p}\n" for p in sorted(denied | set(blocked))))
        reason = "\n".join(notes) + "\nIf the task truly needs the whole file, repeat the same call."
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))
    elif notes:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "\n".join(notes)}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
