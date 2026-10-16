"""Claude matrix benchmark tasks: prompt, optional bug injection, and an acceptance check run after the agent."""
import json
import os
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

SUFFIX = (" Run the relevant tests from the repository root before finishing "
          "(e.g. `python3 -m unittest llm.test_read_hint`, `python3 llm/token-profiler/test_token_profiler.py`).")


def run(repo, *cmd, env=None, input=None, timeout=120):
    return subprocess.run(cmd, cwd=repo, env=env, input=input, text=True, capture_output=True, timeout=timeout)


def unittest_ok(repo, *targets):
    for target in targets:
        cwd, _, target = target.rpartition(":")
        cmd = ("python3", target) if target.endswith(".py") else ("python3", "-m", "unittest", target)
        r = run(Path(repo, cwd), *cmd, timeout=300)
        if r.returncode and cwd:  # agents may make the module importable from the repo root instead
            r = run(repo, "python3", "-m", "unittest", f"{cwd}.{target}", timeout=300)
        if r.returncode:
            return f"{target} failed: {(r.stderr or r.stdout)[-300:]}"
    return None


def py(repo, code):
    r = run(repo, sys.executable, "-c", code)
    return None if r.returncode == 0 else (r.stderr or r.stdout)[-400:]


def fake_bin(tmp, name, body):
    path = Path(tmp) / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


def check_pipe(repo):
    return unittest_ok(repo, "llm.test_read_hint") or py(repo, """
from llm import read_hint as r
assert r.bash_targets("cat llm/idle_compact.py | head -40") == [], r.bash_targets("cat llm/idle_compact.py | head -40")
assert r.bash_targets("cat a.py") == ["a.py"]
assert r.bash_targets("cat -n a.py && echo hi") == ["a.py"]
""")


def check_min_lines(repo):
    with tempfile.TemporaryDirectory() as tmp:
        fake_bin(tmp, "smart-read", "exit 0")
        (Path(tmp) / "big.py").write_text("x = 1\n" * 200)
        (Path(tmp) / "mid.py").write_text("x = 1\n" * 60)
        base = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}"}
        base.pop("READ_HINT_MIN_LINES", None)

        def hint(name, value):
            env = dict(base, **({"READ_HINT_MIN_LINES": value} if value is not None else {}))
            stdin = f'{{"tool_name": "Read", "cwd": "{tmp}", "tool_input": {{"file_path": "{name}"}}}}'
            r = run(repo, "python3", "llm/read_hint.py", env=env, input=stdin)
            return r.returncode, bool(r.stdout.strip())

        for name, value, want in (("big.py", "0", False), ("big.py", None, True), ("mid.py", "50", True), ("mid.py", None, False)):
            rc, hinted = hint(name, value)
            if rc or hinted != want:
                return f"{name} READ_HINT_MIN_LINES={value}: hint={hinted} want={want} rc={rc}"
    return unittest_ok(repo, "llm.test_read_hint")


def check_pyproject(repo):
    return unittest_ok(repo, "llm.test_context7_version_guard") or py(repo, """
import tempfile
from pathlib import Path
from llm import context7_version_guard as g
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp) / "proj"; root.mkdir()
    (root / "pyproject.toml").write_text('[project]\\nname = "x"\\ndependencies = ["requests[socks]==2.31.0", "flask>=3", "Django == 5.0.1"]\\n')
    assert g.pinned_versions(root, {"requests"}) == {"2.31.0": "proj/pyproject.toml"}, g.pinned_versions(root, {"requests"})
    assert g.pinned_versions(root, {"django"}) == {"5.0.1": "proj/pyproject.toml"}, g.pinned_versions(root, {"django"})
    assert g.pinned_versions(root, {"flask"}) == {}
    (root / "pyproject.toml").write_text('[tool.poetry]\\nname = "x"\\n')
    assert g.pinned_versions(root, {"requests"}) == {}
""")


def check_mentions(repo):
    return unittest_ok(repo, "llm.test_context7_version_guard") or py(repo, """
from llm import context7_version_guard as g
assert not g.mentions("requests 12.4 docs", "2.4.1")
assert g.mentions("requests 2.4 docs", "2.4.1")
assert g.mentions("/psf/requests/v2.4.1", "2.4.1")
assert not g.mentions("requests 2.40", "2.4.1")
""")


