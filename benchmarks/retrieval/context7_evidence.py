"""Compare anonymous Context7 CLI against direct official-source retrieval."""

import json
from pathlib import Path
import re
from urllib.parse import urlparse

from collect_code import COUNTERS, read_session, usage_totals
from large import DIRECTORY, elapsed_seconds

MANIFEST = DIRECTORY / "context7-evidence-manifest.json"


def grade(answer, task, spec, expected):
    try:
        data = json.loads(answer)
    except (ValueError, TypeError):
        return dict(facts=False, evidence=False)
    if not isinstance(data, dict) or not isinstance(data.get("facts"), dict):
        return dict(facts=False, evidence=False)
    facts = data.get("version") == spec["version"] and all(
        type(data["facts"].get(k)) is type(v) and data["facts"][k] == v for k, v in expected.items())
    sources = data.get("sources", [])
    urls = [url for source in sources if isinstance(source, str)
            for url in re.findall(r"\]\((https://[^)]+)\)", source)] if isinstance(sources, list) else []
    official = []
    for url in urls:
        parsed = urlparse(url)
        if spec["package"] == "FastAPI":
            allowed = (parsed.hostname == "fastapi.tiangolo.com" or
                       parsed.hostname in ("github.com", "raw.githubusercontent.com")
                       and parsed.path.startswith("/fastapi/fastapi/"))
        else:
            allowed = (parsed.hostname == "zod.dev" or
                       parsed.hostname in ("github.com", "raw.githubusercontent.com")
                       and parsed.path.startswith("/colinhacks/zod/"))
        if allowed:
            official.append(url)
    pinned = any(re.search(r"(?:^|/)v?" + re.escape(spec["version"]) + r"(?:/|$)", urlparse(url).path)
                 for url in official)
    if task == "fastapi_lifetime":
        pinned = pinned or any(urlparse(url).hostname == "fastapi.tiangolo.com"
                               and urlparse(url).path.rstrip("/") == "/advanced/advanced-dependencies"
                               for url in official)
    evidence = (bool(official) and pinned and isinstance(data.get("version_evidence"), str)
                and spec["version"] in data["version_evidence"] and bool(data.get("approach")))
    return dict(facts=facts, evidence=evidence, official_urls=official)


def prepare():
    manifest = json.loads(MANIFEST.read_text())
    if manifest["trials"]:
        raise ValueError("Trials already prepared")
    root = Path(manifest["root"])
    for repeat in (1, 2):
        for index, (task, spec) in enumerate(manifest["tasks"].items()):
            arms = ("direct", "context7") if (repeat + index) % 2 else ("context7", "direct")
            for arm in arms:
                name = f"ctx_evidence_{manifest['stamp']}_{task}_{arm}_r{repeat}"
                workspace = root / name
                workspace.mkdir()
                method = ("Use direct official documentation/tagged-source lookup with web or shell tools. "
                          "Do not invoke Context7 CLI or any MCP retrieval service."
                          if arm == "direct" else
                          f"Use anonymous Context7 CLI {manifest['cli_version']} as your initial documentation route. "
                          f"Executable: {manifest['cli_executable']}. Use literal library and docs commands with "
                          "--json and CTX7_TELEMETRY_DISABLED=1. Resolve a real ID, prefer matching listed versions, "
                          "and never invent a version suffix. Verify source URLs/content cover the pinned version. "
                          "If coverage/query fails or is ambiguous, use official documentation/tagged source as "
                          "fallback and disclose that gap. Never use MCP, login/setup, API keys or saved credentials.")
                prompt = (
                    f"Authorized read-only documentation benchmark. Workspace: {workspace}. {method} "
                    "This trial overrides automatic retrieval-skill loading: do not read or apply any skill. "
                    "Do not inspect benchmark files, other trials, parent history, private data or credentials; "
                    "do not install dependencies, change configuration, delegate or commit. Public query output "
                    "may be saved only in your workspace. Do not guess facts from memory: retrieve evidence. "
                    f"Question: {spec['question']} "
                    f"Return ONLY a JSON object with version='{spec['version']}', facts containing exactly these "
                    f"keys: {', '.join(manifest['expected'][task])}. "
                    "Also include approach (short compatible API/schema example or explanation), sources "
                    "(Markdown links inside JSON strings, official sources only), version_evidence "
                    "(explain how you verified the exact version), and retrieval with library_id (null for "
                    "direct lookup), indexed_version_available (boolean/null), fallback_used (boolean). "
                    "Use JSON booleans for yes/no facts, API names and version numbers as strings; "
                    "cleanup_timing must be before_body or after_body. No markdown fence or trailing prose; "
                    "this JSON format overrides default final-answer style. Stop once all facts are supported.")
                manifest["trials"].append(dict(task=task, arm=arm, repeat=repeat,
                    agent=f"/root/{name}", path=str(workspace), prompt=prompt))
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["trials"][:3], indent=2))


