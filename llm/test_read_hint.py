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
        (self.dir / "big.py").write_text("x = 1\n" * 500)
        (self.dir / "small.py").write_text("x = 1\n" * 10)
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
        self.assertIn("big.py has 500 lines", self.run_hook("Read", {"file_path": str(self.dir / "big.py")}))
        self.assertIn("smart-read outline big.py", self.run_hook("Bash", {"command": "cd x && cat big.py"}))

    def test_ranged_small_piped_or_uninstalled_reads_pass_silently(self):
        self.assertEqual(self.run_hook("Read", {"file_path": str(self.dir / "big.py"), "offset": 1, "limit": 50}), "")
        self.assertEqual(self.run_hook("Read", {"file_path": str(self.dir / "small.py")}), "")
        self.assertEqual(self.run_hook("Bash", {"command": "cat big.py | head -50"}), "")
        self.assertEqual(self.run_hook("Bash", {"command": "sed -n 1,50p big.py"}), "")
        self.assertEqual(self.run_hook("Read", {"file_path": str(self.dir / "big.py")}, env=os.environ | {"PATH": "/usr/bin:/bin"}), "")


if __name__ == "__main__":
    unittest.main()