def check_rename(repo):
    install = Path(repo, "llm/ai-install.sh").read_text()
    if "agent_config claude-effort" not in install or "agent_config effort " in install:
        return "ai-install.sh not updated"
    return unittest_ok(repo, "llm:test_agent_config") or py(repo, """
import sys; sys.path.insert(0, "llm"); import agent_config as a
assert hasattr(a, "claude_effort") and not hasattr(a, "effort")
assert "claude-effort" in a.COMMANDS and "effort" not in a.COMMANDS and "codex-effort" in a.COMMANDS
""")


def check_thinking(repo):
    return unittest_ok(repo, "llm/token-profiler/test_token_profiler.py") or py(repo, """
import importlib.machinery, importlib.util
loader = importlib.machinery.SourceFileLoader("tp", "llm/token-profiler/token-profiler")
spec = importlib.util.spec_from_loader("tp", loader); tp = importlib.util.module_from_spec(spec)
import sys; sys.modules["tp"] = tp; loader.exec_module(tp)
u = tp.claude_usage({"input_tokens": 5, "output_tokens": 100, "output_tokens_details": {"thinking_tokens": 60}})
assert u.reasoning_output_tokens == 60, u
assert tp.claude_usage({"input_tokens": 5, "output_tokens": 9}).reasoning_output_tokens == 0
""")


def check_rtk(repo):
    if err := unittest_ok(repo, "llm.codex.test_codex_rtk_hook"):
        return err
    stdin = '{"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git status"}}'
    with tempfile.TemporaryDirectory() as tmp:
        for case, body in (("missing", None), ("failing", "exit 3"), ("hanging", "sleep 30")):
            path = "/usr/bin:/bin"
            if body:
                fake_bin(tmp, "rtk", body)
                path = f"{tmp}:{path}"
            start = time.monotonic()
            r = run(repo, sys.executable, "llm/codex/codex_rtk_hook.py", env={"PATH": path}, input=stdin, timeout=20)
            if r.returncode or r.stdout.strip() or time.monotonic() - start > 10:
                return f"rtk {case}: exit={r.returncode} out={r.stdout[:80]!r} err={r.stderr[-150:]!r}"
    return None


def check_codex_effort(repo):
    return unittest_ok(repo, "llm:test_agent_config") or py(repo, """
import tempfile, tomllib
from pathlib import Path
import sys; sys.path.insert(0, "llm"); import agent_config as a
with tempfile.TemporaryDirectory() as tmp:
    c = Path(tmp) / "config.toml"
    c.write_text('model = "m"\\n[profiles.deep]\\nmodel_reasoning_effort = "max"\\n[profiles.fast]\\nmodel = "x"\\n')
    a.codex_effort(str(c))
    d = tomllib.loads(c.read_text())
    assert d["model_reasoning_effort"] == a.EFFORT and d["profiles"]["deep"]["model_reasoning_effort"] == "max", d
    assert "model_reasoning_effort" not in d["profiles"]["fast"], d
""")


