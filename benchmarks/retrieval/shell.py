"""Compare shell-only and dispatcher trials without altering historical runs."""

import argparse
import datetime
import hashlib
import json
import os
import re
from pathlib import Path
import shlex
import statistics
import time

from large import DIRECTORY, TASKS, collect, grade, run, tests_digest

MANIFEST = DIRECTORY / "shell-manifest.json"
ARMS = ("shell", "baseline", "optimized")
BASELINE_REVISION = "7e404af"


def prepare():
    if MANIFEST.exists():
        raise ValueError("Preserve existing trials before preparing another experiment")
    old = json.loads((DIRECTORY / "cli-manifest.json").read_text())
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    root = Path.home() / ".codex-work" / f"retrieval-shell-{stamp}"
    root.mkdir()
    skills = {}
    for arm in ARMS[1:]:
        directory = root / arm / "code-retrieval"
        (directory / "references").mkdir(parents=True)
        for relative in ("SKILL.md", "references/local-code.md", "references/library-docs.md"):
            source = f"llm/skills/code-retrieval/{relative}"
            content = (run(["git", "show", f"{BASELINE_REVISION}:{source}"], DIRECTORY, check=True).stdout
                       if arm == "baseline" else (DIRECTORY.parents[1] / source).read_text())
            (directory / relative).write_text(content)
        skills[arm] = str(directory / "SKILL.md")
    manifest = dict(root=str(root), arms=ARMS, transport="cli", repeats=2,
                    parent_thread_id=os.environ["CODEX_THREAD_ID"],
                    session_date=datetime.datetime.now(datetime.timezone.utc).strftime("%Y/%m/%d"),
                    fork_turns="none", max_parallel_workers=3, tool_names=[], agents={}, trials=[],
                    repository=old["repository"], revision=old["revision"],
                    baseline_skill_revision=BASELINE_REVISION,
                    python_executable=old["python_executable"],
                    setup_revision=run(["git", "rev-parse", "HEAD"], DIRECTORY, check=True).stdout.strip(),
                    skill_files={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in root.glob("*/code-retrieval/**/*.md")},
                    tools={name: run([name, "--version"], root, check=True).stdout
                           for name in ("rg", "ag", "ack", "ast-grep")})
    for repeat in (1, 2):
        for index, (task, spec) in enumerate(TASKS.items()):
            baseline = next(t for t in old["trials"] if t["task"] == task)
            offset = (index + repeat) % len(ARMS)
            for arm in ARMS[offset:] + ARMS[:offset]:
                key = f"{task}_{arm}_r{repeat}"
                workspace = root / key
                run(["git", "clone", "--local", "--quiet", baseline["path"], str(workspace)], root, check=True)
                head = run(["git", "rev-parse", "HEAD"], workspace, check=True).stdout.strip()
                source_hash = hashlib.sha256((workspace / baseline["allowed_file"]).read_bytes()).hexdigest()
                if (head != baseline["baseline_commit"] or source_hash != baseline["source_sha256"]
                        or tests_digest(workspace) != baseline["tests_sha256"]):
                    raise ValueError(f"Nonidentical seeded baseline: {key}")
                seed_grade = grade(workspace, baseline["command"], root / f"{key}-baseline.log")
                if not seed_grade["exit_code"]:
                    raise ValueError(f"Seed unexpectedly passes: {key}")
                skill = skills.get(arm)
                method = (f"Read and apply ONLY {skill}; optional references only when needed."
                          if skill else "Do not read or apply any retrieval skill. Use ordinary shell retrieval.")
                prompt = (
                    f"Authorized isolated benchmark trial. Work only in {workspace}, full CPython v3.14.0. "
                    f"{method} This trial overrides automatic retrieval-skill loading. "
                    "Use installed tools only. Do not use Context7 CLI or MCP, Serena, other MCP retrieval, "
                    "upstream answers, git history, indexes, embeddings, dependencies, agents or delegation. "
                    f"Fix this seeded regression: {spec['request']} "
                    "Discover implementation, trace callers/tests, preserve validation and error handling. "
                    "Change only the existing implementation file. Do not alter tests/docs/configs or commit. "
                    "Existing tests cover the regression; add none for this controlled trial. "
                    f"Run PYTHONPATH=Lib {shlex.join(baseline['command'])} . "
                    "The final period is punctuation. Inspect final diff. Final answer under 100 words: "
                    "fix, checks, limitations. Stop after this one task.")
                prompt_path = root / f"{key}-prompt.txt"
                prompt_path.write_text(prompt)
                name = f"/root/shell_{stamp.replace('-', '_')}_{key}"
                manifest["agents"][name] = [task, arm]
                manifest["trials"].append(dict(task=task, arm=arm, repeat=repeat, agent=name,
                    path=str(workspace), prompt=prompt, prompt_path=str(prompt_path), skill_path=skill, forbid_cli=True,
                    command=baseline["command"], allowed_file=baseline["allowed_file"], baseline_commit=head,
                    tests_sha256=baseline["tests_sha256"], source_sha256=source_hash, baseline_grade=seed_grade))
                print(f"Prepared {key}", flush=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(root, flush=True)


def microbench():
    destination = DIRECTORY / "shell-microbench.json"
    if destination.exists():
        raise ValueError("Preserve existing microbenchmark results first")
    old = json.loads((DIRECTORY / "cli-manifest.json").read_text())
    workspace = Path(next(t["path"] for t in old["trials"] if t["task"] == "symlinks"))
    path = "Lib/pathlib/__init__.py"
    commands = {
        "rg": ["rg", "-H", "-n", "-F", "-m", "20", "--", "def is_dir", path],
        "ag": ["ag", "--vimgrep", "--nocolor", "-Q", "-m", "20", "--", "def is_dir", path],
        "ack": ["ack", "--no-filter", "-H", "--nocolor", "--noheading", "-Q", "--max-count=20", "--", "def is_dir", path],
        "ast-grep": ["ast-grep", "run", "--lang", "python", "--pattern", "self.stat()",
                     "--color", "never", path],
    }
    results = {}
    text_lines = []
    for name, command in commands.items():
        run(command, workspace, check=True)
        durations = []
        for _ in range(9):
            start = time.perf_counter()
            result = run(command, workspace, check=True)
            durations.append(time.perf_counter() - start)
        if name != "ast-grep":
            lines = [line.removeprefix(path + ":") for line in result.stdout.splitlines()]
            text_lines.append([re.sub(r"^(\d+):\d+:", r"\1:", line) for line in lines]
                              if name == "ag" else lines)
        results[name] = dict(command=command, median_seconds=statistics.median(durations),
                             output_bytes=len(result.stdout.encode()), output_lines=len(result.stdout.splitlines()))
    if not text_lines[0] or not all(lines == text_lines[0] for lines in text_lines):
        raise ValueError("Text tools returned different results; do not compare speed")
    destination.write_text(json.dumps(dict(workspace=str(workspace), warmups=1, repeats=9,
        source_sha256=hashlib.sha256((workspace / path).read_bytes()).hexdigest(),
        tools={name: run([name, "--version"], workspace, check=True).stdout for name in commands},
        note="Warm-cache subprocess wall time, including startup. AST query differs; no model-token measurement.",
        results=results), indent=2) + "\n")
    print(destination.read_text())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "collect", "microbench"))
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "microbench":
        microbench()
    else:
        collect(MANIFEST)
