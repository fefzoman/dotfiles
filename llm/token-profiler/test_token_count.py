import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TokenCountTest(unittest.TestCase):
    def test_model(self):
        script = Path(__file__).with_name("token-count")
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "input.txt"
            file.write_text("お誕生日おめでとう", encoding="utf-8")
            for options, expected in [([], "8"), (["-m", "gpt-4"], "9"),
                                      (["--model", "gpt-4o"], "8"),
                                      (["--model", "unknown-model"], None)]:
                with self.subTest(options=options):
                    result = subprocess.run([sys.executable, str(script), str(file), *options],
                                            capture_output=True, text=True)
                    if expected is None:
                        self.assertEqual(result.returncode, 2)
                        self.assertIn("Unknown model: unknown-model", result.stderr)
                        self.assertNotIn("Traceback", result.stderr)
                    else:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout.strip(), expected)

    def test_cli(self):
        script = Path(__file__).with_name("token-count")
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "input.txt"
            for data, expected in [(b"", "0"), (b"Hello world", "2"),
                                   (b"<|endoftext|>", "7"), (b"\xff", None)]:
                with self.subTest(data=data):
                    file.write_bytes(data)
                    result = subprocess.run([sys.executable, str(script), str(file)],
                                            capture_output=True, text=True)
                    if expected is None:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertNotIn("Traceback", result.stderr)
                    else:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout.strip(), expected)
            file.unlink()
            result = subprocess.run([sys.executable, str(script), str(file)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)
