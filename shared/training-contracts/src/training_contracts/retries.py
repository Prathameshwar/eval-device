"""Bounded retries for idempotent local I/O, never replaying an append blindly."""

import errno
import random
import time
from collections.abc import Callable
from typing import TypeVar

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
