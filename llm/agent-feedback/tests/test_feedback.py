import contextlib
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from agent_feedback.cli import bounded_lines, main
from agent_feedback.hooks import MAX_MESSAGE_BYTES, fingerprint, normalize
from agent_feedback.report import markdown, summarize
from agent_feedback.storage import Store


def hook(name="SessionStart", **fields):
    return json.dumps({"session_id": "session-1", "hook_event_name": name, **fields}).encode()


def event(raw=None, provider="claude", cursor=None):
    return normalize(raw if raw is not None else hook(), provider, "owner:https://example.test/repo", "0" * 32, cursor)


class HookTests(unittest.TestCase):
    def test_both_providers_and_lifecycle(self):
        expected = {"SessionStart": "session.started", "SessionEnd": "session.ended",
                    "Stop": "turn.completed", "UserPromptSubmit": "turn.started",
                    "SubagentStart": "agent.started", "SubagentStop": "agent.completed",
                    "PermissionRequest": "permission.requested", "PostCompact": "context.compacted"}
        for provider in ("claude", "codex"):
            for name, kind in expected.items():
                with self.subTest(provider=provider, name=name):
                    result = event(hook(name, turn_id="turn-1", agent_id="agent-1"), provider)
                    self.assertEqual(result["event_type"], kind)
                    self.assertEqual(result["turn_id"], fingerprint("turn-1"))
                    self.assertEqual(result["agent_id"], fingerprint("agent-1"))

    def test_tool_status_is_not_inferred_from_completion(self):
        for provider in ("claude", "codex"):
            for code, outcome in ((0, "success"), (127, "failure"), (None, "unknown"),
                                  (False, "unknown"), ("0", "unknown"), (2**40, "unknown")):
                with self.subTest(provider=provider, code=code):
                    result = event(hook("PostToolUse", tool_name="Bash", tool_use_id="call-1",
                                        tool_response={"exit_code": code}, duration_ms=12), provider)
                    self.assertEqual(result["event_type"], "tool.completed")
                    self.assertEqual(result["tool"]["outcome"], outcome)
                    self.assertEqual(result["tool"]["duration_ms"], 12)
                    self.assertEqual("exit_code" in result["tool"], type(code) is int and abs(code) < 2**31)
        self.assertEqual(event(hook("PostToolUseFailure"))["tool"]["outcome"], "failure")

    def test_drop_all_free_form_content(self):
        secret = "sk-secret-DO-NOT-STORE"
        result = event(hook("PostToolUse", session_id=secret, turn_id=secret, agent_id=secret,
                            tool_use_id=secret, tool_name=secret, prompt=secret, cwd=secret,
                            transcript_path=secret, tool_input={"command": secret},
                            tool_response={"stdout": secret}, last_assistant_message=secret))
        self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(result["tool"]["name"], "other")
        self.assertIsNone(result["occurred_at"])

    def test_invalid_messages_become_safe_gaps(self):
        inputs = [b"", b"{", b"[]", b"null", b"\xff", b"{}", hook(session_id=1),
                  hook("Stop", turn_id=[]), hook("unknown"), hook(hook_event_name=[]),
                  b"[" * 2000, b"x" * (MAX_MESSAGE_BYTES + 1)]
        for raw in inputs:
            with self.subTest(raw=raw[:30]):
                result = event(raw)
                self.assertEqual(result["event_type"], "collector.gap")
                self.assertNotIn("payload", result)

    def test_stable_identity_only_where_supported(self):
        raw = hook("PostToolUse", tool_use_id="call-1")
        self.assertEqual(event(raw)["event_id"], event(raw)["event_id"])
        self.assertNotEqual(event(hook("PreToolUse", tool_use_id="call-1"))["event_id"], event(raw)["event_id"])
        self.assertEqual(event(cursor="export:1")["event_id"], event(cursor="export:1")["event_id"])
        self.assertNotEqual(event()["event_id"], event()["event_id"])

    def test_bounded_jsonl_recovers_after_oversized_line(self):
        raw = b"x" * (MAX_MESSAGE_BYTES + 20) + b"\n" + hook() + b"\n{"
        lines = list(bounded_lines(io.BytesIO(raw)))
        self.assertEqual(len(lines), 3)
        self.assertEqual(event(lines[0])["reason"], "oversized_message")
        self.assertEqual(event(lines[1])["event_type"], "session.started")
        self.assertEqual(event(lines[2])["event_type"], "collector.gap")

    def test_published_schema_covers_generated_fields(self):
        root = Path(__file__).resolve().parents[1]
        schema = json.loads((root / "configs/schemas/event-v1.schema.json").read_text())
        for provider in ("claude", "codex"):
            for raw in (hook(), hook("Stop", turn_id="turn"), hook("SubagentStart", agent_id="agent"),
                        hook("PostToolUse", tool_use_id="call", tool_response={"exit_code": 1}), b"{"):
                result = event(raw, provider)
                self.assertLessEqual(set(schema["required"]), set(result))
                self.assertLessEqual(set(result), set(schema["properties"]))
                self.assertIn(result["event_type"], schema["properties"]["event_type"]["enum"])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name) / "state"
        self.store = Store(self.directory)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_private_permissions_and_durable_installation(self):
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.directory / "events.sqlite3").stat().st_mode & 0o777, 0o600)
        other = Store(self.directory)
        try:
            self.assertEqual(other.installation_id, self.store.installation_id)
        finally:
            other.close()

    def test_idempotent_scoped_events_and_sequence(self):
        result = event(cursor="cursor-1")
        self.assertTrue(self.store.append(result))
        self.assertFalse(self.store.append(result))
        for field in ("provider", "repository_id", "session_id", "installation_id"):
            self.assertTrue(self.store.append({**result, field: "different"}))
        rows = list(self.store.events())
        self.assertEqual(len(rows), 5)
        self.assertEqual(len({row["sequence"] for row in rows}), 5)

    def test_retention_purges_expired_events(self):
        self.store.append({**event(), "observed_at": "2000-01-01T00:00:00+00:00"})
        self.assertEqual(list(self.store.events()), [])
        self.store.append(event())
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)

    def test_quota_failure_preserves_previous_event(self):
        self.store.append(event())
        pages = self.store.db.execute("PRAGMA page_count").fetchone()[0]
        self.store.db.execute(f"PRAGMA max_page_count={pages}")
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.append({**event(), "padding": "x" * MAX_MESSAGE_BYTES})
        self.assertEqual(len(list(self.store.events())), 1)

    def test_concurrent_collectors(self):
        def append(index):
            store = Store(self.directory)
            try:
                return store.append(event(cursor=str(index)))
            finally:
                store.close()
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertTrue(all(pool.map(append, range(12))))
        self.assertEqual(len(list(self.store.events())), 12)

    def test_reject_insecure_directory_and_database_links(self):
        insecure = Path(self.temp.name) / "insecure"
        insecure.mkdir(mode=0o755)
        with self.assertRaises(PermissionError):
            Store(insecure)
        linked = Path(self.temp.name) / "linked"
        linked.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaises(PermissionError):
            Store(linked)
        target = Path(self.temp.name) / "target"
        target.write_text("untouched")
        private = Path(self.temp.name) / "private"
        private.mkdir(mode=0o700)
        (private / "events.sqlite3").symlink_to(target)
        with self.assertRaises(OSError):
            Store(private)
        self.assertEqual(target.read_text(), "untouched")


