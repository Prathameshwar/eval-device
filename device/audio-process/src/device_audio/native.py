"""A bounded serial daemon worker for native calls that cannot be interrupted."""

import asyncio
import queue
import threading
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any


class SerialWorker:
    def __init__(self, name: str):
        self.jobs: queue.Queue[tuple[Callable[[], Any], Future[Any]]] = queue.Queue(1)
        self.stopping = threading.Event()
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._run, name=name, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        try:
            while not self.stopping.is_set():
                try:
                    function, future = self.jobs.get(timeout=0.05)
                except queue.Empty:
                    continue
                try:
                    if future.set_running_or_notify_cancel():
                        try:
                            future.set_result(function())
                        except BaseException as exc:
                            future.set_exception(exc)
                finally:
                    self.jobs.task_done()
                    del function, future
        finally:
            while not self.jobs.empty():
                _, future = self.jobs.get_nowait()
                future.cancel()
                self.jobs.task_done()
            self.closed.set()

    async def call(self, function: Callable[[], Any]) -> Any:
        if self.stopping.is_set():
            raise RuntimeError("native worker stopped")
        future: Future[Any] = Future()
        self.jobs.put_nowait((function, future))
        return await asyncio.wrap_future(future)

    def stop(self) -> None:
        # Never join a stuck native call. The runtime is retired and cannot restart
        # it or invoke a second model concurrently; process exit releases the thread.
        self.stopping.set()
