#!/usr/bin/env python3
"""Model-free checks: chunking, identifier splitting, lexical retrieval, fusion."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

os.environ["SMART_READ_CACHE"] = tempfile.mkdtemp()
import smart_read as sr  # noqa: E402

PYTHON = '''import os


def refresh_token(session):
    return session.renew()


class TokenStore:
    def load(self):
        return os.environ["TOKEN"]
''' + "\n".join(f"    def helper_{i}(self):\n        return {i}\n" for i in range(40))

SQL = "with spend as (\n  select * from raw\n)\nselect * from spend\n\ncreate table facebook_spend as select 1\n"


class SmartReadTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "auth.py").write_text(PYTHON)
        (self.root / "models").mkdir()
        (self.root / "models" / "spend.sql").write_text(SQL)
        (self.root / "image.png").write_bytes(b"\x89PNG\0\0")

    def test_python_chunks_follow_symbols_and_split_large_classes(self):
        chunks = sr.chunk_file("auth.py", PYTHON)
        self.assertTrue(chunks[0].symbol.startswith("def refresh_token, class TokenStore"))
        self.assertTrue(all(c.symbol.startswith("def TokenStore.helper_") for c in chunks[1:]))
        self.assertTrue(all(c.end - c.start < sr.MAX_SEGMENT for c in chunks))
        lines = PYTHON.splitlines()
        for c in chunks:
            self.assertEqual(c.text, "\n".join(lines[c.start - 1:c.end]))

    def test_identifier_splitting(self):
        self.assertIn("refresh Token", sr.split_identifiers("refreshToken"))
        self.assertIn("facebook spend", sr.split_identifiers("facebook_spend"))

    def test_lexical_search_refresh_and_path_filter(self):
        db = sr.connect(self.root)
        self.assertEqual(sr.refresh(db, self.root), 2)
        self.assertEqual(sr.refresh(db, self.root), 0)
        hits, _ = sr.search(db, self.root, "renew the token", None, 3, use_dense=False)
        path, symbol = db.execute("SELECT path, symbol FROM chunks WHERE id=?", (hits[0][0],)).fetchone()
        self.assertEqual(path, "auth.py")
        self.assertTrue(symbol.startswith("def refresh_token"))
        hits, _ = sr.search(db, self.root, "facebook spend", "models/", 3, use_dense=False)
        self.assertTrue(hits)
        self.assertTrue(all(db.execute("SELECT path FROM chunks WHERE id=?", (i,)).fetchone()[0] == "models/spend.sql"
                            for i, _ in hits))
        (self.root / "auth.py").write_text("def other():\n    pass\n")
        self.assertEqual(sr.refresh(db, self.root), 1)
        hits, _ = sr.search(db, self.root, "renew", None, 3, use_dense=False)
        self.assertEqual(hits, [])
        self.assertIn("1-", sr.render(db, sr.search(db, self.root, "other", None, 1, False)[0], ""))

    def test_rrf_rewards_agreement(self):
        self.assertEqual(sr.rrf([[1, 2, 3], [2, 3, 1], [2]])[0], 2)
        self.assertEqual(sr.rrf([[1], [2], [3]])[0], 3)  # dense outweighs BM25 and trigram

    def test_outline_lists_symbol_ranges(self):
        text = sr.outline(self.root / "auth.py")
        self.assertIn("def refresh_token", text)
        self.assertIn("class TokenStore", text)


if __name__ == "__main__":
    unittest.main()
