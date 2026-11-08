import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest


class ShellDispatcherTests(unittest.TestCase):
    def test_documented_commands_work_with_piped_stdin_and_ast_ignores_text(self):
        skill = Path(__file__).resolve().parents[2] / "llm/skills/code-retrieval/SKILL.md"
        commands = re.findall(r"`((?:rg -n|ag |ack |ast-grep run )[^`]+)`", skill.read_text())
        self.assertEqual(len(commands), 4)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.py"
            source.write_text('''# self.method(needle)
text = "self.method(needle)"
other = "NEEDLE"
def example(self):
    self.method(1)
    self.method(
        2,
    )
''')
            for command in commands:
                argv = shlex.split(command)
                if not shutil.which(argv[0]):
                    self.skipTest(f"Optional tool unavailable: {argv[0]}")
                argv = [tmp if value == "PATH" else "needle" if value == "TEXT" else value
                        for value in argv]
                if argv[0] == "ast-grep":
                    argv.append("--json=compact")
                with self.subTest(tool=argv[0]):
                    result = subprocess.run(argv, input="", capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    if argv[0] == "ast-grep":
                        self.assertEqual(len(json.loads(result.stdout)), 2)
                    else:
                        self.assertEqual(len(result.stdout.splitlines()), 2)
                        self.assertTrue(all("sample.py:" in line for line in result.stdout.splitlines()))


if __name__ == "__main__":
    unittest.main()