class ReportTests(unittest.TestCase):
    def test_stop_is_not_session_end_and_task_outcome_stays_unknown(self):
        rows = summarize([event(), event(hook("Stop"))])
        self.assertEqual(rows[0]["status"], "incomplete")
        self.assertEqual(rows[0]["turn_completions"], 1)
        rows = summarize([event(), event(hook("Stop")), event(hook("SessionEnd"))])
        self.assertEqual(rows[0]["status"], "ended")
        self.assertEqual(rows[0]["outcome"], "unknown")
        self.assertIsNone(rows[0]["missing_event_count"])

    def test_gaps_missing_start_and_unclosed_tools_are_incomplete(self):
        for middle in (event(hook(turn_id=[])), event(hook("PreToolUse", tool_use_id="call-1"))):
            rows = summarize([event(), middle, event(hook("SessionEnd"))])
            self.assertTrue(all(row["status"] == "incomplete" for row in rows))
        self.assertEqual(summarize([event(hook("SessionEnd"))])[0]["status"], "incomplete")

    def test_unattributed_gap_is_not_assigned_to_another_session(self):
        rows = summarize([event(), event(b"{"), event(hook("SessionEnd"))])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["gaps"], 0)
        self.assertEqual(rows[1]["gaps"], 1)
        self.assertEqual(rows[1]["status"], "incomplete")

    def test_activity_after_session_end_is_incomplete(self):
        rows = summarize([event(), event(hook("SessionEnd")), event(hook("Stop"))])
        self.assertEqual(rows[0]["status"], "incomplete")

    def test_completed_tool_failure_is_not_session_failure(self):
        start = event(hook("PreToolUse", tool_use_id="call-1"))
        end = event(hook("PostToolUse", tool_use_id="call-1", tool_response={"exit_code": 127}))
        row = summarize([event(), start, end, event(hook("SessionEnd"))])[0]
        self.assertEqual(row["tool_failures"], 1)
        self.assertEqual(row["unclosed_tools"], 0)
        self.assertEqual(row["status"], "ended")
        self.assertEqual(row["outcome"], "unknown")

    def test_empty_report_does_not_assert_health(self):
        self.assertIn("does not establish hook health", markdown([]))


