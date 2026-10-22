import contextlib
import io
import json
import os
import subprocess
import sys
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
            "IDLE_COMPACT_TEST_SECONDS": "0.01", "IDLE_COMPACT": "on",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        which = mock.patch.object(ic.shutil, "which", return_value=None)
        which.start()
        self.addCleanup(which.stop)
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
        self.assertEqual(self.run_hook(ic.arm, self.hook, "codex"), "")
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

    def test_manual_checkpoint_writes_in_thread_without_a_fork(self):
        out = json.loads(self.run_hook(ic.guard, self.hook | {"prompt": "$checkpoint"}, "codex"))
        self.assertIn("or $pitstop in a new one", out["hookSpecificOutput"]["additionalContext"])
        self.rows.append(self.row("response_item", {"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": "## Idle checkpoint\n### Goal\nShip the parser fix"}]}, time.time() + 1))
        self.save()
        self.assertEqual(self.run_hook(ic.arm, self.hook, "codex"), "")
        self.assertIn("Ship the parser fix", (ic.folder_for("codex-session") / "checkpoint.md").read_text())
        self.assertIn("Continuing from idle checkpoint codex-session", ic.resume(str(self.home)))

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
        self.assertEqual(ic.last_call(ic.codex_records(self.transcript))[1], 150_000)
        self.assertIn("systemMessage", json.loads(self.run_hook(ic.guard, self.hook, "codex")))

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

    def test_fork_writes_a_model_summary_from_the_thread(self):
        run, calls = subprocess.run, []

        def fake(command, **kwargs):
            if command[0] != "/bin/codex":
                return run(command, **kwargs)
            calls.append((command, kwargs))
            Path(command[command.index("-o") + 1]).write_text(
                "## Idle checkpoint\n### Goal\nFix the parser\n### Decisions\nKeep callers\n### Dead ends\nRegex")

        self.rows.insert(0, self.row("turn_context", {"model": "gpt-test"}))
        self.save()
        with mock.patch.object(ic.shutil, "which", return_value="/bin/codex"), \
                mock.patch.object(ic.subprocess, "run", side_effect=fake):
            self.run_hook(ic.arm, self.hook, "codex")
        command, kwargs = calls[0]
        self.assertEqual(command[1:6], ["exec", "fork", "codex-session", "--ephemeral", "--skip-git-repo-check"])
        self.assertEqual(command[command.index("-m") + 1], "gpt-test")
        self.assertEqual(kwargs["env"]["IDLE_COMPACT"], "off")
        self.assertIn("run $pitstop and then /clear", kwargs["input"])
        self.assertIn("### Dead ends\nRegex", ic.resume(str(self.home)))

    def test_learned_warm_cache_turns_the_block_into_a_hint(self):
        self.rows[-1]["payload"]["info"]["last_token_usage"]["cached_input_tokens"] = 140_000
        self.rows[-1:-1] = [self.row("turn_context", {"model": "gpt-test"}),
                            self.row("event_msg", {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 100_000}}},
                                     self.started - ic.CODEX_CACHE_TTL)]
        self.save()
        ic.write(ic.cache_log(), json.dumps({f"old:{n}": ["gpt-test", True] for n in range(ic.WARM_SAMPLES - 1)}))
        self.run_hook(ic.arm, self.hook, "codex")
        self.assertEqual(len(json.loads(ic.read(ic.cache_log()))), ic.WARM_SAMPLES)
        hint = json.loads(self.run_hook(ic.guard, self.hook | {"prompt": "next"}, "codex"))
        self.assertIn("$pitstop and then /clear", hint["systemMessage"])
        self.assertNotIn("decision", hint)

    def test_warm_switch_blocks_once_and_an_upgrade_hints(self):
        os.environ.pop("IDLE_COMPACT_TEST_SECONDS")
        now = time.time()
        usage = {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 150_000}}}
        self.rows += [self.row("turn_context", {"model": "gpt-5.6-sol", "effort": "high"}, now - 90),
                      self.row("event_msg", usage, now - 60),
                      self.row("event_msg", {"type": "thread_settings_applied",
                                             "thread_settings": {"model": "gpt-5.6-sol", "reasoning_effort": "low"}}, now)]
        self.save()
        hook = self.hook | {"prompt": "next", "model": "gpt-5.5"}
        with mock.patch.object(ic, "codex_version", return_value="0.162.1"):
            self.assertIn("Changing the model and effort", json.loads(self.run_hook(ic.guard, hook, "codex"))["reason"])
            self.assertEqual(self.run_hook(ic.guard, hook, "codex"), "")
        self.rows += [self.row("event_msg", usage, now - 30)]
        self.save()
        hook["model"] = "gpt-5.6-sol"
        with mock.patch.object(ic, "codex_version", return_value="0.163.0"):
            hint = json.loads(self.run_hook(ic.guard, hook, "codex"))["systemMessage"]
        self.assertIn("Codex changed 0.162.1 → 0.163.0", hint)

    def test_patched_agents_md_gets_a_note(self):
        patch = "*** Begin Patch\n*** Update File: sub/AGENTS.md\n@@\n-a\n+b\n*** End Patch"
        note = json.loads(self.run_hook(ic.instructions, {"tool_input": {"command": patch}}, "codex"))
        self.assertIn("AGENTS.md changed", note["systemMessage"])
        self.assertEqual(self.run_hook(ic.instructions, {"tool_input": {"command": "*** Update File: a.py"}}, "codex"), "")

    def test_session_end_saves_excerpts(self):
        self.run_hook(ic.end, self.hook, "codex")
        self.assertIn("Fix the parser", ic.resume(str(self.home)))

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
        self.assertTrue((self.home / ".agents/skills/checkpoint/SKILL.md").is_file())
        for profile in [".claude", ".claude-work"]:
            self.assertTrue((self.home / profile / "commands/pitstop.md").is_file())
            self.assertTrue((self.home / profile / "commands/checkpoint.md").is_file())
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
        os.environ["PATH"] = "/usr/bin:/bin"
        command = [sys.executable, ic.__file__, "arm", "--client", "codex"]
        for hook, enabled in [({**self.hook, "session_id": "../escape"}, "on"), (self.hook, "off")]:
            result = subprocess.run(command, input=json.dumps(hook), text=True, capture_output=True,
                                    env={**os.environ, "IDLE_COMPACT": enabled}, check=True)
            self.assertEqual(result.stdout, "")
            self.assertFalse(ic.state_dir().exists())
        result = subprocess.run(command, input=json.dumps(self.hook), text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout, "")
        result = subprocess.run([sys.executable, ic.__file__, "guard", "--client", "codex"], input=json.dumps(self.hook | {"prompt": "$pitstop"}),
                                text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout)["reason"],
                         "Idle checkpoint codex-session handed off. Run /clear to continue from it in this window.")
        result = subprocess.run([sys.executable, ic.__file__, "clear"], input=json.dumps(self.hook | {"session_id": "codex-new"}),
                                text=True, capture_output=True, check=True)
        loaded = json.loads(result.stdout)
        self.assertTrue(loaded["systemMessage"].startswith("Loaded idle checkpoint codex-session into session codex-new.\n\n"))
        self.assertIn("client: codex", ic.read(ic.folder_for("codex-session") / "checkpoint.md"))
        self.assertIn("Continuing from idle checkpoint codex-session", loaded["hookSpecificOutput"]["additionalContext"])


if __name__ == "__main__":
    unittest.main()