TASKS = {
    "pipe": dict(
        prompt="The read hint fires for `cat llm/idle_compact.py | head -40`, which only prints 40 lines. "
               "Piped reads should not get the large-read hint. Find and fix the bug.",
        inject=[("llm/read_hint.py", 'if "|" in segment or "<" in segment or ">" in segment:',
                 'if "<" in segment or ">" in segment:')],
        check=check_pipe),
    "min_lines": dict(
        prompt="Setting READ_HINT_MIN_LINES=0 should turn the large-read hint off entirely; today it makes every "
               "read get a hint. Implement that, keep the default of 80 lines, and add a test.",
        inject=[], check=check_min_lines),
    "pyproject": dict(
        prompt="The Context7 version guard reads pins from venvs, uv.lock, poetry.lock, requirements*.txt and "
               "node_modules. Also read `==` pins from `[project].dependencies` in pyproject.toml (extras like "
               "`requests[socks]==2.31.0` included), reported with source `<root name>/pyproject.toml` like the "
               "other files. Add a test.",
        inject=[], check=check_pyproject),
    "mentions": dict(
        prompt="Context7 version guard bug: with requests pinned to 2.4.1, a query mentioning `requests 12.4` is "
               "allowed through. It should be denied, since 12.4 is not 2.4. Fix it.",
        inject=[("llm/context7_version_guard.py", r'rf"(?<![\d.]){re.escape(major_minor)}(?!\d)"',
                 r'rf"{re.escape(major_minor)}(?!\d)"')],
        check=check_mentions),
    "rename": dict(
        prompt="Rename the `effort` command in llm/agent_config.py to `claude_effort` (CLI name `claude-effort`) "
               "and update every caller, including the installer and tests.",
        inject=[], check=check_rename),
    "thinking": dict(
        prompt="token-profiler shows 0 Reasoning/thinking tokens for every Claude session, although Claude "
               "transcripts record `usage.output_tokens_details.thinking_tokens`. Find and fix the bug.",
        inject=[("llm/token-profiler/token-profiler", 'int(output_details.get("thinking_tokens") or 0)',
                 'int(output_details.get("reasoning_tokens") or 0)')],
        check=check_thinking),
    "rtk": dict(
        prompt="llm/codex/codex_rtk_hook.py crashes Codex tool calls when rtk is not installed, exits non-zero, "
               "or hangs. In all those cases the hook should exit 0 silently and leave the command unchanged. "
               "Fix it and add tests.",
        inject=[], check=check_rtk),
    "codex_effort": dict(
        prompt="Running `agent_config codex-effort` on a config.toml resets `model_reasoning_effort` inside my "
               "`[profiles.deep]` table to high. Only the top-level key should change. Fix it.",
        inject=[("llm/agent_config.py",
                 '    first_table = re.search(r"(?m)^[ \\t]*\\[", text)\n'
                 '    top, tables = (text[:first_table.start()], text[first_table.start():]) if first_table else (text, "")\n',
                 '    top, tables = text, ""\n')],
        check=check_codex_effort),
}


# Harder tasks: a two-cause bug and multi-part features.

def _claude_fixture(home):
    def call(i, model, effort, inp, created, read, thinking):
        return {"type": "assistant", "timestamp": f"2026-09-20T10:00:{i:02d}Z", "effort": effort, "cwd": "/w",
                "sessionId": "s1", "message": {"id": f"m{i}", "model": model, "role": "assistant",
                "usage": {"input_tokens": inp, "cache_creation_input_tokens": created, "cache_read_input_tokens": read,
                          "output_tokens": 50, "output_tokens_details": {"thinking_tokens": thinking}},
                "content": [{"type": "text", "text": "ok"}]}}
    records = [{"type": "user", "timestamp": "2026-09-20T10:00:00Z", "cwd": "/w", "sessionId": "s1",
                "message": {"role": "user", "content": "Do it"}},
               call(1, "claude-opus-5-5", "high", 10, 90, 900, 30),
               call(2, "claude-opus-5-5", "high", 5, 0, 1095, 10),
               call(3, "claude-haiku-5-5", "low", 20, 0, 480, 0)]
    path = Path(home, ".claude/projects/-w/s1.jsonl"); path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return {("claude-opus-5-5", "high"): (2, 52.5, 20, 1995 / 2100), ("claude-haiku-5-5", "low"): (1, 20, 0, 0.96)}


def _codex_fixture(home):
    def usage(inp, cached, reasoning):
        return {"input_tokens": inp, "cached_input_tokens": cached, "output_tokens": 10,
                "reasoning_output_tokens": reasoning, "total_tokens": inp + 10}
    def call(i, inp, cached, reasoning):
        return {"timestamp": f"2026-09-20T10:00:{i:02d}Z", "type": "token_usage_record",
                "payload": {"response_id": f"r{i}", "usage": usage(inp, cached, reasoning)}}
    def ctx(i, model, effort):
        return {"timestamp": f"2026-09-20T10:00:{i:02d}Z", "type": "turn_context", "payload": {"model": model, "effort": effort, "cwd": "/w"}}
    records = [ctx(0, "gpt-6.1-sol", "medium"), call(1, 1000, 800, 40), call(2, 1200, 1100, 0),
               ctx(3, "gpt-6-luna", "low"), call(4, 500, 0, 0)]
    path = Path(home, ".codex/sessions/2026/09/20/rollout-2026-09-20T10-00-00-0199aaaa-bbbb-7ccc-8ddd-eeeeffff0000.jsonl")
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return {("gpt-6.1-sol", "medium"): (2, 150, 20, 1900 / 2200), ("gpt-6-luna", "low"): (1, 500, 0, 0.0)}


