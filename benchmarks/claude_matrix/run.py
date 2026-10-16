"""Claude matrix benchmark. Usage: run.py [--validate | --regrade | --report]"""
import concurrent.futures
import datetime
import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tasks import HARD, SUFFIX, TASKS as ROUTINE  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = Path.home() / "claude-matrix-runs-20261016"
RESULTS = Path(__file__).with_name("results.json")
COMMIT = "270076e"
REPEATS = 3
TASKS = {**ROUTINE, **HARD}
SETTINGS = {
    "haiku-low": ("claude-haiku-5-5", "low"),
    "haiku-medium": ("claude-haiku-5-5", "medium"),
    "opus-medium": ("claude-opus-5-5", "medium"),
    "opus-high": ("claude-opus-5-5", "high"),
    "opus-xhigh": ("claude-opus-5-5", "xhigh"),
    "opus-max": ("claude-opus-5-5", "max"),
}
HARD_SETTINGS = ("haiku-low", "haiku-medium", "opus-medium", "opus-high", "opus-xhigh")


def plan():
    jobs = [(s, t, r) for r in range(REPEATS) for s in SETTINGS for t in ROUTINE]
    jobs += [(s, t, r) for r in range(REPEATS) for s in HARD_SETTINGS for t in HARD]
    random.Random(0).shuffle(jobs)
    return jobs


def checkout(repo, inject=()):
    repo.mkdir(parents=True)
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", COMMIT], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(repo)], input=archive, check=True)
    for rel, old, new in inject:
        path = repo / rel
        text = path.read_text()
        assert text.count(old) == 1, f"injection does not match {rel}"
        path.write_text(text.replace(old, new))


def metrics(out, model):
    ids, result = set(), {}
    for line in out.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("type") == "assistant" and r["message"].get("model") == model:
            ids.add(r["message"]["id"])
        elif r.get("type") == "result":
            result = r
    usage = (result.get("modelUsage") or {}).get(model, {})
    cached = usage.get("cacheReadInputTokens", 0)
    total = usage.get("inputTokens", 0) + usage.get("cacheCreationInputTokens", 0) + cached
    return dict(calls=len(ids), input=total, fresh=total - cached, cached=cached,
                reasoning=usage.get("thinkingTokens", 0), output=usage.get("outputTokens", 0),
                cost=result.get("total_cost_usd", 0.0), agent_error=bool(result.get("is_error")) or not result)


def grade(task, repo):
    try:
        return TASKS[task]["check"](str(repo))
    except Exception as exc:  # a broken workspace is a failed trial
        return f"check crashed: {exc!r}"


def trial(setting, task, rep):
    model, effort = SETTINGS[setting]
    run_dir = ARTIFACTS / f"{setting}--{task}--{rep}"
    done = run_dir / "result.json"
    if done.exists() and not json.loads(done.read_text())["agent_error"]:
        return
    subprocess.run(["rm", "-rf", str(run_dir)], check=True)
    repo = run_dir / "repo"
    checkout(repo, TASKS[task]["inject"])
    cmd = ["claude", "-p", TASKS[task]["prompt"] + SUFFIX, "--model", model, "--effort", effort,
           "--output-format", "stream-json", "--verbose", "--no-session-persistence", "--strict-mcp-config",
           "--permission-mode", "acceptEdits", "--allowedTools", "Read Grep Glob Edit Write Bash",
           "--disallowedTools", "Agent WebFetch WebSearch"]
    out, start, timed_out = run_dir / "out.jsonl", time.monotonic(), False
    try:
        with out.open("w") as stdout, (run_dir / "err.log").open("w") as stderr:
            subprocess.run(cmd, cwd=repo, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL, timeout=1800)
    except subprocess.TimeoutExpired:
        timed_out = True
    failure = grade(task, repo)
    result = dict(setting=setting, task=task, rep=rep, seconds=round(time.monotonic() - start), timed_out=timed_out,
                  success=failure is None and not timed_out, failure=failure, **metrics(out, model))
    done.write_text(json.dumps(result, indent=1))
    print(setting, task, rep, "PASS" if result["success"] else f"FAIL {str(failure)[:120]}", flush=True)


def trials():
    return [r for p in sorted(ARTIFACTS.glob("*/result.json")) if not (r := json.loads(p.read_text()))["agent_error"]]


def regrade():
    for done in ARTIFACTS.glob("*/result.json"):
        r = json.loads(done.read_text())
        if not r["agent_error"]:
            r["failure"] = grade(r["task"], done.parent / "repo")
            r["success"] = r["failure"] is None and not r["timed_out"]
            done.write_text(json.dumps(r, indent=1))


def summary(rs):
    calls, total = sum(r["calls"] for r in rs), sum(r["input"] for r in rs)
    return dict(trials=len(rs), passed=sum(r["success"] for r in rs), api_calls=calls,
                fresh_per_call=sum(r["fresh"] for r in rs) / calls, reasoning_per_call=sum(r["reasoning"] for r in rs) / calls,
                cache_hit=sum(r["cached"] for r in rs) / total, total_cost=sum(r["cost"] for r in rs),
                median_seconds=statistics.median(r["seconds"] for r in rs))


def report():
    rs = trials()
    suites = {"routine": ROUTINE, "harder": HARD}
    aggregates = {suite: {s: summary(sel) for s in SETTINGS if (sel := [r for r in rs if r["setting"] == s and r["task"] in tasks])}
                  for suite, tasks in suites.items()}
    claude_version = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.split()[0]
    RESULTS.write_text(json.dumps(dict(commit=COMMIT, claude_code_version=claude_version, repetitions=REPEATS,
                                       completed_utc=datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
                                       aggregates=aggregates, trials=rs), indent=1) + "\n")
    for suite, tasks in suites.items():
        print(f"\n{suite}\n| Setting | API calls | Fresh input/call | Reasoning/call | Cache hit | Total cost | Success | Median time |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|")
        for s, a in aggregates[suite].items():
            print(f"| {s} | {a['api_calls']} | {a['fresh_per_call']:,.0f} | {a['reasoning_per_call']:,.0f} | {a['cache_hit']:.1%} "
                  f"| ${a['total_cost']:.2f} | {a['passed']}/{a['trials']} | {a['median_seconds']:.0f}s |")
        print("\n| Task | " + " | ".join(aggregates[suite]) + " |\n|---|" + "---:|" * len(aggregates[suite]))
        for t in tasks:
            cells = [f"{sum(r['success'] for r in rs if r['setting'] == s and r['task'] == t)}/"
                     f"{sum(r['setting'] == s and r['task'] == t for r in rs)}" for s in aggregates[suite]]
            print(f"| {t} | " + " | ".join(cells) + " |")


def validate():
    """Every check must fail on its start state; bug-injection checks must pass on the unmodified commit."""
    scratch = ARTIFACTS / "validate"
    for task, spec in TASKS.items():
        subprocess.run(["rm", "-rf", str(scratch)], check=True)
        checkout(scratch / "start", spec["inject"])
        ok = grade(task, scratch / "start") is not None
        if spec["inject"]:
            checkout(scratch / "clean")
            ok = ok and grade(task, scratch / "clean") is None
        print(task, "ok" if ok else "INVALID")
    subprocess.run(["rm", "-rf", str(scratch)], check=True)


def main():
    if "--validate" in sys.argv:
        return validate()
    if "--regrade" in sys.argv:
        regrade()
    elif "--report" not in sys.argv:
        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            list(pool.map(lambda job: trial(*job), plan()))
    report()


if __name__ == "__main__":
    main()
