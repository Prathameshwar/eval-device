"""Nonblocking capture intake; durable disk journal and one throttled upload worker.

No hashing, filesystem operations, HTTP, encoding or waits run on the caller thread.
An unfinished journal remains recoverable and is never labelled fully synchronized.
"""

import asyncio
import hashlib
import json
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import wave
from collections import deque
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from training_contracts.durability import durable_replace
from training_contracts.privacy import no_link, private_directory

CHUNK = 262144
FRAME_LIMIT = 32768
CLOSE_FLUSH_SECONDS = 15


class SaveQueue(queue.Queue):
    """Result/context FIFO ahead of media; eight urgent commands then one media.

    One writer preserves SQLite ownership and quotas. Lifecycle/media commands
    keep their original ordering; a context always precedes its result.
    """

    def _init(self, maxsize):
        self.urgent = deque()
        self.media = deque()
        self.burst = 0

    def _qsize(self):
        return len(self.urgent) + len(self.media)

    def _put(self, item):
        (self.urgent if item[0] in ("begin", "turn") else self.media).append(item)

    def _get(self):
        if self.urgent and (self.burst < 8 or not self.media):
            self.burst += 1
            return self.urgent.popleft()
        self.burst = 0
        return self.media.popleft()


class JournalConnection(sqlite3.Connection):
    """SQLite contention waits on background threads without dropping queued commands."""

    def retry(self, operation, *args, **kwargs):
        while True:
            try:
                return operation(*args, **kwargs)
            except sqlite3.OperationalError as error:
                if getattr(error, "sqlite_errorcode", 0) & 0xFF not in (
                    sqlite3.SQLITE_BUSY,
                    sqlite3.SQLITE_LOCKED,
                ):
                    raise
                time.sleep(0.05)

    def execute(self, *args, **kwargs):
        return self.retry(super().execute, *args, **kwargs)

    def executescript(self, *args, **kwargs):
        return self.retry(super().executescript, *args, **kwargs)

    def commit(self):
        return self.retry(super().commit)


@dataclass
class SaveReceipt:
    finished: threading.Event = field(default_factory=threading.Event)
    saved: bool = False


def lower_thread_priority():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentThread.restype = wintypes.HANDLE
        kernel.SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
        kernel.SetThreadPriority(kernel.GetCurrentThread(), -1)
    elif hasattr(os, "setpriority"):
        try:
            os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 10)
        except OSError:
            pass


class FileLock:
    def __init__(self, path):
        no_link(path) if path.exists() else None
        self.file = path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                if path.stat().st_size == 0:
                    self.file.write(b"0")
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.file.close()
            raise

    def close(self):
        self.file.close()


