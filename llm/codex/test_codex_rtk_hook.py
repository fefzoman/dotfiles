import json
import subprocess
import unittest
from pathlib import Path


class CodexRtkHookTest(unittest.TestCase):
    def test_installed_rtk_rewrites_only_supported_commands(self):
        for command, rewritten in (
            ("git status", "rtk git status"),
            ("rtk git status", None),
            ("RTK_DISABLED=1 git status", None),
            ("printf hello", None),
        ):
            with self.subTest(command=command):
                result = subprocess.run(
                    ["python3", str(Path(__file__).with_name("codex_rtk_hook.py"))],
                    input=json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                      "tool_input": {"command": command}}),
                    text=True, capture_output=True, check=True,
                )
                if rewritten is None:
                    self.assertEqual(result.stdout, "")
                else:
                    hook = json.loads(result.stdout)["hookSpecificOutput"]
                    self.assertEqual(hook["hookEventName"], "PreToolUse")
                    self.assertEqual(hook["permissionDecision"], "allow")
                    self.assertEqual(hook["updatedInput"]["command"], rewritten)


if __name__ == "__main__":
    unittest.main()
