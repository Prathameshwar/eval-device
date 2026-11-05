"""Loading and preference regressions without Tk, downloads or native inference."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

LOCAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL))

from desktop.manager_client import Controller  # noqa: E402
from desktop.preferences import default_device, inventory_state, preferred_model  # noqa: E402
from service.contracts import runtime_option_names  # noqa: E402
from service.storage import DEFAULTS, LEGACY_DEFAULTS, Store, runtime_defaults  # noqa: E402


class PreferencesTests(unittest.TestCase):
    def test_qwen35_preferred_but_saved_service_selection_is_retained(self):
        models = [{"id": name} for name in ("qwen3-4b", "qwen3-1.7b", "qwen3.5-4b")]
        self.assertEqual(preferred_model(models), "qwen3.5-4b")
        self.assertEqual(preferred_model(models, "qwen3-1.7b"), "qwen3-1.7b")
        self.assertEqual(preferred_model(models, "missing"), "qwen3.5-4b")
        self.assertEqual(preferred_model(models[:-1]), "qwen3-4b")
        self.assertEqual(preferred_model([]), "")

    def test_execution_defaults_gpu_only_for_supported_models(self):
        self.assertEqual(default_device({"gpu_supported": True}), "gpu")
        self.assertEqual(default_device({"gpu_supported": False}), "cpu")
        self.assertEqual(default_device(None), "cpu")

    def test_loading_handles_new_and_already_running_managers(self):
        snapshot = {"models": [{"status": "Checking"}], "hardware": {"gpu_probe": "Checking"}}
        self.assertEqual(inventory_state(snapshot), "loading")
        snapshot["models"] = [{"status": "Not installed"}]
        self.assertEqual(inventory_state(snapshot), "loading")
        snapshot["hardware"]["gpu_probe"] = "Unavailable"
        self.assertEqual(inventory_state(snapshot), "ready")
        self.assertEqual(inventory_state({**snapshot, "initialization": "failed"}), "failed")
        self.assertEqual(inventory_state({**snapshot, "initialization": "loading"}), "loading")

    def test_factory_defaults_upgrade_without_overwriting_custom_preferences(self):
        self.assertEqual(DEFAULTS["gpu_layers"], 20)
        self.assertEqual(runtime_defaults({"settings": LEGACY_DEFAULTS})["gpu_layers"], 20)
        for override in (
            {"settings_customized": True},
            {"operations": [{"action": "settings", "state": "failed"}]},
            {"settings": {**LEGACY_DEFAULTS, "cpu_threads": 6}},
        ):
            with self.subTest(override=override):
                data = {"settings": LEGACY_DEFAULTS, **override}
                self.assertEqual(runtime_defaults(data)["gpu_layers"], 16)

    def test_store_upgrade_keeps_saved_service_options_and_advances_revision_once(self):
        with tempfile.TemporaryDirectory(dir=LOCAL.parent / ".test_artifacts") as name:
            store = Store(Path(name))
            store.data["settings"] = dict(LEGACY_DEFAULTS)
            store.data.pop("settings_customized")
            store.data["revision"] = 5
            store.data["services"] = {"llm": {"options": dict(LEGACY_DEFAULTS)}}
            store.save()
            upgraded = Store(Path(name))
            self.assertEqual(upgraded.data["settings"]["gpu_layers"], 20)
            self.assertEqual(upgraded.data["services"]["llm"]["options"]["gpu_layers"], 16)
            self.assertEqual(upgraded.data["revision"], 6)
            self.assertEqual(Store(Path(name)).data["revision"], 6)

    def test_store_retains_explicit_legacy_factory_choice(self):
        with tempfile.TemporaryDirectory(dir=LOCAL.parent / ".test_artifacts") as name:
            store = Store(Path(name))
            store.data["settings"] = dict(LEGACY_DEFAULTS)
            store.data.pop("settings_customized")
            store.data["operations"] = [{"action": "settings", "state": "succeeded"}]
            store.save()
            reopened = Store(Path(name))
            self.assertTrue(reopened.data["settings_customized"])
            self.assertEqual(reopened.data["settings"]["gpu_layers"], 16)


class RuntimeOptionsTests(unittest.TestCase):
    def test_language_limits_and_gpu_layers_are_not_offered_to_audio(self):
        for capability in ("asr", "tts"):
            for device in ("cpu", "gpu"):
                with self.subTest(capability=capability, device=device):
                    names = runtime_option_names(capability, device)
                    self.assertFalse({"context_size", "max_tokens", "gpu_layers"}.intersection(names))
                    self.assertTrue({"startup_timeout_seconds", "drain_timeout_seconds"}.issubset(names))

    def test_gpu_options_hide_in_cpu_mode_without_losing_language_limits(self):
        names = runtime_option_names("llm", "cpu")
        self.assertFalse({"gpu_layers", "gpu_device_index"}.intersection(names))
        self.assertTrue({"cpu_threads", "context_size", "max_tokens"}.issubset(names))
        gpu = runtime_option_names("llm", "gpu")
        self.assertTrue({"gpu_layers", "gpu_device_index"}.issubset(gpu))

    def test_audio_settings_follow_supported_adapter_options(self):
        whisper = runtime_option_names("asr", "gpu", {"format": "CTranslate2"})
        self.assertIn("cpu_threads", whisper)
        self.assertIn("gpu_device_index", whisper)
        vosk = runtime_option_names("asr", "cpu", {"format": "Vosk"})
        self.assertNotIn("cpu_threads", vosk)
        piper = runtime_option_names("tts", "cpu")
        self.assertEqual(set(piper), {"startup_timeout_seconds", "drain_timeout_seconds"})


class ConnectionTests(unittest.TestCase):
    def test_poll_and_repeated_reconnect_wait_for_initial_connection(self):
        jobs = []
        executor = SimpleNamespace(submit=jobs.append, shutdown=Mock())
        root = SimpleNamespace(after=Mock(return_value="timer"), after_cancel=Mock())
        data = {"operations": []}
        client = SimpleNamespace(connect=Mock(return_value=data), request=Mock(return_value=data))
        snapshots, failures = [], []
        with patch("desktop.manager_client.concurrent.futures.ThreadPoolExecutor", return_value=executor):
            controller = Controller(root, snapshots.append, Mock(), client, failures.append)
        try:
            controller._poll()
            controller.refresh()
            controller.reconnect()
            self.assertEqual(len(jobs), 1)
            self.assertFalse(client.request.called)
            jobs.pop(0)()
            controller._drain()
            self.assertEqual(snapshots, [data])
            self.assertFalse(failures)
            controller.refresh()
            self.assertEqual(len(jobs), 1)
            jobs.pop(0)()
            controller._drain()
            client.request.assert_called_once_with("GET", "/v1/status")
        finally:
            controller.close()

    def test_failed_initial_connection_is_retryable_without_mutation(self):
        jobs = []
        executor = SimpleNamespace(submit=jobs.append, shutdown=Mock())
        root = SimpleNamespace(after=Mock(return_value="timer"), after_cancel=Mock())
        client = SimpleNamespace(connect=Mock(side_effect=OSError()), request=Mock())
        failures = []
        with patch("desktop.manager_client.concurrent.futures.ThreadPoolExecutor", return_value=executor):
            controller = Controller(root, Mock(), Mock(), client, failures.append)
        try:
            jobs.pop(0)()
            controller._drain()
            self.assertTrue(failures)
            self.assertFalse(controller.connecting)
            client.connect.side_effect = None
            client.connect.return_value = {"operations": []}
            controller.reconnect()
            jobs.pop(0)()
            controller._drain()
            self.assertFalse(client.request.called)
        finally:
            controller.close()


if __name__ == "__main__":
    unittest.main()
