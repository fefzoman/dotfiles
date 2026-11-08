import tempfile
import json
import subprocess
import sys
import unittest
from pathlib import Path

from llm import context7_version_guard as guard


class Context7VersionGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = Path(tempfile.mkdtemp())
        self.repo = self.workspace / "repo"
        (self.repo / ".git").mkdir(parents=True)
        (self.repo / ".venv/lib/python3.13/site-packages/boto3-1.43.56.dist-info").mkdir(parents=True)
        (self.repo / "uv.lock").write_text('[[package]]\nname = "apache-airflow"\nversion = "3.1.2"\n')

    def test_denies_unversioned_query_for_pinned_package(self) -> None:
        reason = guard.check({"libraryId": "/boto/boto3", "query": "s3 presigned url"}, self.repo)
        self.assertIn("1.43.56 (repo/.venv)", reason)
        self.assertIn("3.1.2 (repo/uv.lock)", guard.check({"libraryId": "/apache/airflow", "query": "x"}, self.workspace))

    def test_allows_versioned_or_unpinned_queries(self) -> None:
        self.assertIsNone(guard.check({"libraryId": "/boto/boto3", "query": "boto3 1.43 s3 presigned url"}, self.repo))
        self.assertIsNone(guard.check({"libraryId": "/boto/boto3/v1.43.56", "query": "s3"}, self.repo))
        self.assertIsNone(guard.check({"libraryId": "/pallets/flask", "query": "routing"}, self.repo))

    def test_explicit_upgrade_target_can_differ_from_installed_version(self) -> None:
        self.assertIsNone(guard.check({"libraryId": "/apache/airflow",
                                      "query": "target version: 3.2.0; Python compatibility"}, self.workspace))
        self.assertIsNone(guard.check({"libraryId": "/apache/airflow/3.2.0",
                                      "query": "Python compatibility"}, self.workspace))
        self.assertIsNotNone(guard.check({"libraryId": "/apache/airflow",
                                         "query": "Python 3.13 compatibility"}, self.workspace))

    def test_missing_query_is_still_checked_against_project_pin(self) -> None:
        self.assertIsNotNone(guard.check({"libraryId": "/apache/airflow", "query": None}, self.workspace))

    def test_cli_queries_preserve_quotes_wrappers_and_multiple_commands(self) -> None:
        inputs = list(guard.cli_inputs('rtk ctx7 docs /boto/boto3 "s3 presigned url" --json; '
                                       'env CTX7_TELEMETRY_DISABLED=1 /bin/ctx7 docs /apache/airflow "3.1 task"'))
        self.assertEqual(len(inputs), 2)
        self.assertIsNotNone(guard.check(inputs[0], self.repo))
        self.assertIsNone(guard.check(inputs[1], self.repo))
        self.assertEqual(list(guard.cli_inputs('ctx7 library boto3 "s3" --json')), [])

    def test_cli_search_checks_library_names_ids_and_explicit_version(self) -> None:
        inputs = list(guard.cli_inputs('ctx7 search "s3" --library boto3 --library /apache/airflow '
                                       '--library-version 1.43.56 --json'))
        self.assertIsNone(guard.check(inputs[0], self.repo))
        self.assertIsNotNone(guard.check(inputs[1], self.repo))

    def test_cli_options_can_precede_or_follow_positionals(self) -> None:
        for command in ('ctx7 docs --json --language Python /boto/boto3 "s3"',
                        'ctx7 --base-url https://context7.com docs /boto/boto3 --json "s3"',
                        'ctx7 docs /boto/boto3 "s3" --language=Python --json'):
            query, = guard.cli_inputs(command)
            self.assertEqual(query, {"libraryId": "/boto/boto3", "query": "s3"})
            self.assertIsNotNone(guard.check(query, self.repo))

    def test_bash_hook_denies_unversioned_cli_and_allows_versioned_cli(self) -> None:
        for query, denied in (("s3", True), ("boto3 1.43 s3", False)):
            result = subprocess.run([sys.executable, guard.__file__], text=True, capture_output=True,
                                    input=json.dumps({"cwd": str(self.repo), "tool_input": {
                                        "command": f'rtk ctx7 docs /boto/boto3 "{query}" --json'}}))
            self.assertEqual(result.returncode, 0, result.stderr)
            if denied:
                self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
            else:
                self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
