#!/usr/bin/env python3
"""Checkpoint idle Claude Code and Codex sessions; guard cold resumes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

MIN_TOKENS = 120_000
FIRE_FRACTION = 0.9
# GPT-5.6+ defaults to a 30m minimum cache TTL: https://developers.openai.com/api/docs/guides/prompt-caching
CODEX_CACHE_TTL = 30 * 60
SESSION_DAYS = 7
CHECKPOINT_DAYS = 30
OUTPUT_CAP = 2000
HANDOFF_SECONDS = 600
DIGEST_CAP = 12_000
TAIL_BYTES = 2_000_000
HEADER = "## Idle checkpoint"
IDE_NOTE = re.compile(r"(?s)<(ide_[a-z_]+|system-reminder)>.*?</\1>")
SECTIONS = ("Goal", "Constraints", "Decisions", "Dead ends", "Done", "Current state", "Next steps", "Pointers")
EDIT_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}
ROUTINE = re.compile(
    r"(yes|no|ok(ay)?|continue|go( on| ahead)?|proceed|thanks?( you)?|lgtm|do it|next|"
    r"commit( and push)?|push|run (the )?tests?)[.!]*",
    re.I,
)
SECRET = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----"
    r"|\b(?:sk-(?:ant-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abpors]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})"
    r"|(?i:bearer)\s+[A-Za-z0-9._~+/=-]{20,}"
    r"|(?i:password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S{8,}",
    re.S,
)
REQUEST = (
    "Idle checkpoint: the user is away and the prompt cache expires in about {left}. Do not call "
    "tools. Write a checkpoint that lets a fresh session, with no access to this conversation, continue the "
    "work. Keep an item only if that session would act wrongly or waste time without it. Skip routine "
    "operations (commit, push, lint, test reruns), minor fixes that left no decision, tool output, your own "
    "reasoning, and anything the digest below already lists unless you add why. Name exact files, functions, "
    "commands and errors. If an earlier Idle checkpoint is in this conversation, update it instead of "
    f"starting over. Under `{HEADER}`, use exactly these headings: Goal, Done, Decisions, Dead ends, Current "
    "state, Constraints, Next steps, Pointers (turn numbers from the digest). Write 300-1,200 words, scaled "
    'to the work. End with: "After {until}, run /pitstop and then /clear to continue from this checkpoint in this window."'
)
PROTOCOL = (
    "Resume protocol: before any tool call, state the goal and the first next step in two lines and ask the "
    "user to confirm. Treat Decisions and Dead ends as settled unless the user reopens them. For a missing "
    "detail run `python3 ~/.config/dotfiles/idle_compact.py turn {session} T<n>` on the turn a pointer names, "
    '`python3 ~/.config/dotfiles/idle_compact.py search "<words>"` for anything else; never read or grep '
    "transcript.md whole."
)


def state_dir() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "idle-compact"


def marker(session: str, kind: str) -> Path:
    return state_dir() / "sessions" / f"{session}.{kind}"


def handoff(cwd: str) -> Path:
    return state_dir() / "handoff" / project_of(cwd)


def lifetime(client: str = "claude") -> float:
    test = os.environ.get("IDLE_COMPACT_TEST_SECONDS")
    if test:
        return float(test) / FIRE_FRACTION
    return CODEX_CACHE_TTL if client == "codex" else 3600.0


def min_tokens(client: str = "claude") -> int:
    return 1 if client == "codex" else int(os.environ.get("IDLE_COMPACT_TEST_MIN_TOKENS") or MIN_TOKENS)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_relative_to(state_dir()):
        os.chmod(state_dir(), 0o700)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def minutes(seconds: float) -> str:
    count = max(1, round(seconds / 60))
    return f"{count} minute{'s' if count != 1 else ''}"


def clock(stamp: float) -> str:
    return datetime.fromtimestamp(stamp).strftime("%H:%M")


def git(cwd: str, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", cwd, *args], capture_output=True, text=True, timeout=5, check=True
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def project_of(cwd: str) -> str:
    root = Path(git(cwd, "rev-parse", "--show-toplevel") or cwd)
    return f"{re.sub(r'[^A-Za-z0-9._-]+', '-', root.name) or 'root'}-{hashlib.sha1(str(root).encode()).hexdigest()[:6]}"


def redact(text: str) -> str:
    return SECRET.sub("[REDACTED]", text)


def records(path: Path, tail: int | None = None) -> list[dict[str, Any]]:
    try:
        with path.open("rb") as stream:
            size = stream.seek(0, os.SEEK_END)
            stream.seek(max(0, size - tail) if tail else 0)
            if tail and size > tail:
                stream.readline()
            lines = stream.read().splitlines()
    except OSError:
        return []
    out = []
    for raw in lines:
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        if isinstance(record, dict) and not record.get("isSidechain"):
            out.append(record)
    return out


def codex_records(path: Path, tail: int | None = None) -> list[dict[str, Any]]:
    out = []
    for record in records(path, tail):
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        kind, timestamp = payload.get("type"), record.get("timestamp")
        content = []
        normalized = {"timestamp": timestamp, "type": "assistant", "message": {"content": content}}
        if record.get("type") == "response_item":
            if kind == "message" and payload.get("role") in ("user", "assistant"):
                normalized["type"] = payload["role"]
                content += [{"type": "text", "text": b["text"]} for b in payload.get("content") or []
                            if isinstance(b, dict) and isinstance(b.get("text"), str)]
                if normalized["type"] == "user" and any(b["text"].startswith("# AGENTS.md instructions") for b in content):
                    normalized["isMeta"] = True
            elif kind in ("function_call", "custom_tool_call"):
                arguments = payload.get("arguments") or payload.get("input") or ""
                try:
                    arguments = json.loads(arguments)
                except (ValueError, TypeError):
                    arguments = {"input": arguments}
                if not isinstance(arguments, dict):
                    arguments = {"input": arguments}
                content.append({"type": "tool_use", "name": payload.get("name"), "input": arguments})
            elif kind in ("function_call_output", "custom_tool_call_output"):
                content.append({"type": "tool_result", "content": str(payload.get("output", ""))})
            else:
                continue
        elif record.get("type") == "event_msg" and kind == "token_count":
            info = payload.get("info")
            usage = info.get("last_token_usage") if isinstance(info, dict) else None
            tokens = usage.get("input_tokens") if isinstance(usage, dict) else None
            if not isinstance(tokens, int):
                continue
            normalized["message"]["usage"] = {"input_tokens": tokens}
        elif record.get("type") == "event_msg" and kind == "task_started":
            normalized.update(type="user", isMeta=True)
        else:
            continue
        out.append(normalized)
    return out


def stamp(record: dict[str, Any]) -> float:
    try:
        return datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00")).timestamp()
    except (KeyError, ValueError, AttributeError):
        return 0.0


def blocks(record: dict[str, Any]) -> list[dict[str, Any]]:
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b for b in content or [] if isinstance(b, dict)]


def text_of(record: dict[str, Any]) -> str:
    return "\n".join(b.get("text", "") for b in blocks(record) if b.get("type") == "text").strip()


def is_prompt(record: dict[str, Any]) -> bool:
    if record.get("type") != "user" or record.get("isMeta"):
        return False
    origin = record.get("origin")
    if isinstance(origin, dict):
        return origin.get("kind") == "human"
    text = text_of(record)
    return bool(text) and not text.startswith("<") and all(b.get("type") != "tool_result" for b in blocks(record))


def usage(record: dict[str, Any]) -> dict[str, Any] | None:
    message = record.get("message")
    found = message.get("usage") if record.get("type") == "assistant" and isinstance(message, dict) else None
    return found if isinstance(found, dict) else None


def last_call(recs: list[dict[str, Any]]) -> tuple[float, int] | None:
    for record in reversed(recs):
        if found := usage(record):
            tokens = sum(found.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            return stamp(record), tokens
    return None


def one_hour_cache(recs: list[dict[str, Any]]) -> bool:
    for record in reversed(recs):
        created = (usage(record) or {}).get("cache_creation") or {}
        if created.get("ephemeral_1h_input_tokens"):
            return True
        if created.get("ephemeral_5m_input_tokens"):
            return False
    return False


def last_message(recs: list[dict[str, Any]]) -> float:
    return max((stamp(r) for r in recs if r.get("type") in ("user", "assistant")), default=0.0)


def last_prompt(recs: list[dict[str, Any]]) -> float:
    return max((stamp(r) for r in recs if is_prompt(r)), default=0.0)


def turns(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def add(kind: str, when: float, text: str) -> None:
        out.append({"n": len(out) + 1, "kind": kind, "time": when, "text": redact(text)})

    for record in recs:
        when = stamp(record)
        if is_prompt(record):
            add("user", when, IDE_NOTE.sub("", text_of(record)).strip())
            continue
        for block in blocks(record):
            if record.get("type") == "assistant" and block.get("type") == "text" and block.get("text", "").strip():
                add("assistant", when, block["text"].strip())
            elif block.get("type") == "tool_use":
                add("tool", when, f"{block.get('name')} {json.dumps(block.get('input'), ensure_ascii=False)}"[:300])
            elif block.get("type") == "tool_result":
                body = block.get("content")
                body = body if isinstance(body, str) else " ".join(
                    b.get("text", "") for b in body or [] if isinstance(b, dict)
                )
                add("error" if block.get("is_error") else "result", when, body[:OUTPUT_CAP])
    return out


def render_transcript(items: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"## T{t['n']} · {t['kind']} · {datetime.fromtimestamp(t['time']):%Y-%m-%d %H:%M}\n\n{t['text']}" for t in items
    ) + "\n"


def edited_files(recs: list[dict[str, Any]]) -> Counter[str]:
    files: Counter[str] = Counter()
    for record in recs:
        for block in blocks(record):
            if block.get("type") == "tool_use":
                args = block.get("input") or {}
                name = str(block.get("name", ""))
                path = args.get("file_path") or args.get("notebook_path")
                if name in EDIT_TOOLS and path:
                    files[path] += 1
                elif ("replace" in name or "insert" in name) and args.get("relative_path"):
                    files[args["relative_path"]] += 1
                elif "apply_patch" in name:
                    for path in re.findall(r"(?m)^\*\*\* (?:Add|Update|Delete) File: (.+)$", str(args.get("input", ""))):
                        files[path] += 1
    return files


def todos(recs: list[dict[str, Any]]) -> list[str]:
    for record in reversed(recs):
        for block in blocks(record):
            if block.get("type") == "tool_use" and block.get("name") == "TodoWrite":
                return [
                    f"{t.get('status')}: {t.get('content')}"
                    for t in (block.get("input") or {}).get("todos") or []
                    if isinstance(t, dict) and t.get("status") != "completed"
                ]
    return []


def repo_state(path: str, since: float) -> dict[str, Any] | None:
    root = git(path, "rev-parse", "--show-toplevel")
    if not root:
        return None
    return {
        "path": root,
        "branch": git(root, "branch", "--show-current"),
        "head": git(root, "rev-parse", "--short", "HEAD"),
        "uncommitted": git(root, "status", "--porcelain").splitlines()[:30],
        "diffstat": git(root, "diff", "--stat", "HEAD").splitlines()[-1:],
        "commits": git(root, "log", f"--since=@{int(since)}", "--oneline", "-n", "20").splitlines(),
    }


def build_digest(recs: list[dict[str, Any]], cwd: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    started = min((t["time"] for t in items), default=time.time())
    files = edited_files(recs)
    roots = {cwd, *(str(Path(f).parent) for f in files if os.path.isabs(f))}
    repos = {r["path"]: r for r in filter(None, (repo_state(p, started) for p in sorted(roots)[:8]))}
    errors = [t for t in items if t["kind"] == "error"]
    return {
        "cwd": cwd,
        "started": started,
        "requests": [
            {"n": t["n"], "time": t["time"], "text": " ".join(t["text"].split())[:160]}
            for t in items
            if t["kind"] == "user" and not ROUTINE.fullmatch(t["text"].strip()) and not t["text"].startswith("/")
        ],
        "files": files.most_common(40),
        "repos": list(repos.values()),
        "last_error": {"n": errors[-1]["n"], "text": errors[-1]["text"][:300]} if errors else None,
        "todos": todos(recs),
    }


def render_digest(digest: dict[str, Any]) -> str:
    def text(requests: list[dict[str, Any]]) -> str:
        lines = ["Digest of this session (turn numbers match transcript.md):", "Requests:"]
        lines += [f"- T{r['n']} {clock(r['time'])} {r['text']}" for r in requests]
        if digest["files"]:
            lines.append("Files edited: " + ", ".join(f"{f} ({n})" for f, n in digest["files"]))
        for repo in digest["repos"]:
            lines.append(
                f"Repo {repo['path']}: {repo['branch'] or 'detached'} @ {repo['head']}, "
                f"{len(repo['uncommitted'])} uncommitted, {' '.join(repo['diffstat'])}"
            )
            lines += [f"  commit {c}" for c in repo["commits"]]
        if digest["last_error"]:
            lines.append(f"Last error, T{digest['last_error']['n']}: {digest['last_error']['text']}")
        if digest["todos"]:
            lines.append("Open todos: " + "; ".join(digest["todos"]))
        return "\n".join(lines)

    requests = list(digest["requests"])
    while len(text(requests)) > DIGEST_CAP and requests:
        requests.pop(0)
    return text(requests)[:DIGEST_CAP]


# Checkpoint folders


def folder_for(session: str, cwd: str | None = None) -> Path | None:
    found = sorted(state_dir().glob(f"checkpoints/*/*-{session}"))
    if found or cwd is None:
        return found[-1] if found else None
    return state_dir() / "checkpoints" / project_of(cwd) / f"{datetime.now():%Y-%m-%d}-{session}"


def store_checkpoint(folder: Path, session: str, reply: str, cwd: str, transcript: Path, client: str = "claude") -> None:
    current = folder / "checkpoint.md"
    previous = ""
    if current.exists():
        count = len(list(folder.glob("checkpoint-*.md"))) + 1
        previous = f"checkpoint-{count}.md"
        os.replace(current, folder / previous)
    repo = repo_state(cwd, time.time()) or {}
    header = [
        f"session: {session}",
        f"client: {client}",
        f"project: {folder.parent.name}",
        f"cwd: {cwd}",
        f"transcript: {transcript}",
        f"branch: {repo.get('branch', '')}",
        f"head: {repo.get('head', '')}",
        f"time: {datetime.now():%Y-%m-%d %H:%M}",
        f"previous: {previous}",
    ]
    body = reply[reply.find(HEADER):] if HEADER in reply else reply
    write(current, "---\n" + "\n".join(header) + "\n---\n\n" + redact(body).strip() + "\n")


def ordered_sections(body: str) -> str:
    parts = re.split(r"(?m)^(?:#{2,4}\s+|\*\*(?=[A-Z][^*\n]{0,30}:?\*\*))", body)
    named = {}
    for part in parts[1:]:
        title, _, rest = part.partition("\n")
        if "**" in title:
            title, _, inline = title.partition("**")
            rest = f"{inline.lstrip(': ')}\n{rest}".strip()
        key = next((s for s in SECTIONS if title.strip().lower().startswith(s.lower())), None)
        if key and key not in named:
            named[key] = rest.strip()
    if len(named) < 3:
        return body.strip()
    return "\n\n".join(f"### {s}\n{named[s]}" for s in SECTIONS if s in named)


def prune() -> None:
    marker = state_dir() / "pruned"
    if marker.exists() and time.time() - marker.stat().st_mtime < 86400:
        return
    write(marker, "")
    now = time.time()
    for path in state_dir().glob("sessions/*"):
        if now - path.stat().st_mtime > SESSION_DAYS * 86400:
            path.unlink(missing_ok=True)
    for folder in state_dir().glob("checkpoints/*/*"):
        if now - folder.stat().st_mtime > CHECKPOINT_DAYS * 86400:
            for path in folder.iterdir():
                path.unlink(missing_ok=True)
            folder.rmdir()


# Hooks


def native_idle_compact() -> bool:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    config = Path(base) / ".claude.json" if base else Path.home() / ".claude.json"
    try:
        flag = json.loads(config.read_text(encoding="utf-8"))["cachedGrowthBookFeatures"]["tengu_sunny_locket"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return isinstance(flag, dict) and flag.get("mode") == "compact"


def arm(hook: dict[str, Any], client: str = "claude") -> int:
    session, transcript, cwd = hook["session_id"], Path(hook["transcript_path"]), hook.get("cwd") or os.getcwd()
    load_records = codex_records if client == "codex" else records
    recs = load_records(transcript, TAIL_BYTES)
    fired = float(read(marker(session, "fired")) or 0)
    if client == "claude" and fired and fired > last_prompt(recs):
        reply = "\n\n".join(text_of(r) for r in recs if r.get("type") == "assistant" and stamp(r) >= fired - 1)
        folder = folder_for(session)
        if reply and folder and read(marker(session, "stored")) != str(fired):
            store_checkpoint(folder, session, reply, cwd, transcript)
            write(marker(session, "stored"), str(fired))
        return 0
    call = last_call(recs)
    if not call or call[1] < min_tokens(client):
        return 0
    if client == "claude" and (not one_hour_cache(recs) or native_idle_compact()):
        return 0
    prune()
    token = uuid.uuid4().hex
    write(marker(session, "arm"), token)
    seen = last_message(recs)
    gap = lifetime(client)
    fire_at = call[0] + gap * FIRE_FRACTION
    while (wait := fire_at - time.time()) > 0:
        time.sleep(min(60.0, wait))
        if read(marker(session, "arm")) != token or last_message(load_records(transcript, TAIL_BYTES)) > seen:
            return 0
    full = load_records(transcript)
    if read(marker(session, "arm")) != token or last_message(full) > seen:
        return 0
    items = turns(full)
    folder = folder_for(session, cwd)
    digest = build_digest(full, cwd, items)
    if client == "codex":
        digest["last_prompt"] = last_prompt(full)
        if read(marker(session, "arm")) != token or last_message(load_records(transcript, TAIL_BYTES)) > seen:
            return 0
    write(folder / "digest.json", json.dumps(digest, indent=2, ensure_ascii=False) + "\n")
    write(folder / "transcript.md", render_transcript(items))
    if client == "codex":
        # shortcut: Codex cannot wake idle turns; use model summaries when idle rewake is supported.
        requests = [t for t in items if t["kind"] == "user"]
        replies = [t for t in items if t["kind"] == "assistant"]
        selected = [("Goal", requests[:1]), ("Current state", replies[-1:]), ("Pointers: latest request", requests[-1:])]
        sections = [HEADER, "Local transcript excerpts; use the turn pointers to retrieve complete details."]
        for title, entries in selected:
            sections.append(f"### {title}\n" + "\n".join(f"T{t['n']}: {t['text'][:4000]}" for t in entries))
        store_checkpoint(folder, session, "\n\n".join(sections), cwd, transcript, client)
        print(json.dumps({"systemMessage": "Idle checkpoint saved. Run $pitstop and then /clear to continue from it in this window."}))
        return 0
    now = time.time()
    write(marker(session, "fired"), str(now))
    left = minutes(call[0] + lifetime() - now)
    print(REQUEST.format(left=left, until=clock(now + lifetime())) + "\n\n" + render_digest(digest), file=sys.stderr)
    return 2


def codex_last_call(path: Path) -> tuple[float, int] | None:
    return last_call(codex_records(path, TAIL_BYTES))


def unguarded(session: str, call: tuple[float, int] | None, gap: float, client: str = "claude") -> bool:
    return bool(call) and call[1] >= min_tokens(client) and time.time() - call[0] >= gap and read(marker(session, "guard")) != str(call[0])


def codex_guard(hook: dict[str, Any]) -> int:
    session, call = hook["session_id"], codex_last_call(Path(hook["transcript_path"]))
    if not unguarded(session, call, lifetime("codex"), "codex"):
        return 0
    write(marker(session, "guard"), str(call[0]))
    message = (
        f"This thread has {call[1] // 1000}K tokens of context after a {minutes(time.time() - call[0])} "
        "pause. Run /compact now to keep the following turns small."
    )
    print(json.dumps({"systemMessage": message}))
    return 0


def guard(hook: dict[str, Any], client: str = "claude") -> int:
    load_records = codex_records if client == "codex" else records
    session, recs = hook["session_id"], load_records(Path(hook["transcript_path"]), TAIL_BYTES)
    folder, cwd = folder_for(session), hook.get("cwd") or os.getcwd()
    if re.fullmatch(r"\s*[/$]pitstop\s*", str(hook.get("prompt", ""))):
        if folder and resume(cwd, session).startswith("Continuing"):
            write(handoff(cwd), session)
            print(json.dumps({"decision": "block", "reason": f"Idle checkpoint {session} handed off. Run /clear to continue from it in this window."}))
        return 0
    call = last_call(recs)
    if not unguarded(session, call, lifetime(client), client):
        return 0
    checkpoint = folder / "checkpoint.md" if folder else None
    stale = not checkpoint or not checkpoint.exists()
    if not stale:
        written = checkpoint.stat().st_mtime
        if client == "codex":
            written = json.loads(read(folder / "digest.json") or "{}").get("last_prompt", written)
        stale = last_prompt(recs) > written
    if stale:
        return codex_guard(hook) if client == "codex" else 0
    write(marker(session, "guard"), str(call[0]))
    prompt = str(hook.get("prompt", ""))
    reason = (
        f"This thread has about {call[1] // 1000}K tokens after a long pause. An idle checkpoint is ready. "
        "Run $pitstop and then /clear, then paste your prompt; or send this prompt again to keep "
        f"the full session.\n\nYour prompt:\n{prompt[:1500]}"
    ) if client == "codex" else (
        f"Idle checkpoint: the prompt cache expired {minutes(time.time() - call[0])} ago, so continuing "
        f"this session re-sends about {call[1] // 1000}K tokens at the cache-write price. A checkpoint was written "
        f"at {clock(checkpoint.stat().st_mtime)}. To continue from it in this window, run /pitstop and then /clear, then paste your prompt; or "
        f"send the prompt again to continue the full session.\n\nYour prompt:\n{prompt[:1500]}"
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


def drift(digest: dict[str, Any]) -> str:
    lines = []
    for repo in digest.get("repos", []):
        head = git(repo["path"], "rev-parse", "--short", "HEAD")
        if head and head != repo["head"]:
            commits = git(repo["path"], "log", "--oneline", "-n", "20", f"{repo['head']}..HEAD")
            lines.append(f"{repo['path']}: HEAD moved {repo['head']} -> {head}\n{commits}")
        now = git(repo["path"], "status", "--porcelain").splitlines()
        if sorted(now) != sorted(repo["uncommitted"]):
            lines.append(f"{repo['path']}: uncommitted files now: " + ", ".join(line[3:] for line in now[:30]))
    return "\n".join(lines) or "No repo changes since the checkpoint."


def resume(cwd: str, only: str | None = None) -> str:
    handoff(cwd).unlink(missing_ok=True)
    folders = sorted(state_dir().glob(f"checkpoints/{project_of(cwd)}/*"), key=lambda f: f.stat().st_mtime, reverse=True)
    for folder in folders:
        if only and folder.name[11:] != only:
            continue
        checkpoint = folder / "checkpoint.md"
        header, found, body = read(checkpoint).partition("\n---\n")
        if not found:
            continue
        written = checkpoint.stat().st_mtime
        old = re.search(r"(?m)^transcript: (.+)$", header)
        digest = json.loads(read(folder / "digest.json") or "{}")
        codex = "\nclient: codex\n" in header + "\n"
        load_records = codex_records if codex else records
        if old and last_prompt(load_records(Path(old[1]), TAIL_BYTES)) > (digest.get("last_prompt", written) if codex else written):
            continue
        session = folder.name[11:]
        protocol = PROTOCOL.format(session=session)
        if codex:
            protocol = protocol.replace(" and ask the user to confirm", "")
        return "\n\n".join(
            [
                f"Continuing from idle checkpoint {session} (the ID of the session that wrote it), written "
                f"{datetime.fromtimestamp(written):%Y-%m-%d %H:%M} (folder {folder}).",
                ordered_sections(body),
                render_digest(digest) if digest else "",
                "Changes since the checkpoint:\n" + drift(digest),
                protocol,
            ]
        )
    return "No idle checkpoint for this project."


def clear(hook: dict[str, Any]) -> int:
    cwd = hook.get("cwd") or os.getcwd()
    path = handoff(cwd)
    fresh = path.exists() and time.time() - path.stat().st_mtime < HANDOFF_SECONDS
    name = read(path)
    text = resume(cwd, name) if fresh and name else ""
    if text.startswith("Continuing"):
        print(json.dumps({"systemMessage": f"Loaded idle checkpoint {name} into session {hook['session_id']}.",
                          "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    return 0


# Commands for the model


def chunks(path: Path) -> list[tuple[str, str]]:
    text = read(path)
    if path.name == "transcript.md":
        return [(m.group(1), m.group(0)) for m in re.finditer(r"(?ms)^## (T\d+ · [^\n]*)\n.*?(?=^## T\d+ · |\Z)", text)]
    return [(path.name, text)]


def search(query: str, cwd: str, everywhere: bool, session: str | None, since_days: float | None) -> str:
    terms = [t.lower() for t in query.split() if t]
    project = "*" if everywhere else project_of(cwd)
    hits = []
    for folder in state_dir().glob(f"checkpoints/{project}/*"):
        if session and session not in folder.name:
            continue
        if since_days and time.time() - folder.stat().st_mtime > since_days * 86400:
            continue
        for rank, name in ((0, "checkpoint*.md"), (1, "transcript.md")):
            for path in folder.glob(name):
                for label, text in chunks(path):
                    low = text.lower()
                    matched = sum(1 for t in terms if t in low)
                    if matched:
                        hits.append((-matched, rank, -folder.stat().st_mtime, folder.name, label, text))
    lines = []
    for *_, name, label, text in sorted(hits)[:5]:
        words = text.split()
        at = next((i for i, w in enumerate(words) if any(t in w.lower() for t in terms)), 0)
        lines.append(f"{name} {label}: …{' '.join(words[max(0, at - 12):at + 13])}…")
    return ("\n".join(lines) or "No matches.")[:OUTPUT_CAP]


def turn(session: str, number: str) -> str:
    folder = folder_for(session)
    if not folder:
        return "No checkpoint folder for that session."
    parts = chunks(folder / "transcript.md")
    index = next((i for i, (label, _) in enumerate(parts) if label.split(" ")[0] == number.upper()), None)
    if index is None:
        return f"No turn {number} in {folder / 'transcript.md'}."
    around = [parts[i][0] for i in (index - 1, index + 1) if 0 <= i < len(parts)]
    return (parts[index][1].strip()[:OUTPUT_CAP - 200] + "\n\nNearby: " + " | ".join(around))[:OUTPUT_CAP]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("arm").add_argument("--client", choices=("claude", "codex"), default="claude")
    commands.add_parser("resume")
    commands.add_parser("clear")
    commands.add_parser("guard").add_argument("--client", choices=("claude", "codex"), default="claude")
    find = commands.add_parser("search")
    find.add_argument("query")
    find.add_argument("--all", action="store_true")
    find.add_argument("--session")
    find.add_argument("--since", type=float, help="days")
    show = commands.add_parser("turn")
    show.add_argument("session")
    show.add_argument("number")
    args = parser.parse_args()
    if args.command == "search":
        print(search(args.query, os.getcwd(), args.all, args.session, args.since))
        return 0
    if args.command == "turn":
        print(turn(args.session, args.number))
        return 0
    if args.command == "resume":
        print(resume(os.getcwd()))
        return 0
    if os.environ.get("IDLE_COMPACT") == "off":
        return 0
    try:
        hook = json.load(sys.stdin)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", hook["session_id"]):
            return 0
        if args.command == "arm":
            return arm(hook, args.client)
        if args.command == "clear":
            return clear(hook)
        return guard(hook, args.client)
    except (OSError, ValueError, KeyError, TypeError):
        return 0


if __name__ == "__main__":
    sys.exit(main())
