"""Responsive pairing and startup window; all network/model work stays off Tk."""

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from human_test.connection import (
    DEFAULT_PLATFORM,
    ConnectionError,
    PairingClient,
    connection_values,
    read_connection,
)


class PracticeReadyDialog:
    """A dismissible handoff; closing this dialog keeps the prepared session ready."""

    def __init__(self, owner):
        self.owner = owner
        self.window = tk.Toplevel(owner.root)
        self.window.withdraw()
        self.window.title("Ready for Practice")
        self.window.transient(owner.root)
        self.window.resizable(False, False)
        self.window.configure(background="#ffffff")
        self.window.protocol("WM_DELETE_WINDOW", self.dismiss)
        self.window.bind("<Escape>", self.dismiss)
        self.window.bind("<Return>", self.enter)
        style = ttk.Style(self.window)
        style.configure(
            "Ready.TButton",
            background="#087c86",
            foreground="#ffffff",
            font=("Segoe UI", 11, "bold"),
            padding=(20, 12),
            borderwidth=0,
        )
        style.map("Ready.TButton", background=[("active", "#06636b"), ("pressed", "#05545a")])
        style.configure("ReadyInfo.TFrame", background="#f1f6fa")
        style.configure("ReadyInfo.TLabel", background="#f1f6fa", foreground="#172b43", font=("Segoe UI", 10))
        panel = ttk.Frame(self.window, style="Pair.TFrame", padding=28)
        panel.pack(fill="both", expand=True)
        icon = tk.Canvas(panel, width=64, height=64, background="#ffffff", highlightthickness=0)
        icon.pack(pady=(0, 16))
        icon.create_oval(2, 2, 62, 62, fill="#e5f5ef", outline="")
        icon.create_line(19, 32, 28, 41, 46, 23, fill="#087c68", width=4, capstyle="round", joinstyle="round")
        ttk.Label(panel, text="You're ready to practise", style="PairTitle.TLabel").pack()
        ttk.Label(
            panel,
            text="Your device is connected and Practice is ready.",
            style="Pair.TLabel",
            wraplength=430,
            justify="center",
        ).pack(pady=(10, 20))
        if owner.saved:
            identity = ttk.Frame(panel, style="ReadyInfo.TFrame", padding=14)
            identity.pack(fill="x", pady=(0, 20))
            for label, value in (
                ("Tenant", owner.saved["organization_name"]),
                ("Device", owner.saved["device_name"]),
            ):
                ttk.Label(
                    identity,
                    text=f"{label}: {value}",
                    style="ReadyInfo.TLabel",
                    wraplength=400,
                    justify="left",
                ).pack(anchor="w", pady=2)
        self.proceed = ttk.Button(
            panel, text="Proceed to Practice  →", style="Ready.TButton", command=owner.start
        )
        self.proceed.pack(fill="x")
        self.later = ttk.Button(panel, text="Not now", style="Pair.TButton", command=self.dismiss)
        self.later.pack(pady=(10, 0))
        ttk.Label(
            panel,
            text="You can also open Practice from the connection screen.",
            style="Pair.TLabel",
            wraplength=430,
            justify="center",
        ).pack(pady=(16, 0))
        self.window.update_idletasks()
        width = max(500, self.window.winfo_reqwidth())
        height = self.window.winfo_reqheight()
        x = owner.root.winfo_rootx() + (owner.root.winfo_width() - width) // 2
        y = owner.root.winfo_rooty() + (owner.root.winfo_height() - height) // 2
        x = max(0, min(x, self.window.winfo_screenwidth() - width))
        y = max(0, min(y, self.window.winfo_screenheight() - height))
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.deiconify()
        self.window.grab_set()
        self.proceed.focus_set()

    def enter(self, event):
        if isinstance(event.widget, ttk.Button):
            event.widget.invoke()
        else:
            self.owner.start()
        return "break"

    def dismiss(self, _event=None):
        self.owner.ready_dialog = None
        self.window.grab_release()
        self.window.destroy()
        self.owner.primary.focus_set()
        return "break"


