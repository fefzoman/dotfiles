"""Twelve retrieval trials in six pairs, using actual Codex usage counters."""

import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import tomllib

ROOT = Path(__file__).resolve().parents[2]
TASKS = [
    ("line-count", "serena", "In llm/read_hint.py, explain line_count: file eligibility, size limit, "
     "what it counts, and failure behavior. Trace its caller in main and the two line thresholds."),
    ("jsonl-tail", "serena", "In llm/idle_compact.py, explain records(path, tail) and its codex_records caller: "
     "where a tail starts, when the first line is discarded, malformed/sidechain filtering, "
     "missing-file handling, and how Codex records are normalized."),
    ("plugin-policy", "serena", "In llm/agent_config.py, explain context_efficiency for Codex and Claude: "
     "skill settings, plugin changes, preservation of unrelated settings, TOML validation before writes, "
     "and removal of legacy Serena hooks. Include invalid-agent behavior."),
    ("tomllib", "context7", "For Python 3.14 tomllib.loads, explain accepted input type, parse_float's default "
     "and argument, forbidden return types and exception, and invalid TOML behavior. Official source: "
     "https://raw.githubusercontent.com/python/cpython/3.14/Doc/library/tomllib.rst"),
    ("path-exists", "context7", "For Python 3.14 pathlib.Path.exists, explain symlink behavior and "
     "follow_symlinks=False, inaccessible/missing/invalid paths, the 3.14 OSError behavior change, and "
     "how to distinguish errors from absence. Official source: "
     "https://raw.githubusercontent.com/python/cpython/3.14/Doc/library/pathlib.rst"),
    ("subprocess-timeout", "context7", "For Python 3.14 subprocess.run(timeout=...), explain expiration, "
     "child termination and waiting, exception, which operation receives timeout, and the process-creation "
     "timing limitation. Contrast Popen.communicate(timeout=...) cleanup responsibility. Official source: "
     "https://raw.githubusercontent.com/python/cpython/3.14/Doc/library/subprocess.rst"),
]


def completed_usage(events):
    completed = [e["usage"] for e in events if e.get("type") == "turn.completed"]
    if len(completed) != 1:
        raise ValueError("Expected exactly one completed turn")
    usage = completed[0]
    for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
        if type(usage.get(key)) is not int or usage[key] < 0:
            raise ValueError(f"Invalid or missing usage: {key}")
    if usage["cached_input_tokens"] > usage["input_tokens"]:
        raise ValueError("Cached tokens exceed input")
    return dict(usage, total_tokens=usage["input_tokens"] + usage["output_tokens"],
                uncached_input_tokens=usage["input_tokens"] - usage["cached_input_tokens"])


