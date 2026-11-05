"""Native loading, retry and selection checks with a delayed client; no inference."""

import copy
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

LOCAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL))

from desktop.live import LiveModelManager  # noqa: E402
from service.storage import DEFAULTS, LEGACY_DEFAULTS  # noqa: E402


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def labels(widget):
    return [child.cget("text") for child in descendants(widget) if isinstance(child, tk.Label)]


def button(widget, text):
    return next(
        child for child in descendants(widget) if isinstance(child, ttk.Button) and child.cget("text") == text
    )


def model(identifier, capability, gpu):
    return {
        "id": identifier,
        "name": identifier,
        "status": "Installed",
        "installed": True,
        "capability": capability,
        "gpu_supported": gpu,
        "detail": "Fixture",
        "format": "Fixture",
        "device": "CPU / NVIDIA GPU" if gpu else "CPU",
        "size": "Fixture",
        "kind": {"llm": "llm", "asr": "audio", "tts": "voice"}[capability],
        "category": "LLM" if capability == "llm" else "Audio",
    }


class DelayedClient:
    def __init__(self, root):
        self.root, self.port = root, 8790
        self.gate = threading.Event()
        self.posts = []
        self.data = {
            "models": [
                model("piper-en-male", "tts", False),
                model("qwen3-4b", "llm", True),
                model("qwen3.5-4b", "llm", True),
            ],
            "services": [],
            "logs": [],
            "operations": [],
            "revision": 0,
            "settings": dict(LEGACY_DEFAULTS),
            "hardware": {"gpus": [], "gpu_probe": "Checking"},
            "initialization": "loading",
        }

    def connect(self):
        self.gate.wait(5)
        return copy.deepcopy(self.data)

    def request(self, method, path, payload=None):
        if method == "POST":
            assert path == "/v1/actions/refresh"
            self.posts.append(path)
            self.data["initialization"] = "ready"
            operation = {
                "id": payload["request_id"],
                "action": "refresh",
                "state": "succeeded",
                "phase": "Complete",
            }
            self.data["operations"].append(operation)
            return operation
        return copy.deepcopy(self.data)


def main():
    with tempfile.TemporaryDirectory(dir=LOCAL.parent / ".test_artifacts") as name:
        client = DelayedClient(Path(name))
        root = tk.Tk()
        root.withdraw()
        errors = []
        root.report_callback_exception = lambda *error: errors.append(error)
        app = LiveModelManager(root, client)
        checks = 0

        def until(predicate, seconds=5):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                root.update()
                if predicate():
                    return
                time.sleep(0.01)
            raise AssertionError("Loading UI check timed out")

        def combos():
            return [child for child in descendants(app.dialog) if isinstance(child, ttk.Combobox)]

        def layers():
            for frame in descendants(app.dialog):
                if isinstance(frame, tk.Frame) and "Gpu Layers" in labels(frame):
                    spins = [child for child in frame.winfo_children() if isinstance(child, ttk.Spinbox)]
                    if spins:
                        return spins[0].get()
            raise AssertionError("GPU layer control missing")

        try:
            root.update()
            for page in app.PAGES:
                app.show_page(page)
                root.update()
                assert "Loading local models" in labels(app.body)
                assert not any(isinstance(child, ttk.Button) for child in descendants(app.body))
                assert app.loading_progress is not None
                checks += 1
            app.controller._poll()
            assert not app.loading_error and not client.posts
            app._provision()
            assert app.dialog is None
            checks += 1
            client.gate.set()
            until(lambda: app.connected)
            assert not app.loaded and "Loading local models" in labels(app.body)
            progress = app.loading_progress
            client.data["initialization"] = "ready"
            client.data["hardware"]["gpu_probe"] = "Available"
            app.controller.refresh()
            until(lambda: app.loaded)
            assert not progress.winfo_exists() and app.loading_progress is None
            checks += 1
            # Qwen 3.5 wins over catalog order, including an earlier CPU-only voice.
            app._provision()
            root.update()
            assert [control.get() for control in combos()] == ["llm", "qwen3.5-4b", "gpu"]
            assert layers() == "20"
            combos()[2].set("cpu")
            combos()[1].set("qwen3-4b")
            assert combos()[2].get() == "cpu"  # Preserve an explicit CPU selection.
            combos()[0].set("tts")
            assert combos()[2].get() == "cpu"
            assert tuple(combos()[2].cget("values")) == ("cpu",)
            app.dialog.destroy()
            app._model_detail(client.data["models"][2])
            root.update()
            assert combos()[0].get() == "gpu"  # Download/runtime preparation shares the preference.
            app.dialog.destroy()
            app._provision(chosen=client.data["models"][1])
            root.update()
            assert combos()[1].get() == "qwen3-4b"  # An explicit model-card choice wins.
            app.dialog.destroy()
            checks += 4
            saved = {
                "capability": "llm",
                "model_id": "qwen3-4b",
                "configured_device": "cpu",
                "device": "cpu",
                "port": 9017,
                "options": {**DEFAULTS, "gpu_layers": 7},
                "state": "Stopped",
                "ready": False,
                "name": "Language model",
                "kind": "llm",
                "model": "qwen3-4b",
            }
            client.data["services"] = [saved]
            app._snapshot(copy.deepcopy(client.data))
            app._provision(existing=saved)
            root.update()
            assert [control.get() for control in combos()] == ["llm", "qwen3-4b", "cpu"]
            assert "Gpu Layers" not in labels(app.dialog)
            combos()[2].set("gpu")
            assert layers() == "7"
            app.dialog.destroy()
            checks += 1
            client.data["initialization"] = "failed"
            app._snapshot(copy.deepcopy(client.data))
            root.update()
            assert "Could not load local models" in labels(app.body)
            assert app.loading_progress is None
            app.data["metadata_error"] = "Fixture storage unavailable"
            button(app.body, "Try again").invoke()
            assert app.loading_error and not client.posts
            app.data.pop("metadata_error")
            button(app.body, "Try again").invoke()
            until(lambda: app.loaded)
            assert client.posts == ["/v1/actions/refresh"]
            checks += 1
            app._disconnected("Fixture manager unavailable")
            root.update()
            assert not app.loaded and "Could not load local models" in labels(app.body)
            button(app.body, "Try again").invoke()
            until(lambda: app.loaded)
            assert client.posts == ["/v1/actions/refresh"]  # Reconnect never mutates workers.
            assert not errors, errors
            checks += 1
            app.close()
            print(f"Native loading/defaults: {checks} checks passed; delayed client, no model inference")
        finally:
            client.gate.set()
            if not app.controller.closed:
                app.close()


if __name__ == "__main__":
    main()
