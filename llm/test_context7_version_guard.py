import tempfile
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


if __name__ == "__main__":
    unittest.main()
