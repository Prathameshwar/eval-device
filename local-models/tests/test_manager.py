"""Business, privacy, transport and failure regressions without cloud or native models."""

import hashlib
import http.client
import io
import json
import secrets
import sys
import tempfile
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

LOCAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL))

from service.assets import Assets, verify_files  # noqa: E402
from service.catalog import Catalog  # noqa: E402
from service.daemon import InstanceLock, watch_startup  # noqa: E402
from service.errors import ManagerError  # noqa: E402
from service.http_server import JsonServer  # noqa: E402
from service.install_adapter import completed_staging, publish_converted  # noqa: E402
from service.lifecycle import Lifecycle  # noqa: E402
from service.manager import Manager  # noqa: E402
from service.process import run_owned  # noqa: E402
from service.protocol import call  # noqa: E402
from service.security import checked, environment  # noqa: E402
from service.storage import DEFAULTS, Store  # noqa: E402
from service.worker import Worker  # noqa: E402


class FakeAssets:
    def __init__(self, root):
        self.library = root / "library"
        self.verified = True
        self.downloads = 0
        self.gate = threading.Event()
        self.gate.set()

    def inventory(self):
        return {"qwen3-1.7b": {"status": "Installed", "installed": True}}

    def verify(self, _):
        if not self.verified:
            raise ManagerError("integrity", "Model checksum failed", 409)
        return self.library

    def runtime_python(self, _):
        return Path(sys.executable)

    def download(self, *_):
        self.downloads += 1
        self.gate.wait(5)


class FakeLifecycle:
    def __init__(self):
        self.states = {}
        self.start_count = 0

    def hardware(self):
        return {"gpus": [], "cpu_available": True, "gpu_probe": "Unavailable"}

    def status(self, kind):
        return self.states.get(kind, {"state": "Stopped", "ready": False})

    def start(self, config, _):
        self.start_count += 1
        self.states[config["capability"]] = {"state": "Ready", "ready": True, "device": "cpu"}
        return self.states[config["capability"]]

    def stop(self, kind, *_):
        self.states[kind] = {"state": "Stopped", "ready": False}
        return self.states[kind]

    def infer(self, _, payload):
        return {"text": payload["messages"][0]["content"]}

    def close(self):
        pass


def provisioning(revision=0, **updates):
    return {
        "request_id": str(uuid.uuid4()),
        "capability": "llm",
        "model_id": "qwen3-1.7b",
        "device": "cpu",
        "port": 8797,
        "start_at_boot": False,
        "revision": revision,
        **updates,
    }


