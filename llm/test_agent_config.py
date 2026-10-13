import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agent_config


SCRIPT_DIR = Path(__file__).resolve().parent


class AgentInstallationTests(unittest.TestCase):
    def run_installer_function(self, name, home, extra=""):
        source = (SCRIPT_DIR / "ai-install.sh").read_text()
        functions = "\n".join(
            re.search(rf"^{function}\(\) \{{.*?^\}}", source, re.M | re.S)[0]
            for function in ("agent_config", name)
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
                result = self.run_installer_function(
                    "install_superpowers", home,
                    f'export PATH="$HOME:$PATH" mode={mode}',
                )
                calls = (home / "calls").read_text()
                self.assertEqual(result.returncode == 0, mode != "failure", result.stderr)
                self.assertIn(str(home / ".codex"), calls)
                if mode != "failure":
                    self.assertIn(str(home / ".codex-work"), calls)
                self.assertNotIn("plugin add superpowers@openai-curated", calls)
                self.assertEqual("plugin add superpowers@superpowers-dev" in calls, mode == "upstream")

    def test_headroom_stop_race_and_persistent_failure(self):
        for mode in ("success", "race", "failure", "fresh"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                if mode != "fresh":
                    manifest = home / ".headroom/deploy/default/manifest.json"
                    manifest.parent.mkdir(parents=True)
                    manifest.write_text("{}")
                (home / "headroom-ai/bin").mkdir(parents=True)
                python = home / "headroom-ai/bin/python"
                python.write_text('#!/usr/bin/env bash\ntouch "$HOME/work-configured"\n')
                python.chmod(0o755)
                result = self.run_installer_function("install_headroom", home, f'''
mode={mode}
PYTHON_VERSION=3.13
stop_attempts=0
headroom() {{
  if [[ "$*" == "install stop --profile default" ]]; then
    ((stop_attempts+=1))
    [[ "$mode" == success || ( "$mode" == race && "$stop_attempts" -gt 1 ) ]]
  elif [[ "$1 $2" == "install apply" ]]; then
    touch "$HOME/applied"
  else
    return 2
  fi
}}
uv() {{
  if [[ "$1 $2" == "tool dir" ]]; then
    printf '%s\\n' "$HOME"
  else
    touch "$HOME/upgraded"
  fi
}}
''')
                self.assertEqual(result.returncode == 0, mode != "failure", result.stderr)
                for marker in ("upgraded", "applied", "work-configured"):
                    self.assertEqual((home / marker).exists(), mode != "failure", marker)

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


if __name__ == "__main__":
    unittest.main()
