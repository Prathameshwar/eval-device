"""Owned worker lifecycle; inference and resource checks stay in the manager."""

import secrets
import socket
import subprocess
import sys
import threading
import time

from .errors import ManagerError, require
from .protocol import call
from .security import checked, environment, hidden_flags


class Lifecycle:
    def __init__(self, store, assets):
        self.store, self.assets = store, assets
        self.workers = {}
        self.lock = threading.RLock()
        self.start_lock = threading.Lock()

    def start(self, config, progress):
        identifier = config["capability"]
        with self.start_lock:
            if identifier in self.workers and self.workers[identifier]["process"].poll() is None:
                status = self.status(identifier)
                require(
                    status.get("ready") is True and status.get("state") == "Ready",
                    "not_ready",
                    "Existing worker is not ready; inspect status before starting again",
                    409,
                )
                require(
                    status.get("model_id") == config["model_id"]
                    and status.get("device") == ("cuda" if config["device"] == "gpu" else "cpu"),
                    "worker_mismatch",
                    "Existing worker does not match the saved configuration",
                    409,
                )
                return status
            self.assets.verify(config["model_id"])
            python = self.assets.runtime_python(identifier)
            with socket.socket() as probe:
                try:
                    probe.bind(("127.0.0.1", config["port"]))
                except OSError:
                    raise ManagerError(
                        "port_busy", "Worker port is occupied; the existing listener was preserved", 409
                    ) from None
            if config["device"] == "gpu":
                hardware = self.hardware()
                available = next(
                    (
                        g["free_mib"]
                        for g in hardware["gpus"]
                        if g["index"] == config["options"]["gpu_device_index"]
                    ),
                    0,
                )
                require(
                    available >= 512, "gpu_unavailable", "Selected GPU has insufficient available memory", 409
                )
            directory = checked(self.store.root / "workers" / identifier, self.store.root)
            directory.mkdir(parents=True, exist_ok=True)
            key = secrets.token_urlsafe(48)
            worker = {**config, "worker_key": key, "native_state": str(directory / "native")}
            path = directory / "config.json"
            self.store.atomic(path, worker)
            process = subprocess.Popen(
                [str(python), str(self.assets.root / "service/worker.py"), str(path)],
                cwd=self.assets.root,
                env=environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=hidden_flags(),
            )
            guard = None
            try:
                if sys.platform == "win32":
                    from .assets import load_script

                    guard = load_script(
                        self.assets.root / "scripts/process_guard.py", "manager_process_guard"
                    ).ProcessGuard(process)
            except BaseException:
                process.terminate()
                process.wait(timeout=10)
                raise
            entry = {"process": process, "guard": guard, "key": key, "port": config["port"]}
            with self.lock:
                self.workers[identifier] = entry
            try:
                progress(phase="Starting")
                deadline = time.monotonic() + config["options"]["startup_timeout_seconds"]
                while time.monotonic() < deadline:
                    require(
                        process.poll() is None,
                        "worker_exit",
                        "Worker exited during initialization; check model/runtime/resources",
                        409,
                    )
                    try:
                        status = call(entry["port"], key, "GET", "/v1/status", timeout=1)
                        if status["ready"] and status["model_id"] == config["model_id"]:
                            require(
                                status["device"] == ("cuda" if config["device"] == "gpu" else "cpu"),
                                "device_mismatch",
                                "Worker execution did not match the selected device",
                                409,
                            )
                            return status
                    except ManagerError as error:
                        if error.code not in {"unavailable", "timeout"}:
                            raise
                    time.sleep(0.1)
                raise ManagerError("startup_timeout", "Model startup exceeded its deadline", 409)
            except BaseException:
                self._release(identifier)
                raise

    def status(self, identifier):
        with self.lock:
            entry = self.workers.get(identifier)
        if entry is None:
            return {"state": "Stopped", "ready": False, "active": 0}
        if entry["process"].poll() is not None:
            self._release(identifier)
            return {"state": "Failed", "ready": False, "active": 0, "error": "Worker exited unexpectedly"}
        try:
            data = call(entry["port"], entry["key"], "GET", "/v1/status", timeout=1)
            if data.get("failed"):
                self._release(identifier)
                return {
                    "state": "Failed",
                    "ready": False,
                    "active": 0,
                    "error": "Native inference process exited",
                }
            return {
                **data,
                "state": "Failed"
                if data.get("failed")
                else "Stopping"
                if data["draining"]
                else "Ready"
                if data["ready"]
                else "Starting",
            }
        except ManagerError:
            return {"state": "Unavailable", "ready": False, "active": None}

    def stop(self, identifier, timeout, progress):
        with self.lock:
            entry = self.workers.get(identifier)
        if not entry or entry["process"].poll() is not None:
            self._release(identifier)
            return {"state": "Stopped"}
        progress(phase="Draining")
        try:
            data = call(entry["port"], entry["key"], "POST", "/v1/drain", {}, timeout=3)
            deadline = time.monotonic() + timeout
            while data["active"] and time.monotonic() < deadline:
                time.sleep(0.1)
                data = call(entry["port"], entry["key"], "GET", "/v1/status", timeout=2)
            if data["active"]:
                call(entry["port"], entry["key"], "POST", "/v1/resume", {}, timeout=2)
                raise ManagerError("busy", "Active inference did not drain; the worker remains running", 409)
            call(entry["port"], entry["key"], "POST", "/v1/shutdown", {}, timeout=2)
            entry["process"].wait(timeout=10)
        except subprocess.TimeoutExpired:
            # Admission drained and only our registered worker is eligible for termination.
            pass
        self._release(identifier)
        return {"state": "Stopped"}

    def infer(self, identifier, payload, timeout=180):
        with self.lock:
            entry = self.workers.get(identifier)
        require(
            entry is not None and entry["process"].poll() is None,
            "not_running",
            "Start this service first",
            409,
        )
        return call(entry["port"], entry["key"], "POST", "/v1/infer", payload, timeout=timeout)

    def inspect(self, payload):
        with self.lock:
            entry = self.workers.get("llm")
        require(
            entry is not None and entry["process"].poll() is None,
            "not_running",
            "Start LLM in Manage Local Models",
            409,
        )
        return call(entry["port"], entry["key"], "POST", "/v1/inspect", payload, timeout=10)

    def _release(self, identifier):
        with self.lock:
            entry = self.workers.pop(identifier, None)
        if entry:
            try:
                if entry["process"].poll() is None:
                    entry["process"].terminate()
                    entry["process"].wait(timeout=10)
            finally:
                if entry["guard"]:
                    entry["guard"].close()

    def close(self):
        for identifier in list(self.workers):
            self._release(identifier)

    @staticmethod
    def hardware():
        result = {"gpus": [], "cpu_available": True, "gpu_probe": "Unavailable"}
        try:
            completed = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,memory.total,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                env=environment(),
                creationflags=hidden_flags(),
            )
            if completed.returncode == 0:
                for line in completed.stdout.splitlines()[:16]:
                    index, name, total, free = (s.strip() for s in line.split(","))
                    result["gpus"].append(
                        {
                            "index": int(index),
                            "name": name[:120],
                            "total_mib": int(total),
                            "free_mib": int(free),
                        }
                    )
                result["gpu_probe"] = "Available" if result["gpus"] else "No NVIDIA GPU detected"
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        return result
