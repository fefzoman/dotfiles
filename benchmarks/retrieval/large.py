"""Prepare full-repository trials; collect usage from native agents, never CLI agents."""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from collect_code import COUNTERS, method_compliant, read_session, usage_totals

DIRECTORY = Path(__file__).resolve().parent
MANIFEST = DIRECTORY / "large-manifest.json"
ARMS = ("skill", "serena", "context7")
REVISION = "ebf955df7a89ed0c7968f79faec1de49f61ed7cb"
TASKS = {
    "conflicts": dict(
        file="Lib/argparse.py", module="test_argparse",
        old="if not action.option_strings:\n                action.container._remove_action(action)",
        new="if action.option_strings:\n                action.container._remove_action(action)",
        request="The command-line parser's conflict_handler='resolve' leaves obsolete actions in "
                "help/usage after an option is replaced. Fix conflict resolution so fully replaced "
                "actions leave their owning container, while actions retaining non-conflicting "
                "aliases remain usable and visible. Preserve the default conflict error behavior, "
                "argument groups, and parent parsers."),
    "interpolation": dict(
        file="Lib/configparser.py", module="test_configparser",
        old="dict(parser.items(sect, raw=True)),",
        new="dict(parser.items(section, raw=True)),",
        request="Extended configuration interpolation resolves nested ${section:option} values "
                "against the caller's section rather than the referenced section. Fix the shared "
                "recursive path so nested unqualified references use the referenced section and "
                "its defaults. Preserve custom option normalization, raw reads, missing-option "
                "errors, and bounded cycle detection."),
    "symlinks": dict(
        file="Lib/pathlib/__init__.py", module="test_pathlib",
        old="self.stat(follow_symlinks=follow_symlinks).st_mode",
        new="self.stat().st_mode",
        request="The object-oriented filesystem path API's file and directory classification "
                "follows symlinks even when follow_symlinks=False. Fix both classification methods "
                "at their shared implementation layer. Real files/directories must still classify "
                "correctly; symlinks must not classify as their targets when following is disabled. "
                "Preserve default following behavior and existing missing/invalid-path handling."),
}


def run(argv, cwd, **kwargs):
    return subprocess.run(argv, cwd=cwd, text=True, capture_output=True, **kwargs)


def tests_digest(workspace):
    paths = run(["git", "ls-files", "-z", "Lib/test"], workspace, check=True).stdout.split("\0")
    digest = hashlib.sha256()
    for name in sorted(filter(None, paths)):
        digest.update(name.encode() + b"\0" + (workspace / name).read_bytes())
    return digest.hexdigest()


def grade(workspace, command, log):
    result = run(command, workspace, env=dict(os.environ, PYTHONPATH=str(workspace / "Lib")),
                 timeout=120)
    log.write_text(result.stdout + result.stderr)
    return dict(exit_code=result.returncode, log=str(log))


def source_scope_ok(changed, untracked, allowed_file, head, baseline):
    return (head == baseline and changed == [allowed_file]
            and all(f.startswith(".serena/") for f in untracked))


def mcp_calls(call, tool_names):
    calls = re.findall(r"(?:tools\.)?(mcp__serena__\w+|mcp__context7__\w+)\s*\(", call)
    direct = re.match(r"^(mcp__(?:serena|context7)__\w+)\s", call)
    if direct:
        calls.append(direct[1])
    selectors = re.findall(
        r"(\w+)\s*=\s*ALL_TOOLS\.find\(\w+\s*=>\s*/([^/]+)/([i]*)\.test\(\w+\.name\)\)", call)
    for variable, pattern, flags in selectors:
        if not re.search(rf"tools\[{re.escape(variable)}\.name\]\s*\(", call):
            continue
        matches = [name for name in tool_names if re.search(pattern, name, re.I if flags else 0)]
        if len(matches) != 1:
            raise ValueError(f"Ambiguous dynamic tool selector: {pattern}")
        calls.extend(matches)
    return calls


