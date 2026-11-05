"""Private bounded pending records. All filesystem methods run on the disk worker."""

import json
import math
import os
import re
import threading
import time
from datetime import datetime
from itertools import islice
from pathlib import Path
from uuid import UUID

from training_contracts.privacy import StorageError, no_link, private_directory

MAX_RECORD = 131072


class Outbox:
    def __init__(self, root, namespace, *, max_records=1000, max_bytes=64 * 1024 * 1024, max_age=86400):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", namespace):
            raise StorageError("unsafe_namespace")
        self.path = Path(root).absolute() / namespace
        self.max_records, self.max_bytes, self.max_age = max_records, max_bytes, max_age
        self.lock = threading.Lock()
        self.records = {}
        self.bad_count = 0
        self.owner = None
        for part in reversed((self.path, *self.path.parents)):
            if part.exists():
                no_link(part)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        private_directory(self.path.parent)
        self.path.mkdir(exist_ok=True)
        private_directory(self.path)
        owner = self.path / "owner.lock"
        if owner.exists():
            no_link(owner)
        self.owner = owner.open("a+b")
        try:
            self.owner.seek(0)
            if os.name == "nt":
                import msvcrt

                if owner.stat().st_size == 0:
                    self.owner.write(b"0")
                    self.owner.flush()
                self.owner.seek(0)
                msvcrt.locking(self.owner.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.recover()
        except BaseException:
            self.close()
            raise

    def files(self):
        no_link(self.path)
        paths = list(islice(self.path.iterdir(), self.max_records + 20))
        if len(paths) >= self.max_records + 20:
            raise StorageError("history_file_limit")
        return [p for p in paths if p.name != "owner.lock"]

    def recover(self):
        for path in self.files():
            no_link(path)
            if not path.is_file():
                raise StorageError("unsafe_path")
            if path.suffix in {".tmp", ".bad"}:
                if time.time() - path.stat().st_mtime >= self.max_age:
                    path.unlink()
                else:
                    self.bad_count += 1
                continue
            try:
                if path.suffix != ".json" or path.stat().st_size > MAX_RECORD:
                    raise ValueError("invalid record")
                item = json.loads(path.read_text(encoding="utf-8"))
                key = str(UUID(item["record"]["turn_key"]))
                assert path.name == key + ".json"
                record = item["record"]
                assert isinstance(record["input_text"], str) and 1 <= len(record["input_text"]) <= 8000
                assert record["outcome"] in {"completed", "failed", "cancelled"}
                answer = record.get("response_text")
                assert (record["outcome"] == "completed") == (answer is not None)
                assert answer is None or (isinstance(answer, str) and 1 <= len(answer.encode()) <= 32000)
                occurred = datetime.fromisoformat(record["occurred_at"])
                assert occurred.tzinfo is not None
                assert isinstance(item["expires_at"], (int, float)) and math.isfinite(item["expires_at"])
                item["expires_at"] = min(item["expires_at"], occurred.timestamp() + self.max_age)
                metrics = item.get("metrics")
                if metrics is not None:
                    assert isinstance(metrics, dict) and metrics["turn_key"] == key
                    assert datetime.fromisoformat(metrics["occurred_at"]).tzinfo is not None
                assert item["state"] in {"pending", "rejected"}
                if item["expires_at"] <= time.time():
                    path.unlink()
                else:
                    self.records[key] = item
            except (ValueError, KeyError, TypeError, AssertionError):
                path.replace(path.with_suffix(".bad"))
                self.bad_count += 1

    def _write(self, key, item):
        path = self.path / (str(UUID(key)) + ".json")
        temporary = path.with_suffix(".tmp")
        for candidate in (path, temporary):
            if candidate.exists():
                no_link(candidate)
        encoded = json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_RECORD:
            raise StorageError("history_record_limit")
        files = self.files()
        used = sum(p.stat().st_size for p in files)
        previous = path.stat().st_size if path.exists() else 0
        if (not path.exists() and len(files) >= self.max_records) or used - previous + len(
            encoded
        ) > self.max_bytes:
            raise StorageError("history_disk_limit")
        with temporary.open("wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            fd = os.open(self.path, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        with self.lock:
            self.records[key] = item

    def put(self, record, metrics=None):
        key = str(UUID(record["turn_key"]))
        existing = self.records.get(key)
        if existing:
            if existing["record"] != record:
                raise StorageError("history_conflict")
            return
        occurred = datetime.fromisoformat(record["occurred_at"]).timestamp()
        expiry = min(time.time() + self.max_age, occurred + self.max_age)
        if expiry <= time.time():
            raise StorageError("history_expired")
        self._write(key, {"record": record, "metrics": metrics, "expires_at": expiry, "state": "pending"})

    def acknowledge(self, key):
        with self.lock:
            if key in self.records:
                self.records[key] = {**self.records[key], "state": "acknowledged"}
        path = self.path / (str(UUID(key)) + ".json")
        if path.exists():
            no_link(path)
            path.unlink()
        with self.lock:
            self.records.pop(key, None)

    def reject(self, key):
        with self.lock:
            item = self.records.get(key)
        if item:
            rejected = {**item, "state": "rejected"}
            with self.lock:
                self.records[key] = rejected
            self._write(key, rejected)

    def expire(self):
        with self.lock:
            expired = [key for key, item in self.records.items() if item["expires_at"] <= time.time()]
        for key in expired:
            self.acknowledge(key)
        for path in self.files():
            if path.suffix in {".tmp", ".bad"} and time.time() - path.stat().st_mtime >= self.max_age:
                no_link(path)
                path.unlink()
        return len(expired)

    def snapshot(self):
        with self.lock:
            return [item for item in self.records.values() if item["expires_at"] > time.time()]

    def close(self):
        if self.owner:
            self.owner.close()
            self.owner = None
