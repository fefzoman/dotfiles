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
        for key in ("IDLE_COMPACT_TEST_SECONDS", "CLAUDE_CONFIG_DIR"):
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

    def test_arm_skips_empty_or_five_minute_sessions(self) -> None:
        old = time.time() - 30
        os.environ["IDLE_COMPACT_TEST_SECONDS"] = "0.01"
        for recs in ([prompt("x", old), reply("y", old, tokens=0)], [prompt("x", old), reply("y", old, ttl="5m")]):
            self.assertEqual(self.run_hook(ic.arm, self.save(recs))[0], 0)

    def test_arm_wakes_with_digest_then_stores_the_reply(self) -> None:
        old = time.time() - 30
        os.environ["IDLE_COMPACT_TEST_SECONDS"] = "0.01"
        recs = [prompt("<ide_opened_file>a.py opened</ide_opened_file>Fix the token refresh race", old), tool("Edit", {"file_path": f"{self.cwd}/a.py"}, old),
                result("Traceback: boom", old, error=True), prompt("yes", old), reply("done", old)]
        code, _, err = self.run_hook(ic.arm, self.save(recs))
        self.assertEqual(code, 2)
        self.assertIn("Idle checkpoint:", err)
        self.assertIn("T1", err)
        self.assertIn("Fix the token refresh race", err)
        self.assertNotIn("a.py opened", err)
        self.assertNotIn("- T4", err)
        self.assertIn(f"{self.cwd}/a.py (1)", err)
        self.assertIn("Last error, T3: Traceback: boom", err)

        later = time.time() + 1
        hook = self.save(recs + [reply("## Idle checkpoint\n### Goal\nFix race\n### Done\nx\n### Next steps\ny", later)])
        self.assertEqual(self.run_hook(ic.arm, hook)[0], 0)
        folder = ic.folder_for("s1")
        self.assertIn("### Goal\nFix race", (folder / "checkpoint.md").read_text())
        self.assertIn("## T2 · tool ·", (folder / "transcript.md").read_text())
        self.assertEqual(self.run_hook(ic.clear, hook)[1], "")
        self.assertIn("/clear", json.loads(self.run_hook(ic.guard, hook | {"prompt": "/pitstop"})[1])["reason"])
        loaded = json.loads(self.run_hook(ic.clear, hook | {"session_id": "s2"})[1])
        self.assertEqual(loaded["systemMessage"], "Loaded idle checkpoint s1 into session s2.")
        context = loaded["hookSpecificOutput"]["additionalContext"]
        self.assertIn("### Goal\nFix race", context)
        self.assertEqual(self.run_hook(ic.clear, hook)[1], "")

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

    def test_guard_waits_for_a_checkpoint_and_an_expired_cache(self) -> None:
        os.environ["IDLE_COMPACT_TEST_SECONDS"] = "0.9"
        old = time.time() - 30
        self.assertEqual(self.run_hook(ic.guard, self.save([prompt("x", old), reply("y", old)]))[1], "")
        os.environ["IDLE_COMPACT_TEST_SECONDS"] = "3600"
        self.assertEqual(self.run_hook(ic.guard, self.save([prompt("x", old), reply("y", old)]))[1], "")

    def test_codex_guard_hints_after_long_gap(self) -> None:
        event = {"type": "event_msg", "timestamp": iso(time.time() - 4 * 3600),
                 "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 230_000}}}}
        hook = self.save([event])
        self.assertIn("/compact", json.loads(self.run_hook(ic.codex_guard, hook)[1])["systemMessage"])
        self.assertEqual(self.run_hook(ic.codex_guard, hook)[1], "")

    def test_sections_accept_headings_or_bold_labels(self) -> None:
        bold = "## Idle checkpoint\n\n**Next steps:**\n1. run\n\n**Goal:** ship it\n\n**Decisions:**\n- lock"
        ordered = ic.ordered_sections(bold)
        self.assertEqual(ordered.index("### Goal\nship it"), 0)
        self.assertLess(ordered.index("### Decisions"), ordered.index("### Next steps"))

    def test_redaction_and_output_caps(self) -> None:
        text = ic.redact("key sk-ant-abcdefghijklmnopqrstuv and password=hunter2hunter2 ok")
        self.assertNotIn("abcdefghij", text)
        self.assertNotIn("hunter2", text)
        folder = ic.folder_for("s1", self.cwd)
        items = [{"n": i, "kind": "result", "time": time.time(), "text": "needle " + "x " * 3000} for i in range(1, 9)]
        ic.write(folder / "transcript.md", ic.render_transcript(items))
        found = ic.search("needle", self.cwd, False, None, None)
        self.assertLessEqual(len(found), ic.OUTPUT_CAP)
        self.assertEqual(found.count("needle"), 5)
        shown = ic.turn("s1", "T3")
        self.assertLessEqual(len(shown), ic.OUTPUT_CAP)
        self.assertIn("T2 · result", shown)

    def test_native_compactor_makes_arm_step_aside(self) -> None:
        (self.home / ".claude.json").write_text(json.dumps(
            {"cachedGrowthBookFeatures": {"tengu_sunny_locket": {"mode": "compact"}}}))
        os.environ["IDLE_COMPACT_TEST_SECONDS"] = "0.01"
        old = time.time() - 30
        self.assertEqual(self.run_hook(ic.arm, self.save([prompt("x", old), reply("y", old)]))[0], 0)


if __name__ == "__main__":
    unittest.main()
