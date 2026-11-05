"""Persistent, idempotent operator actions and private local inference routing."""

import copy
import queue
import threading
import time

from . import contracts as c
from .assets import Assets
from .catalog import Catalog
from .errors import ManagerError, require
from .lifecycle import Lifecycle


class Manager:
    def __init__(self, store, catalog=None, assets=None, lifecycle=None):
        self.store = store
        self.catalog = catalog or Catalog()
        self.assets = assets or Assets(self.catalog)
        self.lifecycle = lifecycle or Lifecycle(store, self.assets)
        self.queue = queue.Queue()
        self.closed = threading.Event()
        self.statuses = {}
        self.hardware = {"gpus": [], "cpu_available": True, "gpu_probe": "Checking"}
        self.shutdown = None
        self.closing = False
        self.metadata_error = None
        self.initialization = "loading"
        self.port = 8790
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.monitor = threading.Thread(target=self._monitor, daemon=True)
        self.thread.start()
        self.monitor.start()

    def _monitor(self):
        try:
            self._refresh_inventory()
        except Exception:
            self._log("manager", "ERROR", "inventory_check_failed")
        while not self.closed.is_set():
            data = self.store.snapshot()
            for kind in data["services"]:
                try:
                    status = self.lifecycle.status(kind)
                    previous = self.statuses.get(kind, {})
                    if status["state"] == "Stopped" and previous.get("state") == "Failed":
                        status = previous
                    if status["state"] == "Failed" and previous.get("state") != "Failed":
                        self._log(kind, "ERROR", "worker_exited")
                    self.statuses[kind] = status
                except Exception:
                    self.statuses[kind] = {"state": "Unavailable", "ready": False}
            self.closed.wait(1)

    def _refresh_inventory(self):
        self.initialization = "loading"
        try:
            self.hardware = self.lifecycle.hardware()
            self._inventory()
        except Exception:
            self.initialization = "failed"
            raise
        self.initialization = "ready"

    def _inventory(self):
        inventory = self.assets.inventory()
        with self.store.lock:
            self.store.data["inventory"] = inventory
            self.store.save()

    def snapshot(self):
        data = self.store.snapshot()
        services = []
        pending = {op.get("target"): op for op in data["operations"] if op["state"] in {"queued", "running"}}
        for kind, config in data["services"].items():
            status = copy.deepcopy(self.statuses.get(kind, {"state": "Checking", "ready": False}))
            if kind in pending:
                status.update(state=pending[kind].get("phase", "Queued"), busy=True)
            services.append(
                {
                    **config,
                    **status,
                    "configured_device": config["device"],
                    "name": c.CAPABILITIES[kind][0],
                    "kind": {"llm": "llm", "asr": "audio", "tts": "voice"}[kind],
                    "model": self.catalog.get(config["model_id"])["name"],
                }
            )
        return {
            "revision": data["revision"],
            "settings": data["settings"],
            "settings_customized": data["settings_customized"],
            "initialization": self.initialization,
            "services": services,
            "models": self.catalog.public(data["inventory"]),
            "hardware": self.hardware,
            "operations": data["operations"][-100:],
            "logs": data["logs"],
            "library": str(self.assets.library),
            "background": "Detached operator manager",
            "windows_service": "Queued",
            "boot_auto_start": False,
            "metadata_error": self.metadata_error,
            "manager_port": self.port,
        }

    def _log(self, service, level, code):
        try:
            self.store.log(service, level, code)
        except OSError:
            self.metadata_error = "Local metadata cannot be saved. Inference remains available; fix storage and restart the manager before further changes."

    def submit(self, action, payload):
        require(
            action in {"download", "provision", "start", "stop", "remove", "refresh", "settings"},
            "action",
            "Unsupported action",
        )
        with self.store.lock:
            require(not self.closing, "stopping", "Manager is shutting down", 409)
            require(
                not self.metadata_error,
                "metadata_unavailable",
                self.metadata_error or "Metadata unavailable",
                409,
            )
            c.request_id(payload.get("request_id") if isinstance(payload, dict) else None)
            previous = self.store.operation(payload["request_id"])
            if previous:
                require(
                    previous["action"] == action and previous["request"] == payload,
                    "idempotency_conflict",
                    "Request ID was already used for another action",
                    409,
                )
                return previous
            target = "manager"
            if action == "download":
                c.exact(payload, ("request_id", "model_id", "device"))
                model = self.catalog.get(payload["model_id"])
                require(payload["device"] in ("cpu", "gpu"), "device", "Choose CPU or GPU")
                require(
                    payload["device"] == "cpu" or model["gpu_supported"], "device", "Model supports CPU only"
                )
                target = "assets"  # Shared runtimes and legacy installer imports must be serialized.
            elif action == "provision":
                c.provision(payload, self.catalog, self.store.data["settings"], self.port)
                target = payload["capability"]
            elif action in {"start", "stop", "remove"}:
                c.exact(payload, ("request_id", "capability", "revision"))
                target = payload["capability"]
                require(
                    isinstance(target, str) and target in c.CAPABILITIES,
                    "capability",
                    "Unsupported capability",
                )
                require(
                    target in self.store.data["services"],
                    "not_provisioned",
                    "Provision this capability first",
                    409,
                )
            elif action == "settings":
                c.exact(payload, ("request_id", "revision", "settings"))
                c.settings(payload["settings"])
            else:
                c.exact(payload, ("request_id",))
                target = "assets"
            if action in {"settings", "provision", "start", "stop", "remove"}:
                c.integer(payload.get("revision"), 0, 2**53, "Revision")
                require(
                    payload["revision"] == self.store.data["revision"],
                    "revision_conflict",
                    "Configuration changed; refresh before submitting",
                    409,
                )
            require(
                not any(
                    op["state"] in {"queued", "running"} and op["target"] == target
                    for op in self.store.data["operations"]
                ),
                "operation_busy",
                "An operation for this resource is already in progress",
                409,
            )
            require(
                len(self.store.data["operations"]) < 2000,
                "journal_full",
                "Operation journal is full; archive it before further changes",
                409,
            )
            operation = {
                "id": payload["request_id"],
                "action": action,
                "request": copy.deepcopy(payload),
                "target": target,
                "state": "queued",
                "phase": "Queued",
                "updated": time.time(),
            }
            self.store.data["operations"].append(operation)
            self.store.save()
            self.queue.put(operation["id"])
            return copy.deepcopy(operation)

    def _run(self):
        while not self.closed.is_set():
            try:
                identifier = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue
            operation = self.store.operation(identifier)
            last_progress = [0.0]

            def progress(**values):
                now = time.monotonic()
                if now - last_progress[0] >= 0.25 or "bytes_done" not in values:
                    self.store.progress(identifier, **values)
                    last_progress[0] = now

            try:
                self.store.progress(identifier, state="running")
                self._execute(operation, progress)
                self.store.progress(identifier, state="succeeded", phase="Complete")
                self._log(operation["target"], "INFO", operation["action"] + "_complete")
            except Exception as error:
                public = (
                    error
                    if isinstance(error, ManagerError)
                    else ManagerError(
                        "operation_failed",
                        "Operation failed; existing assets and configuration were preserved",
                        500,
                    )
                )
                try:
                    self.store.progress(
                        identifier,
                        state="failed",
                        phase="Failed",
                        error=public.message,
                        error_code=public.code,
                    )
                except OSError:
                    self.metadata_error = "Local metadata cannot be saved. Inference remains available; inspect operation outcomes and fix storage before restarting."
                if operation["action"] == "start":
                    self.statuses[operation["target"]] = {
                        "state": "Failed",
                        "ready": False,
                        "error": public.message,
                    }
                self._log(operation["target"], "ERROR", operation["action"] + "_" + public.code)
            finally:
                self.queue.task_done()

    def _execute(self, op, progress):
        require(
            not self.metadata_error,
            "metadata_unavailable",
            self.metadata_error or "Metadata unavailable",
            409,
        )
        action, payload = op["action"], op["request"]
        if action == "download":
            kind = self.catalog.get(payload["model_id"])["capability"]
            require(
                self.lifecycle.status(kind)["state"] in {"Stopped", "Failed"},
                "runtime_in_use",
                "Stop this capability before preparing its shared runtime",
                409,
            )
            self.assets.download(payload["model_id"], payload["device"] == "gpu", progress)
            self._inventory()
            return
        if action == "refresh":
            self._refresh_inventory()
            return
        with self.store.lock:
            require(
                payload["revision"] == self.store.data["revision"],
                "revision_conflict",
                "Configuration changed while queued; refresh and inspect",
                409,
            )
            data = self.store.snapshot()
        kind = payload.get("capability")
        if action == "provision":
            config = c.provision(payload, self.catalog, data["settings"], self.port)
            require(
                self.lifecycle.status(kind)["state"] in {"Stopped", "Failed"},
                "running",
                "Stop the service before changing its configuration",
                409,
            )
            self.assets.verify(config["model_id"])
            self.assets.runtime_python(kind)
            occupied = {s["port"] for k, s in data["services"].items() if k != kind}
            internal = {s["port"] + 100 for k, s in data["services"].items() if k != kind and k == "llm"}
            require(
                config["port"] not in occupied | internal
                and (kind != "llm" or config["port"] + 100 not in occupied | {self.port}),
                "port_conflict",
                "Configured service ports conflict",
                409,
            )
            self.statuses[kind] = {"state": "Stopped", "ready": False, "active": 0}
        elif action == "start":
            result = self.lifecycle.start(data["services"][kind], progress)
            require(result.get("ready") is True, "not_ready", "Worker has not confirmed model readiness", 409)
            self.statuses[kind] = {**result, "state": "Ready", "ready": True}
            return
        elif action == "stop":
            self.statuses[kind] = self.lifecycle.stop(
                kind, data["services"][kind]["options"]["drain_timeout_seconds"], progress
            )
            return
        elif action == "remove":
            require(
                self.lifecycle.status(kind)["state"] in {"Stopped", "Failed"},
                "running",
                "Stop the service before removing its configuration",
                409,
            )
        with self.store.lock:
            if action == "settings":
                self.store.data["settings"] = c.settings(payload["settings"])
                self.store.data["settings_customized"] = True
            elif action == "provision":
                self.store.data["services"][kind] = config
            else:
                self.store.data["services"].pop(kind)
                self.statuses.pop(kind, None)
            self.store.data["revision"] += 1
            self.store.save()

    def dispatch(self, method, path, payload, query):
        require(not query, "query", "Query parameters are not supported")
        if method == "GET" and path == "/v1/capabilities":
            snapshot = self.snapshot()
            # Consumer admission uses a fresh worker probe, rather than the UI monitor cache.
            for service in snapshot["services"]:
                if not service.get("busy"):
                    service.update(self.lifecycle.status(service["capability"]))
            models = []
            for entry in snapshot["models"]:
                if entry["status"] != "Installed":
                    continue
                model = self.catalog.get(entry["id"])
                info = {"id": model["id"], "capability": model["capability"], "name": model["name"]}
                if model["capability"] == "llm":
                    info["alias"] = model["id"] + "-local"
                if model["capability"] == "asr":
                    from .catalog import WHISPER

                    info["platform_speech"] = model["id"] in WHISPER
                if model["capability"] == "tts":
                    spec = model["spec"]
                    info.update(
                        key=model["voice"],
                        language=spec["language"],
                        gender=spec.get("gender", "male"),
                        default=bool(spec.get("default")),
                    )
                models.append(info)
            return {
                "version": 1,
                "revision": snapshot["revision"],
                "models": models,
                "services": {
                    service["capability"]: {
                        key: service[key]
                        for key in ("model_id", "ready", "state", "device", "configured_device", "options")
                        if key in service
                    }
                    for service in snapshot["services"]
                },
            }
        if method == "POST" and path == "/v1/llm/inspect":
            require(not self.closing, "stopping", "Manager is shutting down", 409)
            return self.lifecycle.inspect(payload)
        if method == "POST" and path == "/v1/shutdown":
            c.exact(payload, ())
            with self.store.lock:
                require(
                    not any(op["state"] in {"queued", "running"} for op in self.store.data["operations"]),
                    "busy",
                    "Wait for manager operations to finish",
                    409,
                )
                require(
                    all(
                        self.lifecycle.status(kind)["state"] in {"Stopped", "Failed"}
                        for kind in self.store.data["services"]
                    ),
                    "busy",
                    "Stop inference services before shutting down the manager",
                    409,
                )
                require(self.shutdown is not None, "unavailable", "Manager shutdown is unavailable", 409)
                self.closing = True
            threading.Timer(0.1, self.shutdown).start()
            return {"stopping": True}
        if method == "GET" and path == "/v1/status":
            return self.snapshot()
        if method == "GET" and path.startswith("/v1/operations/"):
            identifier = c.request_id(path.removeprefix("/v1/operations/"))
            op = self.store.operation(identifier)
            require(
                op is not None,
                "unknown_operation",
                "Operation is unknown; inspect status before retrying",
                404,
            )
            return op
        if method == "POST" and path.startswith("/v1/actions/"):
            return self.submit(path.removeprefix("/v1/actions/"), payload)
        if method == "POST" and path.startswith("/v1/infer/"):
            require(not self.closing, "stopping", "Manager is shutting down", 409)
            kind = path.removeprefix("/v1/infer/")
            require(kind in c.CAPABILITIES, "capability", "Unsupported capability")
            return self.lifecycle.infer(kind, payload)  # Never persisted, audited or replayed.
        raise ManagerError("not_found", "Unknown manager endpoint", 404)

    def close(self):
        self.closed.set()
        self.monitor.join(timeout=7)
        self.lifecycle.close()
