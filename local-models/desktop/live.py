"""Live desktop controls; all long work and inference run outside Tk."""

import datetime as dt
import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from service.contracts import BOUNDS, CAPABILITIES, integer, runtime_option_names, settings
from service.errors import ManagerError
from service.security import LOCAL_ROOT, REPO_ROOT, checked
from service.storage import DEFAULTS, runtime_defaults

from . import theme as t
from .app import ModelManager
from .icons import Icon
from .manager_client import Controller
from .preferences import default_device, inventory_state, preferred_model


class LiveModelManager(ModelManager):
    def __init__(self, root, client=None):
        self.data = {
            "models": [],
            "services": [],
            "logs": [],
            "operations": [],
            "settings": DEFAULTS,
            "revision": 0,
            "hardware": {"gpus": []},
        }
        self.connected = False
        self.loaded = False
        self.loading_error = False
        self.loading_progress = None
        self.status_detail = None
        self.fingerprint = None
        self.message = tk.StringVar(root, "Connecting to local manager…")
        self.connection = tk.StringVar(root, "Loading")
        super().__init__(root)
        self.controller = Controller(root, self._snapshot, self.message.set, client, self._disconnected)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def _disconnected(self, message):
        changed = self.loaded or not self.loading_error
        self.connected = False
        self.loaded = False
        self.loading_error = True
        self.connection.set("Manager unavailable")
        self.message.set(message)
        self._update_service_detail()
        if changed:
            self.show_page(self.page)

    def show_page(self, page):
        self._stop_loading()
        super().show_page(page)

    def _stop_loading(self):
        if self.loading_progress is not None:
            if self.loading_progress.winfo_exists():
                self.loading_progress.stop()
            self.loading_progress = None

    def _page_content(self, page):
        if self.loaded:
            super()._page_content(page)
            return
        panel = t.card(self.body, padx=28, pady=30)
        panel.pack(fill="x", pady=(8, 0))
        Icon(panel, "models", size=32).pack(anchor="w", pady=(0, 16))
        title = "Could not load local models" if self.loading_error else "Loading local models"
        t.label(panel, title, size=18, bold=True).pack(anchor="w")
        t.label(
            panel,
            "Please wait while models, service configurations and GPU availability are checked."
            if not self.loading_error
            else "Check the manager connection and retry. Your model assets and services are preserved.",
            color=t.MUTED,
            wraplength=620,
            justify="left",
        ).pack(anchor="w", pady=(12, 20))
        if self.loading_error:
            t.button(panel, "Try again", self._retry_loading, primary=True).pack(anchor="w")
        else:
            self.loading_progress = ttk.Progressbar(panel, mode="indeterminate", maximum=100)
            self.loading_progress.pack(fill="x", pady=(0, 8))
            self.loading_progress.start(12)
            t.label(panel, "Checking installed models can take a little time.", size=9, color=t.MUTED).pack(
                anchor="w", pady=(8, 0)
            )

    def _retry_loading(self):
        if self.connected:
            if not self._action("refresh"):
                return
        else:
            self.controller.reconnect()
        self.loading_error = False
        self.connection.set("Loading")
        self.message.set("Loading local models and services. Please wait...")
        self.show_page(self.page)

    def _shell(self):
        super()._shell()

        def replace(parent):
            for widget in parent.winfo_children():
                if isinstance(widget, tk.Label):
                    text = widget.cget("text")
                    if text == "UI preview · v0.1":
                        widget.configure(text="LOCAL MODEL MANAGER · v0.2")
                    elif text == "Interface preview":
                        widget.configure(textvariable=self.connection)
                    elif text.startswith("UI preview · Models"):
                        widget.configure(
                            text="Background inference continues when this window closes. Windows service and reboot auto-start are queued."
                        )
                    elif text.startswith("Preview only · Downloads"):
                        widget.configure(textvariable=self.message, wraplength=760)
                replace(widget)

        replace(self.root)

    def _snapshot(self, data):
        was_loaded, was_failed = self.loaded, self.loading_error
        self.connected = True
        state = inventory_state(data)
        self.loaded = state == "ready"
        self.loading_error = state == "failed"
        self.connection.set(
            "Loading"
            if state == "loading"
            else "Model check failed"
            if self.loading_error
            else "Manager read only"
            if data.get("metadata_error")
            else "Manager connected"
        )
        fingerprint = json.dumps(
            {k: data[k] for k in ("models", "services", "revision", "hardware")}, sort_keys=True
        )
        changed = self.fingerprint != fingerprint
        self.fingerprint = fingerprint
        self.data = data
        self._update_service_detail()
        if not self.loaded:
            self.message.set(
                "Model verification failed. Refresh / diagnose to retry."
                if self.loading_error
                else "Loading models and services. Please wait..."
            )
        elif not was_loaded:
            self.message.set("Models and services loaded")
        if was_loaded != self.loaded or was_failed != self.loading_error:
            self.show_page(self.page)
        elif not self.loaded:
            return
        elif self.page == "Logs":
            self._render_logs()
        elif changed and self.page == "Models":
            self._render_models()
        elif changed and self.page in {"Overview", "Services"}:
            self.show_page(self.page)

    def _action(self, name, payload=None, revision=False):
        if self.data.get("metadata_error"):
            self.message.set(self.data["metadata_error"])
            return False
        if not self.connected:
            self.message.set("Connect to the local manager before making changes")
            return False
        if not self.loaded and name != "refresh":
            self.message.set("Wait for local models and services to finish loading")
            return False
        payload = dict(payload or {})
        if revision:
            payload["revision"] = self.data["revision"]
        self.controller.action(name, payload)
        return True

    def _overview(self):
        actions = tk.Frame(self.body, bg=t.BG)
        actions.pack(fill="x", pady=(0, 22))
        t.button(actions, "Download models", lambda: self.show_page("Models"), primary=True).pack(
            side="left", padx=(0, 8)
        )
        t.button(actions, "Provision service", self._provision).pack(side="left", padx=(0, 8))
        t.button(actions, "Refresh / diagnose", lambda: self._action("refresh")).pack(
            side="left", padx=(0, 8)
        )
        t.button(actions, "Reconnect", lambda: self.controller.reconnect()).pack(side="left")
        gpus = self.data["hardware"].get("gpus", [])
        metrics = (
            (
                "Compute",
                gpus[0]["name"] if gpus else "CPU available",
                self.data["hardware"].get("gpu_probe", "Checking GPU"),
            ),
            (
                "Installed models",
                str(sum(m["status"] == "Installed" for m in self.data["models"])),
                "Checksum-verified asset inventory",
            ),
            (
                "Ready services",
                str(sum(s.get("ready", False) for s in self.data["services"])),
                "Readiness follows model loading and warmup",
            ),
        )
        for title, value, detail in metrics:
            panel = t.card(self.body, padx=20, pady=16)
            panel.pack(fill="x", pady=(0, 10))
            t.label(panel, title, size=9, color=t.MUTED).pack(anchor="w")
            t.label(panel, value, size=17, bold=True, wraplength=650).pack(anchor="w", pady=6)
            t.label(panel, detail, size=9, color=t.MUTED).pack(anchor="w")
        self._section(
            self.body,
            "Background inference",
            "The desktop, manager and model workers have separate lifetimes.",
        )
        for service in self.data["services"]:
            panel = self._service_card(self.body, service)
            panel.pack(fill="x", pady=(0, 12))
        if not self.data["services"]:
            t.label(
                self.body, "Download models, then provision the capabilities you need.", color=t.MUTED
            ).pack(anchor="w")

    def _render_models(self):
        for child in self.model_results.winfo_children():
            child.destroy()
        if self.model_filter == "Video":
            self._empty_video(self.model_results)
            return
        query = self.search.get().strip().casefold()
        items = [
            m
            for m in self.data["models"]
            if (
                self.model_filter == "All"
                or m["category"] == self.model_filter
                or self.model_filter == "Installed"
                and m["status"] == "Installed"
            )
            and query in (m["name"] + " " + m["detail"]).casefold()
        ]
        if not items:
            t.label(
                self.model_results,
                "No matching models" if self.connected else "Connecting and checking installed models…",
                color=t.MUTED,
            ).pack(anchor="w")
            return
        grid = tk.Frame(self.model_results, bg=t.BG)
        grid.pack(fill="x")
        self._responsive_grid(grid, [self._model_card(grid, model) for model in items])

    def _model_card(self, parent, model):
        panel = t.card(parent, padx=18, pady=18)
        Icon(panel, model["kind"], size=28).pack(anchor="w", pady=(0, 10))
        t.badge(panel, model["status"]).pack(anchor="w", pady=(0, 10))
        t.label(panel, model["name"], size=14, bold=True, wraplength=290).pack(anchor="w")
        t.label(panel, model["detail"] + " · " + model["format"], color=t.MUTED, size=9, wraplength=290).pack(
            anchor="w", pady=(8, 8)
        )
        t.label(panel, model["device"] + " · " + model["size"], size=9, wraplength=290).pack(
            anchor="w", pady=(0, 16)
        )
        actions = tk.Frame(panel, bg=t.WHITE)
        actions.pack(fill="x")
        t.button(actions, "View details", lambda: self._model_detail(model)).pack(side="left")
        installed = model["status"] == "Installed"
        t.button(
            actions,
            "Provision" if installed else "Download",
            lambda: self._provision(model) if installed else self._model_detail(model),
            disabled=model["status"] == "Checking",
        ).pack(side="right")
        return panel

    def _services(self):
        actions = tk.Frame(self.body, bg=t.BG)
        actions.pack(fill="x", pady=(0, 22))
        t.button(actions, "Provision service", self._provision, primary=True).pack(side="left", padx=(0, 8))
        t.button(actions, "Refresh status", lambda: self.controller.refresh()).pack(side="left")
        if not self.data["services"]:
            t.label(self.body, "No services provisioned yet.", color=t.MUTED).pack(anchor="w")
        grid = tk.Frame(self.body, bg=t.BG)
        grid.pack(fill="x")
        self._responsive_grid(grid, [self._service_card(grid, service) for service in self.data["services"]])

    def _service_card(self, parent, service):
        panel = t.card(parent, padx=18, pady=18)
        Icon(panel, service["kind"], size=28).pack(anchor="w", pady=(0, 10))
        t.badge(panel, service["state"]).pack(anchor="w", pady=(0, 10))
        t.label(panel, service["name"], size=14, bold=True).pack(anchor="w")
        t.label(panel, service["model"], size=9, color=t.MUTED, wraplength=290).pack(anchor="w", pady=(8, 8))
        t.label(panel, service["device"].upper() + " · localhost:" + str(service["port"]), size=9).pack(
            anchor="w", pady=(0, 16)
        )
        actions = tk.Frame(panel, bg=t.WHITE)
        actions.pack(fill="x")
        t.button(actions, "View status", lambda: self._service_detail(service)).pack(anchor="w", pady=(0, 8))
        t.button(
            actions,
            "Start Service",
            lambda: self._start(service),
            primary=True,
            disabled=service.get("busy", False) or service["state"] not in {"Stopped", "Failed"},
        ).pack(side="left", padx=(0, 8))
        t.button(
            actions,
            "Stop Service",
            lambda: self._stop(service),
            disabled=service.get("busy", False) or service["state"] in {"Stopped", "Failed", "Checking"},
        ).pack(side="left")
        t.button(panel, "View Logs", lambda s=service: self._open_logs(s["capability"])).pack(
            anchor="w", pady=(12, 0)
        )
        return panel

    def _start(self, service):
        self._action("start", {"capability": service["capability"]}, True)

    def _stop(self, service):
        if messagebox.askyesno(
            "Stop inference service",
            "Stop "
            + service["name"]
            + "? Active inference will drain first. Model assets will stay installed.",
            parent=self.root,
        ):
            self._action("stop", {"capability": service["capability"]}, True)

    def _dialog(self, title, subtitle):
        self.status_detail = None
        body, actions = super()._dialog(title, subtitle)
        body.winfo_children()[0].destroy()  # The base class provides the explicit preview layout.
        return body, actions

    def _model_detail(self, model):
        body, actions = self._dialog(model["name"], model["detail"])
        for name in ("format", "size", "languages", "license", "status", "location", "error"):
            if name in model:
                self._field(body, name.title(), model[name])
        device = tk.StringVar(body, default_device(model))
        t.label(body, "Prepare runtime for", bold=True).pack(anchor="w", pady=(20, 8))
        ttk.Combobox(
            body,
            textvariable=device,
            values=("cpu", "gpu") if model["gpu_supported"] else ("cpu",),
            state="readonly",
        ).pack(fill="x")
        t.label(
            body,
            "Downloads require network access and disk space. Existing verified models are reused. Progress appears in the window footer.",
            color=t.MUTED,
            size=9,
            wraplength=490,
        ).pack(anchor="w", pady=14)

        def download():
            if self._action("download", {"model_id": model["id"], "device": device.get()}):
                self.dialog.destroy()

        t.button(
            actions,
            "Prepare runtime" if model["status"] == "Installed" else "Download model",
            download,
            primary=True,
            disabled=model["status"] == "Checking",
        ).pack(side="left")

    def _service_detail(self, service):
        body, actions = self._dialog(service["name"], "Current state from the background manager")
        capability = service["capability"]
        fields = {}
        for name in (
            "state",
            "model",
            "configured_device",
            "device",
            "port",
            "active",
            "load_seconds",
            "offloaded_layers",
            "error",
        ):
            fields[name] = tk.StringVar(body)
            self._field(body, name.replace("_", " ").title(), "").configure(textvariable=fields[name])
        self._field(
            body,
            "Inference route",
            f"/v1/infer/{capability} (authenticated manager on 127.0.0.1:{self.controller.client.port})",
        )
        self._field(body, "Windows service / boot", "Queued for next phase")
        t.button(body, "Refresh status", self.controller.refresh).pack(anchor="w", pady=14)

        def configure():
            current = next((s for s in self.data["services"] if s["capability"] == capability), None)
            if current:
                self._provision(existing=current)

        configure_button = t.button(
            body,
            "Configure service",
            configure,
        )
        configure_button.pack(anchor="w", pady=(0, 10))

        def remove():
            if messagebox.askyesno(
                "Remove service configuration",
                "Remove this stopped service configuration? Model files will stay installed.",
                parent=self.dialog,
            ):
                if self._action("remove", {"capability": capability}, True):
                    self.dialog.destroy()

        remove_button = t.button(actions, "Remove configuration", remove)
        remove_button.pack(side="left")
        self.status_detail = {
            "capability": capability,
            "fields": fields,
            "buttons": (configure_button, remove_button),
        }
        self._update_service_detail()

    def _update_service_detail(self):
        detail = self.status_detail
        if not detail or self.dialog is None or not self.dialog.winfo_exists():
            return
        current = next((s for s in self.data["services"] if s["capability"] == detail["capability"]), None)
        for name, variable in detail["fields"].items():
            value = current.get(name, "—") if current else "—"
            if name == "state":
                value = value if self.connected else "Manager unavailable"
                if self.connected and not current:
                    value = "Configuration removed"
            variable.set(str(value))
        can_edit = (
            self.connected
            and self.loaded
            and not self.data.get("metadata_error")
            and current
            and not current.get("busy")
            and current["state"] in {"Stopped", "Failed"}
        )
        for button in detail["buttons"]:
            button.configure(state="normal" if can_edit else "disabled")

    def _provision(self, chosen=None, existing=None):
        if not self.loaded:
            self.message.set("Wait for installed models to finish loading before provisioning")
            return
        installed = [m for m in self.data["models"] if m["status"] == "Installed"]
        body, actions = self._dialog(
            "Provision service",
            "Provisioning saves a worker configuration. Use Start Service to load the model.",
        )
        if not installed:
            t.label(body, "Download and verify a model before provisioning.", color=t.MUTED).pack(anchor="w")
            return
        if existing and not any(m["id"] == existing["model_id"] for m in installed):
            t.label(
                body,
                "The configured model needs verification. Download or repair it before changing this service.",
                color=t.MUTED,
                wraplength=490,
            ).pack(anchor="w")
            return
        initial_kind = (
            existing["capability"]
            if existing
            else chosen["capability"]
            if chosen
            else next(m["capability"] for m in installed if m["id"] == preferred_model(installed))
        )
        existing = existing or next(
            (s for s in self.data["services"] if s["capability"] == initial_kind), None
        )
        kind = tk.StringVar(body, initial_kind)
        selected = tk.StringVar(body)
        device = tk.StringVar(
            body, existing.get("configured_device", existing["device"]) if existing else "gpu"
        )
        port = tk.StringVar(body)
        revision = self.data["revision"]
        options = {}
        defaults = runtime_defaults(self.data)
        saved_services = {service["capability"]: service for service in self.data["services"]}
        if existing:
            saved_services[existing["capability"]] = existing
        base_options = {
            capability: {**defaults, **saved_services.get(capability, {}).get("options", {})}
            for capability in CAPABILITIES
        }
        option_vars = {
            capability: {name: tk.StringVar(body, str(value)) for name, value in values.items()}
            for capability, values in base_options.items()
        }
        previous_model = None
        for title, variable, values in (
            ("Capability", kind, tuple(CAPABILITIES)),
            ("Model", selected, ()),
            ("Execution", device, ("cpu", "gpu")),
        ):
            t.label(body, title, bold=True).pack(anchor="w", pady=(12, 6))
            control = ttk.Combobox(body, textvariable=variable, values=values, state="readonly")
            control.pack(fill="x")
            if title == "Model":
                model_control = control
            if title == "Execution":
                device_control = control
        t.label(body, "Loopback worker port", bold=True).pack(anchor="w", pady=(12, 6))
        ttk.Entry(body, textvariable=port).pack(fill="x")
        t.label(body, "Runtime options", bold=True).pack(anchor="w", pady=(18, 6))
        runtime_panel = tk.Frame(body, bg=t.WHITE)
        runtime_panel.pack(fill="x")

        def render_options(*_):
            for child in runtime_panel.winfo_children():
                child.destroy()
            options.clear()
            model = next((item for item in installed if item["id"] == selected.get()), None)
            for name in runtime_option_names(kind.get(), device.get(), model):
                lower, upper = BOUNDS[name]
                line = tk.Frame(runtime_panel, bg=t.WHITE)
                line.pack(fill="x", pady=3)
                t.label(line, name.replace("_", " ").title(), size=9).pack(side="left")
                options[name] = option_vars[kind.get()][name]
                ttk.Spinbox(line, from_=lower, to=upper, width=9, textvariable=options[name]).pack(
                    side="right"
                )

        def update(*_):
            choices = [model for model in installed if model["capability"] == kind.get()]
            model_control.configure(values=[model["id"] for model in choices])
            saved = saved_services.get(kind.get())
            selected.set(preferred_model(choices, saved["model_id"] if saved else None))
            port.set(str(saved["port"] if saved else CAPABILITIES[kind.get()][2]))
            device.set(saved.get("configured_device", saved["device"]) if saved else "gpu")
            model_changed()

        def model_changed(*_):
            nonlocal previous_model
            model = next((item for item in installed if item["id"] == selected.get()), None)
            device_control.configure(values=("cpu", "gpu") if model and model["gpu_supported"] else ("cpu",))
            if default_device(model) == "cpu":
                device.set("cpu")
            elif previous_model and not previous_model["gpu_supported"]:
                device.set("gpu")
            previous_model = model
            render_options()

        kind.trace_add("write", update)
        selected.trace_add("write", model_changed)
        device.trace_add("write", render_options)
        update()
        if chosen:
            selected.set(chosen["id"])
        ttk.Checkbutton(body, text="Start when the machine boots (queued)", state="disabled").pack(
            anchor="w", pady=(18, 8)
        )
        t.label(
            body,
            "Services survive closing this window. Windows service installation and reboot auto-start will be implemented next.",
            wraplength=490,
            size=9,
            color=t.MUTED,
        ).pack(anchor="w")

        def provision():
            try:
                # Only active inputs are parsed. Legacy hidden options retain their saved values.
                values = {
                    **base_options[kind.get()],
                    **{name: int(value.get()) for name, value in options.items()},
                }
                settings(values)
                worker_port = integer(int(port.get()), 1024, 64000, "Port")
                if worker_port == self.controller.client.port:
                    raise ManagerError("port", "Worker port conflicts with the manager")
                payload = {
                    "capability": kind.get(),
                    "model_id": selected.get(),
                    "device": device.get(),
                    "port": worker_port,
                    "start_at_boot": False,
                    "options": values,
                    "revision": revision,
                }
            except ValueError:
                messagebox.showerror(
                    "Invalid settings", "Ports and runtime options must be whole numbers.", parent=self.dialog
                )
                return
            except ManagerError as error:
                messagebox.showerror("Invalid settings", error.message, parent=self.dialog)
                return
            if self._action("provision", payload):
                self.dialog.destroy()

        t.button(actions, "Provision Service", provision, primary=True).pack(side="left")

    def _open_logs(self, service):
        self.show_page("Logs")
        self.log_service.set(service)
        self._render_logs()

    def _logs(self):
        panel = t.card(self.body, padx=20, pady=20)
        panel.pack(fill="both", expand=True)
        self.log_service = tk.StringVar(panel, "All services")
        self.log_level = tk.StringVar(panel, "All levels")
        self.log_query = tk.StringVar(panel)
        self.follow = tk.BooleanVar(panel, True)
        line = tk.Frame(panel, bg=t.WHITE)
        line.pack(fill="x", pady=(0, 12))
        for variable, values in (
            (self.log_service, ("All services", "manager", "assets", *CAPABILITIES)),
            (self.log_level, ("All levels", "INFO", "WARN", "ERROR")),
        ):
            ttk.Combobox(line, textvariable=variable, values=values, state="readonly", width=17).pack(
                side="left", padx=(0, 10)
            )
            variable.trace_add("write", lambda *_: self._render_logs())
        ttk.Checkbutton(line, text="Follow latest", variable=self.follow).pack(side="left")
        t.button(line, "Export Logs", self._export_logs).pack(side="right")
        ttk.Entry(panel, textvariable=self.log_query).pack(fill="x", pady=(0, 12))
        self.log_query.trace_add("write", lambda *_: self._render_logs())
        self.log_text = tk.Text(
            panel,
            height=17,
            font=("Consolas", 10),
            bg="#F5F8FA",
            fg=t.INK,
            relief="flat",
            padx=12,
            pady=12,
            wrap="word",
        )
        scrollbar = ttk.Scrollbar(panel, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(fill="both", expand=True)
        self._render_logs()
        t.label(
            self.body,
            "Bounded operational events. Prompts, transcripts, media, credentials and native process output are excluded.",
            size=9,
            color=t.MUTED,
            wraplength=680,
        ).pack(anchor="w", pady=18)

    def _filtered_logs(self):
        return [
            row
            for row in self.data["logs"]
            if self.log_service.get() in ("All services", row["service"])
            and self.log_level.get() in ("All levels", row["level"])
            and self.log_query.get().casefold() in (row["service"] + " " + row["message"]).casefold()
        ]

    def _render_logs(self):
        if not hasattr(self, "log_text") or not self.log_text.winfo_exists():
            return
        position = self.log_text.yview()[0]
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        for row in self._filtered_logs():
            timestamp = dt.datetime.fromtimestamp(row["time"]).strftime("%Y-%m-%d %H:%M:%S")
            self.log_text.insert("end", f"{timestamp}  {row['level']}  {row['service']}  {row['message']}\n")
        self.log_text.configure(state="disabled")
        if self.follow.get():
            self.log_text.see("end")
        else:
            self.log_text.yview_moveto(position)

    def _export_logs(self):
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export filtered operational logs",
            defaultextension=".json",
            filetypes=(("JSON", "*.json"),),
        )
        if path:
            try:
                target = checked(Path(path))
                protected = [
                    self.controller.client.root,
                    *(
                        LOCAL_ROOT / name
                        for name in (".manager", ".models", ".library", ".runtime", ".state", ".downloads")
                    ),
                    REPO_ROOT / "local-models/.voices",
                    REPO_ROOT / "device/audio-process/.models",
                ]
                if any(target.is_relative_to(directory.absolute()) for directory in protected):
                    raise ValueError("Managed state/assets cannot be overwritten by log export")
                with open(path, "w", encoding="utf-8") as stream:
                    json.dump(self._filtered_logs(), stream, indent=2)
                self.message.set("Filtered operational logs exported")
            except (OSError, ValueError):
                messagebox.showerror(
                    "Export failed",
                    "Choose a writable location outside managed state and model assets.",
                    parent=self.root,
                )

    def _settings(self):
        panel = t.card(self.body, padx=22, pady=20)
        panel.pack(fill="x")
        self._section(
            panel,
            "Default execution options",
            "Defaults apply to newly provisioned configurations; existing workers keep their saved options.",
        )
        revision = self.data["revision"]
        variables = {}
        defaults = runtime_defaults(self.data)
        for name, (lower, upper) in BOUNDS.items():
            row = tk.Frame(panel, bg=t.WHITE)
            row.pack(fill="x", pady=6)
            t.label(row, name.replace("_", " ").title()).pack(side="left")
            variables[name] = tk.StringVar(panel, str(defaults[name]))
            ttk.Spinbox(row, from_=lower, to=upper, width=10, textvariable=variables[name]).pack(side="right")

        def save():
            try:
                values = {k: int(v.get()) for k, v in variables.items()}
                settings(values)
            except ValueError:
                messagebox.showerror(
                    "Invalid settings", "All values must be whole numbers.", parent=self.root
                )
                return
            except ManagerError as error:
                messagebox.showerror("Invalid settings", error.message, parent=self.root)
                return
            self._action("settings", {"settings": values, "revision": revision})

        t.button(panel, "Save settings", save, primary=True).pack(anchor="w", pady=(16, 0))
        t.button(panel, "Reload saved settings", lambda: self.show_page("Settings")).pack(
            anchor="w", pady=(8, 0)
        )
        self._field(self.body, "Asset storage", self.data.get("library", "Checking"))
        self._field(self.body, "Close window", "Inference continues under the background manager")
        self._field(
            self.body, "Windows service / reboot auto-start", "Queued for the next implementation phase"
        )
        self._field(
            self.body,
            "Human-test / Raspberry Pi",
            "Human-test uses central inference; authenticated Raspberry Pi LAN access is queued",
        )

    def close(self):
        self._stop_loading()
        self.controller.close()
        self.root.destroy()
