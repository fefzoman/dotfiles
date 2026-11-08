from pathlib import Path
import subprocess
import tempfile
import unittest

from large import grade, mcp_calls, source_scope_ok, tests_digest


class LargeTrialTests(unittest.TestCase):
    def test_scope_rejects_extra_files_and_changed_history(self):
        self.assertTrue(source_scope_ok(["Lib/x.py"], [".serena/project.yml"], "Lib/x.py", "a", "a"))
        for changed, untracked, head in [([], [], "a"), (["Lib/x.py", "Lib/test/test_x.py"], [], "a"),
                                         (["Lib/x.py"], ["Lib/extra.py"], "a"), (["Lib/x.py"], [], "b")]:
            self.assertFalse(source_scope_ok(changed, untracked, "Lib/x.py", head, "a"))

    def test_test_digest_includes_paths_and_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", tmp], check=True)
            tests = root / "Lib/test"
            tests.mkdir(parents=True)
            a, b = tests / "a.py", tests / "b.py"
            a.write_text("a")
            b.write_text("b")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            before = tests_digest(root)
            a.write_text("b")
            b.write_text("a")
            self.assertNotEqual(tests_digest(root), before)

    def test_grading_sets_local_pythonpath_and_retains_failure_output(self):
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "grade.log"
            result = grade(root, [sys.executable, "-c",
                                 "import os, sys; print(os.environ['PYTHONPATH']); sys.exit(3)"], log)
            self.assertEqual(result["exit_code"], 3)
            self.assertEqual(log.read_text().strip(), str(root / "Lib"))

    def test_mcp_audit_handles_literal_and_dynamic_calls_not_just_discovery(self):
        names = ["mcp__context7__query_docs", "mcp__context7__resolve_library_id"]
        self.assertEqual(mcp_calls("tools.mcp__serena__find_symbol({})", names),
                         ["mcp__serena__find_symbol"])
        self.assertEqual(mcp_calls('mcp__context7__query_docs {"query":"x"}', names), names[:1])
        selector = "const t = ALL_TOOLS.find(x=>/context7.*query_docs/.test(x.name));"
        self.assertEqual(mcp_calls(selector, names), [])
        self.assertEqual(mcp_calls(selector + "await tools[t.name]({})", names), names[:1])
        with self.assertRaises(ValueError):
            mcp_calls("const t=ALL_TOOLS.find(x=>/context7/.test(x.name)); tools[t.name]({})", names)


if __name__ == "__main__":
    unittest.main()
