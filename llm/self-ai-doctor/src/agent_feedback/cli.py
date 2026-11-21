"""Explicit opt-in collection; hook failures must not block coding."""

import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from . import diagnosis, scan
from .hooks import MAX_MESSAGE_BYTES, PROVIDERS, normalize, repository_id
from .remediation import ProposalError, propose
from .report import markdown, summarize
from .repository import identity, in_scope, root
from .storage import Store


def parser():
    root = argparse.ArgumentParser(prog="agent-feedback")
    root.add_argument("--state-dir", type=Path, default=Path.home() / ".local/state/agent-feedback")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("collect", "ingest"):
        command = commands.add_parser(name)
        command.add_argument("--provider", choices=PROVIDERS, required=True)
        command.add_argument("--repository", required=True, help="canonical remote plus owner scope; stored as a hash")
        command.add_argument("--mode", choices=("off", "metadata"), default="off")
        if name == "collect":
            command.add_argument("--cursor", help="stable delivery ID if supplied by the source")
            command.add_argument("--scope-root", type=Path, help="ignore hooks outside this opted-in Git worktree")
        else:
            command.add_argument("--source-id", required=True, help="stable unique ID for this immutable hook JSONL export")
    for name in ("report", "scan"):
        commands.add_parser(name).add_argument("--format", choices=("markdown", "json"), default="markdown")
    commands.choices["scan"].add_argument("--details", action="store_true",
                                          help="name executables, subcommands and file paths in suggestions; never stored")
    for name in ("analyze", "propose"):
        command = commands.add_parser(name)
        command.add_argument("--repo", type=Path, default=Path.cwd())
        command.add_argument("--repository", help="same explicit identity used during collection, otherwise origin")
        if name == "analyze":
            command.add_argument("--format", choices=("markdown", "json"), default="markdown")
        else:
            command.add_argument("--issue", required=True)
            command.add_argument("--format", choices=("patch", "json"), default="patch")
    return root


def bounded_lines(stream):
    while True:
        raw = stream.readline(MAX_MESSAGE_BYTES + 1)
        if not raw:
            return
        oversized = len(raw) > MAX_MESSAGE_BYTES
        if oversized:
            while raw and not raw.endswith(b"\n"):
                raw = stream.readline(MAX_MESSAGE_BYTES + 1)
            yield b" " * (MAX_MESSAGE_BYTES + 1)
        else:
            yield raw


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command in ("collect", "ingest") and args.mode == "off":
        return 0
    store = None
    try:
        if args.command == "collect":
            raw = sys.stdin.buffer.read(MAX_MESSAGE_BYTES + 1)
            if args.scope_root and (len(raw) > MAX_MESSAGE_BYTES or not in_scope(raw, args.scope_root)):
                return 0
        elif args.command == "scan":
            labels, stats = {}, {"transcripts": 0, "tool_calls": 0, "tokens": 0, "seconds": 0}
            findings = diagnosis.analyze(scan.events(Path.home(), labels, stats, args.details))
            stats["seconds"] = round(stats["seconds"], 1)
            if args.format == "json":
                print(json.dumps({**stats, "repositories": labels, "findings": findings}, indent=2))
            else:
                print(diagnosis.markdown(findings, stats["tokens"]) + f"\nScanned {stats['transcripts']} transcripts, "
                      f"{stats['tool_calls']} tool calls, {stats['tokens']:,} tokens, "
                      f"{stats['seconds'] / 3600:.1f} h of tool steps. Findings can overlap.\n\nRepositories:\n"
                      + "".join(f"- {key[:12]}: {value}\n" for key, value in sorted(labels.items(), key=lambda item: item[1])),
                      end="")
            return 0
        store = Store(args.state_dir)
        if args.command == "report":
            rows = summarize(store.events())
            print(json.dumps(rows, indent=2) if args.format == "json" else markdown(rows), end="\n")
        elif args.command == "collect":
            event = normalize(raw, args.provider, args.repository, store.installation_id, args.cursor)
            store.append(event)
        elif args.command == "ingest":
            for offset, raw in enumerate(bounded_lines(sys.stdin.buffer)):
                cursor = f"{args.source_id}:{offset}"
                store.append(normalize(raw, args.provider, args.repository, store.installation_id, cursor))
        else:
            repo = root(args.repo)
            selected_repository = repository_id(identity(repo, args.repository))
            findings = diagnosis.analyze(event for event in store.events() if event["repository_id"] == selected_repository)
            if args.command == "analyze":
                print(json.dumps(findings, indent=2) if args.format == "json" else diagnosis.markdown(findings))
            else:
                finding = next((row for row in findings if row["issue_id"] == args.issue), None)
                if finding is None:
                    raise ProposalError("Issue not found for this repository in retained evidence; run analyze first.")
                proposal = propose(repo, finding)
                print(json.dumps(proposal, indent=2) if args.format == "json" else proposal["patch"], end="\n" if args.format == "json" else "")
        return 0
    except ProposalError as error:
        print(f"agent-feedback: {error}", file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error, ValueError, RecursionError, subprocess.SubprocessError):
        print("agent-feedback: local command failed; telemetry may be missing. "
              "Check state permissions and repository identity (--repository if origin is unavailable).", file=sys.stderr)
        return 0 if args.command == "collect" else 1
    finally:
        if store is not None:
            store.close()
