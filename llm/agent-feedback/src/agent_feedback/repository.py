"""Resolve explicit repository scopes without executing captured commands."""

import json
import os
from pathlib import Path
import subprocess


def git(repo, *args):
    return subprocess.run(["git", "--no-optional-locks", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True, timeout=2,
                          env={key: value for key, value in os.environ.items() if not key.startswith("GIT_")}).stdout.strip()


def root(repo):
    return Path(git(Path(repo).expanduser().resolve(), "rev-parse", "--show-toplevel")).resolve()


def identity(repo, explicit=None):
    if explicit:
        return explicit
    remote = git(repo, "config", "--local", "--get", "remote.origin.url")
    if not remote:
        raise ValueError("repository identity required")
    return "origin:" + remote.rstrip("/")


def in_scope(raw, scope):
    try:
        payload = json.loads(raw)
        cwd = payload.get("cwd") if isinstance(payload, dict) else None
        if not isinstance(cwd, str) or not Path(cwd).is_absolute():
            return False
        scope = Path(scope).resolve()
        return Path(cwd).resolve().is_relative_to(scope) and root(cwd) == scope
    except (OSError, ValueError, RecursionError, subprocess.SubprocessError):
        return False
