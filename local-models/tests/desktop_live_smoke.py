"""Native Tk controls against authenticated HTTP and a fixture engine supervisor."""

import json
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

from test_manager import FakeAssets, FakeLifecycle

from desktop.live import LiveModelManager
from desktop.manager_client import Client
from service.http_server import JsonServer
from service.manager import Manager
from service.storage import Store


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def button(parent, text):
    return next(w for w in descendants(parent) if isinstance(w, ttk.Button) and w.cget("text") == text)


def main():
    artifact_root = Path(__file__).resolve().parents[2] / ".test_artifacts"
    with tempfile.TemporaryDirectory(dir=artifact_root) as name:
        state_root = Path(name) / "manager"
        store = Store(state_root)
        manager = Manager(store, assets=FakeAssets(Path(name)), lifecycle=FakeLifecycle())
        server = JsonServer(("127.0.0.1", 0), store.key, manager.dispatch)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        root = tk.Tk()
        errors = []
        root.report_callback_exception = lambda *error: errors.append(error)
        app = LiveModelManager(root, Client(state_root, server.server_port))

        def until(predicate, seconds=5):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                root.update()
                if predicate():
                    return
                time.sleep(0.02)
            raise AssertionError("Native desktop check timed out")

        checks = 0
        try:
            until(lambda: app.connected and any(m["status"] == "Installed" for m in app.data["models"]))
            for size in ("1280x820", "1040x700", "1600x1000"):
                root.geometry(size)
                for page in app.PAGES:
                    app.show_page(page)
                    root.update()
                    assert app.body.winfo_reqwidth() <= app.scroll.canvas.winfo_width(), (size, page)
                    checks += 1
            app.show_page("Models")
            app.search.set("qwen")
            app._filter_models("Installed")
            root.update()
            assert "Qwen" in " ".join(
                w.cget("text") for w in descendants(app.model_results) if isinstance(w, tk.Label)
            )
            app._provision(next(m for m in app.data["models"] if m["id"] == "qwen3-1.7b"))
            root.update()
            button(app.dialog, "Provision Service").invoke()
            until(lambda: bool(store.snapshot()["services"]))
            app.controller.refresh()
            until(lambda: bool(app.data["services"]))
            app.show_page("Services")
            button(app.body, "Start Service").invoke()
            until(lambda: manager.lifecycle.start_count == 1)
            app.controller.refresh()
            until(lambda: app.data["services"][0]["state"] == "Ready")
            app.show_page("Services")
            button(app.body, "View status").invoke()
            button(app.dialog, "Refresh status").invoke()
            assert app.dialog.winfo_exists()
            assert app.status_detail["fields"]["state"].get() == "Ready"
            assert button(app.dialog, "Configure service").instate(["disabled"])
            assert any(
                f"127.0.0.1:{server.server_port}" in w.cget("text")
                for w in descendants(app.dialog)
                if isinstance(w, tk.Label)
            )
            with patch("desktop.live.messagebox.askyesno", return_value=True):
                button(app.body, "Stop Service").invoke()
            until(lambda: manager.lifecycle.states["llm"]["state"] == "Stopped")
            app.controller.refresh()
            until(lambda: app.data["services"][0]["state"] == "Stopped")
            assert app.status_detail["fields"]["state"].get() == "Stopped"
            assert not button(app.dialog, "Configure service").instate(["disabled"])
            app.dialog.destroy()
            checks += 1
            # Reconfiguration must preserve explicit GPU, custom port and saved runtime options.
            with store.lock:
                config = store.data["services"]["llm"]
                config.update(device="gpu", port=9017)
                config["options"]["cpu_threads"] = 2
                store.save()
            app.controller.refresh()
            until(lambda: app.data["services"][0]["port"] == 9017)
            app._provision(existing=app.data["services"][0])
            root.update()
            button(app.dialog, "Provision Service").invoke()
            until(lambda: store.snapshot()["revision"] == 2)
            config = store.snapshot()["services"]["llm"]
            assert (config["device"], config["port"], config["options"]["cpu_threads"]) == ("gpu", 9017, 2)
            checks += 1
            app.controller.refresh()
            until(lambda: app.data["revision"] == 2)
            app._provision(existing=app.data["services"][0])
            root.update()
            app.connected = False
            button(app.dialog, "Provision Service").invoke()
            assert app.dialog.winfo_exists()  # Preserve entered values when connection is unavailable.
            app.dialog.destroy()
            app.connected = True
            checks += 1
            app.show_page("Logs")
            export = Path(name) / "export.json"
            with patch("desktop.live.filedialog.asksaveasfilename", return_value=str(export)):
                button(app.body, "Export Logs").invoke()
            assert isinstance(json.loads(export.read_text(encoding="utf-8")), list)
            before = store.path.read_bytes()
            with (
                patch("desktop.live.filedialog.asksaveasfilename", return_value=str(store.path)),
                patch("desktop.live.messagebox.showerror") as error,
            ):
                button(app.body, "Export Logs").invoke()
                assert error.called
            assert store.path.read_bytes() == before
            checks += 1
            app.show_page("Settings")
            button(app.body, "Save settings").invoke()
            until(lambda: store.snapshot()["revision"] == 3)
            assert not errors, errors
            checks += 7
            app.close()
            # Closing the UI sends no manager shutdown; its authenticated HTTP endpoint still works.
            assert Client(state_root, server.server_port).request("GET", "/v1/status")["services"]
            checks += 1
            print(f"Native live desktop: {checks} checks passed (HTTP manager; fixture inference engines)")
        finally:
            if not app.controller.closed:
                app.close()
            server.shutdown()
            server.server_close()
            manager.close()
            thread.join()


if __name__ == "__main__":
    main()
