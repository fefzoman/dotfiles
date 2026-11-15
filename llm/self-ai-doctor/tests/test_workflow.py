import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_feedback.cli import main
from agent_feedback.diagnosis import analyze
from agent_feedback.hooks import fingerprint, normalize
from agent_feedback.install_hooks import install, merged, read_config, replace_config
from agent_feedback.remediation import ProposalError, propose
from agent_feedback.repository import identity, root
from agent_feedback.storage import Store

PROJECT = Path(__file__).resolve().parents[1]
REPOSITORY = "origin:https://example.test/team/repo.git"
SECRET = "sk-untrusted-secret-do-not-persist"


def capture(session="session-1", call="call-1", code=127, command="project-test", provider="claude", **extra):
    payload = {"hook_event_name": "PostToolUse", "session_id": session, "tool_use_id": call,
               "tool_name": "Bash", "tool_input": {"command": command},
               "tool_response": {"exit_code": code, "stdout": SECRET}, **extra}
    return normalize(json.dumps(payload).encode(), provider, REPOSITORY, "0" * 32)


def recurring(code=127):
    return [capture(session, f"call-{index}", code=code, provider=provider)
            for session, provider in (("s1", "claude"), ("s2", "codex")) for index in range(3)]


class DiagnosisTests(unittest.TestCase):
    def test_recurrence_evidence_and_cross_agent_clustering(self):
        events = recurring()
        findings = analyze(events)
        self.assertEqual({row["rule"] for row in findings}, {"missing_executable", "repeated_command_failure"})
        references = {(row["provider"], row["session_id"], row["event_id"]) for row in events}
        for finding in findings:
            self.assertEqual((finding["incidents"], finding["sessions"]), (6, 2))
            self.assertEqual(finding["providers"], ["claude", "codex"])
            self.assertTrue(finding["eligible_for_draft"])
            self.assertEqual(finding["task_outcome"], "unknown")
            self.assertLessEqual({(row["provider"], row["session_id"], row["event_id"])
                                  for row in finding["evidence"]}, references)
            self.assertNotIn(SECRET, json.dumps(finding))
        self.assertEqual({row["issue_id"] for row in analyze(events + events)},
                         {row["issue_id"] for row in findings})
        self.assertTrue(all(row["incidents"] == 6 for row in analyze(events + events)))

    def test_recovered_retry_is_not_reported_as_repeated_failure(self):
        events = [capture(call=f"call-{index}", code=1) for index in range(3)]
        events.append(capture(call="recovery", code=0))
        self.assertEqual(analyze(events), [])

    def test_gate_requires_independent_sessions(self):
        events = [capture(call=f"call-{index}") for index in range(5)]
        self.assertTrue(all(not row["eligible_for_draft"] for row in analyze(events)))
        self.assertEqual(analyze([capture(code=0), capture(call="different", code=0)]), [])

    def test_distinct_commands_are_not_conflated_and_legacy_fields_still_work(self):
        events = [capture(call=f"call-{index}", code=1, command=f"test-{index}") for index in range(4)]
        self.assertEqual(analyze(events), [])
        legacy = capture()
        legacy["tool"].pop("command_fingerprint")
        legacy["tool"].pop("error_family")
        self.assertEqual(analyze([legacy])[0]["rule"], "missing_executable")

    def test_command_can_be_correlated_from_start_event(self):
        events = []
        for index in range(3):
            start = capture(call=str(index), code=None, hook_event_name="PreToolUse")
            end = capture(call=str(index), code=1, tool_input={})
            events.extend((start, end))
        self.assertEqual(analyze(events)[0]["rule"], "repeated_command_failure")

    def test_permission_requests_never_enable_instruction_or_sandbox_changes(self):
        events = [capture(session, str(index), hook_event_name="PermissionRequest")
                  for session in ("one", "two") for index in range(3)]
        finding = analyze(events)[0]
        self.assertEqual(finding["rule"], "permission_friction")
        self.assertFalse(finding["eligible_for_draft"])
        self.assertIn("Do not bypass", finding["recommendation"])

    def test_gap_is_unknown_not_task_failure(self):
        result = normalize(b"{", "codex", REPOSITORY, "0" * 32)
        finding = analyze([result])[0]
        self.assertEqual(finding["rule"], "collection_gap")
        self.assertEqual(finding["task_outcome"], "unknown")
        self.assertFalse(finding["eligible_for_draft"])

    def test_text_classification_does_not_retain_text_or_invent_exit_code(self):
        result = capture(code=None, tool_response=f"{SECRET}: command not found", command=SECRET)
        self.assertEqual(result["tool"]["error_family"], "missing_executable")
        self.assertNotIn("exit_code", result["tool"])
        self.assertNotIn(SECRET, json.dumps(analyze([result])))
        success = capture(code=0, tool_response={"exit_code": 0, "stdout": "command not found"})
        self.assertEqual(analyze([success]), [])


class RepositoryTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="feedback test '")
        self.home = Path(self.temp.name)
        self.repo = self.home / "repo 'quoted'"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("remote", "add", "origin", "https://example.test/team/repo.git")

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args, **kwargs):
        return subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, text=True, check=True, **kwargs)


