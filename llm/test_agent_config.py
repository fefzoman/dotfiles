import io
import json
import os
import re
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from llm import agent_config


SCRIPT_DIR = Path(__file__).resolve().parent


class AgentInstallationTests(unittest.TestCase):
    def test_context_efficiency_preserves_custom_settings_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            config = profile / "config.toml"
            config.write_text('model = "custom"\n[skills]\ninclude_instructions = true\n'
                              'max_context_tokens = 9000\n[plugins."superpowers@superpowers-dev"]\nenabled = true\n'
                              '[plugins."custom@local"]\nenabled = true\n')
            settings = profile / "settings.json"
            settings.write_text('{"env":{"CUSTOM":"yes"},"enabledPlugins":{"custom@local":true}}')
            for agent in ("codex", "claude"):
                self.assertFalse(agent_config.context_efficient(agent, str(profile)))
                agent_config.context_efficiency(agent, str(profile))
                self.assertTrue(agent_config.context_efficient(agent, str(profile)))
                first = (config if agent == "codex" else settings).read_text()
                agent_config.context_efficiency(agent, str(profile))
                self.assertEqual(first, (config if agent == "codex" else settings).read_text())
            data = agent_config.load_toml(str(config))
            self.assertEqual(data["model"], "custom")
            self.assertEqual(data["skills"], {"include_instructions": True, "max_context_tokens": 2000})
            self.assertFalse(data["plugins"]["superpowers@superpowers-dev"]["enabled"])
            self.assertTrue(data["plugins"]["custom@local"]["enabled"])
            data = agent_config.load(str(settings))
            self.assertEqual(data["env"], {"CUSTOM": "yes", "SLASH_COMMAND_TOOL_CHAR_BUDGET": "8000"})
            self.assertFalse(data["enabledPlugins"]["superpowers@claude-plugins-official"])
            self.assertTrue(data["enabledPlugins"]["custom@local"])

    def test_context_efficiency_removes_only_eager_serena_hooks(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            for agent, filename in (("codex", "hooks.json"), ("claude", "settings.json")):
                path = profile / filename
                agent_config.save(str(path), {"hooks": {"SessionStart": [{"hooks": [
                    {"type": "command", "command": "serena-hooks activate --client=" + agent},
                    {"type": "command", "command": "custom-check"}]}], "SessionEnd": [{"hooks": [
                    {"type": "command", "command": "serena-hooks cleanup --client=" + agent}]}]}})
                agent_config.context_efficiency(agent, str(profile))
                commands = [e[3] for e in agent_config.hook_entries(agent_config.load(str(path)))]
                self.assertEqual(commands, ["custom-check", "serena-hooks cleanup --client=" + agent])

    def test_context_efficiency_rejects_unsupported_toml_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            text = 'skills.max_context_tokens = 9000\n'
            path.write_text(text)
            with self.assertRaises((SystemExit, tomllib.TOMLDecodeError)):
                agent_config.context_efficiency("codex", directory)
            self.assertEqual(path.read_text(), text)

    def test_unattended_install_refuses_running_agents(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_installer_function("warn_live_sessions", Path(directory), 'pgrep() { return 0; }')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Stop running agents", result.stderr)

    def test_context_defaults_reach_all_four_installed_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            for name in (".codex", ".codex-work", ".claude", ".claude-work"):
                (home / name).mkdir()
            result = self.run_installer_function("configure_context_efficiency", home)
            self.assertEqual(result.returncode, 0, result.stderr)
            for agent in ("codex", "claude"):
                for name in (f".{agent}", f".{agent}-work"):
                    self.assertTrue(agent_config.context_efficient(agent, str(home / name)))

    def test_platform_plugins_are_scoped_without_touching_work_or_custom_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            for agent, filename in (("codex", "config.toml"), ("claude", "settings.json")):
                for suffix in ("", "-work"):
                    profile = Path(directory) / f".{agent}{suffix}"
                    profile.mkdir()
                    path = profile / filename
                    initial = ('# keep this comment\nmodel = "keep"\n'
                               '[plugins."dlm@dlm-user"]\nenabled = true\nother = 1\n'
                               '[plugins."custom@mine"]\nenabled = true\n' if agent == "codex" else
                               json.dumps({"enabledPlugins": {"dlm@dlm-user": True, "custom@mine": True}, "custom": 1}))
                    path.write_text(initial)
                    self.assertEqual(agent_config.plugins_scoped(agent, str(profile)), bool(suffix))
                    for _ in range(2):
                        agent_config.scope_plugins(agent, str(profile))
                    self.assertTrue(agent_config.plugins_scoped(agent, str(profile)))
                    data = agent_config.load_toml(str(path)) if agent == "codex" else agent_config.load(str(path))
                    plugins = data["plugins"] if agent == "codex" else data["enabledPlugins"]
                    active = plugins["dlm@dlm-user"]["enabled"] if agent == "codex" else plugins["dlm@dlm-user"]
                    self.assertEqual(active, bool(suffix))
                    if suffix:
                        self.assertEqual(path.read_text(), initial)
                    if agent == "codex":
                        self.assertIn("# keep this comment", path.read_text())
                        self.assertEqual(plugins["custom@mine"], {"enabled": True})
                        self.assertEqual(plugins["dlm@dlm-user"]["other"], 1)
                    else:
                        self.assertTrue(plugins["custom@mine"])
                        self.assertEqual(data["custom"], 1)

    def test_pre_tool_hook_keeps_unrelated_hooks_in_same_group(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "settings.json")
            custom = {"type": "command", "command": "custom-check"}
            agent_config.save(path, {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
                {"type": "command", "command": agent_config.READ_HINT}, custom]}]}})
            for _ in range(2):
                agent_config.read_hint(path)
            entries = list(agent_config.hook_entries(agent_config.load(path)))
            self.assertEqual(sum(e[3] == "custom-check" for e in entries), 1)
            self.assertEqual(sum(e[3] == agent_config.READ_HINT for e in entries), 1)

    def test_idle_hook_install_keeps_unrelated_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "settings.json")
            agent_config.save(path, {"hooks": {"Stop": [{"hooks": [
                {"type": "command", "command": f"{agent_config.IDLE_COMPACT} arm"},
                {"type": "command", "command": "custom-check"}]}]}})
            agent_config.idle_compact(path)
            entries = list(agent_config.hook_entries(agent_config.load(path)))
            self.assertEqual(sum(e[3] == "custom-check" for e in entries), 1)

    def test_plugin_scope_rejects_unsupported_toml_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / ".codex"
            profile.mkdir()
            path = profile / "config.toml"
            original = 'plugins = { "dlm@dlm-user" = { enabled = true } }\n'
            path.write_text(original)
            with self.assertRaises((SystemExit, tomllib.TOMLDecodeError)):
                agent_config.scope_plugins("codex", str(profile))
            self.assertEqual(path.read_text(), original)

    def test_duplicate_codex_hooks_are_repaired_and_custom_hooks_survive(self):
        with tempfile.TemporaryDirectory() as directory:
            required = SCRIPT_DIR / "codex/codex-hooks.json"
            path = str(Path(directory) / "hooks.json")
            data = agent_config.load(str(required))
            event = next(iter(data["hooks"]))
            group = json.loads(json.dumps(data["hooks"][event][0]))
            group["hooks"].append({"type": "command", "command": "custom-check"})
            data["hooks"][event].append(group)
            agent_config.save(path, data)
            self.assertFalse(agent_config.hooks_unique(path))
            self.assertFalse(agent_config.codex_hooks_valid(str(required), path))
            agent_config.codex_hooks(path, str(required))
            self.assertTrue(agent_config.codex_hooks_valid(str(required), path))
            self.assertTrue(agent_config.hooks_unique(path))
            self.assertEqual(sum(e[3] == "custom-check" for e in agent_config.hook_entries(agent_config.load(path))), 1)

    def run_installer_function(self, name, home, extra=""):
        source = (SCRIPT_DIR / "ai-install.sh").read_text()
        functions = "\n".join(
            re.search(rf"^{function}\(\) \{{.*?^\}}", source, re.M | re.S)[0]
            for function in ("agent_config", "with_claude_profile", name)
        )
        return subprocess.run(
            ["bash", "-euo", "pipefail", "-c", functions + "\n" + extra + "\n" + name],
            env={**os.environ, "HOME": str(home), "SCRIPT_DIR": str(SCRIPT_DIR)},
            capture_output=True, text=True,
        )

    def test_installs_separate_agent_policies(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            result = self.run_installer_function("install_global_agents", home)
            self.assertEqual(result.returncode, 0, result.stderr)
            for profile, agent, filename in (
                (".codex", "codex", "AGENTS.md"), (".codex-work", "codex", "AGENTS.md"),
                (".claude", "claude", "CLAUDE.md"), (".claude-work", "claude", "CLAUDE.md"),
            ):
                self.assertEqual(
                    (home / profile / filename).read_text(),
                    (SCRIPT_DIR / agent / "__AGENTS.md").read_text(),
                )
                for skill in ("natural-article", "investigation"):
                    self.assertEqual(
                        (home / profile / f"skills/{skill}/SKILL.md").read_text(),
                        (SCRIPT_DIR / f"skills/{skill}/SKILL.md").read_text(),
                    )

    def test_superpowers_installation_and_reuse(self):
        for mode in ("installed", "upstream", "failure"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                mock = home / "codex"
                mock.write_text('''#!/usr/bin/env bash
echo "$CODEX_HOME $*" >> "$HOME/calls"
if [[ "$2" == list ]]; then
  [[ "$mode" == installed ]] && echo '{"installed":[{"pluginId":"superpowers@superpowers-dev","installed":true,"enabled":true}]}' || echo '{"installed":[]}'
else
  [[ "$mode" != failure ]]
fi
''')
                mock.chmod(0o755)
                claude = home / "claude"
                claude.write_text('''#!/usr/bin/env bash
echo "${CLAUDE_CONFIG_DIR:-default} $*" >> "$HOME/calls"
if [[ "$2" == list ]]; then
  [[ "$mode" == installed ]] && echo '[{"id":"superpowers@claude-plugins-official","enabled":true}]' || echo '[]'
fi
''')
                claude.chmod(0o755)
                result = self.run_installer_function(
                    "install_superpowers", home,
                    f'export PATH="$HOME:$PATH" mode={mode}',
                )
                calls = (home / "calls").read_text()
                self.assertEqual(result.returncode == 0, mode != "failure", result.stderr)
                self.assertIn(str(home / ".codex"), calls)
                if mode != "failure":
                    self.assertIn(str(home / ".codex-work"), calls)
                    self.assertIn("default plugin list", calls)
                    self.assertIn(f"{home / '.claude-work'} plugin list", calls)
                self.assertNotIn("plugin add superpowers@openai-curated", calls)
                self.assertEqual("plugin add superpowers@superpowers-dev" in calls, mode == "upstream")
                self.assertEqual(
                    calls.count("plugin install --scope user --yes superpowers@claude-plugins-official"),
                    2 if mode == "upstream" else 0,
                )

    def test_codex_hooks_updates_timeout_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            target, required = Path(directory) / "hooks.json", SCRIPT_DIR / "codex/codex-hooks.json"
            data = agent_config.load(str(required))
            hooks = data["hooks"]["SessionEnd"][0]["hooks"]
            checkpoint = next(h for h in hooks if "idle_compact.py" in h["command"])
            checkpoint["timeout"] = 30
            custom = {"type": "command", "command": "custom-cleanup", "timeout": 2}
            hooks.append(custom)
            agent_config.save(str(target), data)
            for _ in range(2):
                agent_config.codex_hooks(str(target), str(required))
            hooks = agent_config.load(str(target))["hooks"]["SessionEnd"][0]["hooks"]
            self.assertIn(custom, hooks)
            self.assertEqual([h["timeout"] for h in hooks if "idle_compact.py" in h["command"]], [3])

    def test_headroom_unroute_strips_only_headroom_routing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for module in ("headroom/install/models.py", "headroom/providers/codex/install.py"):
                (root / module).parent.mkdir(parents=True, exist_ok=True)
                (root / module).touch()
            (root / "headroom/install/models.py").write_text("def ManagedMutation(*args): return args\n")
            (root / "headroom/providers/codex/install.py").write_text(
                "from pathlib import Path\n"
                "def revert_provider_scope(mutation, manifest):\n"
                "    Path(mutation[2] + '.reverted').write_text(mutation[1])\n")
            claude, codex = root / "claude", root / "codex"
            claude.mkdir()
            codex.mkdir()
            (claude / "settings.json").write_text(json.dumps({"env": {
                "ANTHROPIC_BASE_URL": agent_config.HEADROOM_URL, "ENABLE_TOOL_SEARCH": "true"}}))
            subprocess.run(["python3", str(SCRIPT_DIR / "agent_config.py"), "headroom-unroute", str(claude), str(codex)],
                           env={**os.environ, "PYTHONPATH": directory, "PYTHONDONTWRITEBYTECODE": "1"}, check=True)
            self.assertEqual(json.loads((claude / "settings.json").read_text()), {"env": {"ENABLE_TOOL_SEARCH": "true"}})
            self.assertEqual((codex / "config.toml.reverted").read_text(), "toml-block")
            self.assertTrue(agent_config.claude_direct(str(claude / "settings.json")))

    def test_plugin_identity_and_state(self):
        for plugin_id, installed, enabled in (
            ("superpowers@openai-curated", True, True),
            ("superpowers@superpowers-dev", True, True),
            ("superpowers@untrusted", True, True),
            ("superpowers@openai-curated", False, True),
            ("superpowers@openai-curated", True, False),
            ("ponytail@ponytail", True, True),
        ):
            data = {"installed": [{"pluginId": plugin_id, "installed": installed, "enabled": enabled}]}
            with self.subTest(data=data), patch("sys.stdin", io.StringIO(json.dumps(data))):
                self.assertEqual(
                    bool(agent_config.codex_plugin_enabled("superpowers@openai-curated", "superpowers@superpowers-dev")),
                    plugin_id in ("superpowers@openai-curated", "superpowers@superpowers-dev") and installed and enabled,
                )
            with patch("sys.stdin", io.StringIO(json.dumps(data))):
                self.assertEqual(bool(agent_config.codex_plugin_enabled()), plugin_id == "ponytail@ponytail")

    def test_claude_plugin_identity_and_state(self):
        claude_ids = ("superpowers@claude-plugins-official", "superpowers@superpowers-dev")
        for plugin_id, enabled in (
            ("superpowers@claude-plugins-official", True),
            ("superpowers@superpowers-dev", True),
            ("superpowers@untrusted", True),
            ("superpowers@claude-plugins-official", False),
            ("ponytail@ponytail", True),
        ):
            data = [{"id": plugin_id, "enabled": enabled}]
            with self.subTest(data=data), patch("sys.stdin", io.StringIO(json.dumps(data))):
                self.assertEqual(
                    bool(agent_config.claude_plugin_enabled(*claude_ids)), plugin_id in claude_ids and enabled,
                )
            with patch("sys.stdin", io.StringIO(json.dumps(data))):
                self.assertEqual(bool(agent_config.claude_plugin_enabled()), plugin_id == "ponytail@ponytail")

    def test_codex_shell_path_keeps_tables_codex_added_inside_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.toml"
            agent_config.codex_shell_path(str(config), "/old")
            text = (agent_config.SHELL_BEGIN + config.read_text()
                    + '\n[marketplaces.superpowers-dev]\nsource = "x"\n' + agent_config.SHELL_END + "\n")
            config.write_text(text)
            agent_config.codex_shell_path(str(config), "/new")
            text = config.read_text()
            self.assertIn('[marketplaces.superpowers-dev]\nsource = "x"', text)
            self.assertEqual(text.count("[shell_environment_policy]"), 1)
            self.assertIn('"/new"', text)
            self.assertNotIn('"/old"', text)

    def test_codex_shell_path_preserves_existing_policy_and_reordered_markers(self):
        for policy in (
            '[shell_environment_policy]\ninherit = "none"\nset = { PATH = "/old", KEEP = "yes" }\n',
            '[shell_environment_policy]\ninherit = "none"\n[shell_environment_policy.set]\nPATH = "/old"\nKEEP = "yes"\n',
            '[shell_environment_policy]\ninherit = "none"\n',
        ):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as directory:
                config = Path(directory) / "config.toml"
                config.write_text(
                    agent_config.SHELL_END + '\n[projects."/keep"]\ntrust_level = "trusted"\n'
                    + agent_config.SHELL_BEGIN + "\n" + policy
                )
                expected = tomllib.loads(config.read_text())
                expected["shell_environment_policy"].setdefault("set", {})["PATH"] = "/new"
                agent_config.codex_shell_path(str(config), "/new")
                first = config.read_text()
                self.assertEqual(tomllib.loads(first), expected)
                agent_config.codex_shell_path(str(config), "/new")
                self.assertEqual(config.read_text(), first)

    def test_codex_shell_path_rejects_unsupported_layout_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            original = 'shell_environment_policy = { inherit = "none", set = { PATH = "/old" } }\n'
            config.write_text(original)
            with self.assertRaises((SystemExit, tomllib.TOMLDecodeError)):
                agent_config.codex_shell_path(str(config), "/new")
            self.assertEqual(config.read_text(), original)

    def test_effort_defaults_replace_only_the_top_level_codex_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, settings = Path(tmp) / "config.toml", Path(tmp) / "settings.json"
            config.write_text('model = "gpt"\nmodel_reasoning_effort = "xhigh"\n\n[profiles.deep]\nmodel_reasoning_effort = "max"\n')
            agent_config.codex_effort(str(config))
            agent_config.codex_effort(str(config))
            data = tomllib.loads(config.read_text())
            self.assertEqual(data["model_reasoning_effort"], "medium")
            self.assertEqual(data["profiles"]["deep"]["model_reasoning_effort"], "max")
            settings.write_text('{"effortLevel": "xhigh", "model": "opus"}')
            agent_config.effort(str(settings))
            self.assertEqual(json.loads(settings.read_text()), {"effortLevel": "medium", "model": "opus"})


if __name__ == "__main__":
    unittest.main()
