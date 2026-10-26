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
                self.assertEqual(
                    (home / profile / "skills/natural-article/SKILL.md").read_text(),
                    (SCRIPT_DIR / "skills/natural-article/SKILL.md").read_text(),
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

    def test_headroom_removal_unroutes_all_profiles_then_uninstalls(self):
        for mode in ("installed", "race", "failure", "absent"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                manifest = home / ".headroom/deploy/default/manifest.json"
                manifest.parent.mkdir(parents=True)
                manifest.write_text("{}")
                for profile in (".codex", ".codex-work"):
                    config = home / profile / "config.toml"
                    config.parent.mkdir()
                    config.write_text('model = "keep"\n[mcp_servers.headroom]\ncommand = "missing-headroom"\n'
                                      '[mcp_servers.headroom.tools.headroom_retrieve]\napproval_mode = "approve"\n'
                                      '[mcp_servers.serena]\ncommand = "serena"\n')
                if mode != "absent":
                    (home / "headroom-ai/bin").mkdir(parents=True)
                    python = home / "headroom-ai/bin/python"
                    python.write_text('#!/usr/bin/env bash\necho "unroute $3 $4" >> "$HOME/log"\n')
                    python.chmod(0o755)
                result = self.run_installer_function("remove_headroom", home, f'''
mode={mode}
remove_attempts=0
headroom() {{
  [[ "$*" == "install remove --profile default" ]] || return 2
  ((remove_attempts+=1))
  echo remove >> "$HOME/log"
  [[ "$mode" == installed || ( "$mode" == race && "$remove_attempts" -gt 1 ) ]]
}}
uv() {{
  if [[ "$1 $2" == "tool dir" ]]; then printf '%s\\n' "$HOME"; else echo "uv $*" >> "$HOME/log"; fi
}}
''')
                self.assertEqual(result.returncode == 0, mode != "failure", result.stderr)
                log = (home / "log").read_text().splitlines() if mode != "absent" else []
                unrouted = [f"unroute {home}/.claude {home}/.codex", f"unroute {home}/.claude-work {home}/.codex-work"]
                expected = {"installed": [*unrouted, "remove", "uv tool uninstall headroom-ai"],
                            "race": [*unrouted, "remove", "remove", "uv tool uninstall headroom-ai"],
                            "failure": [*unrouted, "remove", "remove"], "absent": []}
                self.assertEqual(log, expected[mode])
                for profile in (".codex", ".codex-work"):
                    config = agent_config.load_toml(str(home / profile / "config.toml"))
                    self.assertEqual(config, {"model": "keep", "mcp_servers": {"serena": {"command": "serena"}}})

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
            text = config.read_text().replace(
                agent_config.SHELL_END, '\n[marketplaces.superpowers-dev]\nsource = "x"\n' + agent_config.SHELL_END
            )
            config.write_text(text)
            agent_config.codex_shell_path(str(config), "/new")
            text = config.read_text()
            self.assertIn('[marketplaces.superpowers-dev]\nsource = "x"', text)
            self.assertEqual(text.count("[shell_environment_policy]"), 1)
            self.assertIn('"/new"', text)
            self.assertNotIn('"/old"', text)

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