class InitializationTests(unittest.TestCase):
    def test_loading_remains_visible_until_inventory_finishes(self):
        with tempfile.TemporaryDirectory(dir=LOCAL.parent / ".test_artifacts") as name:
            root = Path(name)
            gate, entered = threading.Event(), threading.Event()
            assets = FakeAssets(root)

            def inventory():
                entered.set()
                gate.wait(5)
                return {"qwen3-1.7b": {"status": "Installed", "installed": True}}

            assets.inventory = inventory
            manager = Manager(Store(root), assets=assets, lifecycle=FakeLifecycle())
            try:
                self.assertTrue(entered.wait(2))
                self.assertEqual(manager.snapshot()["initialization"], "loading")
                gate.set()
                deadline = time.monotonic() + 2
                while manager.snapshot()["initialization"] != "ready" and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(manager.snapshot()["initialization"], "ready")
            finally:
                gate.set()
                manager.close()

    def test_inventory_failure_is_explicit_and_refresh_recovers(self):
        with tempfile.TemporaryDirectory(dir=LOCAL.parent / ".test_artifacts") as name:
            root = Path(name)
            assets = FakeAssets(root)
            assets.inventory = Mock(side_effect=OSError("private storage details"))
            manager = Manager(Store(root), assets=assets, lifecycle=FakeLifecycle())
            try:
                deadline = time.monotonic() + 2
                while manager.snapshot()["initialization"] == "loading" and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(manager.snapshot()["initialization"], "failed")
                self.assertNotIn("private storage details", json.dumps(manager.snapshot()))
                assets.inventory.side_effect = None
                assets.inventory.return_value = {"qwen3-1.7b": {"status": "Installed", "installed": True}}
                operation = manager.submit("refresh", {"request_id": str(uuid.uuid4())})
                manager.queue.join()
                self.assertEqual(manager.store.operation(operation["id"])["state"], "succeeded")
                self.assertEqual(manager.snapshot()["initialization"], "ready")
            finally:
                manager.close()


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=LOCAL.parent / ".test_artifacts")
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.assets = FakeAssets(self.root)
        self.life = FakeLifecycle()
        self.manager = Manager(self.store, assets=self.assets, lifecycle=self.life)

    def tearDown(self):
        self.assets.gate.set()
        self.manager.queue.join()
        self.manager.close()
        self.temp.cleanup()

    def submit(self, action, payload):
        op = self.manager.submit(action, payload)
        self.manager.queue.join()
        return self.store.operation(op["id"])

    def test_download_does_not_provision_or_start(self):
        op = self.submit(
            "download", {"request_id": str(uuid.uuid4()), "model_id": "qwen3-1.7b", "device": "cpu"}
        )
        self.assertEqual(op["state"], "succeeded")
        self.assertFalse(self.store.snapshot()["services"])
        self.assertEqual(self.life.start_count, 0)

    def test_provision_start_stop_remove_preserves_assets(self):
        self.assertEqual(self.submit("provision", provisioning())["state"], "succeeded")
        self.assertEqual(self.life.start_count, 0)
        for action in ("start", "stop", "remove"):
            op = self.submit(action, {"request_id": str(uuid.uuid4()), "capability": "llm", "revision": 1})
            self.assertEqual(op["state"], "succeeded", op)
        self.assertEqual(self.assets.downloads, 0)
        self.assertFalse(self.store.snapshot()["services"])

    def test_client_readiness_refreshes_stale_monitor_cache(self):
        self.submit("provision", provisioning())
        self.life.states["llm"] = {"state": "Ready", "ready": True, "device": "cpu"}
        self.manager.statuses["llm"] = {"state": "Unavailable", "ready": False}
        result = self.manager.dispatch("GET", "/v1/capabilities", None, {})
        self.assertTrue(result["services"]["llm"]["ready"])
        self.life.stop("llm")
        self.manager.statuses["llm"] = {"state": "Ready", "ready": True}
        result = self.manager.dispatch("GET", "/v1/capabilities", None, {})
        self.assertFalse(result["services"]["llm"]["ready"])
        self.assertNotIn("logs", result)
        self.assertNotIn("library", result)

    def test_supervised_startup_reports_worker_failure_without_downloading(self):
        self.submit("provision", provisioning())
        self.life.start = Mock(side_effect=ManagerError("startup", "private failure", 409))
        operation = self.manager.submit(
            "start", {"request_id": str(uuid.uuid4()), "capability": "llm", "revision": 1}
        )
        failed, stop = threading.Event(), Mock()
        watch_startup(self.manager, [operation], failed, stop)
        self.assertTrue(failed.is_set())
        stop.assert_called_once()
        self.assertEqual(self.assets.downloads, 0)

    def test_successful_supervised_startup_keeps_manager_available(self):
        self.submit("provision", provisioning())
        operation = self.manager.submit(
            "start", {"request_id": str(uuid.uuid4()), "capability": "llm", "revision": 1}
        )
        failed, stop = threading.Event(), Mock()
        watch_startup(self.manager, [operation], failed, stop)
        self.assertFalse(failed.is_set())
        stop.assert_not_called()
        self.assertEqual(self.life.start_count, 1)
        self.assertEqual(self.assets.downloads, 0)

    def test_request_id_replay_is_one_operation(self):
        payload = provisioning()
        self.submit("provision", payload)
        op = self.manager.submit("provision", payload)
        self.assertEqual(op["state"], "succeeded")
        self.assertEqual(len(self.store.snapshot()["operations"]), 1)

    def test_request_id_conflict_rejected(self):
        payload = provisioning()
        self.submit("provision", payload)
        with self.assertRaises(ManagerError) as error:
            self.manager.submit("provision", {**payload, "port": 8800})
        self.assertEqual(error.exception.code, "idempotency_conflict")

    def test_concurrent_downloads_have_one_winner(self):
        self.assets.gate.clear()

        def attempt(_):
            try:
                self.manager.submit(
                    "download", {"request_id": str(uuid.uuid4()), "model_id": "qwen3-1.7b", "device": "cpu"}
                )
                return True
            except ManagerError as error:
                self.assertEqual(error.code, "operation_busy")
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(attempt, range(8))), 1)

    def test_corrupt_model_does_not_replace_configuration(self):
        self.assets.verified = False
        op = self.submit("provision", provisioning())
        self.assertEqual(op["error_code"], "integrity")
        self.assertFalse(self.store.snapshot()["services"])

    def test_stale_revision_rejected(self):
        self.submit("provision", provisioning())
        with self.assertRaises(ManagerError) as error:
            self.manager.submit("provision", provisioning())
        self.assertEqual(error.exception.code, "revision_conflict")

    def test_running_service_cannot_be_reconfigured_removed_or_runtime_replaced(self):
        self.submit("provision", provisioning())
        self.submit("start", {"request_id": str(uuid.uuid4()), "capability": "llm", "revision": 1})
        for action, payload in (
            ("provision", provisioning(1)),
            ("remove", {"request_id": str(uuid.uuid4()), "capability": "llm", "revision": 1}),
            ("download", {"request_id": str(uuid.uuid4()), "model_id": "qwen3-1.7b", "device": "cpu"}),
        ):
            op = self.submit(action, payload)
            self.assertEqual(op["state"], "failed")
        self.assertEqual(self.store.snapshot()["services"]["llm"]["port"], 8797)

    def test_settings_validate_and_preserve_existing_worker_options(self):
        self.submit("provision", provisioning())
        self.submit(
            "settings",
            {"request_id": str(uuid.uuid4()), "revision": 1, "settings": {**DEFAULTS, "cpu_threads": 2}},
        )
        self.assertEqual(self.store.snapshot()["settings"]["cpu_threads"], 2)
        self.assertTrue(self.store.snapshot()["settings_customized"])
        self.assertEqual(self.store.snapshot()["services"]["llm"]["options"]["cpu_threads"], 4)
        with self.assertRaises(ManagerError):
            self.manager.submit(
                "settings",
                {
                    "request_id": str(uuid.uuid4()),
                    "revision": 2,
                    "settings": {**DEFAULTS, "cpu_threads": True},
                },
            )

    def test_audio_provisioning_accepts_relevant_options_and_normalizes_legacy_shape(self):
        for capability, model, options in (
            ("asr", "large-v3", {"cpu_threads": 6, "startup_timeout_seconds": 90}),
            ("tts", "piper-en-male", {"startup_timeout_seconds": 40, "drain_timeout_seconds": 10}),
        ):
            with self.subTest(capability=capability):
                request = provisioning(
                    self.store.snapshot()["revision"],
                    capability=capability,
                    model_id=model,
                    port=8795 if capability == "asr" else 8798,
                    options=options,
                )
                self.assertEqual(self.submit("provision", request)["state"], "succeeded")
                config = self.store.snapshot()["services"][capability]
                self.assertEqual(set(config["options"]), set(DEFAULTS))
                for key, value in options.items():
                    self.assertEqual(config["options"][key], value)

    def test_start_at_boot_is_explicitly_queued(self):
        with self.assertRaises(ManagerError) as error:
            self.manager.submit("provision", provisioning(start_at_boot=True))
        self.assertEqual(error.exception.code, "startup_queued")

    def test_unknown_model_and_extra_commands_rejected(self):
        for updates in (
            {"model_id": "../bad"},
            {"command": "anything"},
            {"capability": []},
            {"options": {"api_key": "private"}},
        ):
            with self.assertRaises(ManagerError):
                self.manager.submit("provision", provisioning(**updates))

    def test_inference_never_persists_payload_or_output(self):
        secret = "clinical-input-must-not-be-persisted"
        result = self.manager.dispatch("POST", "/v1/infer/llm", {"messages": [{"content": secret}]}, {})
        self.assertEqual(result["text"], secret)
        self.assertNotIn(secret, self.store.path.read_text(encoding="utf-8"))
        self.assertFalse(self.store.snapshot()["operations"])

    def test_store_restart_marks_unknown_work_interrupted_without_replaying(self):
        self.manager.close()
        with self.store.lock:
            self.store.data["operations"].append({"id": str(uuid.uuid4()), "state": "running"})
            self.store.save()
        restarted = Store(self.root)
        self.assertEqual(restarted.snapshot()["operations"][-1]["state"], "interrupted")
        self.assertEqual(self.assets.downloads, 0)

    def test_instance_lock_prevents_second_manager(self):
        first = InstanceLock(self.root)
        try:
            with self.assertRaises(RuntimeError):
                InstanceLock(self.root)
        finally:
            first.close()
        second = InstanceLock(self.root)
        second.close()

    def test_bounded_event_logs_and_no_exception_output(self):
        with self.store.lock:
            self.store.data["logs"] = [{"cursor": i} for i in range(1000)]
        self.store.log("llm", "ERROR", "worker_exit")
        self.assertEqual(len(self.store.snapshot()["logs"]), 1000)

    def test_configuration_port_conflict(self):
        self.submit("provision", provisioning())
        payload = provisioning(1, capability="tts", model_id="piper-en-male", port=8797)
        self.assertEqual(self.submit("provision", payload)["error_code"], "port_conflict")

    def test_failed_start_is_visible_and_never_claims_ready(self):
        self.submit("provision", provisioning())
        with patch.object(self.life, "start", side_effect=ManagerError("worker_exit", "Worker failed", 409)):
            op = self.submit("start", {"request_id": str(uuid.uuid4()), "capability": "llm", "revision": 1})
        self.assertEqual(op["state"], "failed")
        result = self.manager.snapshot()["services"][0]
        self.assertEqual(result["state"], "Failed")
        self.assertFalse(result["ready"])

    def test_start_requires_explicit_readiness(self):
        self.submit("provision", provisioning())
        with patch.object(self.life, "start", return_value={"state": "Unavailable", "ready": False}):
            op = self.submit("start", {"request_id": str(uuid.uuid4()), "capability": "llm", "revision": 1})
        self.assertEqual(op["error_code"], "not_ready")
        self.assertFalse(self.manager.snapshot()["services"][0]["ready"])

    def test_requested_gpu_is_preserved_alongside_actual_cuda_device(self):
        self.submit("provision", provisioning(device="gpu"))
        self.manager.statuses["llm"] = {"state": "Ready", "ready": True, "device": "cuda"}
        service = self.manager.snapshot()["services"][0]
        self.assertEqual((service["configured_device"], service["device"]), ("gpu", "cuda"))

    def test_custom_manager_port_is_reserved_for_outer_and_native_worker(self):
        self.manager.port = 8897
        for port in (8897, 8797):
            with self.assertRaises(ManagerError) as error:
                self.manager.submit("provision", provisioning(port=port))
            self.assertEqual(error.exception.code, "port")

    def test_failed_state_write_rolls_back_before_enqueue(self):
        before = self.store.snapshot()
        with patch.object(self.store, "atomic", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.manager.submit("refresh", {"request_id": str(uuid.uuid4())})
        self.assertEqual(self.store.snapshot(), before)
        self.assertTrue(self.manager.queue.empty())

    def test_shutdown_rejects_running_workers_and_later_mutations(self):
        self.manager.shutdown = lambda: None
        self.submit("provision", provisioning())
        self.submit("start", {"request_id": str(uuid.uuid4()), "capability": "llm", "revision": 1})
        with self.assertRaises(ManagerError):
            self.manager.dispatch("POST", "/v1/shutdown", {}, {})
        self.submit("stop", {"request_id": str(uuid.uuid4()), "capability": "llm", "revision": 1})
        self.manager.dispatch("POST", "/v1/shutdown", {}, {})
        with self.assertRaises(ManagerError) as error:
            self.manager.submit("refresh", {"request_id": str(uuid.uuid4())})
        self.assertEqual(error.exception.code, "stopping")


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.key = secrets.token_urlsafe(48)
        self.requests = []

        def dispatch(method, path, payload, query):
            self.requests.append(payload)
            return {"ok": True}

        self.server = JsonServer(("127.0.0.1", 0), self.key, dispatch)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def raw(self, body="{}", **extra):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        headers = {"Authorization": "Bearer " + self.key, "Content-Type": "application/json", **extra}
        conn.request("POST", "/v1/test", body, headers)
        result = conn.getresponse()
        status = result.status
        result.read()
        conn.close()
        return status

    def test_authenticated_loopback_transport(self):
        self.assertTrue(call(self.server.server_port, self.key, "GET", "/v1/test")["ok"])

    def test_auth_browser_origin_and_wrong_host_rejected(self):
        for headers in (
            {"Authorization": "Bearer wrong"},
            {"Origin": "https://evil.invalid"},
            {"Cookie": "session=1"},
            {"Host": "evil.invalid"},
        ):
            self.assertIn(self.raw(**headers), (400, 401))
        self.assertFalse(self.requests)

    def test_duplicate_fields_nonfinite_and_oversize_rejected(self):
        for body in ('{"request_id":"one","request_id":"two"}', '{"x":NaN}', "[1]"):
            self.assertEqual(self.raw(body), 400)
        self.assertEqual(self.raw(**{"Content-Length": "0"}), 400)
        self.assertEqual(self.raw(**{"Content-Length": str(2 * 1024 * 1024 + 1)}), 413)

    def test_slow_header_connection_has_wall_clock_deadline(self):
        self.server.request_seconds = 0.15
        import socket

        with socket.create_connection(("127.0.0.1", self.server.server_port), timeout=2) as connection:
            connection.sendall(b"POST /v1/test HTTP/1.1\r\n")
            time.sleep(0.3)
            self.assertEqual(connection.recv(1), b"")

    def test_inference_calls_are_never_retried(self):
        with patch("service.protocol.http.client.HTTPConnection") as connection:
            connection.return_value.connect.side_effect = OSError("private-key-not-loggable")
            with self.assertRaises(ManagerError) as error:
                call(1234, self.key, "POST", "/v1/infer/llm", {"messages": []})
            self.assertEqual(connection.call_count, 1)
            self.assertNotIn("private-key", str(error.exception))


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=LOCAL.parent / ".test_artifacts")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_nested_files_verified_and_traversal_rejected(self):
        (self.root / "am").mkdir()
        (self.root / "am/model").write_bytes(b"valid")
        spec = {"bytes": 5, "sha256": hashlib.sha256(b"valid").hexdigest()}
        verify_files(self.root, {"am/model": spec})
        for name in ("../model", "am/../../model", "C:/model", "am\\model", "/model"):
            with self.assertRaises((ManagerError, ValueError)):
                verify_files(self.root, {name: spec})
        with self.assertRaises(ValueError):
            checked(self.root / "../outside", self.root)

    def test_corrupt_and_empty_manifest_rejected(self):
        (self.root / "model").write_bytes(b"bad")
        for files in ({}, {"model": {"bytes": 3, "sha256": "0" * 64}}):
            with self.assertRaises(ManagerError):
                verify_files(self.root, files)

    def test_partial_download_resumes_and_verifies(self):
        data = b"download-fixture"
        target = self.root / "model"
        target.with_name("model.part").write_bytes(data[:4])
        response = io.BytesIO(data[4:])
        response.status = 206
        response.headers = {"Content-Range": f"bytes 4-{len(data) - 1}/{len(data)}"}
        assets = Assets(Catalog())
        spec = {
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "url": "https://example.invalid/model",
        }
        with patch("service.assets.urllib.request.urlopen", return_value=response) as fetch:
            assets.fetch(spec, target, lambda **_: None)
            self.assertEqual(fetch.call_args.args[0].headers["Range"], "bytes=4-")
        self.assertEqual(target.read_bytes(), data)
        self.assertFalse(target.with_name("model.part").exists())

    def test_bad_download_is_not_published(self):
        response = io.BytesIO(b"bad")
        response.status, response.headers = 200, {}
        target = self.root / "model"
        with patch("service.assets.urllib.request.urlopen", return_value=response):
            with self.assertRaises(ManagerError):
                Assets(Catalog()).fetch(
                    {"bytes": 3, "sha256": "0" * 64, "url": "https://example.invalid/model"},
                    target,
                    lambda **_: None,
                )
        self.assertFalse(target.exists())

    def test_worker_drain_rejects_new_input_and_busy_shutdown(self):
        worker = Worker.__new__(Worker)
        worker.admission = threading.Lock()
        worker.active = 1
        worker.draining = False
        worker.dispatch("POST", "/v1/drain", {}, {})
        for route in ("/v1/infer", "/v1/shutdown"):
            with self.assertRaises(ManagerError):
                worker.dispatch("POST", route, {}, {})
        self.assertEqual(worker.active, 1)
        worker.dispatch("POST", "/v1/resume", {}, {})
        self.assertFalse(worker.draining)

    def test_credentials_not_inherited_by_workers(self):
        with patch.dict(
            "os.environ", {"PMS_DATABASE_DSN": "private", "HF_TOKEN": "private", "OPENAI_API_KEY": "private"}
        ):
            clean = environment()
        self.assertFalse({"PMS_DATABASE_DSN", "HF_TOKEN", "OPENAI_API_KEY"} & clean.keys())

    def fixture_assets(self):
        catalog = Catalog()
        catalog.local_root = self.root
        catalog.repo_root = self.root
        catalog.models["qwen3-1.7b"]["spec"] = {
            "name": "fixture.gguf",
            "bytes": 5,
            "sha256": hashlib.sha256(b"model").hexdigest(),
            "url": "https://example.invalid/model",
        }
        catalog.models["qwen3-1.7b"]["bytes"] = 5
        return Assets(catalog)

    def test_existing_model_reuse_does_not_require_duplicate_model_disk_space(self):
        assets = self.fixture_assets()
        legacy = self.root / ".models"
        legacy.mkdir()
        (legacy / "fixture.gguf").write_bytes(b"model")
        with (
            patch.object(assets, "runtime", return_value=Path(sys.executable)),
            patch("service.assets.shutil.disk_usage", return_value=Mock(free=0)),
            patch("service.assets.protect"),
        ):
            self.assertEqual(assets.download("qwen3-1.7b", False, lambda **_: None), legacy)

    def test_new_model_is_verified_and_atomically_published(self):
        assets = self.fixture_assets()
        response = io.BytesIO(b"model")
        response.status, response.headers = 200, {}
        with (
            patch.object(assets, "runtime", return_value=Path(sys.executable)),
            patch("service.assets.urllib.request.urlopen", return_value=response),
            patch("service.assets.protect"),
        ):
            installed = assets.download("qwen3-1.7b", False, lambda **_: None)
        self.assertEqual(assets.verify("qwen3-1.7b"), installed)
        self.assertFalse((assets.library / ".install-qwen3-1.7b").exists())

    def test_atomic_metadata_failure_preserves_previous_source_lock(self):
        assets = self.fixture_assets()
        lock = self.root / "source.json"
        lock.write_text('{"revision":"original"}', encoding="utf-8")
        with patch("service.assets.Path.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                assets._atomic_json(lock, {"revision": "replacement"})
        self.assertEqual(json.loads(lock.read_text(encoding="utf-8"))["revision"], "original")
        self.assertFalse(list(self.root.glob(".metadata-*")))

    def test_incomplete_hf_source_lock_fails_before_download(self):
        assets = self.fixture_assets()
        model = assets.catalog.get("large-v3")
        source = {
            "model_id": model["id"],
            "repo": model["repo"],
            "revision": "0" * 40,
            "files": {name: {} for name in ("config.json", "tokenizer.json", "vocabulary.json")},
        }
        with (
            patch.object(assets, "_hf_specs", return_value=source),
            patch("service.assets.urllib.request.urlopen") as network,
        ):
            with self.assertRaises(ManagerError):
                assets._hf_download(model, self.root, lambda **_: None)
        network.assert_not_called()

    def test_voice_installer_exit_is_reported_without_killing_operation_thread(self):
        assets = self.fixture_assets()
        voice = Mock(publish=Mock(side_effect=SystemExit("private native detail")))
        with (
            patch.object(assets, "runtime", return_value=Path(sys.executable)),
            patch.object(assets, "fetch", return_value=self.root / "voice.tar.bz2"),
            patch("service.assets.load_script", return_value=voice),
            patch("service.assets.protect"),
        ):
            with self.assertRaises(ManagerError) as error:
                assets.download("piper-en-male", False, lambda **_: None)
        self.assertEqual(error.exception.code, "voice_integrity")
        self.assertNotIn("private native", str(error.exception))

    def test_interrupted_converter_publication_resumes_without_reinstall(self):
        staging = self.root / "staging"
        target = staging / "converted"
        target.mkdir(parents=True)
        files = {}
        for name in ("model.bin", "config.json"):
            (target / name).write_bytes(b"model")
            files[name] = {"bytes": 5, "sha256": hashlib.sha256(b"model").hexdigest()}
        (target / "download-manifest.json").write_text(json.dumps({"files": files}), encoding="utf-8")
        (target / "model.bin").rename(staging / "model.bin")  # A prior process died here.
        publish_converted(staging)
        self.assertTrue(completed_staging(staging))
        self.assertFalse(target.exists())

    def test_existing_unready_worker_is_not_restarted_or_claimed_ready(self):
        lifecycle = Lifecycle(None, None)
        process = Mock()
        process.poll.return_value = None
        lifecycle.workers["llm"] = {"process": process}
        with patch.object(lifecycle, "status", return_value={"state": "Unavailable", "ready": False}):
            with self.assertRaises(ManagerError) as error:
                lifecycle.start({"capability": "llm"}, lambda **_: None)
        self.assertEqual(error.exception.code, "not_ready")
        process.terminate.assert_not_called()

    def test_installer_guard_closes_even_when_termination_fails(self):
        import subprocess

        process = Mock()
        process.wait.side_effect = subprocess.TimeoutExpired("installer", 1)
        process.poll.return_value = None
        process.terminate.side_effect = OSError("termination failure")
        guard = Mock()
        with (
            patch("service.process.subprocess.Popen", return_value=process),
            patch("service.process.sys.platform", "win32"),
            patch("service.assets.load_script", return_value=Mock(ProcessGuard=Mock(return_value=guard))),
        ):
            with self.assertRaises(OSError):
                run_owned(["installer"], timeout=1)
        guard.close.assert_called_once()

    def test_failed_native_child_releases_wrapper_before_reprovision(self):
        from unittest.mock import Mock

        lifecycle = Lifecycle(None, None)
        process = Mock()
        process.poll.return_value = None
        guard = Mock()
        lifecycle.workers["llm"] = {"process": process, "guard": guard, "port": 1234, "key": "private"}
        with patch("service.lifecycle.call", return_value={"failed": True, "ready": False}):
            self.assertEqual(lifecycle.status("llm")["state"], "Failed")
        self.assertFalse(lifecycle.workers)
        process.terminate.assert_called_once()
        guard.close.assert_called_once()

    def test_stop_drain_timeout_resumes_admission_without_termination(self):
        from unittest.mock import Mock

        lifecycle = Lifecycle(None, None)
        process = Mock()
        process.poll.return_value = None
        lifecycle.workers["llm"] = {"process": process, "guard": Mock(), "port": 1234, "key": "private"}
        with (
            patch("service.lifecycle.call", return_value={"active": 1}) as request,
            patch("service.lifecycle.time.monotonic", side_effect=[0, 2]),
        ):
            with self.assertRaises(ManagerError) as error:
                lifecycle.stop("llm", 1, lambda **_: None)
        self.assertEqual(error.exception.code, "busy")
        self.assertEqual(request.call_args.args[3], "/v1/resume")
        process.terminate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
