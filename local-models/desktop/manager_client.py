"""Local transport and Tk-safe asynchronous requests. No automatic mutation replay."""

import concurrent.futures
import os
import queue
import re
import subprocess
import sys
import time
import uuid

from service.errors import ManagerError
from service.protocol import call
from service.security import LOCAL_ROOT, checked, environment, hidden_flags


class Client:
    def __init__(self, root=LOCAL_ROOT / ".manager", port=8790):
        self.root, self.port = checked(root), port
        self.launched = None

    def key(self):
        path = checked(self.root / "operator-key.txt", self.root)
        try:
            if path.stat().st_size > 256:
                raise ManagerError("credentials", "Invalid local manager credentials", 403)
            key = path.read_text(encoding="ascii").strip()
        except PermissionError:
            raise ManagerError(
                "permissions", "Local manager state is not accessible to this operator", 403
            ) from None
        except OSError:
            raise ManagerError("unavailable", "Local manager is not available", 503) from None
        if not re.fullmatch(r"[A-Za-z0-9_-]{48,128}", key):
            raise ManagerError("credentials", "Invalid local manager credentials", 403)
        return key

    def request(self, method, path, payload=None, timeout=8):
        return call(self.port, self.key(), method, path, payload, timeout=timeout)

    def connect(self):
        try:
            return self.request("GET", "/v1/status", timeout=1)
        except ManagerError as error:
            if error.code != "unavailable":
                raise
        flags = hidden_flags()
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        self.launched = subprocess.Popen(
            [
                sys.executable,
                str(LOCAL_ROOT / "service/daemon.py"),
                "--root",
                str(self.root),
                "--port",
                str(self.port),
            ],
            cwd=LOCAL_ROOT,
            env=environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            start_new_session=os.name != "nt",
        )
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            try:
                return self.request("GET", "/v1/status", timeout=min(1, deadline - time.monotonic()))
            except ManagerError as error:
                if error.code != "unavailable":
                    raise
            time.sleep(0.1)
        raise ManagerError(
            "unavailable", "Manager could not start; inspect port 8790 and local state permissions", 503
        )


class Controller:
    def __init__(self, root, on_snapshot, on_message, client=None, on_disconnect=None):
        self.root, self.on_snapshot, self.on_message = root, on_snapshot, on_message
        self.client = client or Client()
        self.on_disconnect = on_disconnect or on_message
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.results = queue.Queue()
        self.closed = False
        self.polling = False
        self.connecting = True
        self.pending = {}
        self._job(self.client.connect, "connect")
        self.timer = root.after(100, self._drain)
        self.poll_timer = root.after(2000, self._poll)

    def _poll(self):
        if not self.closed:
            self.refresh()
            self.poll_timer = self.root.after(2000, self._poll)

    def _job(self, function, kind):
        def run():
            try:
                self.results.put((kind, function(), None))
            except Exception as error:
                message = (
                    error.message
                    if isinstance(error, ManagerError)
                    else "Unable to complete the local manager request"
                )
                self.results.put((kind, None, message))

        if not self.closed:
            self.executor.submit(run)

    def refresh(self):
        if not self.closed and not self.polling and not self.connecting:
            self.polling = True
            self._job(lambda: self.client.request("GET", "/v1/status"), "snapshot")

    def reconnect(self):
        if not self.closed and not self.connecting:
            self.connecting = True
            self._job(self.client.connect, "connect")

    def action(self, action, payload):
        identifier = str(uuid.uuid4())
        request = {**payload, "request_id": identifier}
        self.pending[identifier] = action
        self._job(lambda: self.client.request("POST", "/v1/actions/" + action, request), identifier)
        self.on_message("Submitting " + action + "…")
        return identifier

    def _drain(self):
        if self.closed:
            return
        while True:
            try:
                kind, result, error = self.results.get_nowait()
            except queue.Empty:
                break
            if kind in {"snapshot", "connect"}:
                if kind == "connect":
                    self.connecting = False
                else:
                    self.polling = False
                if error:
                    self.on_disconnect(error)
                else:
                    self.on_snapshot(result)
                    if result.get("metadata_error"):
                        self.on_message(result["metadata_error"])
                        continue
                    for op in result["operations"]:
                        if op["state"] in {"queued", "running"}:
                            self.pending[op["id"]] = op["action"]
                        if op["id"] in self.pending:
                            if op["state"] in {"succeeded", "failed", "interrupted"}:
                                self.pending.pop(op["id"])
                                self.on_message(op.get("error", op["action"] + " complete"))
                            else:
                                total = op.get("bytes_total", 0)
                                percent = f" {100 * op.get('bytes_done', 0) // total}%" if total else ""
                                self.on_message(op["action"] + ": " + op["phase"] + percent)
            elif error and not kind.endswith(":inspect"):
                # The original UUID remains visible; inspect it without replaying the POST.
                self.on_message(error + " · Request " + kind)
                self._job(
                    lambda identifier=kind: self.client.request("GET", "/v1/operations/" + identifier),
                    kind + ":inspect",
                )
            elif error:
                self.pending.pop(kind.removesuffix(":inspect"), None)
                self.on_message(error + " · Inspect status before submitting another action.")
            elif kind.endswith(":inspect"):
                if result["state"] in {"failed", "interrupted", "succeeded"}:
                    self.pending.pop(result["id"], None)
                    self.on_message(result.get("error", result["action"] + " complete"))
            if kind not in {"snapshot", "connect"}:
                self.refresh()
        self.timer = self.root.after(100, self._drain)

    def close(self):
        self.closed = True
        self.root.after_cancel(self.timer)
        self.root.after_cancel(self.poll_timer)
        self.executor.shutdown(wait=False, cancel_futures=True)
        # Deliberately leave manager and workers running.