class InstallerTests(RepositoryTestCase):
    def setUp(self):
        super().setUp()
        self.environment = {"HOME": str(self.home), "CODEX_HOME": str(self.home / ".codex"),
                            "CLAUDE_CONFIG_DIR": str(self.home / ".claude")}
        self.paths = [self.home / ".claude/settings.json", self.home / ".codex/hooks.json"]
        self.original = b'{"unrelated":{"keep":true},"hooks":{"PostToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"my-existing-hook"}]}]}}\n'
        for path in self.paths:
            path.parent.mkdir()
            path.write_bytes(self.original)
            path.chmod(0o640)

    def do_install(self):
        with patch.dict(os.environ, self.environment), contextlib.redirect_stdout(io.StringIO()):
            install(self.repo, None, ("claude", "codex"), self.home / "state 'quoted'")

    def test_merge_preserves_existing_settings_backups_and_permissions(self):
        self.do_install()
        snapshots = []
        for path in self.paths:
            config = json.loads(path.read_bytes())
            self.assertEqual(config["unrelated"], {"keep": True})
            self.assertNotIn(REPOSITORY, path.read_text())
            self.assertEqual(config["hooks"]["PostToolUse"][0]["hooks"][0]["command"], "my-existing-hook")
            self.assertEqual(config["hooks"]["PostToolUse"][0]["matcher"], "Bash")
            backups = list(path.parent.glob(path.name + ".agent-feedback-backup-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), self.original)
            self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            snapshots.append(path.read_bytes())
        self.do_install()
        self.assertEqual([path.read_bytes() for path in self.paths], snapshots)
        self.assertTrue(all(len(list(path.parent.glob(path.name + ".agent-feedback-backup-*"))) == 1 for path in self.paths))

    def test_invalid_second_provider_is_detected_before_replacing_first(self):
        self.paths[1].write_bytes(b'{"hooks": [], "secret": "' + SECRET.encode() + b'"}')
        with self.assertRaises(ValueError):
            self.do_install()
        self.assertEqual(self.paths[0].read_bytes(), self.original)
        self.assertFalse(list(self.paths[0].parent.glob("*.agent-feedback-backup-*")))

    def test_new_configs_are_private_and_need_no_backup(self):
        for path in self.paths:
            path.unlink()
        self.do_install()
        for path in self.paths:
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertFalse(list(path.parent.glob("*.agent-feedback-backup-*")))

    def test_reject_ambiguous_or_invalid_json_without_writes(self):
        for raw in (b"{", b"[]", b'{"hooks":{},"hooks":{}}', b'{"value": NaN}',
                    b'{"hooks":{"Stop":[{}]}}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                merged(raw, "claude", "command", "marker")

    def test_symlink_refused_and_concurrent_changes_preserved(self):
        link = self.home / "link"
        link.symlink_to(self.paths[0])
        with self.assertRaises(OSError):
            read_config(link)
        before, mode = read_config(self.paths[0])
        self.paths[0].write_text('{"changed":true}')
        with self.assertRaises(ValueError):
            replace_config(self.paths[0], before, b"{}", mode)
        self.assertEqual(json.loads(self.paths[0].read_text()), {"changed": True})

    def test_installed_handler_collects_only_opted_in_worktree(self):
        self.do_install()
        config = json.loads(self.paths[1].read_bytes())
        command = config["hooks"]["PostToolUse"][-1]["hooks"][0]["command"]
        scoped = {"hook_event_name": "PostToolUse", "session_id": "s", "tool_name": "Bash",
                  "cwd": str(self.repo), "tool_response": {"exit_code": 127},
                  "tool_input": {"command": SECRET}}
        nested = self.repo / "nested-repository"
        nested.mkdir()
        subprocess.run(["git", "init", "-q", str(nested)], check=True, capture_output=True)
        for cwd in (str(self.repo), str(self.home), str(nested), None):
            result = subprocess.run(["/bin/sh", "-c", command], input=json.dumps({**scoped, "cwd": cwd}),
                                    text=True, capture_output=True, check=True)
            self.assertEqual((result.stdout, result.stderr), ("", ""))
        store = Store(self.home / "state 'quoted'")
        try:
            rows = list(store.events())
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["repository_id"], fingerprint(REPOSITORY))
        finally:
            store.close()
        self.assertNotIn(SECRET.encode(), (self.home / "state 'quoted'/events.sqlite3").read_bytes())

    def test_installer_module_supports_personal_and_work_profiles(self):
        for suffix in ("", "-work"):
            environment = {**os.environ, "PYTHONPATH": str(PROJECT / "src"),
                           "CLAUDE_CONFIG_DIR": str(self.home / (".claude" + suffix)),
                           "CODEX_HOME": str(self.home / (".codex" + suffix))}
            result = subprocess.run([sys.executable, "-P", "-m", "agent_feedback.install_hooks",
                                     "--repo", str(self.repo)], env=environment, cwd=self.home,
                                    capture_output=True, text=True, check=True)
            self.assertIn("Merged", result.stdout)
            self.assertEqual(result.stderr, "")
            for name in ("CLAUDE_CONFIG_DIR", "CODEX_HOME"):
                self.assertIn(environment[name], result.stdout)

    def test_multiple_opted_in_repositories_keep_separate_handlers(self):
        self.do_install()
        another = self.home / "another"
        another.mkdir()
        subprocess.run(["git", "init", "-q", str(another)], check=True, capture_output=True)
        with patch.dict(os.environ, self.environment), contextlib.redirect_stdout(io.StringIO()):
            install(another, "owner:another", ("codex",), self.home / "state")
        entries = json.loads(self.paths[1].read_text())["hooks"]["SessionStart"]
        self.assertEqual(len(entries), 2)
        self.assertNotEqual(entries[0]["hooks"][0]["statusMessage"], entries[1]["hooks"][0]["statusMessage"])


class ProposalTests(RepositoryTestCase):
    def finding(self):
        return next(row for row in analyze(recurring()) if row["rule"] == "missing_executable")

    def test_draft_patch_preserves_existing_files_applies_and_is_idempotent(self):
        existing = "# Existing policy\n\nKeep approvals."
        (self.repo / "AGENTS.md").write_text(existing)
        result = propose(self.repo, self.finding())
        self.assertFalse(result["validated"])
        self.assertTrue(result["human_review_required"])
        self.assertEqual((self.repo / "AGENTS.md").read_text(), existing)
        self.assertFalse((self.repo / "CLAUDE.md").exists())
        self.assertNotIn(SECRET, result["patch"])
        self.git("apply", "--check", "-", input=result["patch"])
        self.git("apply", "-", input=result["patch"])
        agents = (self.repo / "AGENTS.md").read_text()
        claude = (self.repo / "CLAUDE.md").read_text()
        self.assertTrue(agents.startswith(existing))
        self.assertIn("Recovery guidance", claude)
        self.assertEqual(agents.split("<!-- agent-feedback:", 1)[1], claude.split("<!-- agent-feedback:", 1)[1])
        self.assertEqual(propose(self.repo, self.finding())["patch"], "")
        other_command = [capture(row["session_id"], str(index), command="different-command", provider=row["provider"])
                         for index, row in enumerate(recurring())]
        other_finding = next(row for row in analyze(other_command) if row["rule"] == "missing_executable")
        self.assertNotEqual(other_finding["issue_id"], self.finding()["issue_id"])
        self.assertEqual(propose(self.repo, other_finding)["patch"], "")

    def test_existing_newline_empty_file_and_two_new_files_have_valid_patches(self):
        for content in (None, "", "# Existing\n"):
            with self.subTest(content=content):
                for target in ("AGENTS.md", "CLAUDE.md"):
                    path = self.repo / target
                    path.unlink(missing_ok=True)
                    if content is not None:
                        path.write_text(content)
                result = propose(self.repo, self.finding())
                self.git("apply", "--check", "-", input=result["patch"])

    def test_targets_and_frequency_gate_fail_closed(self):
        target = self.home / "outside"
        target.write_text("untouched")
        (self.repo / "AGENTS.md").symlink_to(target)
        with self.assertRaises(OSError):
            propose(self.repo, self.finding())
        with self.assertRaises(ProposalError):
            propose(self.repo, analyze([capture()])[0])
        self.assertEqual(target.read_text(), "untouched")

    def test_altered_marker_is_not_overwritten(self):
        finding = self.finding()
        (self.repo / "AGENTS.md").write_text(f"<!-- agent-feedback:{finding['issue_id']} -->\nEdited by user\n")
        with self.assertRaises(ProposalError):
            propose(self.repo, finding)

    def test_cli_analysis_and_proposal_use_only_fresh_repository_scoped_evidence(self):
        state = self.home / "state"
        store = Store(state)
        try:
            for row in recurring():
                store.append(row)
            store.append({**capture("foreign"), "repository_id": fingerprint("another-repo")})
        finally:
            store.close()
        base = ["--state-dir", str(state)]
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(main(base + ["analyze", "--repo", str(self.repo), "--format", "json"]), 0)
        findings = json.loads(stdout.getvalue())
        self.assertTrue(all(row["incidents"] == 6 for row in findings))
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(main(base + ["propose", "--repo", str(self.repo), "--issue", findings[0]["issue_id"], "--format", "json"]), 0)
        proposal = json.loads(stdout.getvalue())
        self.assertEqual(proposal["status"], "draft")
        self.git("apply", "--check", "-", input=proposal["patch"])
        self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_repository_helpers_do_not_use_basename_identity(self):
        self.assertEqual(root(self.repo), self.repo.resolve())
        self.assertEqual(identity(self.repo), REPOSITORY)

    def test_repository_discovery_ignores_inherited_git_environment(self):
        with patch.dict(os.environ, {"GIT_DIR": "/nonexistent", "GIT_WORK_TREE": "/nonexistent"}):
            self.assertEqual(root(self.repo), self.repo.resolve())
            self.assertEqual(identity(self.repo), REPOSITORY)


if __name__ == "__main__":
    unittest.main()
