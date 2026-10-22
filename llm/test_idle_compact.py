import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from llm import idle_compact as ic


def iso(when: float) -> str:
    return datetime.fromtimestamp(when, timezone.utc).isoformat().replace("+00:00", "Z")


def prompt(text: str, when: float) -> dict:
    return {"type": "user", "timestamp": iso(when), "origin": {"kind": "human"},
            "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def reply(text: str, when: float, tokens: int = 250_000, ttl: str = "1h") -> dict:
    return {"type": "assistant", "timestamp": iso(when),
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}],
                        "usage": {"input_tokens": 2, "cache_read_input_tokens": tokens - 1002,
                                  "cache_creation_input_tokens": 1000,
                                  "cache_creation": {f"ephemeral_{ttl}_input_tokens": 1000}}}}


def tool(name: str, args: dict, when: float) -> dict:
    return {"type": "assistant", "timestamp": iso(when),
            "message": {"role": "assistant", "content": [{"type": "tool_use", "name": name, "input": args}]}}


def result(text: str, when: float, error: bool = False) -> dict:
    return {"type": "user", "timestamp": iso(when),
            "message": {"role": "user", "content": [{"type": "tool_result", "content": text, "is_error": error}]}}


class IdleCompactTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        self.cwd = str(self.home / "repo")
        os.mkdir(self.cwd)
        self.env = mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.home / "state"),
                                                "HOME": str(self.home)}, clear=False)
        self.env.start()
        for key in ("IDLE_COMPACT_TEST_SECONDS", "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_EXECPATH", "CLAUDE_PROJECT_DIR"):
            os.environ.pop(key, None)
        self.transcript = self.home / "s1.jsonl"

    def tearDown(self) -> None:
        self.env.stop()

    def save(self, recs: list) -> dict:
        self.transcript.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        return {"session_id": "s1", "transcript_path": str(self.transcript), "cwd": self.cwd}

    def run_hook(self, func, *args) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = func(*args)
        return code, out.getvalue(), err.getvalue()

    def test_prompts_exclude_meta_notifications_and_tool_results(self) -> None:
        now = time.time()
        meta = prompt("Base directory for this skill", now) | {"isMeta": True}
        note = prompt("<task-notification>", now) | {"origin": {"kind": "task-notification"}}
        self.assertTrue(ic.is_prompt(prompt("fix it", now)))
        self.assertFalse(any(ic.is_prompt(r) for r in (meta, note, result("ok", now))))

    def test_arm_skips_sessions_below_the_floor(self) -> None:
        old = time.time() - 30
        os.environ["IDLE_COMPACT_TEST_SECONDS"] = "0.01"
        self.assertEqual(self.run_hook(ic.arm, self.save([prompt("x", old), reply("y", old, tokens=80_000)]))[0], 0)
        self.assertFalse(ic.marker("s1", "arm").exists())

    def test_lifetime_follows_latest_cache_ttl(self) -> None:
        now = time.time()
        self.assertEqual(ic.lifetime("claude", [reply("a", now, ttl="5m")]), 300.0)
        self.assertEqual(ic.lifetime("claude", [reply("a", now, ttl="5m"), reply("b", now)]), 3600.0)
        self.assertEqual(ic.lifetime("claude", [reply("a", now), reply("b", now, ttl="5m")]), 300.0)

    def test_arm_wakes_with_digest_then_stores_the_reply(self) -> None:
        old = time.time() - 30
        os.environ["IDLE_COMPACT_TEST_SECONDS"] = "0.01"
        recs = [prompt("<ide_opened_file>a.py opened</ide_opened_file>Fix the token refresh race", old), tool("Edit", {"file_path": f"{self.cwd}/a.py"}, old),
                result("Traceback: boom", old, error=True), prompt("yes", old), reply("done", old)]
        code, _, err = self.run_hook(ic.arm, self.save(recs))
        self.assertEqual(code, 2)
        self.assertIn("Idle checkpoint:", err)
        self.assertIn("Goal, Done, Decisions, Dead ends", err)
        self.assertIn("run /pitstop and then /clear", err)
        self.assertIn("Fix the token refresh race", err)
        self.assertNotIn("a.py opened", err)
        self.assertNotIn("- T4", err)
        self.assertIn(f"{self.cwd}/a.py (1)", err)
        self.assertIn("Last error, T3: Traceback: boom", err)

        later = time.time() + 1
        hook = self.save(recs + [reply("## Idle checkpoint\n### Goal\nFix race\n### Decisions\nlock\n### Dead ends\nretry", later)])
        self.assertEqual(self.run_hook(ic.arm, hook)[0], 0)
        folder = ic.folder_for("s1")
        self.assertIn("### Goal\nFix race", (folder / "checkpoint.md").read_text())
        self.assertIn("## T2 · tool ·", (folder / "transcript.md").read_text())
        self.assertEqual(self.run_hook(ic.clear, hook)[1], "")
        self.assertIn("/clear", json.loads(self.run_hook(ic.guard, hook | {"prompt": "/pitstop"})[1])["reason"])
        loaded = json.loads(self.run_hook(ic.clear, hook | {"session_id": "s2"})[1])
        self.assertEqual(loaded["systemMessage"], "Loaded idle checkpoint s1 into session s2.")
        context = loaded["hookSpecificOutput"]["additionalContext"]
        self.assertIn("### Dead ends\nretry", context)
        self.assertEqual(self.run_hook(ic.clear, hook)[1], "")

    def test_manual_checkpoint_stores_the_reply_and_clear_loads_it(self) -> None:
        now = time.time()
        recs = [prompt("Fix the token refresh race", now - 60), reply("patched a.py", now - 50, tokens=20_000)]
        hook = self.save(recs) | {"prompt": "/checkpoint"}
        _, out, _ = self.run_hook(ic.guard, hook)
        context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Manual checkpoint:", context)
        self.assertIn("Fix the token refresh race", context)
        self.assertIn("or /pitstop in a new one", context)

        command = {"type": "user", "timestamp": iso(now + 1),
                   "message": {"role": "user", "content": "<command-name>/checkpoint</command-name>"}}
        hook = self.save(recs + [command, reply("## Idle checkpoint\n### Goal\nFix race\n### Next steps\nlock", now + 2)])
        self.assertEqual(self.run_hook(ic.arm, hook), (0, "", ""))
        self.assertIn("### Goal\nFix race", (ic.folder_for("s1") / "checkpoint.md").read_text())
        self.assertNotIn("patched a.py", (ic.folder_for("s1") / "checkpoint.md").read_text())
        loaded = json.loads(self.run_hook(ic.clear, hook | {"session_id": "s2"})[1])
        self.assertIn("### Next steps\nlock", loaded["hookSpecificOutput"]["additionalContext"])

    def test_checkpoint_after_cd_into_a_subdir_loads_in_the_launch_dir(self) -> None:
        os.environ["CLAUDE_PROJECT_DIR"] = self.cwd
        sub = Path(self.cwd) / "sub"
        sub.mkdir()
        now = time.time()
        recs = [prompt("Fix the race", now - 60), reply("patched", now - 50)]
        self.run_hook(ic.guard, self.save(recs) | {"cwd": str(sub), "prompt": "/checkpoint"})
        hook = self.save(recs + [reply("## Idle checkpoint\n### Goal\nFix race", now + 2)]) | {"cwd": str(sub)}
        self.run_hook(ic.arm, hook)
        self.assertIn("/clear", json.loads(self.run_hook(ic.guard, hook | {"prompt": "/pitstop"})[1])["reason"])
        loaded = json.loads(self.run_hook(ic.clear, hook | {"session_id": "s2", "cwd": self.cwd})[1])
        self.assertIn("### Goal\nFix race", loaded["hookSpecificOutput"]["additionalContext"])

    def test_sleeper_waking_after_cache_expiry_stores_excerpts_instead(self) -> None:
        os.environ["IDLE_COMPACT_TEST_SECONDS"] = "0.9"
        now, nap = time.time(), time.sleep
        hook = self.save([prompt("Fix the race", now), reply("patched", now)])
        with mock.patch.object(ic.time, "sleep", lambda s: nap(s + 0.5)):
            self.assertEqual(self.run_hook(ic.arm, hook), (0, "", ""))
        self.assertFalse(ic.marker("s1", "fired").exists())
        self.assertIn("Local transcript excerpts", (ic.folder_for("s1") / "checkpoint.md").read_text())

    def test_newer_activity_or_token_cancels_the_sleeper(self) -> None:
        old = time.time() - 30
        os.environ["IDLE_COMPACT_TEST_SECONDS"] = "1.5"
        hook = self.save([prompt("x", old - 5), reply("y", time.time())])
        with mock.patch.object(ic.time, "sleep", side_effect=lambda _: self.save(
                [prompt("x", old - 5), reply("y", time.time()), prompt("new", time.time() + 1)])):
            self.assertEqual(self.run_hook(ic.arm, hook)[0], 0)

    def test_guard_blocks_once_then_resume_returns_sections_in_order(self) -> None:
        os.environ["IDLE_COMPACT_TEST_SECONDS"] = "0.9"
        old = time.time() - 30
        folder = ic.folder_for("s1", self.cwd)
        ic.write(folder / "digest.json", json.dumps({"requests": [], "files": [], "repos": [],
                                                     "last_error": None, "todos": []}))
        ic.store_checkpoint(folder, "s1", "## Idle checkpoint\n### Next steps\nrun\n### Goal\nship\n### Decisions\nlock",
                            self.cwd, self.transcript)
        hook = self.save([prompt("x", old - 60), reply("cp", old)]) | {"prompt": "continue the fix"}
        _, out, _ = self.run_hook(ic.guard, hook)
        decision = json.loads(out)
        self.assertEqual(decision["decision"], "block")
        self.assertIn("continue the fix", decision["reason"])
        self.assertIn("/pitstop and then /clear", decision["reason"])
        self.assertEqual(self.run_hook(ic.guard, hook)[1], "")

        text = ic.resume(self.cwd)
        self.assertLess(text.index("### Goal"), text.index("### Decisions"))
        self.assertLess(text.index("### Decisions"), text.index("### Next steps"))
        self.assertIn("Resume protocol", text)
        self.assertEqual(ic.resume(str(self.home)), "No idle checkpoint for this project.")

    def test_resume_skips_a_checkpoint_its_chat_moved_past(self) -> None:
        old = time.time() - 30
        folder = ic.folder_for("s1", self.cwd)
        ic.store_checkpoint(folder, "s1", "## Idle checkpoint\n### Goal\nship", self.cwd, self.transcript)
        self.save([prompt("x", old), reply("y", old), prompt("kept going", time.time() + 5)])
        self.assertEqual(ic.resume(self.cwd), "No idle checkpoint for this project.")
        self.save([prompt("x", old), reply("y", old)])
        self.assertIn("### Goal\nship", ic.resume(self.cwd))

    def test_guard_without_checkpoint_hints_once_after_the_cache_expires(self) -> None:
        old = time.time() - 30
        os.environ["IDLE_COMPACT_TEST_SECONDS"] = "3600"
        self.assertEqual(self.run_hook(ic.guard, self.save([prompt("x", old), reply("y", old)]))[1], "")
        os.environ["IDLE_COMPACT_TEST_SECONDS"] = "0.9"
        hint = json.loads(self.run_hook(ic.guard, self.save([prompt("x", old), reply("y", old)]))[1])
        self.assertIn("/compact", hint["systemMessage"])
        self.assertNotIn("decision", hint)
        self.assertEqual(self.run_hook(ic.guard, self.save([prompt("x", old), reply("y", old)]))[1], "")

    def test_five_minute_cache_gets_a_hint_instead_of_a_block(self) -> None:
        os.environ["IDLE_COMPACT_TEST_SECONDS"] = "0.9"
        old = int(time.time()) - 30
        hook = self.save([prompt("x", old - 60), reply("cp", old, ttl="5m")]) | {"prompt": "go on"}
        ic.store_checkpoint(ic.folder_for("s1", self.cwd), "s1", "## Idle checkpoint\n### Goal\nship", self.cwd,
                            self.transcript, prompted=old - 60)
        hint = json.loads(self.run_hook(ic.guard, hook)[1])
        self.assertIn("run /pitstop and then /clear", hint["systemMessage"])
        self.assertNotIn("decision", hint)

    def test_session_end_saves_excerpts_unless_cleared_or_fresh(self) -> None:
        old = time.time() - 30
        hook = self.save([prompt("Fix the token refresh race", old), reply("Patched refresh.py", old)])
        self.assertEqual(self.run_hook(ic.end, hook | {"reason": "clear"}), (0, "", ""))
        self.assertIsNone(ic.folder_for("s1"))
        self.assertEqual(self.run_hook(ic.end, hook | {"reason": "prompt_input_exit"})[0], 0)
        checkpoint = ic.folder_for("s1") / "checkpoint.md"
        self.assertIn("### Goal\nT1: Fix the token refresh race", checkpoint.read_text())
        first = checkpoint.read_text()
        self.run_hook(ic.end, hook)
        self.assertEqual(checkpoint.read_text(), first)

    def test_resume_lists_other_checkpoints_in_the_project(self) -> None:
        old = time.time() - 30
        self.save([prompt("x", old - 60), reply("y", old)])
        for session, goal in (("s1", "ship parser"), ("s2", "fix login")):
            ic.store_checkpoint(ic.folder_for(session, self.cwd), session, f"## Idle checkpoint\n### Goal\n{goal}",
                                self.cwd, self.transcript)
        text = ic.resume(self.cwd)
        self.assertIn("Other idle checkpoints", text)
        self.assertIn("idle_compact.py resume <session>", text)
        self.assertEqual(sum(goal in text for goal in ("ship parser", "fix login")), 2)
        self.assertIn("Continuing from idle checkpoint s2", ic.resume(self.cwd, "s2"))
        self.assertNotIn("Other idle checkpoints", ic.resume(self.cwd, "s2"))

    def test_sections_accept_headings_or_bold_labels(self) -> None:
        bold = "## Idle checkpoint\n\n**Next steps:**\n1. run\n\n**Goal:** ship it\n\n**Decisions:**\n- lock"
        ordered = ic.ordered_sections(bold)
        self.assertEqual(ordered.index("### Goal\nship it"), 0)
        self.assertLess(ordered.index("### Decisions"), ordered.index("### Next steps"))

    def test_redaction_and_output_caps(self) -> None:
        text = ic.redact("key sk-ant-abcdefghijklmnopqrstuv and password=hunter2hunter2 ok "
                         "https://bob:pa55word@db.example.com eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4f")
        self.assertNotIn("abcdefghij", text)
        self.assertNotIn("hunter2", text)
        self.assertNotIn("pa55word", text)
        self.assertNotIn("SflKxwRJ", text)
        self.assertIn("db.example.com", text)
        folder = ic.folder_for("s1", self.cwd)
        items = [{"n": i, "kind": "result", "time": time.time(), "text": "needle " + "x " * 3000} for i in range(1, 9)]
        ic.write(folder / "transcript.md", ic.render_transcript(items))
        found = ic.search("needle", self.cwd, False, None, None)
        self.assertLessEqual(len(found), ic.OUTPUT_CAP)
        self.assertEqual(found.count("needle"), 5)
        shown = ic.turn("s1", "T3")
        self.assertLessEqual(len(shown), ic.OUTPUT_CAP)
        self.assertIn("T2 · result", shown)

    def test_guard_blocks_a_warm_switch_once_and_hints_an_upgrade(self) -> None:
        now = time.time()
        call = reply("done", now - 60) | {"effort": "high", "version": "2.1.300"}
        call["message"]["model"] = "claude-opus-5-5"
        switch = {"type": "user", "timestamp": iso(now - 30), "message": {"role": "user", "content":
                  "<local-command-stdout>Set model to `Sonnet 5.5`</local-command-stdout>"}}
        same = json.loads(json.dumps(switch).replace("Sonnet", "Opus"))
        hook = self.save([prompt("go", now - 70), call, same]) | {"prompt": "next", "effort": {"level": "low"}}
        reason = json.loads(self.run_hook(ic.guard, hook)[1])["reason"]
        self.assertIn("Changing the effort mid-session", reason)
        self.assertTrue(reason.endswith("Your prompt:\nnext"))
        self.assertEqual(self.run_hook(ic.guard, hook)[1], "")

        call["timestamp"] = iso(now - 50)
        hook = self.save([prompt("go", now - 70), call, switch]) | {"prompt": "next"}
        self.assertIn("Changing the model", json.loads(self.run_hook(ic.guard, hook)[1])["reason"])

        call["timestamp"] = iso(now - 40)
        hook = self.save([prompt("go", now - 70), call, same]) | {"prompt": "next"}
        self.assertEqual(self.run_hook(ic.guard, hook)[1], "")
        os.environ["CLAUDE_CODE_EXECPATH"] = "/x/.local/share/claude/versions/2.1.301"
        hint = json.loads(self.run_hook(ic.guard, hook)[1])["systemMessage"]
        self.assertIn("2.1.300 → 2.1.301", hint)

    def test_instruction_edits_get_a_note(self) -> None:
        for path, noted in (("/r/CLAUDE.md", True), ("/r/AGENTS.md", True), ("/r/README.md", False)):
            out = self.run_hook(ic.instructions, {"tool_input": {"file_path": path}})[1]
            self.assertEqual(bool(out), noted)
        self.assertIn("loaded at its start", out or self.run_hook(ic.instructions, {"tool_input": {"file_path": "CLAUDE.md"}})[1])

    def test_native_compactor_flag_delays_but_does_not_skip_the_checkpoint(self) -> None:
        (self.home / ".claude.json").write_text(json.dumps(
            {"cachedGrowthBookFeatures": {"tengu_sunny_locket": {"mode": "compact"}}}))
        os.environ["IDLE_COMPACT_TEST_SECONDS"] = "90"
        now = time.time()
        waits = []
        with mock.patch.object(ic.time, "sleep", side_effect=waits.append), \
                mock.patch.object(ic.time, "time", side_effect=lambda: now + sum(waits)):
            self.assertEqual(self.run_hook(ic.arm, self.save([prompt("x", now), reply("y", now)]))[0], 2)
        self.assertAlmostEqual(sum(waits), 100 * ic.NATIVE_FIRE_FRACTION, delta=0.01)


if __name__ == "__main__":
    unittest.main()