def check_top_model(repo):
    if err := unittest_ok(repo, "llm/token-profiler/test_token_profiler.py"):
        return err
    for profile, fixture in (("claude", _claude_fixture), ("codex", _codex_fixture)):
        with tempfile.TemporaryDirectory() as home:
            expected = fixture(home)
            r = run(repo, sys.executable, "llm/token-profiler/token-profiler", profile, "top", "--by", "model", "--json",
                    env={**os.environ, "HOME": home, "NO_COLOR": "1"})
            if r.returncode:
                return f"{profile}: exit {r.returncode}: {r.stderr[-300:]}"
            try:
                rows = json.loads(r.stdout)
            except ValueError:
                return f"{profile}: not JSON: {r.stdout[:200]!r}"
            got = {(row.get("model"), row.get("effort")): row for row in rows}
            if set(got) != set(expected):
                return f"{profile}: keys {sorted(got)} != {sorted(expected)}"
            if [(row["model"], row["effort"]) for row in rows] != sorted(expected, key=lambda k: -expected[k][0]):
                return f"{profile}: not sorted by calls"
            for key, (calls, fresh, reasoning, hit) in expected.items():
                row = got[key]
                vals = (row.get("calls"), row.get("fresh_tokens_per_call"), row.get("reasoning_tokens_per_call"), row.get("cache_hit"))
                # per-call averages may be rounded to whole tokens
                if any(v is None or abs(float(v) - e) > tol for v, e, tol in zip(vals, (calls, fresh, reasoning, hit), (0, 0.5, 0.5, 0.01))):
                    return f"{profile} {key}: got {vals}, expected {(calls, fresh, reasoning, hit)}"
            plain = run(repo, sys.executable, "llm/token-profiler/token-profiler", profile, "top", "--by", "model",
                        env={**os.environ, "HOME": home, "NO_COLOR": "1"})
            if plain.returncode or not all(m in plain.stdout for m, _ in expected):
                return f"{profile}: table output missing models"
    return None


def check_monorepo(repo):
    return unittest_ok(repo, "llm.test_context7_version_guard") or py(repo, """
import tempfile
from pathlib import Path
from llm import context7_version_guard as g
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp) / "mono"; (root / ".git").mkdir(parents=True)
    api = root / "services" / "api"; api.mkdir(parents=True)
    (root / "requirements.txt").write_text("Django==5.0.1\\n")
    reason = g.check({"libraryId": "/django/django", "query": "models"}, api)
    assert reason and "5.0.1" in reason, reason
    assert g.check({"libraryId": "/django/django", "query": "models 5.0"}, api) is None
    (api / "requirements.txt").write_text("Flask_Login==0.6.3\\n")
    assert g.check({"libraryId": "/maxcountryman/flask-login", "query": "login"}, api)
""")


def check_sed_range(repo):
    if err := unittest_ok(repo, "llm.test_read_hint"):
        return err
    with tempfile.TemporaryDirectory() as tmp:
        fake_bin(tmp, "smart-read", "exit 0")
        (Path(tmp) / "big.py").write_text("x = 1\n" * 300)
        (Path(tmp) / "small.py").write_text("x = 1\n" * 50)
        env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}"}
        env.pop("READ_HINT_MIN_LINES", None)
        cases = {"sed -n '1,200p' big.py": True, 'sed -n "100,$p" big.py': True, "sed -n '1,20p' big.py": False,
                 "sed -n 5p big.py": False, "sed -n '1,200p' big.py | grep x": False,
                 "sed -n '1,200p' small.py": False, "cat big.py": True, "sed -n '250,299p' big.py": False}
        for command, want in cases.items():
            stdin = json.dumps({"tool_name": "Bash", "cwd": tmp, "tool_input": {"command": command}})
            r = run(repo, "python3", "llm/read_hint.py", env=env, input=stdin)
            if r.returncode or bool(r.stdout.strip()) != want:
                return f"{command!r}: hint={bool(r.stdout.strip())} want={want} rc={r.returncode} {r.stderr[-150:]}"
    return None


