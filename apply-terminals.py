#!/usr/bin/env python3
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import tomllib


ROOT = Path(__file__).resolve().parent
PRESETS = ROOT / "config/terminal"


def write_config(path, content):
    path = path.expanduser().resolve()
    if path.exists() and path.read_bytes() == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    if path.exists():
        saved = f"{path}.bak.{time.time_ns()}"
        os.close(os.open(saved, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        shutil.copy2(path, saved)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def merge(target, updates):
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = value


def apply_json(path, preset):
    settings = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(settings, dict):
        raise ValueError(f"{path}: expected a JSON object")
    before = json.dumps(settings, sort_keys=True)
    merge(settings, preset)
    if before != json.dumps(settings, sort_keys=True):
        write_config(path, (json.dumps(settings, indent=4) + "\n").encode())


def apply_alacritty():
    tmux = shutil.which("tmux")
    theme = Path.home() / ".config/alacritty/themes/themes/gruvbox_dark.toml"
    if not tmux or not theme.is_file():
        raise RuntimeError("Alacritty needs tmux and its Gruvbox theme; run ./activate.sh first")
    config = (ROOT / "config/alacritty/alacritty.toml").read_text()
    config = config.replace("@WINDOW_DECORATIONS@", "Buttonless" if sys.platform == "darwin" else "Full")
    config = config.replace("@TMUX_BIN@", json.dumps(tmux)[1:-1])
    tomllib.loads(config)
    write_config(Path.home() / ".config/alacritty/alacritty.toml", config.encode())


def apply_vscode():
    home = Path.home()
    default = home / ("Library/Application Support/Code/User" if sys.platform == "darwin" else ".config/Code/User")
    preset = json.loads((PRESETS / "vscode.json").read_text())
    if sys.platform == "darwin":
        bash = next((p for p in ("/opt/homebrew/bin/bash", "/usr/local/bin/bash") if os.access(p, os.X_OK)), None)
        if bash is None:
            raise RuntimeError("VS Code needs Homebrew Bash for command-output font resets")
        preset["terminal.integrated.profiles.osx"]["bash"]["path"] = bash
    else:
        preset = {k: v for k, v in preset.items() if not k.endswith(".osx")}
    for directory in (default, home / ".vscode-work/User"):
        if not directory.is_dir():
            continue
        for path in [directory / "settings.json", *sorted(directory.glob("profiles/*/settings.json"))]:
            apply_json(path, preset)
            print(f"  {path}")


def apply_macos_terminal():
    if sys.platform != "darwin":
        print("SKIP macOS Terminal: not macOS")
        return
    result = subprocess.run(["defaults", "export", "com.apple.Terminal", "-"], capture_output=True)
    if result.returncode and b"does not exist" not in result.stderr:
        raise RuntimeError(result.stderr.decode().strip())
    settings = plistlib.loads(result.stdout) if result.returncode == 0 else {}
    profile = plistlib.loads((PRESETS / "Alacritty Gruvbox.terminal").read_bytes())
    name = profile["name"]
    profiles = settings.setdefault("Window Settings", {})
    updated = dict(profiles.get(name, {}))
    updated.update(profile)
    if (profiles.get(name) == updated and settings.get("Default Window Settings") == name
            and settings.get("Startup Window Settings") == name):
        return
    if result.returncode == 0:
        saved = Path.home() / f".local/state/dotfiles/terminal-style/Terminal-before-{time.time_ns()}.plist"
        write_config(saved, result.stdout)
    profiles[name] = updated
    settings["Default Window Settings"] = name
    settings["Startup Window Settings"] = name
    subprocess.run(["defaults", "import", "com.apple.Terminal", "-"],
                   input=plistlib.dumps(settings), capture_output=True, check=True)


def apply_orca():
    database = Path.home() / "Library/Application Support/orca/profiles/local-default/profile-state.db"
    if sys.platform != "darwin" or not database.exists():
        print("SKIP Orca: no local macOS profile")
        return
    subprocess.run(["node", str(PRESETS / "apply-orca.cjs")], check=True)


def main():
    failed = False
    for name, apply in (("Alacritty", apply_alacritty), ("VS Code", apply_vscode),
                        ("macOS Terminal", apply_macos_terminal), ("Orca", apply_orca)):
        print(f"Applying {name}...", flush=True)
        try:
            apply()
        except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
            print(f"INCOMPLETE {name}: {error}", file=sys.stderr)
            failed = True
    print("Open new VS Code terminals; reopen macOS Terminal if it was running.")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
