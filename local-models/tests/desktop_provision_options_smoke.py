"""Native provisioning fields, draft isolation and legacy preservation; no inference."""

import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

LOCAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL))

from desktop_loading_smoke import DelayedClient, button, descendants, model  # noqa: E402

from desktop.live import LiveModelManager  # noqa: E402
from service.storage import DEFAULTS  # noqa: E402


def fields(dialog):
    result = {}
    for frame in descendants(dialog):
        children = frame.winfo_children()
        label = next((child for child in children if isinstance(child, tk.Label)), None)
        spin = next((child for child in children if isinstance(child, ttk.Spinbox)), None)
        if label is not None and spin is not None:
            result[label.cget("text")] = spin
    return result


def set_value(control, value):
    control.delete(0, "end")
    control.insert(0, value)


def main():
    with tempfile.TemporaryDirectory(dir=LOCAL.parent / ".test_artifacts") as name:
        client = DelayedClient(Path(name))
        whisper = model("large-v3", "asr", True)
        vosk = model("vosk-model-small-en-us-0.15", "asr", False)
        vosk["format"] = "Vosk"
        client.data["models"].extend((whisper, vosk))
        client.data["initialization"] = "ready"
        client.gate.set()
        root = tk.Tk()
        root.withdraw()
        failures = []
        root.report_callback_exception = lambda *error: failures.append(error)
        app = LiveModelManager(root, client)
        submitted = []
        checks = 0

        def combos():
            return [control for control in descendants(app.dialog) if isinstance(control, ttk.Combobox)]

        def assert_fields(names):
            root.update()
            assert set(fields(app.dialog)) == set(names), set(fields(app.dialog))

        common = {"Startup Timeout Seconds", "Drain Timeout Seconds"}
        llm_cpu = common | {"Cpu Threads", "Context Size", "Max Tokens"}
        try:
            deadline = time.monotonic() + 5
            while not app.loaded:
                root.update()
                assert time.monotonic() < deadline
                time.sleep(0.01)
            app._provision()
            assert_fields(llm_cpu | {"Gpu Device Index", "Gpu Layers"})
            assert fields(app.dialog)["Gpu Layers"].get() == "20"
            set_value(fields(app.dialog)["Gpu Layers"], "23")
            set_value(fields(app.dialog)["Cpu Threads"], "11")
            combos()[2].set("cpu")
            assert_fields(llm_cpu)
            set_value(fields(app.dialog)["Context Size"], "invalid LLM draft")
            combos()[0].set("asr")
            assert_fields(common | {"Cpu Threads", "Gpu Device Index"})
            assert fields(app.dialog)["Cpu Threads"].get() == "4"
            set_value(fields(app.dialog)["Cpu Threads"], "6")
            combos()[2].set("cpu")
            assert_fields(common | {"Cpu Threads"})
            combos()[1].set(vosk["id"])
            assert_fields(common)
            combos()[1].set(whisper["id"])
            assert_fields(common | {"Cpu Threads", "Gpu Device Index"})
            assert fields(app.dialog)["Cpu Threads"].get() == "6"
            combos()[0].set("tts")
            assert_fields(common)
            set_value(fields(app.dialog)["Startup Timeout Seconds"], "75")
            combos()[0].set("llm")
            assert_fields(llm_cpu | {"Gpu Device Index", "Gpu Layers"})
            assert fields(app.dialog)["Gpu Layers"].get() == "23"
            assert fields(app.dialog)["Cpu Threads"].get() == "11"
            assert fields(app.dialog)["Context Size"].get() == "invalid LLM draft"
            combos()[0].set("asr")
            assert_fields(common | {"Cpu Threads", "Gpu Device Index"})
            checks += 9
            # An invalid draft on another capability does not block recognition provisioning.
            with patch.object(
                app,
                "_action",
                side_effect=lambda action, payload: submitted.append((action, payload)) or True,
            ):
                button(app.dialog, "Provision Service").invoke()
            assert not app.dialog.winfo_exists()
            assert submitted[-1][1]["capability"] == "asr"
            assert submitted[-1][1]["options"]["cpu_threads"] == 6
            assert submitted[-1][1]["options"]["context_size"] == DEFAULTS["context_size"]
            checks += 1
            # Hidden invalid GPU input must not prevent a CPU configuration from saving.
            app._provision()
            set_value(fields(app.dialog)["Gpu Layers"], "invalid GPU draft")
            combos()[2].set("cpu")
            assert_fields(llm_cpu)
            with patch.object(
                app,
                "_action",
                side_effect=lambda action, payload: submitted.append((action, payload)) or True,
            ):
                button(app.dialog, "Provision Service").invoke()
            assert not app.dialog.winfo_exists()
            assert submitted[-1][1]["device"] == "cpu"
            assert submitted[-1][1]["options"]["gpu_layers"] == DEFAULTS["gpu_layers"]
            checks += 1
            # Language context/output validation must still run on visible inputs.
            app._provision()
            set_value(fields(app.dialog)["Context Size"], "512")
            set_value(fields(app.dialog)["Max Tokens"], "512")
            with patch("desktop.live.messagebox.showerror") as error, patch.object(app, "_action") as action:
                button(app.dialog, "Provision Service").invoke()
                assert error.called and not action.called and app.dialog.winfo_exists()
            app.dialog.destroy()
            checks += 1
            saved = {
                "capability": "tts",
                "model_id": "piper-en-male",
                "configured_device": "cpu",
                "device": "cpu",
                "port": 9018,
                "options": {**DEFAULTS, "gpu_layers": 13, "cpu_threads": 9, "startup_timeout_seconds": 65},
            }
            app._provision(existing=saved)
            assert_fields(common)
            assert fields(app.dialog)["Startup Timeout Seconds"].get() == "65"
            set_value(fields(app.dialog)["Drain Timeout Seconds"], "15")
            with patch.object(
                app,
                "_action",
                side_effect=lambda action, payload: submitted.append((action, payload)) or True,
            ):
                button(app.dialog, "Provision Service").invoke()
            payload = submitted[-1][1]
            assert payload["capability"] == "tts" and payload["port"] == 9018
            assert payload["options"]["cpu_threads"] == 9 and payload["options"]["gpu_layers"] == 13
            assert payload["options"]["drain_timeout_seconds"] == 15
            assert not failures, failures
            checks += 1
            app.close()
            print(f"Native capability options: {checks} checks passed; no model/service mutation")
        finally:
            if not app.controller.closed:
                app.close()


if __name__ == "__main__":
    main()
