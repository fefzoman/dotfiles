"""Tool-specific retrieval trials, independently checked with Python's AST."""

import ast
import datetime
import hashlib
import json
import os
from pathlib import Path
import re

from collect_code import COUNTERS, read_session, usage_totals
from large import DIRECTORY, elapsed_seconds, run

MANIFEST = DIRECTORY / "specific-manifest.json"
SCOPES = {"shell_true": "Lib/test/test_subprocess.py", "raises_value": "Lib/test/test_asyncio/test_events.py"}
REQUESTS = {
    "shell_true": "List every Python call with a direct keyword argument shell=True (literal True). "
                  "Do not count comments, strings, definitions, or a keyword belonging to a nested call. "
                  "Keyword order and multiline formatting must not affect results.",
    "raises_value": "List every Python call to an attribute named assertRaises whose first positional "
                    "argument is exactly the name ValueError. Include context-manager and function-call "
                    "forms, including multiline calls; exclude strings, comments and other exceptions.",
}


def oracle(source, task):
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        match = (any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True
                     for k in node.keywords) if task == "shell_true" else
                 isinstance(node.func, ast.Attribute) and node.func.attr == "assertRaises" and node.args
                 and isinstance(node.args[0], ast.Name) and node.args[0].id == "ValueError")
        if match:
            found.append(dict(file=SCOPES[task], line=node.lineno))
    return sorted(found, key=lambda r: (r["file"], r["line"]))


def uses_ast_query(call):
    return bool(re.search(r"ast-grep\s+(?:run|scan)\s+(?!--help)\S", call)
                or re.search(r'''['"]ast-grep['"]\s*,\s*['"](?:run|scan)['"]\s*,\s*['"](?!--help)''', call))


def prepare():
    if MANIFEST.exists():
        raise ValueError("Preserve existing trials first")
    old = json.loads((DIRECTORY / "shell-manifest.json").read_text())
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    root = Path.home() / ".codex-work" / f"retrieval-specific-{stamp}"
    root.mkdir()
    corpus = root / "corpus"
    run(["git", "clone", "--local", "--quiet", old["trials"][0]["path"], str(corpus)], root, check=True)
    manifest = dict(root=str(root), corpus=str(corpus), parent_thread_id=os.environ["CODEX_THREAD_ID"],
                    session_date=datetime.datetime.now(datetime.timezone.utc).strftime("%Y/%m/%d"),
                    source_hashes={s: hashlib.sha256((corpus / s).read_bytes()).hexdigest() for s in SCOPES.values()},
                    expected={task: oracle((corpus / scope).read_text(), task) for task, scope in SCOPES.items()},
                    trials=[])
    for repeat in (1, 2):
        for index, (task, scope) in enumerate(SCOPES.items()):
            arms = ("shell", "ast") if (repeat + index) % 2 else ("ast", "shell")
            for arm in arms:
                name = f"specific_{stamp}_{task}_{arm}_r{repeat}"
                method = ("Use ordinary shell tools and Python standard library as needed; do not use ast-grep."
                          if arm == "shell" else
                          "Use ast-grep as the primary source-query engine; actually invoke it. "
                          "Shell and Python standard library may process or verify its output. "
                          "Use installed help if needed; do not assume a pattern handles keyword order.")
                prompt = (f"Authorized read-only retrieval benchmark. Work in {corpus}. {method} "
                          "Do not read any retrieval skill, use other MCP/CLI retrieval services, delegate, "
                          "install tools, access git history, modify files or commit. "
                          f"Inspect only {scope} and installed tool help. Task: {REQUESTS[task]} "
                          "Return ONLY a JSON array of objects with keys file (the supplied relative path) "
                          "and line (the call's starting line, 1-based), sorted by file and line. "
                          "No markdown or explanatory text. Verify completeness, then stop.")
                manifest["trials"].append(dict(task=task, arm=arm, repeat=repeat, agent=f"/root/{name}", prompt=prompt))
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["trials"], indent=2))


def collect():
    manifest = json.loads(MANIFEST.read_text())
    corpus = Path(manifest["corpus"])
    if run(["git", "status", "--porcelain"], corpus, check=True).stdout:
        raise ValueError("Read-only corpus changed")
    for source, digest in manifest["source_hashes"].items():
        if hashlib.sha256((corpus / source).read_bytes()).hexdigest() != digest:
            raise ValueError("Source changed")
    sessions = {}
    for home in (Path.home() / ".codex", Path.home() / ".codex-work"):
        for path in (home / "sessions" / manifest["session_date"]).glob("*.jsonl"):
            with path.open() as stream:
                first = json.loads(next(stream))
            source = first.get("payload", {}).get("source")
            spawn = source.get("subagent", {}).get("thread_spawn", {}) if isinstance(source, dict) else {}
            if spawn.get("parent_thread_id") == manifest["parent_thread_id"]:
                name = spawn.get("agent_path")
                if name in {t["agent"] for t in manifest["trials"]}:
                    if name in sessions:
                        raise ValueError("Duplicate agent session")
                    sessions[name] = path
    results = []
    for trial in manifest["trials"]:
        path = sessions.get(trial["agent"])
        if path is None:
            continue
        rows = read_session(path)
        completions = [r["payload"] for r in rows if r["type"] == "event_msg" and r["payload"].get("type") == "task_complete"]
        if not completions:
            continue
        records = [r["payload"] for r in rows if r["type"] == "token_usage_record"]
        usage = usage_totals(records)
        if any(usage[k] != records[-1]["thread_token_usage"][k] for k in COUNTERS):
            raise ValueError("Usage mismatch")
        answer = completions[-1]["last_agent_message"]
        try:
            correct = json.loads(answer) == manifest["expected"][trial["task"]]
        except (ValueError, TypeError):
            correct = False
        calls = [p.get("name", "") + " " + str(p.get("input", p.get("arguments", "")))
                 for r in rows if r["type"] == "response_item"
                 and (p := r["payload"]).get("type") in ("function_call", "custom_tool_call")]
        ast_calls = [c for c in calls if uses_ast_query(c)]
        forbidden = [c for c in calls if re.search(r"mcp__\w+\s*\(|ctx7\s|code-retrieval/SKILL\.md", c)]
        results.append(dict(**{k: trial[k] for k in ("task", "arm", "repeat", "agent")},
                            session=str(path), session_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            usage=usage, elapsed_seconds=elapsed_seconds(rows), correct=correct, answer=answer,
                            excluded_reason=trial.get("excluded_reason"),
                            method_compliant=not forbidden and bool(ast_calls) == (trial["arm"] == "ast"),
                            contexts=sorted({(r["payload"]["model"], r["payload"].get("effort"))
                                             for r in rows if r["type"] == "turn_context"})))
    complete = len(results) == len(manifest["trials"])
    eligible = [r for r in results if not r["excluded_reason"]]
    pairs = {(r["task"], r["arm"], r["repeat"]) for r in eligible}
    expected = {(task, arm, repeat) for task in manifest["expected"] for arm in ("shell", "ast") for repeat in (1, 2)}
    valid = (complete and pairs == expected and len(eligible) == len(expected)
             and all(r["correct"] and r["method_compliant"] for r in eligible))
    valid = valid and all(len(r["contexts"]) == 1 for r in eligible) and len({tuple(c) for r in eligible for c in r["contexts"]}) == 1
    output = dict(complete=complete, valid_comparison=valid, results=results)
    (DIRECTORY / "specific-results.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"complete": complete, "valid_comparison": valid, "trials": len(results)}))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "collect"))
    args = parser.parse_args()
    prepare() if args.action == "prepare" else collect()
