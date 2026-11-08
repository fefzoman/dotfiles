"""Repeat full-repository trials with shell, old skill, dispatcher, and Context7 CLI."""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex

from large import DIRECTORY, TASKS, collect, grade, run, tests_digest

MANIFEST = DIRECTORY / "cli-manifest.json"
ARMS = ("shell", "previous_skill", "dispatcher", "context7_cli")


def prepare():
    if MANIFEST.exists():
        raise ValueError("Preserve existing results; never overwrite or reuse measured trials")
    old = json.loads((DIRECTORY / "large-manifest.json").read_text())
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    agent_prefix = "cli_" + stamp.replace("-", "_")
    root = Path.home() / ".codex-work" / f"retrieval-cli-{stamp}"
    root.mkdir()
    previous = root / "previous-code-retrieval" / "SKILL.md"
    previous.parent.mkdir()
    original = run(["git", "show", "54cdc6f:llm/skills/code-retrieval/SKILL.md"], DIRECTORY, check=True).stdout
    retired = " For code symbol relationships or nested definitions that text boundaries cannot establish safely, use the existing Serena session when available."
    if original.count(retired) != 1:
        raise ValueError("Unexpected previous skill baseline")
    previous.write_text(original.replace(retired, ""))
    dispatcher = DIRECTORY.parents[1] / "llm/skills/code-retrieval/SKILL.md"
    executable = Path.home() / ".codex-work/context7-cli/node_modules/.bin/ctx7"
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", ""))
    if not config_home.is_absolute():
        config_home = Path.home() / ".config"
    if os.environ.get("CONTEXT7_API_KEY") or any(p.exists() for p in (
            config_home / "context7/credentials.json", Path.home() / ".context7/credentials.json")):
        raise ValueError("This experiment requires an anonymous CLI environment")
    version = run([str(executable), "--version"], root, check=True).stdout.strip()
    manifest = dict(root=str(root), arms=ARMS, transport="cli", repeats=2,
                    parent_thread_id=os.environ["CODEX_THREAD_ID"],
                    session_date=datetime.datetime.now(datetime.timezone.utc).strftime("%Y/%m/%d"),
                    fork_turns="none", max_parallel_workers=3, agent_prefix=agent_prefix,
                    cli_executable=str(executable), cli_version=version,
                    repository=old["repository"], revision=old["revision"], tracked_files=old["tracked_files"],
                    python_files=old["python_files"], python_lines=old["python_lines"],
                    python_executable=old["python_executable"],
                    tool_names=[], agents={}, trials=[],
                    previous_skill_revision="54cdc6f", previous_skill_normalization="Remove only retired Serena escalation sentence",
                    skill_files={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
                        previous, dispatcher, *sorted((dispatcher.parent / "references").glob("*.md")))})
    for repeat in (1, 2):
        for index, (task, spec) in enumerate(TASKS.items()):
            baseline = next(t for t in old["trials"] if t["task"] == task and t["arm"] == "skill")
            for arm in ARMS[(index + repeat) % 4:] + ARMS[:(index + repeat) % 4]:
                key = f"{task}_{arm}_r{repeat}"
                workspace = root / key
                run(["git", "clone", "--local", "--quiet", baseline["path"], str(workspace)], root, check=True)
                head = run(["git", "rev-parse", "HEAD"], workspace, check=True).stdout.strip()
                if head != baseline["baseline_commit"] or tests_digest(workspace) != baseline["tests_sha256"]:
                    raise ValueError(f"Nonidentical baseline: {key}")
                source = workspace / baseline["allowed_file"]
                if hashlib.sha256(source.read_bytes()).hexdigest() != baseline["source_sha256"]:
                    raise ValueError(f"Already-fixed source: {key}")
                baseline_grade = grade(workspace, baseline["command"], root / f"{key}-baseline.log")
                if not baseline_grade["exit_code"]:
                    raise ValueError(f"Seeded baseline unexpectedly passes: {key}")
                skill = str(previous) if arm == "previous_skill" else str(dispatcher) if arm == "dispatcher" else None
                method = (f"Read and apply ONLY the retrieval skill at {skill}. Read its optional references only when needed."
                          if skill else "Do not load or apply any retrieval skill, including the automatically named code-retrieval skill.")
                if arm == "shell":
                    method += " Use ordinary shell source retrieval. Do not use Context7 CLI or any MCP tools."
                elif arm == "context7_cli":
                    method += " Use ordinary shell source retrieval. Before editing, use literal ctx7 library and ctx7 docs commands to verify the relevant Python 3.14 contract. Verify the returned source version."
                else:
                    method += " Use Context7 CLI only for an unresolved version-sensitive contract, not reflexively."
                prompt = (
                    f"One authorized isolated implementation trial. Work only in {workspace}, a complete CPython v3.14.0 checkout. "
                    "This prompt controls retrieval for the benchmark: do not automatically read any other installed retrieval skill. "
                    "Serena has been removed from persisted setup; the current runtime may expose stale tool names. "
                    "Do not call Serena, its manual, or Context7 MCP. Do not initialize removed backends. "
                    f"{method}\n\nFix this seeded regression: {spec['request']}\n\n"
                    f"The official ctx7 {version} executable is {executable}; use that literal path or prepend its parent to PATH. "
                    "Use --json noninteractively, with CTX7_TELEMETRY_DISABLED=1 and no credentials or API keys. "
                    "Never run ctx7 setup/login or use saved authentication. If anonymous queries fail, report the failure and use matching official docs, never silently rely on memory. "
                    "Discover the implementation and trace affected callers and existing tests before editing. "
                    "Change only the existing implementation file needed for this fix. Do not alter tests, docs, configs, "
                    "or unrelated code. Do not fetch upstream answers, use git history to recover the answer, "
                    "install dependencies, create indexes/embeddings, delegate, launch CLI agents, or commit. "
                    "Existing tests cover the regression; do not add tests in this controlled trial. "
                    f"Run in your workspace: PYTHONPATH=Lib {shlex.join(baseline['command'])}\n"
                    "Inspect the final diff. Final answer under 100 words: fix, checks, limitations. Stop after this one task.")
                prompt_path = root / f"{key}-prompt.txt"
                prompt_path.write_text(prompt)
                name = f"/root/{agent_prefix}_{key}"
                manifest["agents"][name] = [task, arm]
                manifest["trials"].append(dict(task=task, arm=arm, repeat=repeat, agent=name, path=str(workspace),
                    prompt=prompt, prompt_path=str(prompt_path), skill_path=skill, command=baseline["command"],
                    allowed_file=baseline["allowed_file"], baseline_commit=head, tests_sha256=baseline["tests_sha256"],
                    source_sha256=baseline["source_sha256"], baseline_grade=baseline_grade))
                print(f"Prepared {key}", flush=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(root, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "collect"))
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    else:
        collect(MANIFEST)
