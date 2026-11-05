"""Generic desktop ownership lock; no model files or lifecycle operations."""

import os

from training_contracts.privacy import no_link


class FileLock:
    def __init__(self, path, busy_message, timeout=0):
        self.path, self.busy_message = path, busy_message
        self.stream = None

    def __enter__(self):
        if self.path.exists():
            no_link(self.path)
        self.stream = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                if self.path.stat().st_size == 0:
                    self.stream.write(b"0")
                    self.stream.flush()
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            self.stream = None
            raise RuntimeError(self.busy_message) from None
        return self

    def __exit__(self, *_):
        if self.stream:
            self.stream.close()
            self.stream = None
