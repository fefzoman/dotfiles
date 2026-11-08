from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest


class ShellDispatcherTests(unittest.TestCase):
    def test_default_text_and_optional_structural_file_queries(self):
        skill = Path(__file__).resolve().parents[2] / "llm/skills/code-retrieval/SKILL.md"
        commands = re.findall(r"`(rg -n[^`]+)`", skill.read_text())
        reference = skill.parent / "references/structural-search.md"
        commands += re.findall(r"^(rtk ast-grep scan .+)$", reference.read_text(), re.M)
        self.assertEqual(len(commands), 2)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.py"
            source.write_text('''# self.method(needle)
text = "self.method(needle)"
other = "NEEDLE"
def example(self):
    try:
        self.method(1)
    except:
        pass
''')
            (Path(tmp) / "decoy.py").write_text('''# except:
text = "except:"
try:
    pass
except ValueError:
    pass
''')
            for command in commands:
                argv = shlex.split(command)
                if argv[0] == "rtk":
                    argv = argv[1:]
                if not shutil.which(argv[0]):
                    self.skipTest(f"Optional tool unavailable: {argv[0]}")
                argv = [tmp if value == "PATH" else "needle" if value == "TEXT" else value
                        for value in argv]
                with self.subTest(tool=argv[0]):
                    result = subprocess.run(argv, input="", capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    if argv[0] == "ast-grep":
                        self.assertEqual(result.stdout.splitlines(), [str(source)])
                    else:
                        self.assertEqual(len(result.stdout.splitlines()), 2)
                        self.assertTrue(all("sample.py:" in line for line in result.stdout.splitlines()))


if __name__ == "__main__":
    unittest.main()
