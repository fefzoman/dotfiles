"""SQLite is both the local spool and metadata index in this first slice."""

import json
import os
from pathlib import Path
import sqlite3
import stat
import uuid
from datetime import datetime, timedelta, timezone

MAX_DATABASE_BYTES = 16 * 1024 * 1024
RETENTION_DAYS = 7


class Store:
    def __init__(self, directory):
        directory = Path(directory).expanduser()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise PermissionError("state directory must be private and owned by the current user")
        path = directory / "events.sqlite3"
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.getuid() or info.st_mode & 0o077):
                raise PermissionError("unsafe database permissions")
        finally:
            os.close(fd)
        self.db = sqlite3.connect(path, timeout=0.2)
        try:
            self.db.execute("PRAGMA journal_mode=DELETE")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA secure_delete=ON")
            page_size = self.db.execute("PRAGMA page_size").fetchone()[0]
            self.db.execute(f"PRAGMA max_page_count={MAX_DATABASE_BYTES // page_size}")
            with self.db:
                self.db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('installation_id', ?)", (uuid.uuid4().hex,))
                self.db.execute("""CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    installation_id TEXT NOT NULL, provider TEXT NOT NULL,
                    repository_id TEXT NOT NULL, session_id TEXT NOT NULL,
                    event_id TEXT NOT NULL, observed_at TEXT NOT NULL, data TEXT NOT NULL,
                    UNIQUE (installation_id, provider, repository_id, session_id, event_id))""")
                self.db.execute("CREATE INDEX IF NOT EXISTS events_time ON events(observed_at)")
            self.installation_id = self.db.execute(
                "SELECT value FROM metadata WHERE key='installation_id'"
            ).fetchone()[0]
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def append(self, event):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
        with self.db:
            self.db.execute("DELETE FROM events WHERE observed_at < ?", (cutoff,))
        with self.db:
            result = self.db.execute(
                """INSERT OR IGNORE INTO events
                (installation_id, provider, repository_id, session_id, event_id, observed_at, data)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                tuple(event[key] for key in ("installation_id", "provider", "repository_id", "session_id",
                                            "event_id", "observed_at")) + (json.dumps(event, sort_keys=True),),
            )
        return result.rowcount == 1

    def events(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
        for sequence, data in self.db.execute(
            "SELECT sequence, data FROM events WHERE observed_at >= ? ORDER BY sequence", (cutoff,)
        ):
            yield {**json.loads(data), "sequence": sequence}