def check_effort_arg(repo):
    if err := unittest_ok(repo, "llm:test_agent_config"):
        return err
    with tempfile.TemporaryDirectory() as tmp:
        s, c = Path(tmp, "settings.json"), Path(tmp, "config.toml")
        def cli(*args):
            return run(repo, sys.executable, "llm/agent_config.py", *args)
        s.write_text('{"model": "opus"}')
        if cli("effort", str(s), "xhigh").returncode or json.loads(s.read_text()) != {"model": "opus", "effortLevel": "xhigh"}:
            return f"effort xhigh: {s.read_text()}"
        if cli("effort", str(s)).returncode or json.loads(s.read_text())["effortLevel"] != "high":
            return "effort default"
        before = s.read_text(); r = cli("effort", str(s), "turbo")
        if r.returncode != 2 or not r.stderr.strip() or s.read_text() != before:
            return f"effort turbo: rc={r.returncode} err={r.stderr!r} changed={s.read_text() != before}"
        c.write_text('model = "m"\n[profiles.deep]\nmodel_reasoning_effort = "low"\n')
        if cli("codex-effort", str(c), "max").returncode:
            return "codex-effort max failed"
        d = tomllib.loads(c.read_text())
        if d.get("model_reasoning_effort") != "max" or d["profiles"]["deep"]["model_reasoning_effort"] != "low":
            return f"codex-effort max: {d}"
        before = c.read_text(); r = cli("codex-effort", str(c), "MAX!")
        if r.returncode != 2 or not r.stderr.strip() or c.read_text() != before:
            return f"codex-effort bogus: rc={r.returncode}"
    return None


HARD = {
    "top_model": dict(
        prompt="Add `top --by model` to token-profiler, for both Claude and Codex profiles. With `--json` it prints "
               "a JSON list with one object per (model, effort) pair: `model`, `effort` (empty string when unknown), "
               "`calls`, `fresh_tokens_per_call` (input not served from cache, averaged over calls), "
               "`reasoning_tokens_per_call`, and `cache_hit` (cached input / total input, 0-1), sorted by calls "
               "descending. Without `--json` it prints a readable table. Add tests.",
        inject=[], check=check_top_model),
    "monorepo": dict(
        prompt="The Context7 version guard stopped working in my monorepo. Running from `services/api`, with "
               "`Django==5.0.1` pinned in the repo root's requirements.txt, an unversioned query for "
               "`/django/django` goes through instead of being denied. Fix it.",
        inject=[("llm/context7_version_guard.py", 'return re.sub(r"[-_.]+", "-", name).lower()',
                 'return re.sub(r"[-_.]+", "-", name)'),
                ("llm/context7_version_guard.py", "return list(dict.fromkeys([cwd, path]))", "return [cwd]")],
        check=check_monorepo),
    "sed_range": dict(
        prompt="The large-read hint ignores `sed -n 'START,ENDp' FILE`, which agents use to print big chunks. Treat "
               "it as a read of that line range: hint when the range covers at least READ_HINT_MIN_LINES lines of "
               "the file (`$` means the last line). Single-line prints like `sed -n 5p FILE`, smaller ranges, and "
               "piped commands stay silent. Add tests.",
        inject=[], check=check_sed_range),
    "effort_arg": dict(
        prompt="Let `agent_config.py effort SETTINGS [LEVEL]` and `agent_config.py codex-effort CONFIG [LEVEL]` take "
               "an optional effort level, defaulting to EFFORT. Accept only low, medium, high, xhigh and max; "
               "anything else must exit with status 2, print an error to stderr, and leave the file untouched. "
               "Add tests.",
        inject=[], check=check_effort_arg),
}
