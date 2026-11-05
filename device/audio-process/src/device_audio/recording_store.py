"""Private, quota-limited recording files. Called only by the dedicated disk thread."""

import csv
import io
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import time
import wave
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, BinaryIO
from uuid import UUID

from .config import Settings
from .retries import DiskRetries, RetryingFile

FORMAT = "device-audio-recording-v1"
RESERVE = 16384  # Covers the manifest, its atomic replacement, and file headers.
FILES = {"audio.wav", "transcript.jsonl", "session.json", "session.json.tmp"}


def completion_fallback(audio_complete: bool, transcript_complete: bool) -> str:
    return {
        (True, True): "none",
        (False, True): "transcript_only",
        (True, False): "audio_only",
        (False, False): "stream_only",
    }[(audio_complete, transcript_complete)]


class StorageError(Exception):
    pass


def no_link(path: Path) -> None:
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
        or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)
    ):
        raise StorageError("unsafe_path")


def private_directory(path: Path) -> None:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        identity = subprocess.check_output(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=5,
        )
        sid = next(csv.reader([identity.strip()]))[1]
        if not re.fullmatch(r"S-\d+(?:-\d+)+", sid):
            raise StorageError("permissions")
        api = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        pointer = ctypes.c_void_p
        api.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(pointer),
            ctypes.POINTER(wintypes.ULONG),
        ]
        api.GetSecurityDescriptorDacl.argtypes = [
            pointer,
            ctypes.POINTER(wintypes.BOOL),
            ctypes.POINTER(pointer),
            ctypes.POINTER(wintypes.BOOL),
        ]
        api.SetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR,
            ctypes.c_int,
            wintypes.DWORD,
            pointer,
            pointer,
            pointer,
            pointer,
        ]
        api.SetNamedSecurityInfoW.restype = wintypes.DWORD
        kernel.LocalFree.argtypes = [pointer]
        kernel.LocalFree.restype = pointer
        descriptor = pointer()
        if not api.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            f"D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)", 1, ctypes.byref(descriptor), None
        ):
            raise StorageError("permissions")
        try:
            present, defaulted = wintypes.BOOL(), wintypes.BOOL()
            dacl = pointer()
            if (
                not api.GetSecurityDescriptorDacl(
                    descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)
                )
                or not present.value
            ):
                raise StorageError("permissions")
            # Replace the entire DACL: remove inherited AND explicit grants to other users.
            if api.SetNamedSecurityInfoW(str(path), 1, 0x80000004, None, None, dacl, None):
                raise StorageError("permissions")
        finally:
            kernel.LocalFree(descriptor)
    else:
        path.chmod(0o600 if path.is_file() else 0o700)


@dataclass
class OpenFiles:
    audio: BinaryIO
    wav: wave.Wave_write
    text: BinaryIO


class RecordingStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.recording_dir.absolute()
        self.records: dict[str, dict[str, Any]] = {}
        self.open_files: dict[str, OpenFiles] = {}
        self.lock: BinaryIO | None = None
        self.used = 0
        self.charges: dict[str, int] = {}
        self.retry = DiskRetries(settings.recording_retry_attempts, settings.recording_retry_delay_seconds)

    def initialize(self) -> list[dict[str, Any]]:
        # Refuse reparse points, including a redirected parent of the configured directory.
        for parent in (*reversed(self.root.parents), self.root):
            if parent.exists() or parent.is_symlink():
                no_link(parent)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        no_link(self.root)
        marker = self.root / ".store.json"
        if not marker.exists() and any(self.root.iterdir()):
            raise StorageError("unmanaged_directory")
        private_directory(self.root)
        lock_path = self.root / ".writer.lock"
        if lock_path.exists():
            no_link(lock_path)
        self.lock = lock_path.open("a+b")
        self.lock.seek(0)
        if sys.platform == "win32":
            import msvcrt

            if not lock_path.stat().st_size:
                self.lock.write(b"\0")
                self.lock.flush()
            self.lock.seek(0)
            msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if marker.exists():
            no_link(marker)
            if marker.stat().st_size > 128 or json.loads(marker.read_text()) != {"format": FORMAT}:
                raise StorageError("unmanaged_directory")
        else:
            marker.write_text(json.dumps({"format": FORMAT}), encoding="utf-8")
        for directory in self.root.iterdir():
            if directory.name in {".store.json", ".writer.lock"}:
                continue
            self._directory(directory.name)
            manifest = directory / "session.json"
            self._check_files(directory)
            if not manifest.exists():
                # Before the first manifest commits, no media files can be created.
                initial_files = list(directory.iterdir())
                if any(
                    p.name != "session.json.tmp" or p.stat().st_size > RESERVE // 2 for p in initial_files
                ):
                    raise StorageError("unmanaged_directory")
                for path in initial_files:
                    path.unlink()
                directory.rmdir()
                continue
            if manifest.stat().st_size > RESERVE // 2:
                raise StorageError("invalid_manifest")
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if (
                data.get("format") != FORMAT
                or data.get("id") != directory.name
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(data.get("client_id", "")))
                or not isinstance(data.get("created_at"), (int, float))
                or not 0 < data["created_at"] < 1e12
            ):
                raise StorageError("invalid_manifest")
            audio_path, text_path = directory / "audio.wav", directory / "transcript.jsonl"
            audio_valid = (
                audio_path.exists() and audio_path.stat().st_size == data.get("audio_bytes", -1) + 44
            )
            text_valid = text_path.exists() and text_path.stat().st_size == data.get("transcript_bytes", -1)
            valid_saved = audio_valid and text_valid
            # A process interrupted before finalization never leaves a falsely complete receipt.
            if data.get("status") != "saved" or not valid_saved:
                reason = data.get("reason")
                if data.get("status") == "saved":
                    reason = "integrity_mismatch"
                elif reason in (None, "unfinalized"):
                    reason = "interrupted"
                audio_complete = (
                    bool(data.get("audio_complete", data.get("status") == "saved")) and audio_valid
                )
                text_complete = (
                    bool(data.get("transcript_complete", data.get("status") == "saved")) and text_valid
                )
                data.update(
                    status="incomplete",
                    finalized=True,
                    reason=reason,
                    audio_complete=audio_complete,
                    transcript_complete=text_complete,
                    fallback=completion_fallback(audio_complete, text_complete),
                )
                self._repair_audio(directory)
                data["transcripts"] = self._trim_text(directory)
                data["audio_bytes"] = (
                    max(0, (directory / "audio.wav").stat().st_size - 44)
                    if (directory / "audio.wav").exists()
                    else 0
                )
                data["transcript_bytes"] = (
                    (directory / "transcript.jsonl").stat().st_size
                    if (directory / "transcript.jsonl").exists()
                    else 0
                )
                self._manifest(directory, data)
            self.records[directory.name] = data
        self._recount()
        self.prune()
        return list(self.records.values())

    def _directory(self, recording_id: str) -> Path:
        if str(UUID(recording_id)) != recording_id:
            raise StorageError("unsafe_path")
        no_link(self.root)
        directory = self.root / recording_id
        if directory.exists() or directory.is_symlink():
            no_link(directory)
            if not directory.is_dir():
                raise StorageError("unsafe_path")
        return directory

    def _check_files(self, directory: Path) -> None:
        for path in directory.iterdir():
            if path.name not in FILES:
                raise StorageError("unmanaged_directory")
            no_link(path)
            if not path.is_file() or path.stat().st_nlink != 1:
                raise StorageError("unsafe_path")

    def _manifest(self, directory: Path, data: dict[str, Any]) -> None:
        self.retry.run(lambda: self._manifest_once(directory, data))

    def _manifest_once(self, directory: Path, data: dict[str, Any]) -> None:
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
        if len(encoded) > RESERVE // 2:
            raise StorageError("metadata_limit")
        self._check_files(directory)
        temporary = directory / "session.json.tmp"
        with temporary.open("wb") as target:
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        temporary.replace(directory / "session.json")

    def _size(self, recording_id: str) -> int:
        directory = self._directory(recording_id)
        self._check_files(directory)
        physical = sum(
            (directory / name).stat().st_size
            for name in ("audio.wav", "transcript.jsonl")
            if (directory / name).exists()
        )
        data = self.records.get(recording_id, {})
        buffered = data.get("audio_bytes", 0) + 44 + data.get("transcript_bytes", 0)
        return max(RESERVE + max(physical, buffered), self.charges.get(recording_id, 0))

    def _recount(self) -> None:
        self.used = sum(self._size(key) for key in self.records)

    def _remove(self, recording_id: str) -> None:
        directory = self._directory(recording_id)
        self._check_files(directory)
        # Only fixed, verified files in an owned session directory; never recursive deletion.
        for path in directory.iterdir():
            path.unlink()
        directory.rmdir()
        del self.records[recording_id]
        self.charges.pop(recording_id, None)

    def prune(self, extra: int = 0, new_record: bool = False) -> list[str]:
        removed = []
        cutoff = time.time() - self.settings.recording_retention_hours * 3600
        for key, data in sorted(self.records.items(), key=lambda item: item[1]["created_at"]):
            if key in self.open_files:
                continue
            if (
                data["created_at"] < cutoff
                or self.used + extra > self.settings.recording_max_bytes
                or len(self.records) + int(new_record) > self.settings.recording_max_sessions
            ):
                size = self._size(key)
                self._remove(key)
                self.used -= size
                removed.append(key)
        if self.used + extra > self.settings.recording_max_bytes:
            raise StorageError("storage_limit")
        if new_record and len(self.records) >= self.settings.recording_max_sessions:
            raise StorageError("storage_limit")
        return removed

    def _room(self, count: int) -> None:
        self.prune(extra=count)
        if shutil.disk_usage(self.root).free < self.settings.recording_min_free_bytes + count:
            raise StorageError("disk_space")

    def begin(self, data: dict[str, Any]) -> None:
        key = data["id"]
        self.prune(extra=RESERVE + 44, new_record=True)
        self._room(RESERVE + 44)
        directory = self._directory(key)
        directory.mkdir(mode=0o700)  # Exclusive server-generated name; never overwrite an old session.
        initial = {
            **data,
            "status": "incomplete",
            "reason": "unfinalized",
            "audio_bytes": 0,
            "transcript_bytes": 0,
            "transcripts": 0,
        }
        self.records[key] = initial
        self.used += RESERVE + 44
        self.charges[key] = RESERVE + 44
        self._manifest(directory, initial)
        audio = io.BufferedWriter(
            self.retry.run(lambda: RetryingFile(directory / "audio.wav", self.retry)), buffer_size=65536
        )
        text = None
        try:
            wav = wave.open(audio, "wb")
            wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            wav.writeframesraw(b"")
            text = io.BufferedWriter(
                self.retry.run(lambda: RetryingFile(directory / "transcript.jsonl", self.retry)),
                buffer_size=65536,
            )
            self.open_files[key] = OpenFiles(audio, wav, text)
        except BaseException:
            audio.close()
            if text:
                text.close()
            raise

    def audio(self, key: str, pcm: bytes) -> None:
        self._room(len(pcm))
        self.used += len(pcm)  # Reserve before I/O; a partial write must not bypass the cap.
        self.charges[key] += len(pcm)
        self.open_files[key].wav.writeframesraw(pcm)
        self.records[key]["audio_bytes"] += len(pcm)

    def transcript(self, key: str, event: dict[str, Any]) -> None:
        encoded = (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
        if len(encoded) > self.settings.max_text_chars * 12 + 65536:
            raise StorageError("text_limit")
        self._room(len(encoded))
        self.used += len(encoded)
        self.charges[key] += len(encoded)
        self.open_files[key].text.write(encoded)
        self.records[key]["transcript_bytes"] += len(encoded)
        self.records[key]["transcripts"] += 1

    def flush(self) -> dict[str, dict[str, str]]:
        errors: dict[str, dict[str, str]] = {}
        for key, files in list(self.open_files.items()):
            for component, actions in (
                ("audio", (partial(files.wav.writeframes, b""), files.audio.flush)),
                ("transcript", (files.text.flush,)),
            ):
                try:
                    for action in actions:
                        action()
                except Exception:
                    errors.setdefault(key, {})[component] = "write_failed"
        return errors

    def finish(self, key: str, receipt: dict[str, Any]) -> dict[str, Any]:
        data = self.records[key]
        files = self.open_files.pop(key, None)
        failed: set[str] = set()
        if files:
            for component, actions in (
                ("audio", (files.wav.close, files.audio.flush)),
                ("transcript", (files.text.flush,)),
            ):
                for action in actions:
                    try:
                        action()
                    except Exception:
                        failed.add(component)
            for component, target in (("audio", files.audio), ("transcript", files.text)):
                try:
                    self.retry.run(partial(os.fsync, target.fileno()))
                except Exception:
                    failed.add(component)
                finally:
                    try:
                        target.close()
                    except Exception:
                        failed.add(component)
        result = {
            **receipt,
            "finalized": True,
            "audio_bytes": data["audio_bytes"],
            "transcript_bytes": data["transcript_bytes"],
            "transcripts": data["transcripts"],
            "audio_complete": (
                receipt.get("audio_complete", True)
                and "audio" not in failed
                and receipt["received_audio_bytes"] == data["audio_bytes"]
            ),
            "transcript_complete": (
                receipt.get("transcript_complete", True)
                and "transcript" not in failed
                and receipt["received_transcripts"] == data["transcripts"]
            ),
        }
        if failed:
            result.update(status="incomplete", reason=receipt.get("reason") or "write_failed")
        elif not result["audio_complete"] or not result["transcript_complete"]:
            result.update(status="incomplete", reason=receipt.get("reason") or "missing_data")
        if result["status"] == "incomplete":
            result["fallback"] = completion_fallback(result["audio_complete"], result["transcript_complete"])
        self._manifest(self._directory(key), result)
        self.records[key] = result
        self.charges.pop(key, None)
        self._recount()
        return result

    def _repair_audio(self, directory: Path) -> None:
        path = directory / "audio.wav"
        if not path.exists() or path.stat().st_size < 44:
            return
        with path.open("r+b") as target:
            header = target.read(44)
            if header[:4] != b"RIFF" or header[8:16] != b"WAVEfmt " or header[36:40] != b"data":
                raise StorageError("invalid_audio_file")
            size = (path.stat().st_size - 44) // 2 * 2
            target.truncate(44 + size)
            target.seek(4)
            target.write(struct.pack("<I", size + 36))
            target.seek(40)
            target.write(struct.pack("<I", size))

    def _trim_text(self, directory: Path) -> int:
        path = directory / "transcript.jsonl"
        if not path.exists():
            return 0
        with path.open("r+b") as target:
            size = path.stat().st_size
            start = max(0, size - (self.settings.max_text_chars * 12 + 65536))
            target.seek(start)
            tail = target.read()
            if tail and not tail.endswith(b"\n"):
                last = tail.rfind(b"\n")
                target.truncate(start + last + 1 if last >= 0 else 0)
            target.seek(0)
            count = 0
            while block := target.read(65536):
                count += block.count(b"\n")
            return count

    def shutdown(self) -> None:
        for key in list(self.open_files):
            try:
                data = self.records[key]
                self.finish(
                    key,
                    {
                        **data,
                        "status": "incomplete",
                        "reason": "interrupted",
                        "received_audio_bytes": data["audio_bytes"],
                        "received_transcripts": data["transcripts"],
                    },
                )
            except Exception:
                pass
        if self.lock:
            self.lock.close()
            self.lock = None
