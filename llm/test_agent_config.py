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
    def test_retrieval_only_migration_preserves_model_permissions_and_unrelated_hooks(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            binaries = home / ".local/bin"
            binaries.mkdir(parents=True)
            installed = home / ".config/dotfiles"
            installed.mkdir(parents=True)
            (installed / "context7_version_guard.py").write_text("retired")
            for name, code in (("npm", 0), ("uv", 0), ("codex", 0), ("claude", 1), ("pgrep", 1)):
                path = binaries / name
                path.write_text(f'#!/bin/sh\nif [ "{name} $*" = "npm prefix --global" ]; then echo "$HOME/.local"; fi\nexit {code}\n')
                path.chmod(0o755)
            original = 'model="custom"\nmodel_reasoning_effort="high"\napproval_policy="on-request"\n'
            for agent in ("codex", "claude"):
                for name in (f".{agent}", f".{agent}-work"):
                    profile = home / name
                    profile.mkdir()
                    (profile / "RTK.md").write_text("custom RTK guidance\n")
                    if agent == "codex":
                        (profile / "config.toml").write_text(original)
                    agent_config.save(str(profile / ("hooks.json" if agent == "codex" else "settings.json")),
                                      {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
                                          {"type": "command", "command": "custom-check"},
                                          {"type": "command", "command": agent_config.RETIRED_CONTEXT7_GUARD}]}]}})
            result = subprocess.run(["bash", str(SCRIPT_DIR / "ai-install.sh"), "--retrieval-only"],
                                    env={**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")},
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((installed / "context7_version_guard.py").exists())
            self.assertEqual((installed / "ai-install.sh").read_text(), (SCRIPT_DIR / "ai-install.sh").read_text())
            for agent in ("codex", "claude"):
                for name in (f".{agent}", f".{agent}-work"):
                    profile = home / name
                    reference = f"@{profile}/RTK.md" if agent == "codex" else "@RTK.md"
                    self.assertTrue(agent_config.policy_matches(str(SCRIPT_DIR / agent / "__AGENTS.md"),
                                    str(profile / ("AGENTS.md" if agent == "codex" else "CLAUDE.md")),
                                    str(profile / "RTK.md"), reference))
                    self.assertEqual((profile / "RTK.md").read_text(), "custom RTK guidance\n")
            for name in (".codex", ".codex-work"):
                self.assertEqual((home / name / "config.toml").read_text(), original)
                entries = list(agent_config.hook_entries(agent_config.load(str(home / name / "hooks.json"))))
                self.assertIn(("PreToolUse", "Bash", "command", "custom-check"), entries)
                self.assertNotIn(("PreToolUse", "Bash", "command", agent_config.RETIRED_CONTEXT7_GUARD), entries)
            for name in (".claude", ".claude-work"):
                entries = list(agent_config.hook_entries(agent_config.load(str(home / name / "settings.json"))))
                self.assertEqual(entries, [("PreToolUse", "Bash", "command", "custom-check")])

    def test_retrieval_cleanup_removes_both_mcps_from_all_profiles_without_adding_any(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "bin").mkdir()
            for name in ("codex", "claude"):
                path = home / "bin" / name
                path.write_text('#!/bin/sh\necho "' + name + ' $*" >> "$HOME/calls"\n')
                path.chmod(0o755)
            for name in (".codex", ".codex-work"):
                (home / name).mkdir()
                (home / name / "config.toml").write_text('[mcp_servers.serena]\n[mcp_servers.context7]\n')
            agent_config.save(str(home / ".claude.json"), {"mcpServers": {"serena": {}, "context7": {}}})
            (home / ".claude-work").mkdir()
            agent_config.save(str(home / ".claude-work/.claude.json"), {"mcpServers": {"serena": {}, "context7": {}}})
            result = self.run_installer_function("remove_retrieval_mcps", home, 'export PATH="$HOME/bin:$PATH"')
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = (home / "calls").read_text().splitlines()
            self.assertEqual(sum("mcp remove" in call for call in calls), 4)
            for name in (".claude", ".claude-work"):
                self.assertTrue(agent_config.retrieval_mcps_absent("claude", str(home / name)))
            self.assertFalse(any("mcp add" in call for call in calls))
            self.assertFalse(any("mcp get" in call for call in calls))

    def test_cleanup_uninstalls_context7_and_removes_only_retired_tool_state(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / "bin").mkdir()
            for name in ("npm", "uv"):
                path = home / "bin" / name
                path.write_text('#!/bin/sh\necho "' + name + ' $*" >> "$HOME/calls"\n'
                                'if [ "$*" = "tool list" ]; then echo "serena-agent v1"; fi\n'
                                'if [ "$*" = "prefix --global" ]; then echo "$HOME/global"; fi\n')
                path.chmod(0o755)
            (home / ".serena").mkdir()
            for relative in (".codex-work/context7-cli", "custom-config/context7", ".context7"):
                path = home / relative
                path.mkdir(parents=True)
                (path / "state").write_text("retired")
            (home / "unrelated").write_text("keep")
            result = self.run_installer_function("remove_retired_retrieval_tools", home,
                       'export PATH="$HOME/bin:$PATH"; export XDG_CONFIG_HOME="$HOME/custom-config"')
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = (home / "calls").read_text()
            self.assertIn(f"npm uninstall --global --prefix {home}/.local ctx7 @upstash/context7-mcp", calls)
            self.assertIn(f"npm uninstall --global --prefix {home}/global ctx7 @upstash/context7-mcp", calls)
            self.assertNotIn("npm install", calls)
            self.assertIn("tool uninstall serena-agent", calls)
            self.assertIn("cache clean serena-agent", calls)
            self.assertFalse((home / ".serena").exists())
            for relative in (".codex-work/context7-cli", "custom-config/context7", ".context7"):
                self.assertFalse((home / relative).exists())
            self.assertEqual((home / "unrelated").read_text(), "keep")

    def test_retrieval_mcp_check_preserves_custom_servers_and_checks_claude_project_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            for agent in ("codex", "claude"):
                profile = home / f".{agent}"
                profile.mkdir()
                self.assertTrue(agent_config.retrieval_mcps_absent(agent, str(profile)))
                if agent == "codex":
                    path = profile / "config.toml"
                    path.write_text('[mcp_servers.custom]\ncommand="keep"\n')
                else:
                    path = home / ".claude.json"
                    path.write_text('{"mcpServers":{"custom":{}}}')
                self.assertTrue(agent_config.retrieval_mcps_absent(agent, str(profile)))
                path.write_text('[mcp_servers.context7]\ncommand="old"\n' if agent == "codex" else
                                '{"projects":{"/repo":{"mcpServers":{"serena":{}}}}}')
                self.assertFalse(agent_config.retrieval_mcps_absent(agent, str(profile)))
                self.assertTrue(agent_config.retrieval_mcps_absent(agent, str(profile), "unrelated"))

    def test_claude_cleanup_covers_legacy_and_project_registrations_without_data_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            profiles = [home / ".claude", home / ".claude-work"]
            for profile in profiles:
                profile.mkdir()
            paths = [home / ".claude.json", profiles[0] / ".claude.json", profiles[1] / ".claude.json"]
            original = {"custom": "keep", "mcpServers": {"context7": {}, "serena": {}, "custom": {"command": "keep"}},
                        "projects": {"/repo": {"custom": "keep", "mcpServers": {"context7": {}, "custom": {}}}}}
            expected = {"custom": "keep", "mcpServers": {"custom": {"command": "keep"}},
                        "projects": {"/repo": {"custom": "keep", "mcpServers": {"custom": {}}}}}
            for path in paths:
                agent_config.save(str(path), original)
            for profile in profiles:
                self.assertFalse(agent_config.retrieval_mcps_absent("claude", str(profile)))
                for _ in range(2):
                    agent_config.remove_claude_retrieval_mcps(str(profile))
                self.assertTrue(agent_config.retrieval_mcps_absent("claude", str(profile)))
            for path in paths:
                self.assertEqual(agent_config.load(str(path)), expected)

    def test_context_efficiency_preserves_custom_settings_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            config = profile / "config.toml"
            config.write_text('model = "custom"\n[skills]\ninclude_instructions = true\n'
                              'max_context_tokens = 9000\n[plugins."superpowers@superpowers-dev"]\nenabled = true\n'
                              '[plugins."ponytail@ponytail"]\nenabled = false\n'
                              '[plugins."custom@local"]\nenabled = true\n'
                              '[mcp_servers.custom]\ncommand = "custom"\n')
            settings = profile / "settings.json"
            settings.write_text('{"env":{"CUSTOM":"yes"},"enabledPlugins":{"custom@local":true,"ponytail@ponytail":false}}')
            for agent in ("codex", "claude"):
                self.assertFalse(agent_config.context_efficient(agent, str(profile)))
                agent_config.context_efficiency(agent, str(profile))
                self.assertTrue(agent_config.context_efficient(agent, str(profile)))
                first = (config if agent == "codex" else settings).read_text()
                agent_config.context_efficiency(agent, str(profile))
                self.assertEqual(first, (config if agent == "codex" else settings).read_text())
            data = agent_config.load_toml(str(config))
            self.assertEqual(data["model"], "custom")
            self.assertEqual(data["mcp_servers"], {"custom": {"command": "custom"}})
            self.assertEqual(data["skills"], {"include_instructions": False, "max_context_tokens": 2000})
            self.assertFalse(data["plugins"]["superpowers@superpowers-dev"]["enabled"])
            self.assertTrue(data["plugins"]["custom@local"]["enabled"])
            self.assertTrue(data["plugins"]["ponytail@ponytail"]["enabled"])
            data = agent_config.load(str(settings))
            self.assertEqual(data["env"], {"CUSTOM": "yes", "SLASH_COMMAND_TOOL_CHAR_BUDGET": "8000"})
            self.assertFalse(data["enabledPlugins"]["superpowers@claude-plugins-official"])
            self.assertTrue(data["enabledPlugins"]["custom@local"])
            self.assertTrue(data["enabledPlugins"]["ponytail@ponytail"])

    def test_context_efficiency_removes_all_retired_hooks_but_keeps_custom(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            for agent, filename in (("codex", "hooks.json"), ("claude", "settings.json")):
                path = profile / filename
                agent_config.save(str(path), {"description": "custom Serena session cleanup, retain", "hooks": {"SessionStart": [{"hooks": [
                    {"type": "command", "command": "serena-hooks activate --client=" + agent},
                    {"type": "command", "command": "custom-check"}]}], "SessionEnd": [{"hooks": [
                    {"type": "command", "command": "serena-hooks cleanup --client=" + agent}]}]}})
                agent_config.context_efficiency(agent, str(profile))
                commands = [e[3] for e in agent_config.hook_entries(agent_config.load(str(path)))]
                self.assertEqual(commands, ["custom-check"])
                self.assertEqual(agent_config.load(str(path))["description"], "custom retain")

    def test_context7_cleanup_removes_bash_and_mcp_guards_but_keeps_custom_hooks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "settings.json")
            agent_config.save(path, {"hooks": {"PreToolUse": [{"matcher": "mcp__context7__query-docs", "hooks": [
                {"type": "command", "command": agent_config.RETIRED_CONTEXT7_GUARD},
                {"type": "command", "command": "custom-check"}]},
                {"matcher": "Bash", "hooks": [
                    {"type": "command", "command": agent_config.RETIRED_CONTEXT7_GUARD},
                    {"type": "command", "command": "custom-shell-check"}]}]}})
            for _ in range(2):
                agent_config.remove_legacy_hooks(path)
            entries = list(agent_config.hook_entries(agent_config.load(path)))
            self.assertEqual([e[3] for e in entries], ["custom-check", "custom-shell-check"])

    def test_context7_path_cleanup_preserves_other_config_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"HOME": directory}):
            path = Path(directory) / "config.toml"
            retired = str(Path(directory) / ".codex-work/context7-cli/node_modules/.bin")
            path.write_text('model="custom"\nmodel_reasoning_effort="high"\n[shell_environment_policy]\n'
                            f'set = {{PATH = "/usr/bin:{retired}:/keep:{retired}", OTHER = "keep"}}\n')
            expected = tomllib.loads(path.read_text())
            expected["shell_environment_policy"]["set"]["PATH"] = "/usr/bin:/keep"
            for _ in range(2):
                agent_config.remove_context7_path(str(path))
                self.assertEqual(tomllib.loads(path.read_text()), expected)

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

    def test_read_hint_keeps_unrelated_hooks_in_same_group(self):
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
                self.assertIn("Automatically apply `code-retrieval`", (home / profile / filename).read_text())
                if agent == "codex":
                    self.assertTrue(agent_config.codex_model_instructions_valid(
                        str(home / profile / "config.toml"), str(SCRIPT_DIR / "codex-model-instructions.md")))
                    self.assertEqual(agent_config.load_toml(str(home / profile / "config.toml"))["model_instructions_file"],
                                     str((home / profile / "model-instructions.md").resolve()))
                for skill in ("natural-article", "code-retrieval"):
                    self.assertEqual(
                        (home / profile / f"skills/{skill}/SKILL.md").read_text(),
                        (SCRIPT_DIR / f"skills/{skill}/SKILL.md").read_text(),
                    )
                for source in (SCRIPT_DIR / "skills/code-retrieval/references").glob("*.md"):
                    self.assertEqual((home / profile / "skills/code-retrieval/references" / source.name).read_bytes(),
                                     source.read_bytes())

    def test_docs_only_updates_policies_and_skills_only(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".local/bin").mkdir(parents=True)
            (home / ".local/bin/pgrep").write_text("#!/bin/sh\nexit 1\n")
            (home / ".local/bin/pgrep").chmod(0o755)
            for agent in ("codex", "claude"):
                for name in (f".{agent}", f".{agent}-work"):
                    (home / name).mkdir()
                    (home / name / "RTK.md").write_text("custom RTK guidance\n")
                    (home / name / "config.toml").write_text('model="custom"\n')
            result = subprocess.run(["bash", str(SCRIPT_DIR / "ai-install.sh"), "--docs-only"],
                                    env={**os.environ, "HOME": str(home)}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for agent in ("codex", "claude"):
                for name in (f".{agent}", f".{agent}-work"):
                    profile = home / name
                    reference = f"@{profile}/RTK.md" if agent == "codex" else "@RTK.md"
                    self.assertTrue(agent_config.policy_matches(str(SCRIPT_DIR / agent / "__AGENTS.md"),
                                    str(profile / ("AGENTS.md" if agent == "codex" else "CLAUDE.md")),
                                    str(profile / "RTK.md"), reference))
                    for skill in ("natural-article", "code-retrieval"):
                        self.assertEqual((profile / f"skills/{skill}/SKILL.md").read_text(),
                                         (SCRIPT_DIR / f"skills/{skill}/SKILL.md").read_text())
                    self.assertEqual((profile / "config.toml").read_text(), 'model="custom"\n')
                    self.assertFalse((profile / "model-instructions.md").exists())
                    self.assertFalse((profile / "system-prompt.md").exists())

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
            data["hooks"]["SessionStart"] = [{"matcher": "clear", "hooks": [
                {"type": "command", "command": f"{agent_config.IDLE_COMPACT} clear", "timeout": 10}]}]
            agent_config.save(str(target), data)
            self.assertFalse(agent_config.codex_hooks_valid(str(required), str(target)))
            for _ in range(2):
                agent_config.codex_hooks(str(target), str(required))
            self.assertNotIn("SessionStart", agent_config.load(str(target))["hooks"])
            self.assertTrue(agent_config.codex_hooks_valid(str(required), str(target)))
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

    def test_permission_defaults_preserve_unrelated_settings_and_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            config, settings = Path(directory) / "config.toml", Path(directory) / "settings.json"
            config.write_text('sandbox_mode = "read-only"\napproval_policy = "on-request"\ndefault_permissions = "old"\n'
                              '[sandbox_workspace_write]\nnetwork_access = false\nwritable_roots = ["/tmp"]\n'
                              '[profiles.custom]\napproval_policy = "on-request"\n')
            settings.write_text(json.dumps({"model": "custom", "permissions": {"deny": ["Read(.env)"]},
                                           "sandbox": {"excludedCommands": ["docker *"],
                                                       "network": {"deniedDomains": ["blocked.example"]}}}))
            for _ in range(2):
                agent_config.codex_permissions(str(config))
                agent_config.claude_permissions(str(settings))
                codex = tomllib.loads(config.read_text())
                claude = json.loads(settings.read_text())
                self.assertEqual(codex, {"sandbox_mode": "danger-full-access", "approval_policy": "never",
                                        "default_permissions": ":danger-full-access",
                                        "sandbox_workspace_write": {"network_access": False, "writable_roots": ["/tmp"]},
                                        "profiles": {"custom": {"approval_policy": "on-request"}}})
                self.assertEqual(claude["permissions"], {"defaultMode": "dontAsk", "blockWritesOutsideWorkingDirectories": True,
                                                       "allow": ["Bash", "Edit", "Write", "NotebookEdit"], "deny": ["Read(.env)"]})
                self.assertEqual(claude["sandbox"], {"enabled": False, "excludedCommands": ["docker *"],
                                                   "network": {"deniedDomains": ["blocked.example"]}})
                self.assertEqual(claude["model"], "custom")

    def test_codex_permissions_create_defaults_and_reject_unsupported_layout_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            agent_config.codex_permissions(str(config))
            self.assertEqual(tomllib.loads(config.read_text()), {"sandbox_mode": "danger-full-access", "approval_policy": "never",
                                                                 "default_permissions": ":danger-full-access"})
            original = '"sandbox_mode" = "read-only"\n'
            config.write_text(original)
            with self.assertRaises((SystemExit, tomllib.TOMLDecodeError)):
                agent_config.codex_permissions(str(config))
            self.assertEqual(config.read_text(), original)

    def test_codex_permissions_remove_managed_profile_and_keep_other_profiles(self):
        managed = (f'{agent_config.PERMISSIONS_BEGIN}\n[permissions.dotfiles]\nextends = ":workspace"\n'
                   f'{agent_config.PERMISSIONS_END}\n')
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            for extra, profiles in (("", None), ('[permissions.custom]\nextends = ":read-only"\n', {"custom": {"extends": ":read-only"}})):
                config.write_text('default_permissions = "dotfiles"\n' + extra + managed)
                agent_config.codex_permissions(str(config))
                first = config.read_text()
                agent_config.codex_permissions(str(config))
                self.assertEqual(config.read_text(), first)
                self.assertNotIn(agent_config.PERMISSIONS_BEGIN, first)
                self.assertEqual(tomllib.loads(first).get("permissions"), profiles)

    def test_codex_model_instructions_preserve_settings_and_are_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, prompt = Path(tmp) / "config.toml", Path(tmp) / "prompt.md"
            prompt.write_text("Complete the task safely.\n")
            source = Path(tmp) / "source.md"
            source.write_bytes(prompt.read_bytes())
            for original in ("", 'model = "custom"\nmodel_instructions_file = "/old"\n'
                             '[profiles.custom]\nmodel_instructions_file = "/keep"\n'):
                config.write_text(original)
                expected = tomllib.loads(original) | {"model_instructions_file": str(prompt.resolve())}
                agent_config.codex_model_instructions(str(config), str(prompt))
                first = config.read_text()
                self.assertEqual(tomllib.loads(first), expected)
                agent_config.codex_model_instructions(str(config), str(prompt))
                self.assertEqual(config.read_text(), first)
                self.assertTrue(agent_config.codex_model_instructions_valid(str(config), str(source)))
            prompt.write_text("")
            self.assertFalse(agent_config.codex_model_instructions_valid(str(config), str(source)))
            with self.assertRaises(SystemExit):
                agent_config.codex_model_instructions(str(config), str(prompt))
            self.assertEqual(config.read_text(), first)
            prompt.unlink()
            with self.assertRaises(FileNotFoundError):
                agent_config.codex_model_instructions(str(config), str(prompt))
            self.assertEqual(config.read_text(), first)

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
