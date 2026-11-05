"""Foreground manager usable from the desktop launcher or an OS service supervisor."""

import argparse
import os
import signal
import sys
import threading
from pathlib import Path
from uuid import uuid4

LOCAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL))

from service.http_server import JsonServer  # noqa: E402
from service.manager import Manager  # noqa: E402
from service.security import checked, identity, protect  # noqa: E402
from service.storage import Store  # noqa: E402


class InstanceLock:
    def __init__(self, root):
        self.root = checked(root)
        self.root.mkdir(parents=True, exist_ok=True)
        protect(self.root, identity())
        path = checked(self.root / "daemon.lock", self.root)
        try:
            self.stream = path.open("x+b")
            self.stream.write(b"1")
            self.stream.flush()
        except FileExistsError:
            self.stream = path.open("r+b")
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise RuntimeError("Manager is already running") from None

    def close(self):
        self.stream.close()


def watch_startup(manager, operations, failed, stop):
    """Expose asynchronous boot failures to the OS supervisor without replaying inference."""
    pending = {operation["id"] for operation in operations}
    while pending and not manager.closed.is_set():
        for identifier in tuple(pending):
            operation = manager.store.operation(identifier)
            if not operation or operation["state"] == "failed":
                failed.set()
                stop()
                return
            if operation["state"] == "succeeded":
                pending.remove(identifier)
        if pending:
            manager.closed.wait(0.2)


def serve(root=LOCAL / ".manager", port=8790, start_selected=()):
    lock = InstanceLock(root)
    manager = server = None
    try:
        store = Store(root)
        manager = Manager(store)
        server = JsonServer(("127.0.0.1", port), store.key, manager.dispatch, client_key=store.client_key)
        manager.port = server.server_port
        manager.shutdown = server.shutdown
        # Explicit boot provisioning only; never download or change models at startup.
        operations = []
        for capability in dict.fromkeys(start_selected):
            operations.append(
                manager.submit(
                    "start",
                    {
                        "request_id": str(uuid4()),
                        "capability": capability,
                        "revision": store.snapshot()["revision"],
                    },
                )
            )

        def stop(*_):
            threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        startup_failed = threading.Event()
        if operations:
            threading.Thread(
                target=watch_startup,
                args=(manager, operations, startup_failed, server.shutdown),
                name="model-startup",
                daemon=True,
            ).start()
        server.serve_forever(poll_interval=0.2)
        if startup_failed.is_set():
            raise RuntimeError("Selected model startup failed; inspect manager operation status")
    finally:
        if server:
            server.server_close()
        if manager:
            manager.close()
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=LOCAL / ".manager")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--start-selected", nargs="*", choices=("llm", "asr", "tts"), default=[])
    args = parser.parse_args()
    serve(args.root, args.port, args.start_selected)


if __name__ == "__main__":
    main()
