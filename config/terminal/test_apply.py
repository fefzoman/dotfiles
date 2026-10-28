import importlib.util
import json
import plistlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("apply_terminals", ROOT / "apply-terminals.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class ApplyTests(unittest.TestCase):
    def test_preserves_nested_settings_and_backs_up_only_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            before = {"editor.fontSize": 17, "workbench.colorCustomizations": {"other": "#123456"},
                      "terminal.integrated.profiles.osx": {"zsh": {"path": "zsh"}}}
            path.write_text(json.dumps(before))
            path.chmod(0o600)
            preset = json.loads((ROOT / "config/terminal/vscode.json").read_text())
            app.apply_json(path, preset)
            result = json.loads(path.read_text())
            self.assertEqual(result["editor.fontSize"], 17)
            self.assertEqual(result["workbench.colorCustomizations"]["other"], "#123456")
            self.assertEqual(result["terminal.integrated.profiles.osx"]["zsh"]["path"], "zsh")
            self.assertEqual(result["terminal.integrated.fontSize"], 14)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            backups = list(path.parent.glob("settings.json.bak.*"))
            self.assertEqual(json.loads(backups[0].read_text()), before)
            app.apply_json(path, preset)
            self.assertEqual(list(path.parent.glob("settings.json.bak.*")), backups)

    def test_invalid_json_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"broken":')
            with self.assertRaises(ValueError):
                app.apply_json(path, {"terminal.integrated.fontSize": 14})
            self.assertEqual(path.read_text(), '{"broken":')
            self.assertEqual(list(path.parent.glob("*.bak.*")), [])

    def test_writes_through_symlinks_without_replacing_them(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.json"
            link = Path(directory) / "settings.json"
            target.write_text('{"other": true}')
            link.symlink_to(target)
            app.apply_json(link, {"terminal.integrated.fontSize": 14})
            self.assertTrue(link.is_symlink())
            self.assertTrue(json.loads(target.read_text())["other"])

    def test_terminal_import_preserves_profiles_and_preferences(self):
        before = {"other": True, "Window Settings": {"Personal": {"Shell": "keep"},
                  "Alacritty Gruvbox": {"custom": True}}}
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            exported = subprocess.CompletedProcess([], 0, plistlib.dumps(before), b"")
            imported = subprocess.CompletedProcess([], 0, b"", b"")
            with mock.patch.object(app.sys, "platform", "darwin"), \
                    mock.patch.object(app.Path, "home", return_value=home), \
                    mock.patch.object(app.subprocess, "run", side_effect=[exported, imported]) as run:
                app.apply_macos_terminal()
            settings = plistlib.loads(run.call_args.kwargs["input"])
            self.assertTrue(settings["other"])
            self.assertEqual(settings["Window Settings"]["Personal"], {"Shell": "keep"})
            self.assertTrue(settings["Window Settings"]["Alacritty Gruvbox"]["custom"])
            saved = list(home.glob(".local/state/dotfiles/terminal-style/*.plist"))
            self.assertEqual(plistlib.loads(saved[0].read_bytes()), before)
            self.assertEqual(saved[0].stat().st_mode & 0o777, 0o600)

    def test_alacritty_substitutes_paths_and_keeps_15_points(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            theme = home / ".config/alacritty/themes/themes/gruvbox_dark.toml"
            theme.parent.mkdir(parents=True)
            theme.touch()
            with mock.patch.object(app.Path, "home", return_value=home), \
                    mock.patch.object(app.shutil, "which", return_value="/installed/tmux"):
                app.apply_alacritty()
            config = app.tomllib.loads((home / ".config/alacritty/alacritty.toml").read_text())
            self.assertEqual(config["font"]["size"], 15)
            self.assertEqual(config["terminal"]["shell"]["program"], "/installed/tmux")


if __name__ == "__main__":
    unittest.main()
