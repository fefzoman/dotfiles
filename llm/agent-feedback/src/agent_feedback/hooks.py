"""Normalize documented hook envelopes without retaining free-form content."""

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

from . import __version__

MAX_MESSAGE_BYTES = 1024 * 1024
PROVIDERS = ("claude", "codex")
HOOK_EVENTS = {
    "SessionStart": "session.started",
    "SessionEnd": "session.ended",
    "UserPromptSubmit": "turn.started",
    "Stop": "turn.completed",
    "PreToolUse": "tool.started",
    "PostToolUse": "tool.completed",
    "PostToolUseFailure": "tool.failed",
    "SubagentStart": "agent.started",
    "SubagentStop": "agent.completed",
    "PermissionRequest": "permission.requested",
    "PostCompact": "context.compacted",
}
TOOL_NAMES = {"Bash", "Read", "Write", "Edit", "Glob", "Grep", "apply_patch"}
GAP_REASONS = {"invalid_message", "unsupported_hook", "oversized_message"}


def tool_metadata(payload, hook):
    name = payload.get("tool_name")
    tool = {"name": name if isinstance(name, str) and name in TOOL_NAMES else "other"}
    duration = payload.get("duration_ms")
    if type(duration) is int and 0 <= duration <= 2**53 - 1:
        tool["duration_ms"] = duration
    arguments = payload.get("tool_input")
    command = arguments.get("command") if isinstance(arguments, dict) else None
    if tool["name"] == "Bash" and isinstance(command, str) and command:
        tool["command_fingerprint"] = fingerprint(command)
    path = arguments.get("file_path") if isinstance(arguments, dict) else None
    if tool["name"] in ("Read", "Edit", "Write") and isinstance(path, str) and path:
        tool["path_fingerprint"] = fingerprint(path)
        if tool["name"] == "Read":
            # The same file range, so paging through a file is not a re-read.
            tool["target_fingerprint"] = fingerprint(json.dumps(
                [path] + [arguments.get(key) for key in ("offset", "limit", "pages")]))
    # Tool response shapes vary; never infer exit status from model-facing prose.
    response = payload.get("tool_response")
    code = response.get("exit_code") if isinstance(response, dict) else None
    if type(code) is int and -(2**31) <= code < 2**31:
        tool["exit_code"] = code
    else:
        code = None
    tool["outcome"] = (
        "failure" if hook == "PostToolUseFailure" or (code is not None and code != 0)
        else "success" if code == 0 else "unknown"
    )
    text = [payload.get("error")]
    text += [response.get("stderr"), response.get("stdout")] if isinstance(response, dict) else [response]
    missing = any(isinstance(value, str) and re.search(r"\bcommand not found\b", value, re.I) for value in text)
    if tool["name"] == "Bash" and (code == 127 or missing):
        tool["error_family"] = "missing_executable"
    return tool


def fingerprint(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError("invalid identifier")
    return fingerprint(value)


def repository_id(value):
    if isinstance(value, str) and value.startswith("sha256:"):
        digest = value.removeprefix("sha256:")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid repository digest")
        return digest
    return identifier(value)


def base_event(provider, repository, installation, session_id):
    if provider not in PROVIDERS:
        raise ValueError("unsupported provider")
    return {
        "schema_version": "1.0",
        "collector_version": __version__,
        "source": "hooks",
        "source_schema_version": "documented-hooks-2026-11-14",
        "provider": provider,
        "installation_id": installation,
        "repository_id": repository_id(repository),
        "session_id": session_id,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "occurred_at": None,
        "context": {"coverage": "metadata_only", "ordering_uncertain": True},
        "privacy": {"raw_payload_retained": False, "redacted": True},
    }


def normalize(raw, provider, repository, installation, cursor=None):
    if len(raw) > MAX_MESSAGE_BYTES:
        return gap(provider, repository, installation, "oversized_message", cursor)
    session = None
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("expected object")
        session = identifier(payload.get("session_id"))
        hook = payload.get("hook_event_name")
        if not isinstance(hook, str) or hook not in HOOK_EVENTS:
            return gap(provider, repository, installation, "unsupported_hook", cursor, session)
        event = base_event(provider, repository, installation, session)
        event["event_type"] = HOOK_EVENTS[hook]
        for source, target in (("turn_id", "turn_id"), ("tool_use_id", "span_id"),
                               ("agent_id", "agent_id")):
            if payload.get(source) is not None:
                event[target] = identifier(payload[source])
        if hook.startswith(("PreTool", "PostTool")) or hook == "PermissionRequest":
            event["tool"] = tool_metadata(payload, hook)
        stable = cursor
        if stable is None and event.get("span_id"):
            stable = hook + ":" + event["span_id"]
        event["event_id"] = identifier(stable) if stable is not None else uuid.uuid4().hex
        return event
    except (ValueError, TypeError, RecursionError, UnicodeError):
        return gap(provider, repository, installation, "invalid_message", cursor, session)


def gap(provider, repository, installation, reason, cursor=None, session=None):
    if reason not in GAP_REASONS:
        raise ValueError("invalid gap reason")
    event = base_event(provider, repository, installation, session or fingerprint("unknown-session"))
    event.update(event_type="collector.gap", reason=reason,
                 event_id=identifier(cursor) if cursor is not None else uuid.uuid4().hex)
    return event
