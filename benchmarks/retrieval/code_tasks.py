"""Small, independent Python 3.14 code-fix fixtures for the three retrieval arms."""

TASKS = {
    "toml": {
        "request": "Fix read_config(path): accept a filesystem path to UTF-8 TOML and return its parsed dict. "
        "All TOML floats, including nested values, must be decimal.Decimal with original precision. "
        "Integers stay integers. Preserve FileNotFoundError and tomllib.TOMLDecodeError; do not swallow errors.",
        "source": '''from pathlib import Path
import tomllib


def read_config(path):
    return tomllib.load(Path(path).read_text(encoding="utf-8"))
''',
        "tests": '''import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
import tomllib
from app import read_config


class Checks(unittest.TestCase):
    def test_precision_and_types(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.toml"
            p.write_text('price = 0.12345678901234567890123456789\\ncount = 7\\n[nested]\\nrate = 1.25\\nlabel = "café"\\n', encoding="utf-8")
            result = read_config(p)
            self.assertEqual(result["price"], Decimal("0.12345678901234567890123456789"))
            self.assertIs(type(result["price"]), Decimal)
            self.assertIs(type(result["count"]), int)
            self.assertEqual(result["nested"], {"rate": Decimal("1.25"), "label": "café"})

    def test_errors(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.toml"
            with self.assertRaises(FileNotFoundError):
                read_config(p)
            p.write_text("broken = [", encoding="utf-8")
            with self.assertRaises(tomllib.TOMLDecodeError):
                read_config(p)
''',
    },
    "timeout": {
        "request": "Fix run_text(argv, timeout): run the command without a shell, capture decoded stdout/stderr, "
        "and return stdout on success. Pass timeout through and let subprocess.run kill and wait for a timed-out "
        "child, then raise TimeoutExpired. Raise CalledProcessError with captured stderr on nonzero exit. "
        "Do not implement custom process management or swallow exceptions.",
        "source": '''import subprocess


def run_text(argv, timeout):
    return subprocess.run(argv, capture_output=True, text=True).stdout
''',
        "tests": '''import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from app import run_text


class Checks(unittest.TestCase):
    def test_success_and_stderr(self):
        self.assertEqual(run_text([sys.executable, "-c", "print('ok')"], 5), "ok\\n")
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            run_text([sys.executable, "-c", "import sys; print('bad', file=sys.stderr); sys.exit(3)"], 5)
        self.assertEqual(caught.exception.returncode, 3)
        self.assertEqual(caught.exception.stderr, "bad\\n")

    def test_timeout_child_is_not_left_running(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "leaked"
            code = f"import time; from pathlib import Path; time.sleep(1); Path({str(marker)!r}).touch()"
            with self.assertRaises(subprocess.TimeoutExpired):
                run_text([sys.executable, "-c", code], 0.15)
            time.sleep(1.1)
            self.assertFalse(marker.exists())

    def test_delegates_to_run(self):
        with patch("app.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "out", "")) as run:
            self.assertEqual(run_text(["program"], 2.5), "out")
        self.assertEqual(run.call_args.args, (["program"],))
        self.assertEqual(run.call_args.kwargs, {"capture_output": True, "text": True, "timeout": 2.5, "check": True})
''',
    },
    "pathkind": {
        "request": "Fix entry_kind(path) for Python 3.14: return 'symlink' for any symlink, even a broken one, "
        "without following it; otherwise 'file', 'directory', or 'other'. Only a FileNotFoundError means 'missing'. "
        "PermissionError and other OSError must propagate, including on Python 3.14 where Path.exists suppresses "
        "OS errors. Inspect metadata once using pathlib, not a sequence of exists/is_file calls.",
        "source": '''from pathlib import Path


def entry_kind(path):
    path = Path(path)
    if not path.exists():
        return "missing"
    if path.is_file():
        return "file"
    if path.is_dir():
        return "directory"
    return "other"
''',
        "tests": '''import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from app import entry_kind


class Checks(unittest.TestCase):
    def test_entries_and_links(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            f = root / "f"
            f.touch()
            self.assertEqual(entry_kind(f), "file")
            self.assertEqual(entry_kind(root), "directory")
            self.assertEqual(entry_kind(root / "absent"), "missing")
            for name, target in (("live", f), ("broken", root / "absent"), ("dirlink", root)):
                link = root / name
                link.symlink_to(target)
                self.assertEqual(entry_kind(link), "symlink")

    def test_errors_propagate(self):
        for error in (PermissionError("denied"), OSError("I/O")):
            with self.subTest(error=error), patch.object(Path, "stat", side_effect=error):
                with self.assertRaises(type(error)):
                    entry_kind("anything")

    def test_single_nonfollowing_metadata_read(self):
        with patch.object(Path, "stat", return_value=SimpleNamespace(st_mode=0)) as stat:
            self.assertEqual(entry_kind("other"), "other")
        stat.assert_called_once_with(follow_symlinks=False)
''',
    },
    "argparse": {
        "request": "Fix parse_args(argv): --cache enables caching, --no-cache disables it, and the default is True. "
        "Neither flag takes a value. Accept positional paths both before and after options, preserving order. "
        "Reject abbreviated flags such as --no-ca using normal argparse errors. Use Python 3.14 argparse's "
        "standard features, not manual argv parsing; return the Namespace with cache and paths.",
        "source": '''import argparse


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=bool, default=True)
    parser.add_argument("paths", nargs="*")
    return parser.parse_args(argv)
''',
        "tests": '''import contextlib
import io
import unittest
from app import parse_args


class Checks(unittest.TestCase):
    def test_boolean_flags(self):
        self.assertIs(parse_args([]).cache, True)
        self.assertIs(parse_args(["--cache"]).cache, True)
        self.assertIs(parse_args(["--no-cache"]).cache, False)
        self.assertIs(parse_args(["--no-cache", "--cache"]).cache, True)

    def test_intermixed_order(self):
        result = parse_args(["a", "--no-cache", "b", "c"])
        self.assertEqual(result.paths, ["a", "b", "c"])
        self.assertIs(result.cache, False)
        self.assertEqual(parse_args(["--", "--cache"]).paths, ["--cache"])

    def test_invalid_flags_and_values(self):
        for argv in (["--no-ca"], ["--cache=false"], ["--unknown"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    parse_args(argv)
                self.assertEqual(caught.exception.code, 2)
''',
    },
}
