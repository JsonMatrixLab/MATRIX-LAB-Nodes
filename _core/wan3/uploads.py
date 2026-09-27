"""Account-scoped asset reuse; signed PUT tickets and API keys are never stored."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from .private_storage import private_file


class UploadCache:
    # Provider asset retention is seven days; renew a day early. Ticket expiry is separate.
    MAX_AGE = 6 * 24 * 60 * 60

    def __init__(self, path, *, clock=time.time):
        self.path = Path(path)
        self.clock = clock

    def get_or_upload(self, asset, scope, upload, *, check_cancelled=None, wait_limit=600):
        key = hashlib.sha256(json.dumps([scope, asset.sha256, asset.size, asset.content_type]).encode()).hexdigest()
        private_file(self.path)
        deadline = time.monotonic() + wait_limit
        with closing(sqlite3.connect(self.path, timeout=0.1, isolation_level=None)) as con:
            while True:
                if check_cancelled:
                    check_cancelled()
                try:
                    con.execute("BEGIN IMMEDIATE")
                    break
                except sqlite3.OperationalError as exc:
                    if "locked" not in str(exc).lower() or time.monotonic() >= deadline:
                        raise
            try:
                con.execute("CREATE TABLE IF NOT EXISTS assets (identity TEXT PRIMARY KEY, url TEXT NOT NULL, created REAL NOT NULL)")
                row = con.execute("SELECT url,created FROM assets WHERE identity=?", (key,)).fetchone()
                now = self.clock()
                if row and 0 <= now - row[1] < self.MAX_AGE:
                    con.commit()
                    return row[0]
                # A cache-only transaction serializes uploads across processes. A cancelled
                # waiter owns no shared request; a crash releases the SQLite lock automatically.
                if check_cancelled:
                    check_cancelled()
                url = upload()
                if not isinstance(url, str) or not url.startswith("https://"):
                    raise ValueError("Upload did not return a usable HTTPS asset URL.")
                con.execute("INSERT OR REPLACE INTO assets VALUES(?,?,?)", (key, url, self.clock()))
                con.commit()
                return url
            except BaseException:
                con.rollback()
                raise