def main():
    source_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    config = tomllib.loads((source_home / "config.toml").read_text())
    model, effort = config["model"], config["model_reasoning_effort"]
    skill = (ROOT / "llm/skills/code-retrieval/SKILL.md").read_text()
    artifacts = Path(tempfile.mkdtemp(prefix="retrieval-benchmark-"))
    home, workspace = artifacts / "home", artifacts / "repo"
    home.mkdir()
    (home / "auth.json").symlink_to(source_home / "auth.json")
    (workspace / "llm").mkdir(parents=True)
    sources = {}
    for file in ("read_hint.py", "idle_compact.py", "agent_config.py"):
        target = workspace / "llm" / file
        shutil.copyfile(ROOT / "llm" / file, target)
        sources[file] = hashlib.sha256(target.read_bytes()).hexdigest()
    (workspace / ".serena").mkdir()
    (workspace / ".serena/project.yml").write_text(
        'project_name: retrieval-benchmark\nlanguages: [python]\nread_only: true\n')
    document = dict(
        started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        cli_version=subprocess.check_output(["codex", "--version"], text=True).strip(),
        model=model, effort=effort, artifacts=str(artifacts), source_sha256=sources,
        skill_sha256=hashlib.sha256(skill.encode()).hexdigest(), results=[])
    output = Path(__file__).with_name("results.json")
    for index, (task, tool, question) in enumerate(TASKS):
        # Alternate pair order to reduce, not eliminate, cache/order bias.
        for arm in (("skill", tool) if index % 2 == 0 else (tool, "skill")):
            name = f"{task}-{arm}"
            directory = artifacts / name
            directory.mkdir()
            method = (
                "Use local shell retrieval only; do not use MCP tools. For remote documentation, "
                "fetch the official source URL with curl or Python's standard library, then read relevant sections."
                if arm == "skill" else
                f"Use {tool} MCP as your primary evidence source, including its required initialization or "
                "library resolution. Only use shell retrieval as fallback after a tool failure or missing evidence. "
                "Use Context7 anonymously; never sign in. Do not launch additional servers yourself."
            )
            prompt = (
                "This is an authorized read-only retrieval benchmark, not a code-change task. "
                "Do not edit files, install packages, create embeddings, run indexing, delegate, or commit. "
                "Follow this retrieval skill in both benchmark arms:\n\n" + skill +
                "\n\nControlled method for this trial: " + method +
                "\nAnswer from retrieved evidence, not memory. Be concise (at most 220 words), "
                "include source paths or URLs, and state any unavailable evidence. "
                "Do not discuss the benchmark or run tests.\n\nQuestion: " + question)
            (directory / "prompt.txt").write_text(prompt)
            args = ["codex", "exec", "--ignore-user-config", "--ignore-rules", "--json", "--color", "never",
                    "--sandbox", "read-only", "--skip-git-repo-check", "--cd", str(workspace),
                    "-c", f"model={json.dumps(model)}", "-c", f"model_reasoning_effort={json.dumps(effort)}",
                    "-c", 'approval_policy="never"', "-c", 'web_search="disabled"',
                    "--disable", "multi_agent"]
            if arm != "skill":
                server = config["mcp_servers"][tool]
                for key in ("command", "args"):
                    args += ["-c", f"mcp_servers.{tool}.{key}={json.dumps(server[key])}"]
                args += ["-c", f"mcp_servers.{tool}.startup_timeout_sec=60"]
            start = time.monotonic()
            timed_out = False
            with (directory / "events.jsonl").open("w") as out, (directory / "stderr.log").open("w") as err:
                process = subprocess.Popen(args + [prompt], stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                           env=os.environ | {"CODEX_HOME": str(home)}, start_new_session=True)
                try:
                    code = process.wait(timeout=240)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=20)
                    timed_out, code = True, process.returncode
                except BaseException:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                        process.wait(timeout=20)
                    raise
            events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines() if line]
            messages = [e["item"]["text"] for e in events if e.get("type") == "item.completed"
                        and e["item"].get("type") == "agent_message"]
            calls = [e["item"] for e in events if e.get("type") == "item.completed"
                     and e["item"].get("type") in ("mcp_tool_call", "command_execution")]
            result = dict(task=task, arm=arm, exit_code=code, timed_out=timed_out,
                          elapsed_seconds=round(time.monotonic() - start, 2),
                          answer="\n\n".join(messages), tool_calls=len(calls),
                          mcp_calls=[dict(server=c.get("server"), tool=c.get("tool"), status=c.get("status"))
                                     for c in calls if c.get("type") == "mcp_tool_call"])
            try:
                result["usage"] = completed_usage(events)
            except ValueError as error:
                result["usage_error"] = str(error)
            result["retrieval_executed"] = any(
                c.get("exit_code") == 0 if arm == "skill" else
                c.get("server") == tool and c.get("status") == "completed"
                for c in calls)
            document["results"].append(result)
            valid = code == 0 and not timed_out and "usage" in result and result["retrieval_executed"]
            document["status"] = "running" if valid else "blocked"
            output.write_text(json.dumps(document, indent=2) + "\n")
            print(name, code, result.get("usage", result.get("usage_error")), flush=True)
            if document["status"] == "blocked":
                print("No successful retrieval; stop rather than count failure as token savings.", flush=True)
                return
    document["status"] = "completed; answer quality requires review"
    output.write_text(json.dumps(document, indent=2) + "\n")
    print("Artifacts:", artifacts, flush=True)


if __name__ == "__main__":
    main()
