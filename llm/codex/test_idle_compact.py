import contextlib
import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from llm import agent_config, idle_compact as ic


class CodexIdleCompactTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name)
        self.env = mock.patch.dict(os.environ, {
            "HOME": str(self.home), "XDG_STATE_HOME": str(self.home / "state"),
            "IDLE_COMPACT_TEST_SECONDS": "0.01", "IDLE_COMPACT_TEST_MIN_TOKENS": "120000", "IDLE_COMPACT": "on",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.transcript = self.home / "session.jsonl"
        self.hook = {"session_id": "codex-session", "transcript_path": str(self.transcript), "cwd": str(self.home)}
        self.started = int(time.time()) - ic.CODEX_CACHE_TTL - 10
        self.rows = [
            self.row("response_item", {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": "# AGENTS.md instructions\nProject policy"},
                {"type": "input_text", "text": "<environment_context>Bootstrap metadata</environment_context>"},
            ]}),
            self.row("response_item", {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": "Fix the parser without changing its callers."}
            ]}),
            self.row("response_item", {"type": "custom_tool_call", "name": "functions.apply_patch",
                     "input": "*** Begin Patch\n*** Update File: parser.py\n@@\n-old\n+new\n*** End Patch"}),
            self.row("response_item", {"type": "reasoning", "content": "Private reasoning"}),
            self.row("response_item", {"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": "Parser fixed; tests passed. token=secret-value-for-test"}
            ]}),
            self.row("event_msg", {"type": "token_count", "info": {
                "last_token_usage": {"input_tokens": 150_000}
            }}),
        ]
        self.save()

    def row(self, kind, payload, when=None):
        return {"timestamp": datetime.fromtimestamp(self.started if when is None else when, timezone.utc).isoformat(),
                "type": kind, "payload": payload}

    def save(self):
        self.transcript.write_text("\n".join(json.dumps(r) for r in self.rows) + "\n")

    def run_hook(self, function, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(function(*args), 0)
        return output.getvalue()

    def test_checkpoint_resume_and_one_time_cold_guard(self):
        output = self.run_hook(ic.arm, self.hook, "codex")
        self.assertIn("$pitstop", json.loads(output)["systemMessage"])
        folder = ic.folder_for("codex-session")
        checkpoint = (folder / "checkpoint.md").read_text()
        self.assertIn("client: codex", checkpoint)
        self.assertIn("Parser fixed; tests passed.", checkpoint)
        self.assertIn("[REDACTED]", checkpoint)
        transcript = (folder / "transcript.md").read_text()
        self.assertNotIn("Private reasoning", transcript)
        self.assertNotIn("Bootstrap metadata", transcript)
        self.assertNotIn("Project policy", checkpoint)
        self.assertNotIn("secret-value-for-test", transcript)
        self.assertIn("parser.py", ic.resume(str(self.home)))
        self.rows.append(self.row("event_msg", {"type": "task_started"}, time.time()))
        self.save()
        self.hook["prompt"] = "Continue with the next parser case."
        blocked = json.loads(self.run_hook(ic.guard, self.hook, "codex"))
        self.assertEqual(blocked["decision"], "block")
        self.assertIn(self.hook["prompt"], blocked["reason"])
        self.assertEqual(self.run_hook(ic.guard, self.hook, "codex"), "")
        self.assertIn("Parser fixed", ic.resume(str(self.home)))

    def test_an_accepted_later_prompt_makes_the_checkpoint_stale(self):
        self.run_hook(ic.arm, self.hook, "codex")
        self.rows.append(self.row("response_item", {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "Change the approach to preserve whitespace."}
        ]}, time.time()))
        self.save()
        self.assertEqual(ic.resume(str(self.home)), "No idle checkpoint for this project.")
        self.assertNotIn("decision", json.loads(self.run_hook(ic.guard, self.hook, "codex")))

    def test_65k_session_checkpoints_before_the_30_minute_cache_boundary(self):
        os.environ.pop("IDLE_COMPACT_TEST_SECONDS")
        self.rows[-1]["payload"]["info"]["last_token_usage"]["input_tokens"] = 65_000
        self.save()
        now = [self.started + 1619]

        def wait(seconds):
            self.assertIsNone(ic.folder_for("codex-session"))
            now[0] += seconds

        with mock.patch.object(ic.time, "time", side_effect=lambda: now[0]), \
                mock.patch.object(ic.time, "sleep", side_effect=wait):
            self.run_hook(ic.arm, self.hook, "codex")
        self.assertIsNotNone(ic.folder_for("codex-session"))
        self.assertEqual(now[0] - self.started, 1620)

    def test_65k_checkpoint_is_offered_once_at_the_cache_boundary(self):
        self.run_hook(ic.arm, self.hook, "codex")
        os.environ.pop("IDLE_COMPACT_TEST_SECONDS")
        self.rows[-1]["payload"]["info"]["last_token_usage"]["input_tokens"] = 65_000
        self.save()
        with mock.patch.object(ic.time, "time", return_value=self.started + 1799):
            self.assertEqual(self.run_hook(ic.guard, self.hook, "codex"), "")
        with mock.patch.object(ic.time, "time", return_value=self.started + 1800):
            output = self.run_hook(ic.guard, self.hook, "codex")
            self.assertTrue(output)
            offered = json.loads(output)
            self.assertEqual(offered["decision"], "block")
            self.assertEqual(self.run_hook(ic.guard, self.hook, "codex"), "")

    def test_65k_session_without_checkpoint_gets_a_hint_at_the_cache_boundary(self):
        os.environ.pop("IDLE_COMPACT_TEST_SECONDS")
        self.rows[-1]["payload"]["info"]["last_token_usage"]["input_tokens"] = 65_000
        self.save()
        with mock.patch.object(ic.time, "time", return_value=self.started + 1799):
            self.assertEqual(self.run_hook(ic.guard, self.hook, "codex"), "")
        with mock.patch.object(ic.time, "time", return_value=self.started + 1800):
            output = self.run_hook(ic.guard, self.hook, "codex")
            self.assertTrue(output)
            hint = json.loads(output)
            self.assertIn("/compact", hint["systemMessage"])
            self.assertNotIn("decision", hint)

    def test_new_turn_cancels_the_idle_worker(self):
        os.environ["IDLE_COMPACT_TEST_SECONDS"] = "60"
        self.rows[-1]["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.save()

        def user_returns(_):
            self.rows.append(self.row("event_msg", {"type": "task_started"}, time.time() + 1))
            self.save()

        with mock.patch.object(ic.time, "sleep", side_effect=user_returns):
            self.assertEqual(self.run_hook(ic.arm, self.hook, "codex"), "")
        self.assertIsNone(ic.folder_for("codex-session"))

    def test_malformed_latest_usage_keeps_the_previous_valid_call(self):
        self.rows.append(self.row("event_msg", {"type": "token_count", "info": "malformed"}))
        self.save()
        self.assertEqual(ic.codex_last_call(self.transcript)[1], 150_000)
        self.assertIn("systemMessage", json.loads(self.run_hook(ic.codex_guard, self.hook)))

    def test_activity_during_snapshot_invalidates_the_checkpoint(self):
        build_digest = ic.build_digest

        def user_returns(*args):
            self.rows.append(self.row("event_msg", {"type": "task_started"}, time.time()))
            self.save()
            return build_digest(*args)

        with mock.patch.object(ic, "build_digest", side_effect=user_returns):
            self.assertEqual(self.run_hook(ic.arm, self.hook, "codex"), "")
        self.assertEqual(ic.resume(str(self.home)), "No idle checkpoint for this project.")
        warning = json.loads(self.run_hook(ic.guard, self.hook, "codex"))
        self.assertNotIn("decision", warning)

    def test_empty_context_and_malformed_usage_do_not_arm(self):
        for info in [{"last_token_usage": {"input_tokens": 0}}, "malformed", {"last_token_usage": None}]:
            with self.subTest(info=info):
                self.rows[-1]["payload"]["info"] = info
                self.save()
                self.assertEqual(self.run_hook(ic.arm, self.hook, "codex"), "")
        self.assertIsNone(ic.folder_for("codex-session"))

    def test_installer_sets_up_both_clients_and_codex_hooks_are_idempotent(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "ai-install.sh").read_text()
        start = script.index("install_idle_compact() {")
        function = script[start:script.index("\n}", start) + 2]
        subprocess.run(["bash", "-c", 'agent_config() { python3 "$SCRIPT_DIR/agent_config.py" "$@"; }\n'
                        + function + "\ninstall_idle_compact"], check=True,
                       env={**os.environ, "SCRIPT_DIR": str(root)}, capture_output=True)
        self.assertTrue((self.home / ".config/dotfiles/idle_compact.py").is_file())
        self.assertTrue((self.home / ".agents/skills/pitstop/SKILL.md").is_file())
        for profile in [".claude", ".claude-work"]:
            self.assertTrue((self.home / profile / "commands/pitstop.md").is_file())
            self.assertIn("Stop", json.loads((self.home / profile / "settings.json").read_text())["hooks"])
        required = root / "codex/codex-hooks.json"
        target = self.home / "hooks.json"
        agent_config.codex_hooks(str(target), str(required))
        original = target.read_text()
        agent_config.codex_hooks(str(target), str(required))
        self.assertEqual(target.read_text(), original)
        stop = json.loads(original)["hooks"]["Stop"][0]["hooks"][0]
        self.assertTrue(stop["async"])
        self.assertGreater(stop["timeout"], ic.CODEX_CACHE_TTL)

    def test_cli_client_selection_opt_out_and_session_validation(self):
        command = ["python3", ic.__file__, "arm", "--client", "codex"]
        for hook, enabled in [({**self.hook, "session_id": "../escape"}, "on"), (self.hook, "off")]:
            result = subprocess.run(command, input=json.dumps(hook), text=True, capture_output=True,
                                    env={**os.environ, "IDLE_COMPACT": enabled}, check=True)
            self.assertEqual(result.stdout, "")
            self.assertFalse(ic.state_dir().exists())
        result = subprocess.run(command, input=json.dumps(self.hook), text=True, capture_output=True, check=True)
        self.assertIn("$pitstop", json.loads(result.stdout)["systemMessage"])


if __name__ == "__main__":
    unittest.main()
