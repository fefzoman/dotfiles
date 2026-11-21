"""Backfill tool metadata and cost from local Claude/Codex transcripts in memory; nothing is stored."""

from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
import re
import shlex
import subprocess

from .hooks import normalize
from .repository import identity, root

INSTALLATION = "local-scan"
MARKERS = ('"tool_use"', '"tool_result"', '"usage"', '"promptId"', '"session_meta"', '"turn_context"',
           '"task_started"', '"token_count"', '"function_call', '"custom_tool_call')
# Harness-written result headers, not model prose.
EXIT_HEADER = re.compile(r"^(?:Process exited with code|Exit code:) (-?\d+)$", re.M)
TEXT_LIMIT = 64 * 1024
CLAUDE_USAGE = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
IDLE_SECONDS = 300
WRAPPERS = {"rtk", "sudo", "env", "time", "command", "exec"}
FAMILIES = {
    "read": {"cat", "sed", "head", "tail", "rg", "grep", "find", "fd", "ls", "nl", "wc", "awk", "tree", "less", "jq"},
    "remote": {"aws", "gcloud", "gsutil", "bq", "az", "kubectl", "docker", "terraform", "curl", "ssh", "psql",
               "mysql", "gh", "airflow"},
    "wait": {"until", "while", "sleep", "watch"},
    "run": {"python", "python3", "uv", "pytest", "npm", "npx", "node", "make", "dbt", "ruff", "go", "cargo",
            "bash", "sh", "zsh"},
}
ERRORS = (("permission", r"permission denied|operation not permitted"), ("missing_file", r"no such file or directory"),
          ("timeout", r"timed out|timeout"), ("usage", r"usage:|unrecognized argument|invalid option|unknown option"),
          ("test_failure", r"\bFAILED\b|AssertionError|\b\d+ failed\b"))


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


def stamp(value):
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return None


def text_size(content):
    if isinstance(content, str):
        return len(content)
    blocks = content if isinstance(content, list) else ()
    return sum(len(block["text"]) for block in blocks if isinstance(block, dict) and isinstance(block.get("text"), str))


def bill(stats, billed, key, tokens):
    """Count each model call once; resumed sessions copy earlier records."""
    if key in billed or type(tokens) is not int:
        return None
    billed.add(key)
    stats["tokens"] += tokens
    return tokens


def claude(path, stats, billed):
    calls, cwd, turn = {}, None, None
    for record in records(path):
        cwd = record.get("cwd") or cwd
        turn = record.get("promptId") or turn
        message = record.get("message")
        message = message if isinstance(message, dict) else {}
        usage = message.get("usage")
        tokens = None
        if record.get("type") == "assistant" and isinstance(usage, dict) and message.get("id"):
            tokens = bill(stats, billed, ("claude", message["id"]),
                          sum(value for key in CLAUDE_USAGE if type(value := usage.get(key)) is int))
        content = message.get("content")
        for block in content if isinstance(content, list) else ():
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                calls[block.get("id")] = {
                    "session": record.get("sessionId"), "cwd": cwd, "turn": turn, "id": block.get("id"),
                    "name": block.get("name"), "input": block.get("input"),
                    "start": stamp(record.get("timestamp")), "tokens": tokens}
                tokens = None  # parallel calls of one reply share its usage once
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in calls:
                call = calls[block["tool_use_id"]]
                call.update(end=stamp(record.get("timestamp")), failed=block.get("is_error") is True,
                            output_bytes=text_size(block.get("content")))
                if call["failed"] and isinstance(block.get("content"), str):
                    call["error"] = block["content"][:TEXT_LIMIT]
    return list(calls.values())


def exit_code(output):
    if not isinstance(output, str):
        return None
    try:
        code = json.loads(output)["metadata"]["exit_code"]  # legacy `shell` tool output
        return code if type(code) is int else None
    except (ValueError, TypeError, KeyError, IndexError, RecursionError):
        match = EXIT_HEADER.search(output[:1024])
        return int(match.group(1)) if match else None


def codex(path, stats, billed):
    calls, pending, session, cwd, turn = {}, [], None, None, None
    for record in records(path):
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        kind, call_id = payload.get("type"), payload.get("call_id")
        if record.get("type") == "session_meta":
            session, cwd = payload.get("id"), payload.get("cwd")
        elif record.get("type") == "turn_context" or kind == "task_started":
            turn, cwd = payload.get("turn_id") or turn, payload.get("cwd") or cwd
        elif kind == "token_count":
            info = payload.get("info")
            usage = info.get("last_token_usage") if isinstance(info, dict) else None
            total = usage.get("total_tokens") if isinstance(usage, dict) else None
            tokens = bill(stats, billed, ("codex", session, record.get("timestamp"), total), total)
            if pending:
                pending[0]["tokens"] = tokens  # usage of the reply that issued these calls
            pending = []
        elif kind in ("function_call", "custom_tool_call"):
            try:
                arguments = json.loads(payload.get("arguments") or "{}")
            except (ValueError, TypeError, RecursionError):
                arguments = {}
            command = arguments.get("cmd", arguments.get("command")) if isinstance(arguments, dict) else None
            if isinstance(command, list) and all(isinstance(part, str) for part in command):
                command = shlex.join(command)
            name = payload.get("name")
            calls[call_id] = call = {
                "session": session, "cwd": cwd, "turn": turn, "id": call_id,
                "name": "Bash" if name in ("exec_command", "shell") else name, "input": {"command": command},
                "start": stamp(record.get("timestamp")), "tokens": None}
            pending.append(call)
        elif kind in ("function_call_output", "custom_tool_call_output") and call_id in calls:
            output = payload.get("output")
            code = exit_code(output)
            calls[call_id].update(end=stamp(record.get("timestamp")), exit_code=code,
                                  output_bytes=text_size(output))
            if code and isinstance(output, str):
                calls[call_id]["error"] = output[:TEXT_LIMIT]
    return list(calls.values())