class CLITests(unittest.TestCase):
    def invoke(self, state, command, raw=b"", *extra):
        argv = ["--state-dir", str(state), command]
        if command != "report":
            argv += ["--provider", "codex", "--repository", "owner:example.test/repo"]
        argv += list(extra)
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(raw))), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(argv)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_collection_is_off_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "off"
            self.assertEqual(self.invoke(path, "collect", hook()), (0, "", ""))
            self.assertFalse(path.exists())

    def test_ingest_replay_truncation_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = hook() + b"\n" + hook("PostToolUse", tool_use_id="call-1") + b"\n{"
            for _ in range(2):
                self.assertEqual(self.invoke(directory, "ingest", raw, "--mode", "metadata", "--source-id", "export-1"), (0, "", ""))
            status, output, error = self.invoke(directory, "report", b"", "--format", "json")
            self.assertEqual((status, error), (0, ""))
            rows = json.loads(output)
            self.assertEqual(sum(row["events"] for row in rows), 3)
            self.assertEqual(sum(row["gaps"] for row in rows), 1)

    def test_hook_failure_is_fail_open_but_ingest_failure_is_not(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("agent_feedback.cli.Store", side_effect=OSError("DO-NOT-PRINT-SECRET")):
                for command, extra, status in (("collect", [], 0), ("ingest", ["--source-id", "export"], 1)):
                    result, output, error = self.invoke(directory, command, hook(), "--mode", "metadata", *extra)
                    self.assertEqual(result, status)
                    self.assertEqual(output, "")
                    self.assertIn("telemetry may be missing", error)
                    self.assertNotIn("DO-NOT-PRINT-SECRET", error)

    def test_secrets_do_not_reach_database_reports_or_hook_output(self):
        secret = "postgres://user:super-secret@example.test/private"
        with tempfile.TemporaryDirectory() as directory:
            raw = hook("PostToolUse", tool_name=secret, session_id=secret, tool_input={"command": secret},
                       tool_response={"stdout": secret}, prompt=secret)
            self.assertEqual(self.invoke(directory, "collect", raw, "--mode", "metadata"), (0, "", ""))
            self.assertNotIn(secret.encode(), (Path(directory) / "events.sqlite3").read_bytes())
            for format in ("markdown", "json"):
                status, output, error = self.invoke(directory, "report", b"", "--format", format)
                self.assertEqual((status, error), (0, ""))
                self.assertNotIn(secret, output)


if __name__ == "__main__":
    unittest.main()
