"""Manage Local Models: presentation-only desktop interface.

Navigation and preview dialogs work. Operational controls remain disabled;
this module never imports an installer, engine, supervisor or platform client.
"""

import tkinter as tk
from tkinter import ttk

from . import theme as t
from .icons import Icon, app_icon
from .preview import LOGS, MODELS, SERVICES


class ModelManager:
    PAGES = {
        "Overview": "Your local inference workspace, at a glance.",
        "Models": "Browse language, audio and video capabilities in one place.",
        "Services": "Provision and manage independent background inference services.",
        "Logs": "Inspect service events and diagnose startup or runtime issues.",
        "Settings": "Configure storage, execution preferences and background startup.",
    }

    def __init__(self, root):
        self.root = root
        self.page = ""
        self.dialog = None
        self.nav = {}
        self.nav_buttons = {}
        self.model_filter = "All"
        self.root.title("Manage Local Models")
        self.window_icon = app_icon(root)
        self.root.iconphoto(True, self.window_icon)
        self.root.geometry("1280x820")
        self.root.minsize(1040, 700)
        t.configure(root)
        self._shell()
        self.show_page("Overview")

    def _shell(self):
        sidebar = tk.Frame(self.root, bg=t.NAVY, width=218)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg=t.NAVY, padx=22, pady=28)
        brand.pack(fill="x")
        Icon(brand, "models", size=32, color="#61D4C6").pack(anchor="w", pady=(0, 12))
        t.label(brand, "Manage\nLocal Models", size=19, color=t.WHITE, bold=True, justify="left").pack(
            anchor="w"
        )
        t.label(brand, "DESKTOP WORKSPACE", size=8, color="#A3B7C6").pack(anchor="w", pady=(12, 0))
        self._nav_item(sidebar, "Overview", "overview")
        self._nav_item(sidebar, "Models", "models")
        self._nav_item(sidebar, "Services", "services")
        self._nav_item(sidebar, "Logs", "logs")
        bottom = tk.Frame(sidebar, bg=t.NAVY)
        bottom.pack(side="bottom", fill="x", pady=16)
        self._nav_item(bottom, "Settings", "settings")
        t.label(bottom, "UI preview · v0.1", size=9, color="#A3B7C6", padx=22).pack(anchor="w", pady=(14, 0))

        workspace = tk.Frame(self.root, bg=t.BG)
        workspace.pack(side="left", fill="both", expand=True)
        top = tk.Frame(workspace, bg=t.WHITE, padx=26, pady=14)
        top.pack(fill="x")
        t.label(top, "LOCAL INFERENCE WORKSPACE", size=9, bold=True, color=t.MUTED).pack(side="left")
        t.badge(top, "Interface preview").pack(side="right")
        banner = tk.Frame(workspace, bg=t.TEAL_BG, padx=24, pady=10)
        banner.pack(fill="x", padx=24, pady=(18, 0))
        Icon(banner, "info", size=20).pack(side="left", padx=(0, 10))
        t.label(
            banner,
            "UI preview · Models, hardware, service states and logs below are sample data.",
            size=9,
            color=t.TEAL_DARK,
            wraplength=690,
        ).pack(side="left", fill="x", expand=True)
        footer = tk.Frame(workspace, bg=t.BG, padx=26, pady=12)
        footer.pack(side="bottom", fill="x")
        t.label(
            footer,
            "Preview only · Downloads and service operations will be connected later.",
            size=9,
            color=t.MUTED,
        ).pack(anchor="w")
        self.host = tk.Frame(workspace, bg=t.BG)
        self.host.pack(fill="both", expand=True)

    def _nav_item(self, parent, name, icon):
        row = tk.Frame(parent, bg=t.NAVY)
        row.pack(fill="x", padx=12, pady=3)
        symbol = Icon(row, icon, color="#B7C9D6", bg=t.NAVY, size=21)
        symbol.pack(side="left", padx=(12, 4))
        control = tk.Button(
            row,
            text=name,
            command=lambda: self.show_page(name),
            anchor="w",
            bg=t.NAVY,
            fg="#D6E3EC",
            activebackground=t.NAV_HOVER,
            activeforeground=t.WHITE,
            relief="flat",
            bd=0,
            font=t.font(11),
            padx=12,
            pady=13,
            highlightthickness=1,
            highlightbackground=t.NAVY,
            highlightcolor="#61D4C6",
        )
        control.pack(side="left", fill="x", expand=True)
        symbol.bind("<Button-1>", lambda _: self.show_page(name))
        self.nav[name] = row, symbol, control
        self.nav_buttons[name] = control

    def show_page(self, page):
        self.page = page
        for name, (row, symbol, control) in self.nav.items():
            bg = t.NAV_HOVER if name == page else t.NAVY
            row.configure(bg=bg)
            symbol.configure(bg=bg)
            control.configure(bg=bg, highlightbackground=bg, fg=t.WHITE if name == page else "#D6E3EC")
        for child in self.host.winfo_children():
            child.destroy()
        self.scroll = t.ScrollArea(self.host)
        self.scroll.pack(fill="both", expand=True)
        self.body = tk.Frame(self.scroll.body, bg=t.BG, padx=24, pady=24)
        self.body.pack(fill="both", expand=True)
        heading = tk.Frame(self.body, bg=t.BG)
        heading.pack(fill="x", pady=(0, 22))
        t.label(heading, page, size=24, bold=True).pack(anchor="w")
        t.label(heading, self.PAGES[page], color=t.MUTED, wraplength=680).pack(anchor="w", pady=(6, 0))
        self._page_content(page)
        self.scroll.canvas.yview_moveto(0)

    def _page_content(self, page):
        {
            "Overview": self._overview,
            "Models": self._models,
            "Services": self._services,
            "Logs": self._logs,
            "Settings": self._settings,
        }[page]()

    def _section(self, parent, title, subtitle=None):
        line = tk.Frame(parent, bg=parent.cget("bg"))
        line.pack(fill="x", pady=(0, 14))
        t.label(line, title, size=13, bold=True).pack(anchor="w")
        if subtitle:
            t.label(line, subtitle, color=t.MUTED, size=9, wraplength=650).pack(anchor="w", pady=(4, 0))
        return line

    def _overview(self):
        actions = tk.Frame(self.body, bg=t.BG)
        actions.pack(fill="x", pady=(0, 22))
        t.button(actions, "Download models", lambda: self.show_page("Models"), primary=True).pack(
            side="left", padx=(0, 10)
        )
        t.button(actions, "Provision service", self._provision).pack(side="left")

        metrics = tk.Frame(self.body, bg=t.BG)
        metrics.pack(fill="x", pady=(0, 28))
        items = (
            ("gpu", "COMPUTE", "NVIDIA GPU", "4.0 GB VRAM · sample hardware"),
            ("storage", "MODEL LIBRARY", "3 installed", "LLM, recognition and voice · sample"),
            ("services", "INFERENCE", "2 ready", "1 stopped · sample service states"),
        )
        for index, (icon, caption, value, detail) in enumerate(items):
            metrics.columnconfigure(index, weight=1, uniform="metrics")
            panel = t.card(metrics, padx=16, pady=18)
            panel.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 6, 0))
            Icon(panel, icon).pack(anchor="w", pady=(0, 12))
            t.label(panel, caption, size=8, color=t.MUTED, bold=True).pack(anchor="w")
            t.label(panel, value, size=19, bold=True).pack(anchor="w", pady=(6, 6))
            t.label(panel, detail, size=9, color=t.MUTED, wraplength=200).pack(anchor="w")
        self._section(self.body, "Background services", "Model assets stay installed when a service stops.")
        panel = t.card(self.body)
        panel.pack(fill="x")
        for index, service in enumerate(SERVICES):
            row = tk.Frame(panel, bg=t.WHITE, padx=18, pady=15)
            row.pack(fill="x")
            row.columnconfigure(1, weight=1)
            Icon(row, service["kind"], size=26).grid(row=0, column=0, rowspan=2, padx=(0, 14))
            t.label(row, service["name"], bold=True).grid(row=0, column=1, sticky="w")
            t.label(row, service["model"], size=9, color=t.MUTED).grid(
                row=1, column=1, sticky="w", pady=(5, 0)
            )
            t.badge(row, service["state"]).grid(row=0, column=2, rowspan=2, padx=12)
            t.button(row, "View status", lambda s=service: self._service_detail(s)).grid(
                row=0, column=3, rowspan=2
            )
            if index < len(SERVICES) - 1:
                tk.Frame(panel, bg=t.LINE, height=1).pack(fill="x", padx=18)
        note = tk.Frame(self.body, bg=t.BG, pady=18)
        note.pack(fill="x")
        t.label(note, "Shared by Human-test and the future Raspberry Pi client", bold=True).pack(anchor="w")
        t.label(
            note,
            "Client connections and independent background execution will be implemented later.",
            size=9,
            color=t.MUTED,
            wraplength=680,
        ).pack(anchor="w", pady=(5, 0))

    def _tabs(self, parent, names, selected, callback):
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x", pady=(0, 16))
        self.tab_buttons = {}
        for name in names:
            control = t.button(row, name, lambda n=name: callback(n), primary=name == selected)
            control.pack(side="left", padx=(0, 8))
            self.tab_buttons[name] = control

    def _models(self):
        self.model_filter = "All"
        self.search = tk.StringVar()
        self._tabs(self.body, ("All", "LLM", "Audio", "Video", "Installed"), "All", self._filter_models)
        search_row = tk.Frame(self.body, bg=t.BG)
        search_row.pack(fill="x", pady=(0, 20))
        t.label(search_row, "Search models", size=9, color=t.MUTED).pack(anchor="w", pady=(0, 6))
        ttk.Entry(search_row, textvariable=self.search).pack(fill="x")
        self.model_results = tk.Frame(self.body, bg=t.BG)
        self.model_results.pack(fill="x")
        self.search.trace_add("write", lambda *_: self._render_models())
        self._render_models()

    def _filter_models(self, category):
        self.model_filter = category
        for name, control in self.tab_buttons.items():
            control.configure(style="Primary.TButton" if name == category else "TButton")
        self._render_models()

    def _render_models(self):
        for child in self.model_results.winfo_children():
            child.destroy()
        if self.model_filter == "Video":
            self._empty_video(self.model_results)
            return
        query = self.search.get().strip().casefold()
        items = [
            m
            for m in MODELS
            if (
                self.model_filter == "All"
                or m["category"] == self.model_filter
                or (self.model_filter == "Installed" and m["status"] == "Installed")
            )
            and query in (m["name"] + " " + m["detail"]).casefold()
        ]
        if not items:
            box = t.card(self.model_results, padx=24, pady=28)
            box.pack(fill="x")
            t.label(box, "No matching models", size=14, bold=True).pack(anchor="w")
            t.label(box, "Try another name or category.", color=t.MUTED).pack(anchor="w", pady=(8, 0))
            return
        grid = tk.Frame(self.model_results, bg=t.BG)
        grid.pack(fill="x")
        panels = [self._model_card(grid, model) for model in items]
        self._responsive_grid(grid, panels)

    def _model_card(self, parent, model):
        panel = t.card(parent, padx=18, pady=18)
        top = tk.Frame(panel, bg=t.WHITE)
        top.pack(fill="x", pady=(0, 16))
        Icon(top, model["kind"], size=28).pack(side="left")
        t.badge(top, model["status"]).pack(side="right")
        t.label(panel, model["name"], size=14, bold=True).pack(anchor="w")
        t.label(panel, model["detail"], size=9, color=t.MUTED, wraplength=285).pack(anchor="w", pady=(6, 16))
        t.label(panel, model["format"], size=9).pack(anchor="w")
        t.label(panel, model["device"] + " · " + model["size"], size=9, color=t.MUTED, wraplength=290).pack(
            anchor="w", pady=(6, 18)
        )
        actions = tk.Frame(panel, bg=t.WHITE)
        actions.pack(fill="x")
        t.button(actions, "View details", lambda: self._model_detail(model)).pack(side="left")
        t.button(
            actions, "Provision service" if model["status"] == "Installed" else "Download", disabled=True
        ).pack(side="right")
        return panel

    def _responsive_grid(self, parent, panels):
        previous = [None]

        def layout(event):
            columns = 2 if event.width >= 780 else 1
            if previous[0] == columns:
                return
            previous[0] = columns
            for index in range(2):
                parent.columnconfigure(
                    index, weight=1 if index < columns else 0, uniform="cards" if index < columns else ""
                )
            for index, panel in enumerate(panels):
                panel.grid(
                    row=index // columns,
                    column=index % columns,
                    sticky="nsew",
                    padx=(0, 12 if columns == 2 and index % columns == 0 else 0),
                    pady=(0, 12),
                )

        parent.bind("<Configure>", layout)
        # Lay out before the first width negotiation; the Configure event then adapts it.
        layout(type("Geometry", (), {"width": self.host.winfo_width() - 60})())

    def _empty_video(self, parent):
        panel = t.card(parent, padx=28, pady=28)
        panel.pack(fill="x")
        Icon(panel, "video", size=36).pack(anchor="w", pady=(0, 14))
        t.badge(panel, "Planned").pack(anchor="w", pady=(0, 12))
        t.label(panel, "Video analysis models", size=18, bold=True).pack(anchor="w")
        t.label(
            panel,
            "A video model catalog will appear here when analysis adapters are available.",
            color=t.MUTED,
            wraplength=600,
        ).pack(anchor="w", pady=(10, 18))
        tk.Frame(panel, bg=t.LINE, height=1).pack(fill="x", pady=(0, 18))
        t.label(panel, "Video recording is a separate capability", bold=True).pack(anchor="w")
        t.label(
            panel,
            "The existing video receiver records submitted video and requires no inference model.",
            size=9,
            color=t.MUTED,
            wraplength=600,
        ).pack(anchor="w", pady=(7, 20))
        t.button(panel, "Download video model", disabled=True).pack(anchor="w")

    def _services(self):
        actions = tk.Frame(self.body, bg=t.BG)
        actions.pack(fill="x", pady=(0, 22))
        t.button(actions, "Provision service", self._provision, primary=True).pack(side="left")
        t.label(actions, "Preview configuration; installation is not connected.", size=9, color=t.MUTED).pack(
            side="left", padx=16
        )
        grid = tk.Frame(self.body, bg=t.BG)
        grid.pack(fill="x")
        panels = []
        for service in SERVICES:
            panel = t.card(grid, padx=18, pady=18)
            top = tk.Frame(panel, bg=t.WHITE)
            top.pack(fill="x", pady=(0, 16))
            Icon(top, service["kind"], size=28).pack(side="left")
            t.badge(top, service["state"]).pack(side="right")
            t.label(panel, service["name"], size=15, bold=True).pack(anchor="w")
            t.label(panel, service["model"], color=t.MUTED, wraplength=295).pack(anchor="w", pady=(7, 20))
            self._field(panel, "Installation", service["installation"])
            self._field(panel, "Execution", service["device"])
            self._field(panel, "Readiness", service["readiness"])
            buttons = tk.Frame(panel, bg=t.WHITE)
            buttons.pack(fill="x", pady=(18, 8))
            t.button(buttons, "Start Service", primary=True, disabled=True).pack(side="left", padx=(0, 8))
            t.button(buttons, "Stop Service", disabled=True).pack(side="left")
            links = tk.Frame(panel, bg=t.WHITE)
            links.pack(fill="x")
            t.button(links, "View status", lambda s=service: self._service_detail(s)).pack(
                side="left", padx=(0, 8)
            )
            t.button(links, "View Logs", lambda s=service: self._open_logs(s["name"])).pack(side="left")
            panels.append(panel)
        self._responsive_grid(grid, panels)

    def _field(self, parent, name, value):
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x", pady=5)
        row.columnconfigure(1, weight=1)
        t.label(row, name, size=9, color=t.MUTED, width=13).grid(row=0, column=0, sticky="nw")
        value_label = t.label(row, value, size=9, wraplength=230)
        value_label.grid(row=0, column=1, sticky="w", padx=(8, 0))
        return value_label

    def _open_logs(self, service):
        self.show_page("Logs")
        self.log_service.set(service)
        self._render_logs()

    def _logs(self):
        panel = t.card(self.body, padx=20, pady=20)
        panel.pack(fill="x")
        controls = tk.Frame(panel, bg=t.WHITE)
        controls.pack(fill="x", pady=(0, 16))
        self.log_service = tk.StringVar(value="All services")
        self.log_level = tk.StringVar(value="All levels")
        self.log_query = tk.StringVar()
        for index, (caption, variable, options) in enumerate(
            (
                ("Service", self.log_service, ("All services", *(s["name"] for s in SERVICES))),
                ("Level", self.log_level, ("All levels", "INFO", "WARN", "ERROR")),
            )
        ):
            controls.columnconfigure(index, weight=1)
            field = tk.Frame(controls, bg=t.WHITE)
            field.grid(row=0, column=index, sticky="ew", padx=(0, 12))
            t.label(field, caption, size=9, color=t.MUTED).pack(anchor="w", pady=(0, 6))
            combo = ttk.Combobox(field, textvariable=variable, values=options, state="readonly", width=21)
            combo.pack(fill="x")
            combo.bind("<<ComboboxSelected>>", lambda _: self._render_logs())
        t.label(panel, "Search log messages", size=9, color=t.MUTED).pack(anchor="w", pady=(0, 6))
        ttk.Entry(panel, textvariable=self.log_query).pack(fill="x", pady=(0, 16))
        self.log_query.trace_add("write", lambda *_: self._render_logs())
        toolbar = tk.Frame(panel, bg=t.WHITE)
        toolbar.pack(fill="x", pady=(0, 12))
        t.badge(toolbar, "Sample events").pack(side="left")
        t.button(toolbar, "Export Logs", disabled=True).pack(side="right", padx=(8, 0))
        t.button(toolbar, "Follow latest", disabled=True).pack(side="right")
        self.log_text = tk.Text(
            panel,
            height=15,
            font=("Consolas", 10),
            bg="#F5F8FA",
            fg=t.INK,
            relief="flat",
            padx=14,
            pady=14,
            wrap="word",
            cursor="arrow",
            highlightthickness=1,
            highlightbackground=t.LINE,
        )
        bar = ttk.Scrollbar(panel, command=self.log_text.yview)
        bar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=bar.set)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_configure("WARN", foreground="#835B12")
        self.log_text.tag_configure("ERROR", foreground="#AA302B")
        self._render_logs()
        note = tk.Frame(self.body, bg=t.BG, pady=18)
        note.pack(fill="x")
        t.label(note, "Operational events only", bold=True).pack(anchor="w")
        t.label(
            note,
            "Future logs will redact credentials, prompts, transcripts and private media.",
            size=9,
            color=t.MUTED,
            wraplength=660,
        ).pack(anchor="w", pady=(5, 0))

    def _render_logs(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        count = 0
        for timestamp, level, service, message in LOGS:
            if self.log_service.get() not in ("All services", service):
                continue
            if self.log_level.get() not in ("All levels", level):
                continue
            if self.log_query.get().casefold() not in (service + " " + message).casefold():
                continue
            self.log_text.insert("end", f"{timestamp}  {level:4}  {service}\n          {message}\n\n", level)
            count += 1
        if not count:
            self.log_text.insert("end", "No sample events match these filters.")
        self.log_text.configure(state="disabled")

    def _settings(self):
        for title, detail, rows in (
            (
                "Model storage",
                "One shared asset library for every client.",
                (
                    ("Location", "Shared asset location will be configured later"),
                    ("Downloads", "Verified assets; explicit operator downloads"),
                ),
            ),
            (
                "Execution preferences",
                "Choose the device for each supported capability.",
                (
                    ("Device policy", "Explicit CPU / GPU selection"),
                    ("GPU sharing", "Resource limits will be configured per service"),
                ),
            ),
            (
                "Background startup",
                "The manager window and background services have separate lifetimes.",
                (
                    ("Start at boot", "Optional, configured during service provisioning"),
                    ("Close window", "Planned behavior: services continue running"),
                ),
            ),
            (
                "Client connectivity",
                "Human-test locally; Raspberry Pi through a future paired gateway.",
                (
                    ("Pairing", "Planned"),
                    ("LAN access", "Authenticated gateway configuration comes later"),
                ),
            ),
        ):
            panel = t.card(self.body, padx=22, pady=20)
            panel.pack(fill="x", pady=(0, 14))
            self._section(panel, title, detail)
            for name, value in rows:
                self._field(panel, name, value)
        t.button(self.body, "Save settings", primary=True, disabled=True).pack(anchor="w", pady=(6, 0))

    def _dialog(self, title, subtitle):
        if self.dialog is not None and self.dialog.winfo_exists():
            self.dialog.destroy()
        window = tk.Toplevel(self.root)
        self.dialog = window
        window.title(title + " · Manage Local Models")
        window.geometry("640x670")
        window.minsize(560, 520)
        window.transient(self.root)
        window.configure(bg=t.WHITE)
        window.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - 640) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - 670) // 2)
        window.geometry(f"+{x}+{y}")
        window.bind("<Escape>", lambda _: window.destroy())
        actions = tk.Frame(window, bg=t.WHITE, padx=24, pady=16)
        actions.pack(side="bottom", fill="x")
        t.button(actions, "Close", window.destroy).pack(side="right")
        viewport = t.ScrollArea(window, bg=t.WHITE)
        viewport.pack(fill="both", expand=True)
        body = tk.Frame(viewport.body, bg=t.WHITE, padx=24, pady=22)
        body.pack(fill="x")
        t.badge(body, "UI preview").pack(anchor="w", pady=(0, 12))
        t.label(body, title, size=21, bold=True).pack(anchor="w")
        t.label(body, subtitle, color=t.MUTED, wraplength=490).pack(anchor="w", pady=(8, 24))
        return body, actions

    def _model_detail(self, model):
        body, actions = self._dialog(model["name"], model["detail"])
        for name, value in (
            ("Category", model["category"]),
            ("Format", model["format"]),
            ("Download size", model["size"]),
            ("Languages", model["languages"]),
            ("Execution", model["device"]),
            ("Sample state", model["status"]),
            ("Source / license", "Pinned catalog metadata will be connected later"),
        ):
            self._field(body, name, value)
        progress = t.card(body, padx=16, pady=18)
        progress.pack(fill="x", pady=(24, 0))
        t.label(progress, "Download preview", size=12, bold=True).pack(anchor="w")
        t.label(progress, "Sample: downloading · 42%", size=9, color=t.MUTED).pack(anchor="w", pady=(10, 8))
        ttk.Progressbar(progress, value=42).pack(fill="x")
        t.label(progress, "Download → verify → installed", size=9, color=t.MUTED).pack(
            anchor="w", pady=(10, 0)
        )
        t.button(actions, "Download model", primary=True, disabled=True).pack(side="left")

    def _service_detail(self, service):
        body, actions = self._dialog(
            service["name"], "Service status preview · no live checks are performed."
        )
        t.badge(body, service["state"]).pack(anchor="w", pady=(0, 16))
        for name, value in (
            ("Installation", service["installation"]),
            ("Process state", service["state"]),
            ("Model", service["model"]),
            ("Model assets", "Not configured" if service["kind"] == "video" else "Installed · sample"),
            ("Readiness", service["readiness"]),
            ("Execution", service["device"]),
            ("Active clients", "No live client data"),
            ("Last check", "Preview only"),
        ):
            self._field(body, name, value)
        t.label(
            body,
            "Installing a model does not provision a service. A running process is ready only\n"
            "after model loading and warmup succeed.",
            color=t.MUTED,
            size=9,
            wraplength=490,
            justify="left",
        ).pack(anchor="w", pady=(22, 0))
        t.button(actions, "Start Service", primary=True, disabled=True).pack(side="left", padx=(0, 8))
        t.button(actions, "Stop Service", disabled=True).pack(side="left")

    def _provision(self):
        body, actions = self._dialog(
            "Provision service", "Choose a capability and model for background inference."
        )
        for number, title in (
            ("01", "Capability"),
            ("02", "Model and execution"),
            ("03", "Startup preference"),
        ):
            group = tk.Frame(body, bg=t.WHITE)
            group.pack(fill="x", pady=(0, 16))
            t.label(group, number, color=t.TEAL, bold=True, size=10).pack(side="left", padx=(0, 10))
            t.label(group, title, bold=True).pack(side="left")
            if number == "01":
                capability = ttk.Combobox(
                    body,
                    state="disabled",
                    values=("Language model", "Speech recognition", "Speech synthesis"),
                )
                capability.set("Language model")
                capability.pack(fill="x", pady=(0, 22))
            elif number == "02":
                self._field(body, "Model", "Qwen 3.5 4B · sample selection")
                self._field(body, "Execution", "NVIDIA GPU · sample preference")
                t.label(
                    body,
                    "Model choices and compatibility checks will be connected later.",
                    size=9,
                    color=t.MUTED,
                    wraplength=490,
                ).pack(anchor="w", pady=(5, 22))
            else:
                ttk.Checkbutton(body, text="Start this service when the laptop boots", state="disabled").pack(
                    anchor="w", pady=(0, 16)
                )
        t.label(
            body,
            "Preview only. This form does not install a service, change startup settings\nor load a model.",
            size=9,
            color=t.MUTED,
            wraplength=490,
            justify="left",
        ).pack(anchor="w")
        t.button(actions, "Provision Service", primary=True, disabled=True).pack(side="left")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Manage Local Models")
    parser.add_argument("--preview", action="store_true", help="Display sample layout without a backend")
    args = parser.parse_args()
    root = tk.Tk()
    if args.preview:
        ModelManager(root)
    else:
        from .live import LiveModelManager

        LiveModelManager(root)
    root.mainloop()
