"""Bounded retries for idempotent local I/O, never replaying an append blindly."""

import errno
import io
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")
TRANSIENT_ERRNOS = {errno.EINTR, errno.EAGAIN, errno.EBUSY, errno.ETIMEDOUT, errno.EIO}
TRANSIENT_WINDOWS = {32, 33, 121, 170, 1117, 1237}


def transient_io(exc: OSError) -> bool:
    return exc.errno in TRANSIENT_ERRNOS or getattr(exc, "winerror", None) in TRANSIENT_WINDOWS


class DiskRetries:
    def __init__(self, attempts: int, delay: float):
        self.attempts = attempts
        self.delay = delay
        self.retries = 0
        self.exhausted = 0

    def run(self, operation: Callable[[], T]) -> T:
        for attempt in range(self.attempts):
            try:
                return operation()
            except OSError as exc:
                if not transient_io(exc):
                    raise
                if attempt + 1 == self.attempts:
                    self.exhausted += 1
                    raise
                self.retries += 1
                # This runs only in the dedicated disk thread.
                time.sleep(self.delay * 2**attempt * random.uniform(0.8, 1.2))
        raise AssertionError("invalid retry attempts")


class RetryingFile(io.FileIO):
    """A buffered writer's raw layer. Retry at a fixed offset, even after a partial write."""

    def __init__(self, path: Path, policy: DiskRetries):
        super().__init__(path, "xb")
        self.policy = policy
        self.failed = False

    def _write_once(self, data: memoryview) -> int | None:
        return super().write(data)

    def write(self, data: Any) -> int:
        if self.failed:
            raise OSError(errno.EBADF, "recording file stopped after a failed write")
        view = memoryview(data).cast("B")
        offset = self.tell()

        def overwrite() -> int:
            self.seek(offset)
            written = 0
            while written < len(view):
                count = self._write_once(view[written:])
                if count is None or count <= 0:
                    raise OSError(errno.EIO, "recording write made no progress")
                written += count
            return written

        try:
            return self.policy.run(overwrite)
        except BaseException:
            # A later flush/close must not append the retained buffer after an uncertain prefix.
            self.failed = True
            raise