def collect():
    import hashlib
    manifest = json.loads(MANIFEST.read_text())
    names = {t["agent"] for t in manifest["trials"]}
    sessions = {}
    for home in (Path.home() / ".codex", Path.home() / ".codex-work"):
        for path in (home / "sessions" / manifest["session_date"]).glob("*.jsonl"):
            with path.open() as stream:
                source = json.loads(next(stream)).get("payload", {}).get("source")
            spawn = source.get("subagent", {}).get("thread_spawn", {}) if isinstance(source, dict) else {}
            if spawn.get("agent_path") in names and spawn.get("parent_thread_id") == manifest["parent_thread_id"]:
                if spawn["agent_path"] in sessions:
                    raise ValueError("Duplicate session")
                sessions[spawn["agent_path"]] = path
    results = []
    for trial in manifest["trials"]:
        path = sessions.get(trial["agent"])
        if path is None:
            continue
        rows = read_session(path)
        done = [r["payload"] for r in rows if r["type"] == "event_msg" and r["payload"].get("type") == "task_complete"]
        if not done:
            continue
        records = [r["payload"] for r in rows if r["type"] == "token_usage_record"]
        usage = usage_totals(records)
        if any(usage[k] != records[-1]["thread_token_usage"][k] for k in COUNTERS):
            raise ValueError("Usage mismatch")
        calls = [p.get("name", "") + " " + str(p.get("input", p.get("arguments", "")))
                 for r in rows if r["type"] == "response_item"
                 and (p := r["payload"]).get("type") in ("function_call", "custom_tool_call")]
        commands = {m for call in calls for m in re.findall(r'''ctx7["']?\s+(library|docs)\b''', call)}
        forbidden = [c for c in calls if re.search(r"mcp__\w+\s*\(|code-retrieval/SKILL\.md|ctx7\s+(?:login|setup)", c)]
        method = not forbidden and (commands >= {"library", "docs"} if trial["arm"] == "context7" else not commands)
        answer = done[-1]["last_agent_message"]
        results.append(dict(**{k: trial[k] for k in ("task", "arm", "repeat", "agent")},
            session=str(path), session_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), answer=answer,
            grade=grade(answer, trial["task"], manifest["tasks"][trial["task"]], manifest["expected"][trial["task"]]),
            usage=usage, elapsed_seconds=elapsed_seconds(rows), method_compliant=method,
            observed_cli_commands=sorted(commands), excluded_reason=trial.get("excluded_reason"),
            contexts=sorted({(r["payload"]["model"], r["payload"].get("effort")) for r in rows if r["type"] == "turn_context"})))
    eligible = [r for r in results if not r["excluded_reason"]]
    pairs = {(r["task"], r["arm"], r["repeat"]) for r in eligible}
    expected = {(task, arm, repeat) for task in manifest["tasks"] for arm in ("direct", "context7") for repeat in (1, 2)}
    complete = len(results) == len(manifest["trials"])
    valid = (complete and pairs == expected and len(eligible) == len(expected)
             and all(r["method_compliant"] for r in eligible)
             and all(len(r["contexts"]) == 1 for r in eligible)
             and len({tuple(c) for r in eligible for c in r["contexts"]}) == 1)
    output = dict(complete=complete, valid_comparison=valid, results=results)
    MANIFEST.with_name("context7-evidence-results.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(dict(complete=complete, valid_comparison=valid, trials=len(results))))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "collect"))
    args = parser.parse_args()
    prepare() if args.action == "prepare" else collect()