def time_steps(calls):
    """A call's step lasts until the session's next call, unless the agent went idle after the result."""
    sessions = defaultdict(list)
    for call in calls:
        if call["start"] is not None:
            sessions[call["session"]].append(call)
    for rows in sessions.values():
        rows.sort(key=lambda call: call["start"])
        for call, following in zip(rows, rows[1:] + [None]):
            end = call.get("end")
            if following and (end is None or following["start"] - end <= IDLE_SECONDS):
                call["seconds"] = max(0.0, following["start"] - call["start"])
            elif end is not None:
                call["seconds"] = max(0.0, end - call["start"])


def payloads(call):
    start = {"hook_event_name": "PreToolUse", "session_id": call["session"], "tool_use_id": call["id"],
             "turn_id": call["turn"], "tool_name": call["name"], "tool_input": call["input"]}
    if "end" not in call:
        return start, None
    if call.get("failed"):
        result = {**start, "hook_event_name": "PostToolUseFailure", "error": call.get("error")}
    else:
        response = {"exit_code": call.get("exit_code")}
        if "error" in call:
            response["stderr"] = call["error"]
        result = {**start, "hook_event_name": "PostToolUse", "tool_response": response}
    return start, result


def command_words(command):
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    while words:
        if re.fullmatch(r"[A-Za-z_]\w*=.*", words[0]) or words[0] in WRAPPERS:
            words = words[2:] if words[:2] == ["rtk", "proxy"] else words[1:]
        elif words[0] == "cd" and "&&" in words:
            words = words[words.index("&&") + 1:]
        else:
            break
    return words


def local(call, details):
    """Fixed-vocabulary labels always; command and path names only with --details, never arguments."""
    arguments = call["input"] if isinstance(call["input"], dict) else {}
    command, path = arguments.get("command"), arguments.get("file_path")
    words = command_words(command) if isinstance(command, str) else []
    name = Path(words[0]).name if words else None
    info = {"family": next((family for family, names in FAMILIES.items() if name in names), None)}
    if isinstance(call.get("error"), str):
        info["error"] = next((kind for kind, pattern in ERRORS if re.search(pattern, call["error"], re.I)), "other")
    if details and name:
        info["executable"] = name if re.fullmatch(r"[\w.+-]{1,64}", name) else "(unusual name)"
        # A second word is shown only when it looks like a subcommand, not an argument.
        sub = words[1] if len(words) > 1 and re.fullmatch(r"[a-z][a-z0-9-]{0,31}", words[1]) else None
        info["command"] = f"{info['executable']} {sub}" if sub else info["executable"]
    if isinstance(path, str) and path:
        prefix = (call.get("cwd") or "").rstrip("/") + "/"
        inside = not path.startswith("/") or (prefix != "/" and path.startswith(prefix))
        info["where"] = ("tool_output" if "/tool-results/" in path
                         else "task_output" if "/tasks/" in path and path.endswith(".output")
                         else "repo" if inside else "outside")
        if details:
            info["path"] = path.removeprefix(prefix) if prefix != "/" else path
    return info


def repository(cwd, cache):
    if cwd not in cache:
        try:
            cache[cwd] = identity(root(cwd))
        except (OSError, TypeError, ValueError, subprocess.SubprocessError):
            cache[cwd] = f"path:{cwd or 'unknown'}"
    return cache[cwd]


def events(home, labels, stats, details=False):
    """Yield normalized events; fill labels (repository_id -> identity) and stats as a side effect."""
    cache, seen, billed = {}, set(), set()
    for provider, path in transcripts(home):
        stats["transcripts"] += 1
        calls = [call for call in (claude if provider == "claude" else codex)(path, stats, billed)
                 if (provider, call["id"]) not in seen]
        time_steps(calls)
        for call in calls:
            seen.add((provider, call["id"]))
            name = repository(call["cwd"], cache)
            stats["tool_calls"] += 1
            stats["seconds"] += call.get("seconds", 0)
            for payload in payloads(call):
                if payload is None:
                    continue
                event = normalize(json.dumps(payload).encode(), provider, name, INSTALLATION)
                labels[event["repository_id"]] = name
                if payload["hook_event_name"] != "PreToolUse" and event["event_type"] != "collector.gap":
                    event["tool"].update({key: call[key] for key in ("tokens", "seconds", "output_bytes")
                                          if call.get(key) is not None})
                    event["local"] = local(call, details)
                yield event