class ConnectionWindow:
    def __init__(self, root, factory, *, force=False, manage=False):
        self.root, self.factory = root, factory
        self.events = queue.Queue()
        self.cancelled = threading.Event()
        self.busy = False
        self.result = None
        self.ready_dialog = None
        self.ready_prompt_shown = False
        self.saved = None
        self.legacy = None
        self.error = ""
        try:
            self.saved = read_connection()
        except ConnectionError as error:
            self.error = str(error)
        if not self.saved and not force:
            from demo import HERE
            from external_pms import load_external

            try:
                self.legacy = load_external(HERE)
            except RuntimeError:
                pass
        if force:
            self.saved = None
        root.title("Human-test · Connect your device")
        root.geometry("860x820")
        root.minsize(720, 760)
        root.configure(background="#edf2f7")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Pair.TFrame", background="#ffffff")
        style.configure("Pair.TLabel", background="#ffffff", foreground="#172b43", font=("Segoe UI", 10))
        style.configure(
            "PairTitle.TLabel", background="#ffffff", foreground="#102b45", font=("Segoe UI", 21, "bold")
        )
        style.configure(
            "PairStep.TLabel", background="#ffffff", foreground="#087c86", font=("Segoe UI", 10, "bold")
        )
        style.configure("PairError.TLabel", background="#ffffff", foreground="#9b2636", font=("Segoe UI", 10))
        style.configure("Pair.TButton", font=("Segoe UI", 10), padding=(18, 10))
        style.configure("Pair.TEntry", padding=8)
        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True, padx=18, pady=18)
        panel = ttk.Frame(self.tabs, padding=24, style="Pair.TFrame")
        self.tabs.add(panel, text="Device connection")
        ttk.Label(panel, text="PATIENT PRACTICE", style="PairStep.TLabel").pack(anchor="w")
        ttk.Label(panel, text="Connect your device", style="PairTitle.TLabel").pack(anchor="w", pady=(10, 7))
        ttk.Label(
            panel,
            text="Pair once with the platform. Your device will reconnect automatically.",
            style="Pair.TLabel",
            wraplength=590,
        ).pack(anchor="w")
        self.steps = tk.StringVar(value="1  Connect     →     2  Enroll device     →     3  Prepare Practice")
        ttk.Label(panel, textvariable=self.steps, style="PairStep.TLabel").pack(anchor="w", pady=(20, 14))
        self.form = ttk.Frame(panel, style="Pair.TFrame")
        self.form.pack(fill="x")
        self.address = tk.StringVar(value=(self.saved or {}).get("pms_url", DEFAULT_PLATFORM))
        self.identifier = tk.StringVar(value=(self.saved or {}).get("device_unique_id", ""))
        self.token = tk.StringVar()
        self.entries = []
        for label, variable, limit, masked in (
            ("Platform address", self.address, 2048, False),
            ("Device unique ID or registration UUID", self.identifier, 50, False),
            ("Enrollment token", self.token, 256, True),
        ):
            ttk.Label(self.form, text=label, style="Pair.TLabel").pack(anchor="w", pady=(8, 4))
            validate = (root.register(lambda value, maximum=limit: len(value) <= maximum), "%P")
            entry = ttk.Entry(
                self.form,
                textvariable=variable,
                show="•" if masked else "",
                style="Pair.TEntry",
                validate="key",
                validatecommand=validate,
            )
            entry.pack(fill="x")
            self.entries.append(entry)
        ttk.Label(
            self.form,
            text="Get an enrollment token from the tenant's Devices page. It expires after 15 minutes.",
            style="Pair.TLabel",
            wraplength=590,
        ).pack(anchor="w", pady=(8, 4))
        self.binding = tk.StringVar()
        ttk.Label(panel, textvariable=self.binding, style="Pair.TLabel", wraplength=590).pack(
            anchor="w", pady=(10, 0)
        )
        self.clear_button = ttk.Button(panel, text="Clear saved provisioning", command=self.clear)
        self.clear_button.pack(anchor="w", pady=(8, 0))
        self.state = tk.StringVar(value=self.error or "Enter the device ID and token to connect.")
        ttk.Label(panel, textvariable=self.state, style="Pair.TLabel", wraplength=590).pack(
            anchor="w", pady=(16, 8)
        )
        self.progress = ttk.Progressbar(panel, mode="indeterminate")
        self.progress.pack(fill="x")
        self.details = tk.StringVar()
        ttk.Label(panel, textvariable=self.details, style="PairError.TLabel", wraplength=590).pack(
            anchor="w", pady=(8, 8)
        )
        footer = ttk.Frame(panel, style="Pair.TFrame")
        footer.pack(side="bottom", fill="x", pady=(14, 0))
        self.secondary = ttk.Button(
            footer, text="Change connection", style="Pair.TButton", command=self.change
        )
        self.secondary.pack(side="left")
        self.cancel_button = ttk.Button(footer, text="Close", style="Pair.TButton", command=self.close)
        self.cancel_button.pack(side="right")
        self.primary = ttk.Button(footer, text="Connect & start", style="Pair.TButton", command=self.start)
        self.primary.pack(side="right", padx=8)
        ttk.Label(
            panel,
            text="Start assigned services in Manage Local Models separately. Human-test only connects to running inference services.",
            style="Pair.TLabel",
            wraplength=590,
        ).pack(anchor="w", pady=(8, 0))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Return>", self.enter)
        self.show_saved()
        self.poll_id = root.after(80, self.poll)
        self.auto_id = None
        root.bind("<Destroy>", self.destroyed, add="+")
        if (self.saved or self.legacy) and not manage:
            self.auto_id = root.after(150, self.start)

    def destroyed(self, event):
        if event.widget is self.root:
            for timer in (self.poll_id, self.auto_id):
                if timer:
                    self.root.after_cancel(timer)

    def enter(self, _event=None):
        if self.tabs.select() == self.tabs.tabs()[0] and not self.busy:
            self.start()

    def clear(self):
        if self.busy or self.result:
            return
        if not messagebox.askyesno(
            "Clear device provisioning",
            "Remove this desktop's saved device credential and desktop connection settings?\n\nInstalled models, recordings and history are kept. The platform device registration remains; use a new enrollment token to pair again.",
            parent=self.root,
        ):
            return
        from demo import ROOT
        from provisioning import reset_connection

        try:
            reset_connection(ROOT)
        except RuntimeError as error:
            self.details.set(str(error))
            return
        except Exception:
            self.details.set(
                "Could not clear provisioning. Close other app windows and check folder permissions."
            )
            return
        self.saved = self.legacy = None
        self.identifier.set("")
        self.token.set("")
        self.details.set("")
        self.state.set("Provisioning cleared. Enter the device ID and a new enrollment token.")
        self.show_saved()

    def show_saved(self):
        if self.saved or self.legacy:
            self.form.pack_forget()
            self.primary.configure(text="Retry connection")
            if self.saved:
                self.binding.set(
                    f"Tenant: {self.saved['organization_name']}\nDevice: {self.saved['device_name']} ({self.saved['device_unique_id']})"
                )
            else:
                self.binding.set("Checking your existing desktop configuration…")
        else:
            self.binding.set("")
            self.form.pack(fill="x", after=self.form.master.winfo_children()[3])
            self.primary.configure(text="Connect & start")

    def change(self):
        if self.busy:
            return
        self.saved = self.legacy = None
        self.details.set("")
        self.state.set("Enter the device ID and a new enrollment token.")
        self.show_saved()

    def emit(self, text):
        self.events.put(("progress", text))

    def start(self):
        if self.busy or self.cancelled.is_set():
            return
        if self.result:
            if self.ready_dialog:
                self.ready_dialog.dismiss()
            self.root.destroy()
            return
        # Tk values are read only on the Tk thread.
        address, identifier, token = self.address.get(), self.identifier.get(), self.token.get()
        saved, legacy = self.saved, self.legacy
        self.busy = True
        self.details.set("")
        self.progress.start(12)
        for widget in (*self.entries, self.primary, self.secondary, self.clear_button):
            widget.configure(state="disabled")
        self.cancel_button.configure(text="Cancel")
        self.worker = threading.Thread(
            target=self.work, args=(address, identifier, token, saved, legacy), daemon=True
        )
        self.worker.start()

    def work(self, address, identifier, token, saved, legacy):
        import startup
        from demo import HERE
        from external_pms import ExternalPMS

        demo = None
        startup.progress_reporter = lambda state, detail: self.emit(detail)
        try:
            if self.cancelled.is_set():
                return
            demo = self.factory()
            demo.acquire_ownership()
            if legacy:
                settings = legacy
            else:
                client = PairingClient(saved["pms_url"] if saved else address)
                client.cancelled = self.cancelled.is_set
                try:
                    with startup.phase("Reconnect saved device" if saved else "Enroll and save device"):

                        def progress(detail):
                            startup.message("CHECK", detail)

                        data = (
                            client.resume(saved, progress)
                            if saved
                            else client.pair(identifier, token, progress)
                        )
                finally:
                    client.close()
                self.events.put(("paired", data))
                settings = ExternalPMS(_env_file=HERE / ".env", **connection_values(data))
            if self.cancelled.is_set():
                return
            self.emit("Checking assigned models and connecting to central inference…")
            demo.external_settings = settings
            demo.services.cancelled = self.cancelled.is_set
            values = demo.start()
            if self.cancelled.is_set():
                return
            self.events.put(("ready", (demo, values)))
            demo = None  # Ownership passes to the main launcher.
        except startup.StopRequested:
            startup.message("STOP", "Setup cancelled; saved enrollment is retained")
        except Exception as error:
            if demo is not None:
                demo.failed = True
            startup.record_failure("Connect and prepare desktop", error)
            message = (
                str(error)
                if isinstance(error, RuntimeError)
                else "Setup could not finish. See human-test/.local/platform-client/launcher.log for the failure trace."
            )
            self.events.put(("error", message))
        finally:
            # Cleanup progress must not overwrite the actual failure shown to the user.
            startup.progress_reporter = None
            if demo is not None:
                try:
                    demo.close()
                except Exception as error:
                    startup.record_failure("Close desktop connection", error)
                    self.events.put(
                        (
                            "error",
                            "The desktop connection could not close. Check the launcher log before retrying.",
                        )
                    )
            startup.progress_reporter = None
            self.events.put(("finished", None))

    def poll(self):
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                self.state.set(value)
            elif kind == "paired":
                self.saved = value
                self.token.set("")
                self.show_saved()
            elif kind == "ready":
                self.result = value
                self.state.set("Connected. Assigned models and Practice access are ready.")
                self.steps.set("✓  Connected     ✓  Enrolled     ✓  Practice ready")
            elif kind == "error":
                self.state.set("Setup needs attention")
                self.details.set(value)
                self.token.set("")
            elif kind == "finished":
                self.busy = False
                self.progress.stop()
                for widget in (*self.entries, self.primary, self.secondary, self.clear_button):
                    widget.configure(state="normal")
                self.cancel_button.configure(text="Close")
                if self.result:
                    self.primary.configure(text="Open Practice")
                    self.secondary.configure(state="disabled")
                    self.clear_button.configure(state="disabled")
                if self.cancelled.is_set():
                    self.root.destroy()
                    return
                if self.result and not self.ready_prompt_shown:
                    self.ready_prompt_shown = True
                    self.ready_dialog = PracticeReadyDialog(self)
        self.poll_id = self.root.after(80, self.poll)

    def close(self):
        if self.ready_dialog:
            self.ready_dialog.dismiss()
        self.cancelled.set()
        if self.busy:
            self.state.set("Finishing the current connection request…")
            self.cancel_button.configure(state="disabled")
        else:
            self.root.destroy()


def launch(factory, *, force=False, manage=False):
    root = tk.Tk()
    window = ConnectionWindow(root, factory, force=force, manage=manage)
    root.mainloop()
    if window.cancelled.is_set():
        if window.result:
            window.result[0].close()
        return None
    return window.result