def prepare(base, root, python):
    if MANIFEST.exists() or root.exists():
        raise ValueError("Use fresh manifest and workspace paths; existing trials are never overwritten")
    revision = run(["git", "rev-parse", "HEAD"], base, check=True).stdout.strip()
    if revision != REVISION or run(["git", "status", "--porcelain"], base, check=True).stdout:
        raise ValueError("Preparation requires a clean checkout of the pinned CPython revision")
    files = run(["git", "ls-files", "-z"], base, check=True).stdout.split("\0")
    files = [base / f for f in files if f]
    pyfiles = [f for f in files if f.suffix == ".py"]
    skill = DIRECTORY.parents[1] / "llm/skills/code-retrieval/SKILL.md"
    manifest = dict(
        root=str(root), repository="https://github.com/python/cpython", tag="v3.14.0",
        revision=revision,
        tracked_files=len(files), python_files=len(pyfiles),
        python_lines=sum(f.read_bytes().count(b"\n") for f in pyfiles),
        tracked_bytes=sum(f.stat().st_size for f in files),
        python_executable=str(python),
        python=run([str(python), "--version"], base, check=True).stdout.strip(),
        parent_thread_id=os.environ["CODEX_THREAD_ID"],
        session_date=datetime.datetime.now(datetime.timezone.utc).strftime("%Y/%m/%d"),
        skill=str(skill), skill_sha256=hashlib.sha256(skill.read_bytes()).hexdigest(),
        tool_names=["mcp__context7__resolve_library_id", "mcp__context7__query_docs"],
        fork_turns="none", max_parallel_workers=3,
        agents={}, trials=[])
    root.mkdir(parents=True)
    instructions = {
        "skill": f"Read and apply {skill}. Use skill-guided shell source retrieval. Do not use "
                 "Serena source tools or Context7.",
        "serena": "Do NOT read, load, or apply any retrieval skill, including code-retrieval. "
                  "Use the existing Serena MCP server as your primary source retrieval method. "
                  "Read its manual once, activate this workspace with that session ID, and use "
                  "symbol and reference tools. Do not use Context7 or start another server.",
        "context7": "Do NOT read, load, or apply any retrieval skill, including code-retrieval. "
                    "Use ordinary shell tools for local source retrieval. Resolve Python in "
                    "Context7 anonymously and query the Python 3.14 documentation relevant to "
                    "the reported behavior before editing. Do not use Serena source tools. "
                    "If 3.14 is unavailable, report the returned version; do not claim it matched.",
    }
    for index, (task, spec) in enumerate(TASKS.items()):
        command = [str(python), "-m", "test", "-q", spec["module"]]
        upstream = grade(base, command, root / f"{task}-upstream.log")
        if upstream["exit_code"]:
            raise ValueError(f"Upstream tests failed: {upstream}")
        for arm in ARMS[index:] + ARMS[:index]:
            workspace = root / f"{task}-{arm}"
            shutil.copytree(base, workspace, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            source = workspace / spec["file"]
            original = source.read_text()
            expected = 2 if task == "symlinks" else 1
            if original.count(spec["old"]) != expected:
                raise ValueError(f"Unexpected seed locations: {task}")
            source.write_text(original.replace(spec["old"], spec["new"]))
            run(["git", "init", "-q"], workspace, check=True)
            run(["git", "add", "."], workspace, check=True)
            run(["git", "-c", "user.name=Benchmark", "-c", "user.email=benchmark@localhost",
                 "commit", "-qm", "Seed isolated benchmark baseline"], workspace, check=True)
            (workspace / ".serena").mkdir()
            (workspace / ".serena/project.yml").write_text(
                f"project_name: large-{task}-{arm}\nlanguages: [python]\n"
                "encoding: utf-8\nread_only: false\nignored_paths: []\n")
            baseline = grade(workspace, command, root / f"{task}-{arm}-baseline.log")
            if not baseline["exit_code"]:
                raise ValueError(f"Seeded regression did not fail: {task}")
            prompt = (
                f"Authorized parallel large-repository code benchmark, one isolated trial. "
                f"Work only in {workspace}, a full pinned CPython v3.14.0 checkout with a seeded "
                f"regression. {instructions[arm]}\n\nImplement this fix: {spec['request']}\n\n"
                "Discover the implementation and trace affected callers and existing tests before "
                "editing. Change only the existing implementation source file(s) needed for this "
                "fix. Do not change tests, docs, configs, or unrelated code. Do not fetch upstream "
                "code, use git history to recover the answer, install dependencies, create indexes "
                "or embeddings, delegate, launch CLI agents, or commit. Tests already cover the "
                "regression; do not add tests for this controlled experiment. "
                f"Run the existing tests with this exact command in your workspace: "
                f"PYTHONPATH=Lib {shlex.join(command)} . The final period is punctuation, not an "
                "argument. Inspect the final diff. Keep your final answer below 100 words: "
                "fix, checks, limitations. Stop after completing this one implementation task.")
            name = f"/root/large_{task}_{arm}"
            manifest["agents"][name] = [task, arm]
            manifest["trials"].append(dict(
                task=task, arm=arm, path=str(workspace), prompt=prompt, command=command,
                allowed_file=spec["file"], source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                baseline_commit=run(["git", "rev-parse", "HEAD"], workspace, check=True).stdout.strip(),
                tests_sha256=tests_digest(workspace), baseline_grade=baseline, upstream_grade=upstream))
            print(f"Prepared {task}/{arm}: upstream passed, regression failed", flush=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


def cli_method_compliant(trial, calls, skill_reads, cli_commands):
    if calls:
        return False
    expected = trial.get("skill_path")
    if not expected and skill_reads:
        return False
    observed = {path for call in skill_reads
                for path in re.findall(r"/[^\s\"'`\\]+code-retrieval/SKILL\.md", call)}
    if observed != ({expected} if expected else set()):
        return False
    if trial["arm"] == "shell":
        return not cli_commands
    if trial["arm"] == "context7_cli":
        return {"library", "docs"} <= set(cli_commands)
    return True


def collect(manifest_path=MANIFEST):
    manifest = json.loads(manifest_path.read_text())
    for name, digest in manifest.get("skill_files", {}).items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Skill changed during experiment: {name}")
    sessions = {}
    for home in (Path.home() / ".codex", Path.home() / ".codex-work"):
        for path in (home / "sessions" / manifest["session_date"]).glob("*.jsonl"):
            with path.open() as stream:
                first = json.loads(next(stream))
            source = first.get("payload", {}).get("source")
            if not isinstance(source, dict):
                continue
            spawn = source.get("subagent", {}).get("thread_spawn", {})
            name = spawn.get("agent_path")
            if name in manifest["agents"] and spawn.get("parent_thread_id") == manifest["parent_thread_id"]:
                if name in sessions:
                    raise ValueError(f"Multiple sessions for {name}")
                sessions[name] = path
    results = []
    for trial in manifest["trials"]:
        name = trial.get("agent") or next(n for n, pair in manifest["agents"].items() if pair == [trial["task"], trial["arm"]])
        if name not in sessions:
            continue
        path = sessions[name]
        rows = read_session(path)
        if not any(r["type"] == "event_msg" and r["payload"].get("type") == "task_complete" for r in rows):
            continue
        records = [r["payload"] for r in rows if r["type"] == "token_usage_record"]
        totals = usage_totals(records)
        if any(totals[k] != records[-1].get("thread_token_usage", {}).get(k) for k in COUNTERS):
            raise ValueError(f"Usage aggregate mismatch: {name}")
        workspace = Path(trial["path"])
        if tests_digest(workspace) != trial["tests_sha256"]:
            raise ValueError(f"Tests modified: {name}")
        changed = run(["git", "diff", "HEAD", "--name-only"], workspace, check=True).stdout.splitlines()
        untracked = run(["git", "ls-files", "--others", "--exclude-standard"], workspace, check=True).stdout.splitlines()
        head = run(["git", "rev-parse", "HEAD"], workspace, check=True).stdout.strip()
        scope_ok = source_scope_ok(changed, untracked, trial["allowed_file"], head, trial["baseline_commit"])
        patch = run(["git", "diff", "HEAD"], workspace, check=True).stdout
        grade_result = grade(workspace, trial["command"], Path(manifest["root"]) / f"{workspace.name}-grade.log")
        contexts = sorted({(r["payload"].get("model"), r["payload"].get("effort"))
                           for r in rows if r["type"] == "turn_context"})
        calls, skill_reads, cli_commands = [], [], []
        for row in rows:
            p = row["payload"]
            if row["type"] != "response_item" or p.get("type") not in ("function_call", "custom_tool_call"):
                continue
            call = p.get("name", "") + " " + str(p.get("input", p.get("arguments", "")))
            calls.extend(mcp_calls(call, manifest["tool_names"]))
            if "code-retrieval/SKILL.md" in call:
                skill_reads.append(call)
            cli_commands.extend(re.findall(r"ctx7[\"']?\s+(library|docs|search)\b", call))
        if manifest.get("transport") == "cli":
            method_ok = cli_method_compliant(trial, calls, skill_reads, cli_commands)
        else:
            method_ok = method_compliant(trial["arm"], calls)
            method_ok = method_ok and (bool(skill_reads) if trial["arm"] == "skill" else not skill_reads)
        results.append(dict(task=trial["task"], arm=trial["arm"], agent=name, session=str(path),
                            session_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), usage=totals,
                            per_response_usage=records, contexts=contexts, grade=grade_result,
                            source_scope_ok=scope_ok, tests_unchanged=True, patch=patch,
                            observed_mcp_calls=calls, skill_read_calls=skill_reads,
                            observed_cli_commands=cli_commands, repeat=trial.get("repeat", 1),
                            method_compliant=method_ok))
    summary = {}
    for arm in manifest.get("arms", ARMS):
        group = [r for r in results if r["arm"] == arm]
        summary[arm] = dict(trials=len(group), tests_pass=sum(r["grade"]["exit_code"] == 0 for r in group),
                            **{k: sum(r["usage"][k] for r in group) for k in (*COUNTERS, "calls", "total_tokens", "uncached_input_tokens")})
    complete = len(results) == len(manifest["trials"])
    valid = complete and all(r["grade"]["exit_code"] == 0 and r["source_scope_ok"] and r["method_compliant"] for r in results)
    valid = (valid and all(len(r["contexts"]) == 1 for r in results)
             and len({tuple(c) for r in results for c in r["contexts"]}) == 1)
    status = "complete" if complete else "blocked" if manifest.get("blocked_reason") else "in progress"
    document = dict(status=status, valid_comparison=valid, blocked_reason=manifest.get("blocked_reason"),
                    collected_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    manifest=str(manifest_path), summary=summary, results=results)
    manifest_path.with_name(manifest_path.name.replace("manifest", "results")).write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps(dict(status=document["status"], valid_comparison=valid, summary=summary), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "collect"))
    parser.add_argument("--base", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--python", type=Path, default=Path("/opt/homebrew/bin/python3.14"))
    args = parser.parse_args()
    if args.action == "collect":
        collect()
    elif not args.base or not args.root:
        parser.error("prepare requires --base and --root")
    else:
        prepare(args.base.resolve(), args.root.resolve(), args.python.resolve())
