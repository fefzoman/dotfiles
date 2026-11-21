"""Merge opt-in, repository-scoped handlers into existing user hooks."""

import argparse
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile
import uuid

from .hooks import HOOK_EVENTS, fingerprint, repository_id
from .repository import identity, root

MAX_CONFIG_BYTES = 1024 * 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate config key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("non-JSON numeric constant")


def decode_config(raw):
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)


def read_config(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None, 0o600
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
            raise ValueError("unsafe config file")
        raw = stream.read(MAX_CONFIG_BYTES + 1)
        if len(raw) > MAX_CONFIG_BYTES:
            raise ValueError("config is too large")
        return raw, stat.S_IMODE(info.st_mode)


def merged(raw, provider, command, marker):
    config = decode_config(raw) if raw is not None else {}
    if not isinstance(config, dict):
        raise ValueError("expected settings object")
    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("expected hooks object")
    handler = {"type": "command", "command": command, "timeout": 3, "statusMessage": marker}
    for event in HOOK_EVENTS:
        if provider == "codex" and event == "PostToolUseFailure":
            continue
        entries = hooks.setdefault(event, [])
        if not isinstance(entries, list):
            raise ValueError("expected hook entries")
        kept = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                raise ValueError("unexpected existing hook structure")
            if any(not isinstance(item, dict) for item in entry["hooks"]):
                raise ValueError("unexpected existing handler")
            remaining = [item for item in entry["hooks"] if item.get("statusMessage") != marker]
            if remaining or not entry["hooks"]:
                kept.append({**entry, "hooks": remaining})
        hooks[event] = kept + [{"hooks": [handler]}]
    if raw is not None and config == decode_config(raw):
        return raw
    result = (json.dumps(config, indent=2, ensure_ascii=True) + "\n").encode()
    if len(result) > MAX_CONFIG_BYTES:
        raise ValueError("merged config is too large")
    return result


def replace_config(path, before, after, mode):
    if before == after:
        return None
    if read_config(path)[0] != before:
        raise ValueError("config changed concurrently; retry")
    backup = None
    if before is not None:
        backup = path.with_name(path.name + ".agent-feedback-backup-" + uuid.uuid4().hex)
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(before)
            stream.flush()
            os.fsync(stream.fileno())
    fd, temporary = tempfile.mkstemp(prefix=".agent-feedback-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(after)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        if read_config(path)[0] != before:
            raise ValueError("config changed concurrently; retry")
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return backup


def install(repo, repository, providers, state_dir):
    repo = root(repo)
    repository = "sha256:" + repository_id(identity(repo, repository))
    marker = "agent-feedback:" + fingerprint(str(repo))[:20]
    source = str(Path(__file__).resolve().parents[1])
    plans = []
    with ExitStack() as stack:
        for provider in providers:
            if provider == "claude":
                directory = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
                path = directory / "settings.json"
            else:
                directory = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
                path = directory / "hooks.json"
            directory = directory.expanduser().absolute()
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = directory / path.name
            lock_fd = os.open(directory / ".agent-feedback-install.lock",
                              os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            lock = stack.enter_context(os.fdopen(lock_fd, "w"))
            info = os.fstat(lock.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
                raise ValueError("unsafe installation lock")
            fcntl.flock(lock, fcntl.LOCK_EX)
            command = shlex.join(["env", "PYTHONPATH=" + source, sys.executable, "-P", "-m", "agent_feedback",
                                  "--state-dir", str(Path(state_dir).expanduser().resolve()), "collect",
                                  "--provider", provider, "--repository", repository,
                                  "--scope-root", str(repo), "--mode", "metadata"])
            before, mode = read_config(path)
            plans.append((path, before, merged(before, provider, command, marker), mode))
        for path, before, after, mode in plans:
            backup = replace_config(path, before, after, mode)
            print(f"{'Unchanged' if before == after else 'Merged'}: {path}")
            if backup:
                print(f"Backup: {backup}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="only this Git worktree is opted in")
    parser.add_argument("--repository", help="stable owner/remote identity; required without origin")
    parser.add_argument("--agent", choices=("all", "claude", "codex"), default="all")
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".local/state/agent-feedback")
    args = parser.parse_args(argv)
    try:
        providers = ("claude", "codex") if args.agent == "all" else (args.agent,)
        install(args.repo, args.repository, providers, args.state_dir)
        return 0
    except (OSError, ValueError, RecursionError, subprocess.SubprocessError):
        print("agent-feedback: installation failed; check config JSON, file permissions and repository "
              "identity (--repository is required without origin). Earlier file merges may have completed; "
              "backups are beside changed files. No trust or permission settings were changed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
