"""Grade isolated code trials and aggregate native-agent per-response token usage."""

import datetime
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = Path(__file__).resolve().parent
COUNTERS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
            "output_tokens", "reasoning_output_tokens")


def usage_totals(records):
    unique = {}
    for record in records:
        response = record["response_id"]
        if response in unique and unique[response] != record["usage"]:
            raise ValueError("Conflicting usage for the same response")
        usage = record["usage"]
        for key in COUNTERS:
            if type(usage.get(key)) is not int or usage[key] < 0:
                raise ValueError(f"Missing or invalid usage: {key}")
        if usage["cached_input_tokens"] + usage["cache_write_input_tokens"] > usage["input_tokens"]:
            raise ValueError("Cached/written input exceeds input")
        if usage["reasoning_output_tokens"] > usage["output_tokens"]:
            raise ValueError("Reasoning exceeds output")
        unique[response] = usage
    if not unique:
        raise ValueError("No per-response usage records")
    result = {key: sum(u[key] for u in unique.values()) for key in COUNTERS}
    return dict(result, calls=len(unique),
                total_tokens=result["input_tokens"] + result["output_tokens"],
                uncached_input_tokens=result["input_tokens"] - result["cached_input_tokens"])


def read_session(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def method_compliant(arm, calls):
    retrieval = [c for c in calls if c != "mcp__serena__initial_instructions"]
    if arm == "skill":
        return not retrieval
    if arm == "serena":
        return (any(c.startswith("mcp__serena__find_") for c in retrieval)
                and not any(c.startswith("mcp__context7__") for c in retrieval))
    return ("mcp__context7__query_docs" in retrieval
            and not any(c.startswith("mcp__serena__") for c in retrieval))


def main():
    manifest = json.loads((DIRECTORY / "code-manifest.json").read_text())
    trials = {(t["task"], t["arm"]): t for t in manifest["trials"]}
    sessions = {}
    for home in (Path.home() / ".codex", Path.home() / ".codex-work"):
        directory = home / "sessions" / manifest["session_date"]
        for path in directory.glob("*.jsonl"):
            with path.open() as stream:
                first = json.loads(next(stream))
            if first["type"] != "session_meta":
                continue
            source = first["payload"].get("source")
            if not isinstance(source, dict):
                continue
            spawn = source.get("subagent", {}).get("thread_spawn", {})
            name = spawn.get("agent_path", "")
            if name in manifest["agents"] and spawn.get("parent_thread_id") == manifest["parent_thread_id"]:
                if name in sessions:
                    raise ValueError(f"Multiple sessions for {name}")
                sessions[name] = path
    results = []
    for name, identity in manifest["agents"].items():
        task, arm = identity
        if name not in sessions:
            continue
        path = sessions[name]
        rows = read_session(path)
        completed = any(r["type"] == "event_msg" and r["payload"].get("type") == "task_complete" for r in rows)
        if not completed:
            continue
        records = [r["payload"] for r in rows if r["type"] == "token_usage_record"]
        contexts = {(r["payload"].get("model"), r["payload"].get("effort"))
                    for r in rows if r["type"] == "turn_context"}
        totals = usage_totals(records)
        aggregate = records[-1].get("thread_token_usage")
        if not aggregate or any(totals[k] != aggregate.get(k) for k in COUNTERS):
            raise ValueError(f"Missing or mismatched final usage aggregate: {name}")
        workspace = Path(trials[(task, arm)]["path"])
        tests_unchanged = hashlib.sha256((workspace / "test_app.py").read_bytes()).hexdigest() == trials[(task, arm)]["tests_sha256"]
        if not tests_unchanged:
            raise ValueError(f"Changed test fixture: {name}")
        grade = subprocess.run([manifest["python_executable"], "-m", "unittest", "-v"], cwd=workspace,
                               text=True, capture_output=True, timeout=30)
        (workspace / "grade.log").write_text(grade.stdout + grade.stderr)
        calls, final = [], []
        for row in rows:
            payload = row["payload"]
            if row["type"] != "response_item":
                continue
            if payload.get("type") in ("function_call", "custom_tool_call"):
                text = payload.get("name", "") + " " + str(payload.get("input", payload.get("arguments", "")))
                calls += re.findall(r"(?:tools\.)?(mcp__serena__\w+|mcp__context7__\w+)\s*\(", text)
            if payload.get("type") == "message" and payload.get("role") == "assistant":
                final += [c["text"] for c in payload.get("content", []) if c.get("type") == "output_text"]
        result = dict(task=task, arm=arm, agent=name, session=str(path), usage=totals,
                      session_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                      per_response_usage=[dict(response_id=r["response_id"], usage=r["usage"]) for r in records],
                      contexts=sorted(contexts), tests_pass=grade.returncode == 0,
                      tests_unchanged=tests_unchanged, observed_mcp_calls=calls,
                      method_compliant=method_compliant(arm, calls),
                      final_answer=final[-1] if final else "", patch="")
        original = trials[(task, arm)]["source"]
        result["patch"] = "".join(difflib.unified_diff(original.splitlines(True),
                                    (workspace / "app.py").read_text().splitlines(True),
                                    fromfile="a/app.py", tofile="b/app.py"))
        results.append(result)
    summary = {}
    for arm in ("skill", "serena", "context7"):
        group = [r for r in results if r["arm"] == arm]
        summary[arm] = dict(trials=len(group), tests_pass=sum(r["tests_pass"] for r in group),
                            method_compliant=sum(r["method_compliant"] for r in group),
                            **{k: sum(r["usage"][k] for r in group)
                               for k in (*COUNTERS, "calls", "total_tokens", "uncached_input_tokens")})
    document = dict(completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    status="complete" if len(results) == 12 else "in progress",
                    valid_comparison=len(results) == 12 and all(
                        r["tests_pass"] and r["tests_unchanged"] and r["method_compliant"] for r in results)
                    and len({tuple(c) for r in results for c in r["contexts"]}) == 1,
                    manifest=str(DIRECTORY / "code-manifest.json"), summary=summary, results=results)
    (DIRECTORY / "code-results.json").write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