def database(root):
    db = sqlite3.connect(root / "journal.sqlite", timeout=0.1, factory=JournalConnection)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, state TEXT NOT NULL,
          incomplete INTEGER NOT NULL DEFAULT 0, outcome TEXT NOT NULL DEFAULT 'interrupted',
          manifest TEXT, acknowledged INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY, session TEXT NOT NULL,
          kind TEXT NOT NULL, path TEXT NOT NULL, sequence INTEGER NOT NULL, size INTEGER NOT NULL DEFAULT 0,
          ready INTEGER NOT NULL DEFAULT 0, uploaded INTEGER NOT NULL DEFAULT 0,
          metadata TEXT, error TEXT, external INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS item_session ON items(session);
        CREATE INDEX IF NOT EXISTS item_pending ON items(uploaded,ready,kind);
        CREATE TABLE IF NOT EXISTS control(id INTEGER PRIMARY KEY CHECK(id=1), busy_until REAL NOT NULL);
        INSERT OR IGNORE INTO control(id,busy_until) VALUES(1,0);
    """)
    # Forward-only local journal upgrades preserve recordings and old pending work.
    for table in ("items", "sessions"):
        columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        for name, declaration in (
            ("retry_at", "REAL NOT NULL DEFAULT 0"),
            ("attempts", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in columns:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
    if "auth_until" not in {row[1] for row in db.execute("PRAGMA table_info(control)")}:
        db.execute("ALTER TABLE control ADD COLUMN auth_until REAL NOT NULL DEFAULT 0")
    if "error" not in {row[1] for row in db.execute("PRAGMA table_info(sessions)")}:
        db.execute("ALTER TABLE sessions ADD COLUMN error TEXT")
    if "context_size" not in {row[1] for row in db.execute("PRAGMA table_info(sessions)")}:
        db.execute("ALTER TABLE sessions ADD COLUMN context_size INTEGER NOT NULL DEFAULT 0")
    db.commit()
    return db


class SessionSync:
    def __init__(self, settings, emit, *, transport=None, drain=False):
        self.settings = settings.model_copy(deep=True)
        self.emit, self.transport = emit, transport
        self.drain = drain
        self.disk_ok = False
        namespace = hashlib.sha256(
            json.dumps(
                [settings.pms_url.rstrip("/"), str(settings.organization_id), str(settings.device_id)]
            ).encode()
        ).hexdigest()
        self.root = settings.session_sync_dir / namespace
        self.queue = SaveQueue(maxsize=256)  # At most 8 MiB; reserve eight result/context slots.
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.retry_requested = threading.Event()
        self.guard = threading.Lock()
        self.current = None
        self.active_work = 0
        self.pending_bytes = 0
        self.failed = set()
        self.video_pending = set()
        self.disk = threading.Thread(target=self._disk, name="session-sync-disk", daemon=True)
        self.upload = threading.Thread(target=self._upload, name="session-sync-upload", daemon=True)
        self.disk.start()
        self.upload.start()

    def notify(self, text):
        try:
            self.emit("session_sync", text)
        except Exception:
            pass

    def submit(self, command, sid, *args):
        if not sid or self.stop.is_set():
            return False
        if self.ready.is_set() and not self.disk_ok:
            self.notify("Sync needs attention: local storage is unavailable; this capture was not saved.")
            return False
        weight = 1024 + sum(len(value) if isinstance(value, bytes) else 0 for value in args)
        if command == "turn":
            weight += 4 * (len(args[0].get("input_text", "")) + len(args[0].get("response_text") or ""))
        elif command == "begin" and args:
            weight += 4 * len(args[0].get("snapshot", {}).get("system", "")) + 4096
        with self.guard:
            try:
                budget = 8 * 1024 * 1024 - (131072 if command in ("audio", "video") else 0)
                if self.pending_bytes + weight > budget:
                    raise queue.Full
                if command in ("audio", "video") and self.queue.qsize() >= 248:
                    raise queue.Full
                self.queue.put_nowait((command, str(sid), args, weight))
                self.pending_bytes += weight
                return True
            except queue.Full:
                self.failed.add(str(sid))
        self.notify("Sync needs attention: local save queue is full. Practice can continue.")
        return False

    def activate(self, conversation):
        if not conversation:
            return None
        sid = conversation["context"]["conversation_id"]
        with self.guard:
            needed = self.current != sid
            if needed:
                # Set before queue admission: the disk worker may fail immediately.
                self.current = sid
        if needed and not self.submit("begin", sid, conversation):
            with self.guard:
                if self.current == sid:
                    self.current = None
        return sid

    def busy(self, value):
        with self.guard:
            self.active_work = max(0, self.active_work + (1 if value else -1))

    def retry(self):
        self.retry_requested.set()
        self.notify("Pending uploads will retry when practice is idle.")

    def audio_start(self, sid, stream):
        self.submit("audio_start", sid, stream)

    def audio(self, sid, stream, pcm, rate=16000, kind="microphone"):
        # Frames are immutable bytes already used by capture/playback; keep the same reference.
        if len(pcm) > FRAME_LIMIT:
            for offset in range(0, len(pcm), FRAME_LIMIT):
                self.submit("audio", sid, stream, pcm[offset : offset + FRAME_LIMIT], rate, kind)
        else:
            self.submit("audio", sid, stream, pcm, rate, kind)

    def audio_end(self, sid, stream):
        self.submit("audio_end", sid, stream)

    def turn(self, sid, record):
        return self.submit("turn", sid, record)

    async def save_turn(self, sid, record):
        receipt = SaveReceipt()
        if not self.submit("turn", sid, record, receipt):
            return False
        # The UI event loop remains free. Never report a queued result as locally durable.
        completed = await asyncio.to_thread(receipt.finished.wait, 5)
        if not completed:
            self.notify("Result save pending on this device; keep the app open until local saving finishes.")
        return completed and receipt.saved

    def video_start(self, sid):
        with self.guard:
            if sid not in self.video_pending:
                self.active_work += 1
            self.video_pending.add(sid)
        self.submit("video_start", sid)

    def video_file(self, sid, path):
        self.submit("video", sid, str(path))

    def video_end(self, sid, incomplete=False):
        self.submit("video_end", sid, incomplete)
        with self.guard:
            if sid in self.video_pending:
                self.active_work = max(0, self.active_work - 1)
            self.video_pending.discard(sid)

    def end(self, sid=None, outcome="completed"):
        sid = sid or self.current
        self.submit("end", sid, outcome)
        if self.current == sid:
            self.current = None

    def _disk(self):
        lower_thread_priority()
        db = None
        owner = None
        streams = {}
        closing = {}
        videos = set()
        capturing = set()
        try:
            for parent in reversed((self.root, *self.root.parents)):
                if parent.exists():
                    no_link(parent)
            self.root.mkdir(parents=True, exist_ok=True)
            private_directory(self.root)
            deadline = time.monotonic() + (30 if self.drain else 0)
            while True:
                try:
                    owner = FileLock(self.root / "writer.lock")
                    break
                except OSError:
                    if not self.drain or time.monotonic() >= deadline:
                        raise
                    self.stop.wait(0.1)
            no_link(self.root / "journal.sqlite") if (self.root / "journal.sqlite").exists() else None
            db = database(self.root)
            if not self.drain:
                db.execute("UPDATE control SET busy_until=0,auth_until=0 WHERE id=1")
            # Keep a bounded receipt history. Never remove unacknowledged captures.
            expired = [
                r[0]
                for r in db.execute(
                    "SELECT id FROM sessions WHERE acknowledged=1 AND created<? AND NOT EXISTS(SELECT 1 FROM items WHERE session=sessions.id AND uploaded=0)",
                    (time.time() - 30 * 86400,),
                )
            ]
            for sid in expired:
                (self.root / (str(UUID(sid)) + ".context")).unlink(missing_ok=True)
                (self.root / (str(UUID(sid)) + ".context.part")).unlink(missing_ok=True)
                db.execute("DELETE FROM items WHERE session=?", (sid,))
                db.execute("DELETE FROM sessions WHERE id=?", (sid,))
            # Reconcile snapshots from older journals and crashes between file replacement
            # and accounting. This bounded scan runs once on the disk worker at startup.
            for row in db.execute("SELECT id FROM sessions WHERE context_size=0").fetchall():
                path = self.root / (str(UUID(row["id"])) + ".context")
                if not path.exists():
                    path = path.with_suffix(".context.part")
                try:
                    no_link(path)
                except FileNotFoundError:
                    continue
                db.execute("UPDATE sessions SET context_size=? WHERE id=?", (path.stat().st_size, row["id"]))
            recovering = {
                row[0] for row in db.execute("SELECT id FROM sessions WHERE state IN ('open','closing')")
            }
            if recovering:
                recovered_bytes, recovered_count = db.execute(
                    "SELECT coalesce(sum(size),0),count(*) FROM items WHERE uploaded=0"
                ).fetchone()
                recovered_bytes += db.execute(
                    "SELECT coalesce(sum(context_size),0) FROM sessions"
                ).fetchone()[0]
                recovered_per_session = dict(
                    db.execute("SELECT session,count(*) FROM items GROUP BY session")
                )
                # Camera files contain their session identity. Recover completed segments
                # even if the GUI stopped before consuming the camera's final notifications.
                for receipt in islice(self.settings.video_recording_dir.glob("*/*/*/*/session.json"), 2000):
                    try:
                        for parent in (receipt, *receipt.parents):
                            no_link(parent)
                        if receipt.stat().st_size > 65536:
                            continue
                        saved = json.loads(receipt.read_text(encoding="utf-8"))
                        sid = saved.get("archive_id")
                        if sid not in recovering or saved.get("archive_namespace") != self.root.name:
                            continue
                        for name in saved.get("segments", [])[:120]:
                            if not re.fullmatch(r"video-[0-9]{4}\.mkv", name):
                                continue
                            path = receipt.parent / name
                            no_link(path)
                            if (
                                path.is_file()
                                and not db.execute(
                                    "SELECT 1 FROM items WHERE path=?", (str(path),)
                                ).fetchone()
                            ):
                                size = path.stat().st_size
                                if (
                                    not 0 < size <= CHUNK * 1024
                                    or recovered_bytes + size > self.settings.session_sync_max_bytes
                                    or recovered_count >= 20000
                                    or recovered_per_session.get(sid, 0) >= 4000
                                ):
                                    continue
                                recovered_bytes += size
                                recovered_count += 1
                                recovered_per_session[sid] = recovered_per_session.get(sid, 0) + 1
                                db.execute(
                                    "INSERT INTO items(id,session,kind,path,sequence,size,ready,external) VALUES(?,?,'video',?,?,?,1,1)",
                                    (
                                        str(uuid4()),
                                        sid,
                                        str(path),
                                        db.execute(
                                            "SELECT count(*) FROM items WHERE session=?", (sid,)
                                        ).fetchone()[0],
                                        path.stat().st_size,
                                    ),
                                )
                    except (OSError, ValueError, KeyError, TypeError):
                        continue
            # A process stopped without a seal is visibly interrupted. Repair complete PCM
            # samples in its last WAV part, never claim the unflushed tail was captured.
            db.execute("UPDATE sessions SET incomplete=1,state='closing' WHERE state IN ('open','closing')")
            for item in db.execute("SELECT * FROM items WHERE ready=0").fetchall():
                path = Path(item["path"])
                partial = path.with_suffix(".part")
                if item["kind"] == "turn":
                    candidate = path if path.exists() else partial
                    try:
                        no_link(candidate)
                        if candidate.stat().st_size <= 131072:
                            json.loads(candidate.read_bytes())
                            if candidate != path:
                                with candidate.open("r+b") as output:
                                    os.fsync(output.fileno())
                                durable_replace(candidate, path)
                            db.execute(
                                "UPDATE items SET ready=1,size=? WHERE id=?",
                                (path.stat().st_size, item["id"]),
                            )
                    except (OSError, ValueError):
                        pass
                if path.exists() and item["kind"] in ("microphone", "patient_audio"):
                    try:
                        no_link(path)
                        with wave.open(str(path), "rb") as saved_wav:
                            if saved_wav.getnchannels() != 1 or saved_wav.getsampwidth() != 2:
                                raise ValueError("invalid PCM")
                        db.execute(
                            "UPDATE items SET ready=1,size=? WHERE id=?", (path.stat().st_size, item["id"])
                        )
                    except (OSError, ValueError, wave.Error):
                        pass
                if partial.exists() and item["kind"] in ("microphone", "patient_audio"):
                    try:
                        no_link(partial)
                        with partial.open("rb") as source:
                            header = source.read(44)
                            pcm = source.read(5 * 48000 * 2 + FRAME_LIMIT)
                        rate = int.from_bytes(header[24:28], "little")
                        if len(header) == 44 and rate in (16000, 22050, 24000, 44100, 48000) and pcm:
                            repaired = path.with_suffix(".repair")
                            with wave.open(str(repaired), "wb") as output:
                                output.setparams((1, 2, rate, 0, "NONE", "not compressed"))
                                output.writeframes(pcm[: len(pcm) // 2 * 2])
                            with repaired.open("r+b") as output:
                                os.fsync(output.fileno())
                            durable_replace(repaired, path)
                            partial.unlink()
                            db.execute(
                                "UPDATE items SET ready=1,size=? WHERE id=?",
                                (path.stat().st_size, item["id"]),
                            )
                    except (OSError, ValueError, wave.Error):
                        pass
            for row in db.execute("SELECT id FROM sessions WHERE state='closing'").fetchall():
                closing[row["id"]] = 0
            db.commit()
            known = {row[0] for row in db.execute("SELECT id FROM sessions")}
            reported_failures = set()
            last_control = 0.0
            last_busy = False
            self.disk_ok = True
            self.ready.set()

            def capacity(sid, size):
                used, count = db.execute(
                    "SELECT coalesce(sum(size),0),count(*) FROM items WHERE uploaded=0"
                ).fetchone()
                used += db.execute("SELECT coalesce(sum(context_size),0) FROM sessions").fetchone()[0]
                count_session = db.execute("SELECT count(*) FROM items WHERE session=?", (sid,)).fetchone()[0]
                if (
                    used + size > self.settings.session_sync_max_bytes
                    or count >= 20000
                    or count_session >= 4000
                ):
                    raise OSError("local quota")
                if shutil.disk_usage(self.root).free < size + 64 * 1024 * 1024:
                    raise OSError("disk space")

            def finish_stream(identity):
                entry = streams.pop(identity, None)
                if entry:
                    item, audio, partial, final, size, flushed, raw = entry
                    try:
                        audio.close()
                        raw.flush()
                        os.fsync(raw.fileno())
                    finally:
                        raw.close()
                    durable_replace(partial, final)
                    db.execute("UPDATE items SET ready=1,size=? WHERE id=?", (final.stat().st_size, item))

            while not self.stop.is_set() or not self.queue.empty():
                if self.retry_requested.is_set():
                    self.retry_requested.clear()
                    # Expired or checksum-rejected media cannot be made valid by retrying.
                    db.execute(
                        "UPDATE items SET error=NULL,retry_at=0,attempts=0 WHERE error IN ('file_unavailable','403') OR error IS NULL"
                    )
                    db.execute(
                        "UPDATE sessions SET retry_at=0,attempts=0,acknowledged=0,error=NULL WHERE acknowledged=0 OR (acknowledged=-1 AND error='403')"
                    )
                    db.execute("UPDATE control SET auth_until=0 WHERE id=1")
                    db.commit()
                try:
                    command, sid, args, weight = self.queue.get(timeout=0.1)
                except queue.Empty:
                    command = None
                if command:
                    try:
                        if sid not in known:
                            if len(known) >= 5000:
                                raise OSError("local session limit")
                            db.execute(
                                "INSERT OR IGNORE INTO sessions(id,state,created) VALUES(?,'open',?)",
                                (sid, time.time()),
                            )
                            known.add(sid)
                        state = db.execute("SELECT state FROM sessions WHERE id=?", (sid,)).fetchone()[0]
                        if state == "sealed":
                            # Final receipts cannot be amended after server acknowledgement.
                            if command not in ("end", "audio_end", "video_end", "begin"):
                                self.notify("Sync needs attention: capture arrived after session closure.")
                            continue
                        if command == "begin" and args:
                            # Cache the fixed, scoped snapshot once, outside capture/UI work.
                            data = json.dumps(
                                {"context": args[0]["context"], "snapshot": args[0].get("snapshot", {})},
                                ensure_ascii=False,
                            ).encode()
                            if len(data) > 131072:
                                raise ValueError("conversation snapshot too large")
                            path = self.root / (str(UUID(sid)) + ".context")
                            temporary = path.with_suffix(".context.part")
                            for candidate in (path, temporary):
                                try:
                                    no_link(candidate)
                                except FileNotFoundError:
                                    pass
                            if path.exists():
                                if path.stat().st_size > 131072 or path.read_bytes() != data:
                                    raise ValueError("conversation snapshot changed")
                                db.execute("UPDATE sessions SET context_size=? WHERE id=?", (len(data), sid))
                                continue
                            reserved = db.execute(
                                "SELECT context_size FROM sessions WHERE id=?", (sid,)
                            ).fetchone()[0]
                            capacity(sid, max(0, len(data) - reserved))
                            # Reserve space before writing, including interrupted partial files.
                            db.execute("UPDATE sessions SET context_size=? WHERE id=?", (len(data), sid))
                            # Admission must survive a crash before the snapshot is replaced.
                            db.commit()
                            with temporary.open("wb") as output:
                                output.write(data)
                                output.flush()
                                os.fsync(output.fileno())
                            durable_replace(temporary, path)
                            db.execute("UPDATE sessions SET context_size=? WHERE id=?", (len(data), sid))
                        elif command == "incomplete":
                            db.execute("UPDATE sessions SET incomplete=1 WHERE id=?", (sid,))
                        elif command == "audio_start":
                            capturing.add((sid, args[0]))
                        elif command == "audio":
                            stream, pcm, rate, kind = args
                            if not pcm:
                                continue
                            identity = (sid, stream)
                            if identity not in streams:
                                capacity(sid, 5 * rate * 2 + FRAME_LIMIT + 44)
                                item = str(uuid4())
                                path = self.root / (item + ".wav")
                                partial = path.with_suffix(".part")
                                db.execute(
                                    "INSERT INTO items(id,session,kind,path,sequence,size) VALUES(?,?,?,?,?,?)",
                                    (
                                        item,
                                        sid,
                                        kind,
                                        str(path),
                                        db.execute(
                                            "SELECT count(*) FROM items WHERE session=?", (sid,)
                                        ).fetchone()[0],
                                        5 * rate * 2 + FRAME_LIMIT + 44,
                                    ),
                                )
                                db.commit()
                                raw = partial.open("xb")
                                audio = wave.open(raw, "wb")
                                audio.setparams((1, 2, rate, 0, "NONE", "not compressed"))
                                streams[identity] = [item, audio, partial, path, 0, 0, raw]
                            entry = streams[identity]
                            entry[1].writeframesraw(pcm)
                            entry[4] += len(pcm)
                            if entry[4] - entry[5] >= rate * 2:
                                entry[6].flush()
                                os.fsync(entry[6].fileno())
                                entry[5] = entry[4]
                            if entry[4] >= 5 * rate * 2:
                                finish_stream(identity)
                        elif command == "audio_end":
                            finish_stream((sid, args[0]))
                            capturing.discard((sid, args[0]))
                        elif command in ("turn", "video"):
                            item = str(uuid4())
                            external = command == "video"
                            if external:
                                path = Path(args[0]).resolve()
                                if (
                                    not path.is_relative_to(self.settings.video_recording_dir.resolve())
                                    or path.suffix != ".mkv"
                                ):
                                    raise ValueError("invalid recording path")
                                for parent in (path, *path.parents):
                                    no_link(parent)
                                capacity(sid, path.stat().st_size)
                                if path.stat().st_size > CHUNK * 1024:
                                    raise ValueError("video segment too large")
                                # Camera events can be retried without creating duplicate recordings.
                                if db.execute("SELECT 1 FROM items WHERE path=?", (str(path),)).fetchone():
                                    continue
                            else:
                                path = self.root / (item + ".json")
                                data = json.dumps(args[0], ensure_ascii=False).encode()
                                if len(data) > 131072:
                                    raise ValueError("turn too large")
                                capacity(sid, len(data))
                                db.execute(
                                    "INSERT INTO items(id,session,kind,path,sequence,size) VALUES(?,?,'turn',?,?,?)",
                                    (
                                        item,
                                        sid,
                                        str(path),
                                        db.execute(
                                            "SELECT count(*) FROM items WHERE session=?", (sid,)
                                        ).fetchone()[0],
                                        len(data),
                                    ),
                                )
                                db.commit()
                                with path.with_suffix(".part").open("wb") as output:
                                    output.write(data)
                                    output.flush()
                                    os.fsync(output.fileno())
                                durable_replace(path.with_suffix(".part"), path)
                            size = path.stat().st_size
                            db.execute(
                                "INSERT INTO items(id,session,kind,path,sequence,size,ready,external) VALUES(?,?,?,?,?,?,1,?) ON CONFLICT(id) DO UPDATE SET ready=1,size=excluded.size",
                                (
                                    item,
                                    sid,
                                    "video" if external else "turn",
                                    str(path),
                                    db.execute(
                                        "SELECT count(*) FROM items WHERE session=?", (sid,)
                                    ).fetchone()[0],
                                    size,
                                    int(external),
                                ),
                            )
                            if command == "turn":
                                db.commit()
                                if len(args) > 1:
                                    args[1].saved = True
                                self.notify("Result saved on this device; server sync is pending.")
                        elif command == "video_start":
                            videos.add(sid)
                        elif command == "video_end":
                            videos.discard(sid)
                            if args[0]:
                                self.failed.add(sid)
                        elif command == "end":
                            db.execute(
                                "UPDATE sessions SET state='closing',outcome=? WHERE id=? AND state='open'",
                                (args[0], sid),
                            )
                            closing[sid] = time.monotonic() + 30
                    except Exception:
                        with self.guard:
                            self.failed.add(sid)
                            if command == "begin" and self.current == sid:
                                self.current = None
                        self.notify(
                            "Sync needs attention: a recording could not be saved. Practice continues."
                        )
                    finally:
                        if command == "turn" and len(args) > 1:
                            args[1].finished.set()
                        with self.guard:
                            self.pending_bytes -= weight
                        self.queue.task_done()
                with self.guard:
                    failed, busy = set(self.failed), self.active_work
                for identity in failed - reported_failures:
                    db.execute("UPDATE sessions SET incomplete=1 WHERE id=?", (identity,))
                reported_failures |= failed
                if not self.drain and (
                    bool(busy) != last_busy or (busy and time.monotonic() - last_control >= 3)
                ):
                    db.execute(
                        "UPDATE control SET busy_until=? WHERE id=1", (time.time() + 10 if busy else 0,)
                    )
                    last_control, last_busy = time.monotonic(), bool(busy)
                if self.queue.empty():
                    for sid, deadline in list(closing.items()):
                        unfinished = sid in videos or any(identity[0] == sid for identity in capturing)
                        if unfinished and time.monotonic() < deadline:
                            continue
                        if unfinished:
                            db.execute("UPDATE sessions SET incomplete=1 WHERE id=?", (sid,))
                            for identity in list(streams):
                                if identity[0] == sid:
                                    finish_stream(identity)
                                    capturing.discard(identity)
                        row = db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
                        ids = [
                            r[0]
                            for r in db.execute("SELECT id FROM items WHERE session=? ORDER BY id", (sid,))
                        ]
                        manifest = json.dumps(
                            {"items": ids, "incomplete": bool(row["incomplete"]), "outcome": row["outcome"]}
                        )
                        db.execute(
                            "UPDATE sessions SET state='sealed',manifest=? WHERE id=? AND manifest IS NULL",
                            (manifest, sid),
                        )
                        del closing[sid]
                db.commit()
                if self.drain:
                    break
        except Exception:
            self.disk_ok = False
            self.notify("Session sync unavailable: local journal could not be opened.")
        finally:
            self.ready.set()
            for entry in streams.values():
                try:
                    entry[1].close()
                    entry[6].flush()
                    os.fsync(entry[6].fileno())
                    entry[6].close()
                except Exception:
                    pass
            if db:
                db.close()
            if owner:
                owner.close()

    def _upload(self):
        while not self.stop.is_set():
            if not self._upload_once():
                return
            self.stop.wait(1)

    def _upload_once(self):
        lower_thread_priority()
        self.ready.wait()
        if not self.disk_ok:
            return False
        owner = None
        db = None
        try:
            while not self.stop.is_set():
                try:
                    owner = FileLock(self.root / "uploader.lock")
                    break
                except OSError:
                    self.stop.wait(2)
            if not owner:
                return
            with (
                database(self.root) as db,
                httpx.Client(
                    base_url=self.settings.pms_url,
                    headers={"Authorization": "Bearer " + self.settings.pms_token.get_secret_value()},
                    timeout=8,
                    trust_env=False,
                    transport=self.transport,
                ) as client,
            ):
                uploader_loop(
                    db,
                    client,
                    self.settings,
                    self.stop,
                    self.notify,
                    drain=self.drain,
                    busy=lambda: bool(self.active_work),
                )
        except Exception:
            self.notify("Sync paused: pending recordings remain on this device.")
            return True
        finally:
            if db:
                db.close()
            if owner:
                owner.close()
        return False

    async def close(self):
        if self.current:
            self.end(outcome="interrupted")
        # Hosts finalize cameras first. Retain a bounded wait for callers that
        # still have an outstanding recorder.
        deadline = time.monotonic() + 2
        while self.video_pending and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        self.stop.set()
        await asyncio.to_thread(self.disk.join, CLOSE_FLUSH_SECONDS)
        await asyncio.to_thread(self.upload.join, 0.1)
        if self.disk.is_alive():
            self.notify("Sync flush incomplete: keep the device running until local saving finishes.")
            raise RuntimeError("Session archive disk writer did not finish during shutdown")
        if self.disk_ok and self.transport is None and self.settings.session_sync_background:
            # Credentials travel once through an anonymous pipe, never arguments or disk.
            await asyncio.to_thread(self._background)

    def _background(self):
        values = self.settings.model_dump(mode="json")
        values["pms_token"] = self.settings.pms_token.get_secret_value()
        values["local_models_key"] = ""
        process = subprocess.Popen(
            [sys.executable, "-m", "training_client.session_sync"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
        try:
            process.stdin.write(json.dumps(values).encode())
        finally:
            process.stdin.close()


def uploader_loop(db, client, settings, stop, notify, *, drain=False, busy=lambda: False):
    def paused():
        return (
            stop.is_set()
            or busy()
            or max(db.execute("SELECT busy_until,auth_until FROM control WHERE id=1").fetchone())
            > time.time()
        )

    def schedule(table, identity, terminal=None, *, pending=False):
        attempts = db.execute(f"SELECT attempts FROM {table} WHERE id=?", (identity,)).fetchone()[0]
        delay = 2 if pending else min(60, 2 ** min(attempts, 6))
        db.execute(
            f"UPDATE {table} SET retry_at=?,attempts=? WHERE id=?",
            (time.time() + delay, attempts if pending else attempts + 1, identity),
        )
        if terminal:
            if table == "items":
                db.execute("UPDATE items SET error=? WHERE id=?", (terminal, identity))
            else:
                db.execute("UPDATE sessions SET acknowledged=-1,error=? WHERE id=?", (terminal, identity))
        db.commit()

    def failed(table, identity, error):
        terminal = None
        if isinstance(error, httpx.HTTPStatusError):
            status = error.response.status_code
            if status in (400, 403, 404, 409, 410, 413, 415, 422):
                terminal = str(status)
            if status in (401, 403):
                notify("Sync needs renewed device access. Pending recordings remain on this device.")
                if status == 401:
                    db.execute("UPDATE control SET auth_until=? WHERE id=1", (time.time() + 60,))
            elif status == 410:
                notify("Recording retention/upload deadline passed. The local copy is retained for review.")
            else:
                notify("Sync needs attention. Pending recordings are retained locally.")
        elif isinstance(error, (FileNotFoundError, PermissionError)):
            terminal = "file_unavailable"
            notify("Sync needs attention: a local recording is unavailable.")
        else:
            notify("Sync pending: recordings will retry when the server is available.")
        schedule(table, identity, terminal)

    launched = idle = time.monotonic()
    while not stop.is_set():
        if drain and time.monotonic() - launched > 7 * 86400:
            return
        if paused():
            stop.wait(0.5)
            continue
        item = db.execute(
            "SELECT * FROM items WHERE ready=1 AND uploaded=0 AND error IS NULL AND retry_at<=? ORDER BY CASE WHEN kind='turn' THEN 0 ELSE 1 END, retry_at, rowid LIMIT 1",
            (time.time(),),
        ).fetchone()
        session = db.execute(
            "SELECT * FROM sessions WHERE state='sealed' AND acknowledged=0 AND retry_at<=? ORDER BY retry_at,created LIMIT 1",
            (time.time(),),
        ).fetchone()
        if not item and not session:
            pending = db.execute(
                "SELECT EXISTS(SELECT 1 FROM items WHERE uploaded=0 AND error IS NULL) OR EXISTS(SELECT 1 FROM sessions WHERE state='sealed' AND acknowledged=0)"
            ).fetchone()[0]
            if drain and not pending and time.monotonic() - idle > 30:
                return
            stop.wait(0.25)
            continue
        idle = time.monotonic()
        if item:
            try:
                path = Path(item["path"])
                no_link(path)
                metadata = json.loads(item["metadata"]) if item["metadata"] else None
                if not metadata or metadata.get("hashing"):
                    hashes = metadata["hashes"] if metadata else []
                    with path.open("rb") as source:
                        source.seek(len(hashes) * CHUNK)
                        while data := source.read(CHUNK):
                            if paused():
                                break
                            hashes.append(hashlib.sha256(data).hexdigest())
                            # Bound hash/disk throughput as well as network throughput.
                            stop.wait(len(data) / (8 * 1024 * 1024))
                    if paused():
                        db.execute(
                            "UPDATE items SET metadata=? WHERE id=?",
                            (json.dumps({"hashing": True, "hashes": hashes}), item["id"]),
                        )
                        db.commit()
                        continue
                    metadata = dict(
                        kind=item["kind"], byte_size=item["size"], hashes=hashes, sequence=item["sequence"]
                    )
                    db.execute("UPDATE items SET metadata=? WHERE id=?", (json.dumps(metadata), item["id"]))
                    db.commit()
                base = f"/api/v1/device/session-archives/{item['session']}/items/{item['id']}"
                if paused():
                    continue
                response = client.put(base, json=metadata)
                response.raise_for_status()
                received = response.json()["received"]
                if (
                    not isinstance(received, list)
                    or any(
                        type(index) is not int or not 0 <= index < len(metadata["hashes"])
                        for index in received
                    )
                    or len(set(received)) != len(received)
                ):
                    raise ValueError("invalid received chunks")
                with path.open("rb") as source:
                    for index, digest in enumerate(metadata["hashes"]):
                        if paused():
                            break
                        if index in received:
                            continue
                        source.seek(index * CHUNK)
                        data = source.read(CHUNK)
                        began = time.monotonic()
                        reply = client.put(base + f"/chunks/{index}", content=data)
                        reply.raise_for_status()
                        ack = reply.json()
                        if ack.get("index") != index or ack.get("sha256") != digest:
                            raise ValueError("invalid acknowledgement")
                        received.append(index)
                        stop.wait(
                            max(
                                0,
                                len(data) / settings.session_sync_bytes_per_second
                                - (time.monotonic() - began),
                            )
                        )
                if set(received) == set(range(len(metadata["hashes"]))):
                    db.execute("UPDATE items SET uploaded=1 WHERE id=?", (item["id"],))
                    db.commit()
                    if not item["external"]:
                        path.unlink(missing_ok=True)
                    notify("Session recordings saved to server.")
            except (httpx.HTTPError, OSError, ValueError, KeyError) as error:
                failed("items", item["id"], error)
        # A failed item must not prevent final manifests or unrelated sessions from progressing.
        if session and not paused():
            try:
                response = client.put(
                    f"/api/v1/device/session-archives/{session['id']}/manifest",
                    json=json.loads(session["manifest"]),
                )
                response.raise_for_status()
                body = response.json()
                transfer_complete = body.get("transfer_status") == "synced"
                if "transfer_status" not in body:
                    # Compatible old servers conflate missing capture with pending transfer.
                    transfer_complete = body["sync_status"] == "synced" or (
                        body["sync_status"] == "incomplete"
                        and not db.execute(
                            "SELECT 1 FROM items WHERE session=? AND uploaded=0", (session["id"],)
                        ).fetchone()
                    )
                if transfer_complete:
                    db.execute("UPDATE sessions SET acknowledged=1 WHERE id=?", (session["id"],))
                    db.commit()
                    notify(
                        "Session fully synced."
                        if body["sync_status"] == "synced"
                        else "Session saved with missing recording data. Review sync status."
                    )
                else:
                    schedule("sessions", session["id"], pending=True)
            except (httpx.HTTPError, OSError, ValueError, KeyError) as error:
                failed("sessions", session["id"], error)
        stop.wait(0.25)


def main():
    from .config import Settings

    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        return
    settings = Settings(_env_file=None, **json.loads(raw))
    # The GUI has a bounded flush interval; do not compete with its final writes.
    time.sleep(3)
    sync = SessionSync(settings, lambda *_: None, drain=True)
    sync.disk.join()
    sync.upload.join()


if __name__ == "__main__":
    main()
