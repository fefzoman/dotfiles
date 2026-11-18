"""Backfill tool metadata from local Claude/Codex transcripts in memory; nothing is stored."""

import json
from pathlib import Path
import re
import shlex
import subprocess

from .hooks import normalize
from .repository import identity, root

INSTALLATION = "local-scan"
MARKERS = ('"tool_use"', '"tool_result"', '"session_meta"', '"function_call', '"custom_tool_call')
# Harness-written result header, not model prose.
EXIT_HEADER = re.compile(r"^(?:Process exited with code|Exit code:) (-?\d+)$", re.M)
TEXT_LIMIT = 64 * 1024


def transcripts(home):
    for provider, pattern in (("claude", ".claude*/projects/**/*.jsonl"), ("codex", ".codex*/sessions/**/*.jsonl"),
                              ("codex", ".codex*/archived_sessions/**/*.jsonl")):
        for path in sorted(Path(home).glob(pattern)):
            yield provider, path


def records(path):
    with open(path, encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not any(marker in line for marker in MARKERS):
                continue
            try:
                record = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if isinstance(record, dict):
                yield record


def claude(path):
    calls, cwd = {}, None
    for record in records(path):
        cwd = record.get("cwd") or cwd
        message = record.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else ():
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                start = {"hook_event_name": "PreToolUse", "session_id": record.get("sessionId"),
                         "tool_use_id": block.get("id"), "tool_name": block.get("name"), "tool_input": block.get("input")}
                calls[block.get("id")] = cwd, start
                yield cwd, start
            elif block.get("type") == "tool_result":
                call = block.get("tool_use_id")
                # The result keeps its call's cwd so both land in the same repository.
                start_cwd, start = calls.get(call, (cwd, {"session_id": record.get("sessionId"), "tool_use_id": call}))
                result = {**start, "hook_event_name": "PostToolUse"}
                if block.get("is_error") is True:
                    result["hook_event_name"] = "PostToolUseFailure"
                    if isinstance(block.get("content"), str):
                        result["error"] = block["content"][:TEXT_LIMIT]
                yield start_cwd, result


def exit_code(output):
    if not isinstance(output, str):
        return None
    try:
        code = json.loads(output)["metadata"]["exit_code"]  # legacy `shell` tool output
        return code if type(code) is int else None
    except (ValueError, TypeError, KeyError, IndexError, RecursionError):
        match = EXIT_HEADER.search(output[:1024])
        return int(match.group(1)) if match else None


def codex(path):
    session = cwd = None
    calls = {}
    for record in records(path):
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        kind, call = payload.get("type"), payload.get("call_id")
        if record.get("type") == "session_meta":
            session, cwd = payload.get("id"), payload.get("cwd")
        elif kind in ("function_call", "custom_tool_call"):
            try:
                arguments = json.loads(payload.get("arguments") or "{}")
            except (ValueError, TypeError, RecursionError):
                arguments = {}
            command = arguments.get("cmd", arguments.get("command")) if isinstance(arguments, dict) else None
            if isinstance(command, list) and all(isinstance(part, str) for part in command):
                command = shlex.join(command)
            name = payload.get("name")
            calls[call] = start = {
                "hook_event_name": "PreToolUse", "session_id": session, "tool_use_id": call,
                "tool_name": "Bash" if name in ("exec_command", "shell") else name, "tool_input": {"command": command}}
            yield cwd, start
        elif kind in ("function_call_output", "custom_tool_call_output"):
            output = payload.get("output")
            code = exit_code(output)
            response = {"exit_code": code}
            if code and isinstance(output, str):
                response["stderr"] = output[:TEXT_LIMIT]
            yield cwd, {**calls.get(call, {"session_id": session, "tool_use_id": call}),
                        "hook_event_name": "PostToolUse", "tool_response": response}


def repository(cwd, cache):
    if cwd not in cache:
        try:
            cache[cwd] = identity(root(cwd))
        except (OSError, TypeError, ValueError, subprocess.SubprocessError):
            cache[cwd] = f"path:{cwd or 'unknown'}"
    return cache[cwd]


def events(home, labels, stats):
    """Yield normalized events; fill labels (repository_id -> identity) and stats as a side effect."""
    cache, seen = {}, set()
    for provider, path in transcripts(home):
        stats["transcripts"] += 1
        for cwd, payload in (claude if provider == "claude" else codex)(path):
            # Resumed sessions copy earlier records; count each tool call once.
            key = (provider, payload["hook_event_name"], payload.get("tool_use_id"))
            if key in seen:
                continue
            seen.add(key)
            name = repository(cwd, cache)
            event = normalize(json.dumps(payload).encode(), provider, name, INSTALLATION)
            labels[event["repository_id"]] = name
            stats["tool_calls"] += payload["hook_event_name"] == "PreToolUse"
            yield event
