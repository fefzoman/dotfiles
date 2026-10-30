#!/usr/bin/env python3
"""Model-free checks: chunking, identifier splitting, lexical retrieval, fusion."""

import contextlib
import fcntl
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ["SMART_READ_CACHE"] = tempfile.mkdtemp()
import smart_read as sr  # noqa: E402

CLI = [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(Path(sr.__file__).parent)!r}); "
       "import smart_read as sr; "
       "sr.embedder = lambda: (_ for _ in ()).throw(AssertionError('models disabled in CLI tests')); "
       "sys.exit(sr.main())"]

PYTHON = '''import os


def refresh_token(session):
    return session.renew()


class TokenStore:
    def load(self):
        return os.environ["TOKEN"]
''' + "\n".join(f"    def helper_{i}(self):\n        return {i}\n" for i in range(40))

SQL = "with spend as (\n  select * from raw\n)\nselect * from spend\n\ncreate table facebook_spend as select 1\n"


class SmartReadTest(unittest.TestCase):
    def test_lexical_search_works_when_cache_is_not_writable(self):
        with patch.object(sr, "CACHE", Path("/unwritable/cache")), \
                patch.object(Path, "mkdir", side_effect=PermissionError("sandbox")), \
                patch.object(sys, "argv", ["smart-read", "search", "renew token", "--lexical"]), \
                patch.object(sr, "repo_root", return_value=self.root), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(sr.main(), 0)
        self.assertIn("auth.py", output.getvalue())

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve() / "repo"
        self.root.mkdir()
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
        self.addCleanup(db.close)
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

    def test_search_never_embeds_pending_chunks_or_starts_workers(self):
        for extra in (0, 201):
            with self.subTest(extra=extra), contextlib.closing(sr.connect(self.root)) as db:
                sr.refresh(db, self.root)
                db.executemany("INSERT INTO chunks(path, text) VALUES('extra.py', 'pending')", [()] * extra)
                pending = db.execute("SELECT count(*) FROM chunks WHERE vec IS NULL").fetchone()[0]
                popen = sr.subprocess.Popen

                def foreground_only(*args, **kwargs):
                    if kwargs.get("start_new_session"):
                        raise AssertionError("search spawned a worker")
                    return popen(*args, **kwargs)

                with patch.object(sr, "embedder", side_effect=AssertionError("search loaded a model")), \
                     patch.object(sr.subprocess, "Popen", side_effect=foreground_only):
                    hits, note = sr.search(db, self.root, "renew token", None, 3)
                self.assertTrue(hits)
                self.assertIn("smart-read index", note)
                self.assertEqual(db.execute("SELECT count(*) FROM chunks WHERE vec IS NULL").fetchone()[0], pending)

    def test_search_uses_existing_vectors_and_lexical_fallback(self):
        import numpy as np

        with contextlib.closing(sr.connect(self.root)) as db:
            sr.refresh(db, self.root)
            cid = db.execute("SELECT id FROM chunks WHERE path='models/spend.sql'").fetchone()[0]
            db.execute("UPDATE chunks SET vec=? WHERE id=?", (np.array([1, 0], dtype=np.float32).tobytes(), cid))
            db.commit()

            def no_index(*args, **kwargs):
                self.fail("search tried to embed chunks")

            model = SimpleNamespace(query_embed=lambda queries: iter([[1, 0]]), embed=no_index)
            with patch.object(sr, "embedder", return_value=model):
                hits, note = sr.search(db, self.root, "renew token", None, 50)
            self.assertIn(cid, [i for i, _ in hits])
            self.assertTrue(any(db.execute("SELECT path FROM chunks WHERE id=?", (i,)).fetchone()[0] == "auth.py"
                                for i, _ in hits))
            self.assertIn("smart-read index", note)

    def test_cli_rejects_parent_directory_without_creating_cache(self):
        cache = self.root / "unused-cache"
        for command in (["search", "token", "--lexical"], ["index", "--root", str(self.root.parent)]):
            result = subprocess.run([*CLI, *command], cwd=self.root.parent,
                                    env=os.environ | {"SMART_READ_CACHE": str(cache)}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Git repository", result.stderr)
        self.assertFalse(cache.exists())
        self.assertEqual(sr.repo_root(self.root / "models"), self.root)

    def test_embedding_reads_only_one_batch_at_a_time_and_saves_progress(self):
        with contextlib.closing(sr.connect(self.root)) as db:
            db.executemany("INSERT INTO chunks(path, symbol, text) VALUES('x.py', 'x', 'text')", [()] * 130)
            db.commit()
            loaded, sizes = [], []

            def row_factory(cursor, row):
                if "text" in [column[0] for column in cursor.description]:
                    loaded.append(row)
                return row

            def embed(texts, batch_size):
                self.assertLessEqual(len(loaded), 64)
                loaded.clear()
                sizes.append(len(texts))
                return ([1, 0] for _ in texts)

            db.row_factory = row_factory
            output = io.StringIO()
            with patch.object(sr, "embedder", return_value=SimpleNamespace(embed=embed)), \
                 contextlib.redirect_stderr(output):
                self.assertEqual(sr.embed_pending(db), 130)
            self.assertEqual(sizes, [64, 64, 2])
            self.assertIn("130/130", output.getvalue())
            self.assertEqual(db.execute("SELECT count(*) FROM chunks WHERE vec IS NOT NULL").fetchone()[0], 130)

    def test_interrupted_batch_preserves_committed_vectors_for_resume(self):
        with contextlib.closing(sr.connect(self.root)) as db:
            db.executemany("INSERT INTO chunks(path, symbol, text) VALUES('x.py', 'x', 'text')", [()] * 65)
            db.commit()

            def embed(texts, batch_size):
                if len(texts) == 1:
                    raise KeyboardInterrupt
                return ([1, 0] for _ in texts)

            with patch.object(sr, "embedder", return_value=SimpleNamespace(embed=embed)), \
                 contextlib.redirect_stderr(io.StringIO()), self.assertRaises(KeyboardInterrupt):
                sr.embed_pending(db)
        with contextlib.closing(sr.connect(self.root)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM chunks WHERE vec IS NOT NULL").fetchone()[0], 64)
            model = SimpleNamespace(embed=lambda texts, batch_size: ([1, 0] for _ in texts))
            with patch.object(sr, "embedder", return_value=model), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(sr.embed_pending(db), 1)

    def test_cli_lock_prevents_overlap_and_survives_stale_timestamp(self):
        sr.CACHE.mkdir(parents=True, exist_ok=True)
        lock_path = sr.CACHE / f"{sr.cache_key(self.root)}.indexing"
        with lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.utime(lock_path, (0, 0))
            for command in (["index", "--root", str(self.root)], ["search", "token", "--lexical"]):
                result = subprocess.run([*CLI, *command], cwd=self.root,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn("in use", result.stderr)
        result = subprocess.run([*CLI, "search", "token", "--lexical"], cwd=self.root,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("auth.py", result.stdout)

    def test_interrupted_index_releases_lock_and_can_resume(self):
        argv = ["smart-read", "index", "--root", str(self.root)]
        with patch.object(sys, "argv", argv), patch.object(sr, "embedder", side_effect=KeyboardInterrupt), \
             contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            try:
                result = sr.main()
            except KeyboardInterrupt:
                result = None
            self.assertEqual(result, 130)
        with patch.object(sys, "argv", argv), \
             patch.object(sr, "embedder", return_value=SimpleNamespace(embed=lambda texts, batch_size: ([1, 0] for _ in texts))), \
             contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sr.main(), 0)
        with contextlib.closing(sr.connect(self.root)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM chunks WHERE vec IS NULL").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
