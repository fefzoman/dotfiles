import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).with_name("read_hint.py")


class ReadHintTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "big.py").write_text("x = 1\n" * 80)
        (self.dir / "small.py").write_text("x = 1\n" * 79)
        bin_dir = self.dir / "bin"
        bin_dir.mkdir()
        (bin_dir / "smart-read").write_text("#!/bin/sh\n")
        (bin_dir / "smart-read").chmod(0o755)
        self.env = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}"}

    def run_hook(self, tool, tool_input, env=None):
        hook = {"cwd": str(self.dir), "tool_name": tool, "tool_input": tool_input}
        out = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(hook), capture_output=True, text=True,
                             env=env or self.env, check=True).stdout
        return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""

    def test_whole_reads_of_large_files_get_a_hint(self):
        self.assertIn("big.py has 80 lines", self.run_hook("Read", {"file_path": str(self.dir / "big.py")}))
        self.assertIn("smart-read outline big.py", self.run_hook("Bash", {"command": "cd x && cat big.py"}))

    def test_first_whole_read_of_a_huge_file_is_denied_once_per_session(self):
        (self.dir / "huge.py").write_text("x = 1\n" * 300)
        hook = {"cwd": str(self.dir), "session_id": f"t{os.getpid()}", "tool_name": "Read",
                "tool_input": {"file_path": str(self.dir / "huge.py")}}

        def run(extra=None):
            out = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(hook | (extra or {})),
                                 capture_output=True, text=True, env=self.env, check=True).stdout
            return json.loads(out)["hookSpecificOutput"]

        self.addCleanup(Path(tempfile.gettempdir(), f"read-hint-{hook['session_id']}").unlink, missing_ok=True)
        first = run()
        self.assertEqual(first["permissionDecision"], "deny")
        self.assertIn("huge.py has 300 lines", first["permissionDecisionReason"])
        self.assertNotIn("permissionDecision", run())
        self.assertNotIn("permissionDecision", run({"tool_input": {"file_path": str(self.dir / "big.py")}}))

    def test_ranged_small_piped_or_uninstalled_reads_pass_silently(self):
        self.assertEqual(self.run_hook("Read", {"file_path": str(self.dir / "big.py"), "offset": 1, "limit": 50}), "")
        self.assertEqual(self.run_hook("Read", {"file_path": str(self.dir / "small.py")}), "")
        self.assertEqual(self.run_hook("Bash", {"command": "cat big.py | head -50"}), "")
        self.assertEqual(self.run_hook("Bash", {"command": "sed -n 1,50p big.py"}), "")
        self.assertEqual(self.run_hook("Read", {"file_path": str(self.dir / "big.py")}, env=os.environ | {"PATH": "/usr/bin:/bin"}), "")


if __name__ == "__main__":
    unittest.main()
