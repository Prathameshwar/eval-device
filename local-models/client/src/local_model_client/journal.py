"""Bounded metadata for inspecting uncertain submissions after a device restart."""

import sqlite3
import time
from pathlib import Path

from training_contracts.privacy import no_link, private_tree


class Requests:
    def __init__(self, directory):
        root = private_tree(Path(directory))
        self.path = root / "requests.sqlite3"
        if self.path.exists() or self.path.is_symlink():
            no_link(self.path)
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, state TEXT NOT NULL, stamp REAL NOT NULL)"
            )

    def note(self, identity, state):
        with sqlite3.connect(self.path, timeout=2) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM requests WHERE stamp < ?", (time.time() - 86400,))
            if (
                not db.execute("SELECT 1 FROM requests WHERE id=?", (identity,)).fetchone()
                and db.execute("SELECT count(*) FROM requests").fetchone()[0] >= 100000
            ):
                raise ValueError("Inference journal is full")
            db.execute(
                "INSERT INTO requests VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET state=excluded.state",
                (identity, state, time.time()),
            )

    def recent(self):
        with sqlite3.connect(self.path) as db:
            return [
                {"id": row[0], "status": row[1]}
                for row in db.execute("SELECT id, state FROM requests ORDER BY stamp DESC LIMIT 20")
            ]
