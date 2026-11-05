"""Native Tk regression: responsive pairing, retained enrollment, retry and layout."""

import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import connection_window


def main():
    paired = dict(
        version=1,
        pms_url="https://platform.example",
        device_id=str(uuid4()),
        device_unique_id="Desk01",
        device_name="Training device",
        organization_id=str(uuid4()),
        organization_name="Training tenant",
        department_id=None,
        credential="dev_fixture",
    )
    release = threading.Event()
    calls = []
    demos = []

    class Pairing:
        def __init__(self, *args):
            pass

        def pair(self, identifier, token, progress):
            calls.append("pair")
            progress("Enrolling this device...")
            assert release.wait(5)
            return paired

        def resume(self, saved, progress):
            calls.append("resume")
            return saved

        def close(self):
            pass

    class Demo:
        def __init__(self):
            demos.append(self)
            self.services = SimpleNamespace()
            self.closed = False

        def acquire_ownership(self):
            pass

        def start(self):
            if len(demos) == 1:
                raise RuntimeError("Install the assigned local model, then retry.")
            return {"ready": "yes"}

        def close(self):
            self.closed = True

    def pump(until, seconds=5):
        deadline = time.monotonic() + seconds
        while not until():
            root.update()
            assert time.monotonic() < deadline, "Tk operation did not finish"
            time.sleep(0.01)
        root.update()

    with (
        patch.object(connection_window, "read_connection", return_value=None),
        patch.object(connection_window, "PairingClient", Pairing),
    ):
        root = tk.Tk()
        window = connection_window.ConnectionWindow(root, Demo, force=True)
        root.geometry("650x650")
        root.update()
        window.entries[1].insert(0, "x" * 51)
        assert window.identifier.get() == ""
        window.identifier.set("Desk01")
        window.token.set("enr_" + "x" * 32)
        for button in (window.primary, window.secondary, window.cancel_button):
            assert button.winfo_ismapped(), "Action must be visible at minimum size"
            assert button.winfo_rooty() + button.winfo_height() <= root.winfo_rooty() + root.winfo_height()
        window.start()
        pump(lambda: "Enrolling" in window.state.get())
        assert window.busy and window.primary.instate(["disabled"])
        release.set()
        pump(lambda: not window.busy)
        assert window.saved == paired and window.token.get() == ""
        assert "Install" in window.details.get() and demos[0].closed
        assert window.ready_dialog is None, "Failed preparation must not offer to proceed"
        assert len(window.tabs.tabs()) == 1, "Human-test must expose no model-management tab"
        assert not hasattr(window, "offline")
        window.start()
        pump(lambda: not window.busy)
        assert calls == ["pair", "resume"], "Startup retry must reuse enrollment"
        assert window.result and window.primary.cget("text") == "Open Practice"
        dialog = window.ready_dialog
        assert dialog and dialog.window.winfo_ismapped()
        assert root.grab_current() is dialog.window
        for button in (dialog.proceed, dialog.later):
            assert button.winfo_ismapped()
            assert button.winfo_rooty() + button.winfo_height() <= (
                dialog.window.winfo_rooty() + dialog.window.winfo_height()
            )
        # The title-bar close only dismisses the invitation, preserving ready services.
        dialog.window.tk.call(dialog.window.protocol("WM_DELETE_WINDOW"))
        root.update()
        assert window.ready_dialog is None and root.grab_current() is None
        assert window.result and not window.cancelled.is_set() and not demos[-1].closed
        assert window.primary.winfo_ismapped() and not window.primary.instate(["disabled"])
        started = time.monotonic()
        pump(lambda: time.monotonic() - started > 0.2)
        assert window.ready_dialog is None, "Polling must not reopen a dismissed dialog"
        window.close()
        assert window.cancelled.is_set()
        window.result[0].close()
    # Automatic reconnect prompts once, then hands the same prepared session to Practice.
    for action in ("proceed", "not_now", "escape"):
        with (
            patch.object(connection_window, "read_connection", return_value=paired),
            patch.object(connection_window, "PairingClient", Pairing),
        ):
            root = tk.Tk()
            window = connection_window.ConnectionWindow(root, Demo)
            pump(lambda current=window: current.ready_dialog is not None)
            dialog = window.ready_dialog
            prepared = window.result
            assert not window.busy and calls[-1] == "resume"
            if action == "proceed":
                dialog.proceed.invoke()
            else:
                if action == "not_now":
                    dialog.later.invoke()
                else:
                    dialog.window.focus_force()
                    dialog.window.event_generate("<Escape>")
                root.update()
                assert window.ready_dialog is None and root.winfo_exists()
                assert not window.cancelled.is_set() and window.result is prepared
                window.primary.invoke()
            assert not window.cancelled.is_set() and window.result is prepared
            assert not prepared[0].closed, "Proceed transfers ownership without stopping services"
            prepared[0].close()
    with (
        patch.object(connection_window, "read_connection", return_value=paired),
        patch("provisioning.reset_connection") as reset,
        patch.object(connection_window.messagebox, "askyesno", return_value=True),
    ):
        root = tk.Tk()
        window = connection_window.ConnectionWindow(root, Demo, manage=True)
        started = time.monotonic()
        pump(lambda: time.monotonic() - started > 0.3)
        assert not window.busy and window.saved == paired, "Manage must not automatically connect"
        window.clear_button.invoke()
        root.update()
        reset.assert_called_once()
        assert not window.saved and window.form.winfo_ismapped()
        assert "Provisioning cleared" in window.state.get()
        window.close()
    # Closing during a read-only readiness check cancels only the connection work.
    with (
        patch.object(connection_window, "read_connection", return_value=paired),
        patch.object(connection_window, "PairingClient", Pairing),
    ):
        root = tk.Tk()
        failures = []
        root.report_callback_exception = lambda *error: failures.append(error)
        stopped = threading.Event()

        class WaitingDemo(Demo):
            def start(self):
                deadline = time.monotonic() + 5
                while not self.services.cancelled():
                    assert time.monotonic() < deadline
                    time.sleep(0.01)
                stopped.set()
                raise RuntimeError("Connection cancelled")

        window = connection_window.ConnectionWindow(root, WaitingDemo, manage=True)
        window.start()
        root.after(100, window.close)
        root.after(5000, root.quit)
        root.mainloop()
        assert stopped.is_set() and window.cancelled.is_set() and not failures
    # The actual desktop header exposes a single icon and uses normal cleanup.
    from human_test import app
    from human_test.config import Settings

    async def initialize(self):
        pass

    with (
        patch.object(app.Window, "initialize", initialize),
        patch.object(app.messagebox, "askyesno", return_value=True),
    ):
        root = tk.Tk()
        window = app.Window(root, Settings(_env_file=None, speaker_output=False))
        root.update()
        assert window.provision_button.cget("text") == "⚙"
        assert window.provision_button.winfo_ismapped()
        previous_status = window.health.get()
        window.provision_button.event_generate("<Enter>")
        root.update()
        assert window.health.get() == previous_status
        window.provision_button.event_generate("<Leave>")
        root.after(100, window.provision_button.invoke)
        root.mainloop()
        assert window.reopen_provisioning and window.closing
    print(
        "Pairing, read-only model connection, cancellation, setup/reset, layout and enrollment retry passed"
    )


if __name__ == "__main__":
    main()
