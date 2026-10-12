import tempfile
import tomllib
import unittest
from pathlib import Path

from llm.agent_config import CODEX_STATUSLINE, codex_statusline


class CodexStatuslineTest(unittest.TestCase):
    def test_upgrades_previous_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text('[tui]\nstatus_line = ["context-used", "context-window-size", "five-hour-limit", "weekly-limit"] # footer\n')
            codex_statusline(str(path))
            installed = path.read_text()
            self.assertEqual(tomllib.loads(installed)["tui"]["status_line"], CODEX_STATUSLINE)
            self.assertIn("# footer", installed)
            codex_statusline(str(path))
            self.assertEqual(path.read_text(), installed)

    def test_install_preserves_settings_and_is_idempotent(self):
        for original in ('model = "gpt-6.1-sol"\n', '[tui] # existing\nscreen_reader_detection_done = true\n'):
            with self.subTest(original=original), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.toml"
                path.write_text(original)
                codex_statusline(str(path))
                installed = path.read_text()
                data = tomllib.loads(installed)
                self.assertEqual(data["tui"]["status_line"], CODEX_STATUSLINE)
                for key, value in tomllib.loads(original).items():
                    if key == "tui":
                        self.assertTrue(value.items() <= data[key].items())
                    else:
                        self.assertEqual(data[key], value)
                codex_statusline(str(path))
                self.assertEqual(path.read_text(), installed)

    def test_preserves_custom_or_disabled_statusline(self):
        for value in ('["model-name"]', '[]'):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.toml"
                original = f"[tui]\nstatus_line = {value}\n"
                path.write_text(original)
                codex_statusline(str(path))
                self.assertEqual(path.read_text(), original)


if __name__ == "__main__":
    unittest.main()
