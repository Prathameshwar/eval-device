"""The ⋮ menu: every conversation control that is not a moment-to-moment action.

The menu mirrors existing controls rather than replacing them: check and radio items bind to
the same Tk variables as the drawer widgets, and every command calls the same ``Window``
method. Enabled state is computed each time the menu opens (``postcommand``), so it can never
drift from the widgets that ``lock_options`` and the retry handler already manage.
"""

from . import theme


class OverflowMenu:
    def __init__(self, window, anchor):
        self.window = window
        self.anchor = anchor
        self.menu = theme.menu(window.root, postcommand=self.refresh)
        self.camera_menu = theme.menu(self.menu)
        self.mic_menu = theme.menu(self.menu)
        self.voice_menu = theme.menu(self.menu)
        self.index = {}
        self.build()

    def add(self, key, kind="command", **options):
        getattr(self.menu, f"add_{kind}")(**options)
        self.index[key] = self.menu.index("end")

    def build(self):
        w = self.window
        self.add("mic", label="●  Start microphone", command=w.toggle)
        self.add("send", label="Send audio now", command=w.send_now.set)
        self.add("cancel", label="Cancel", command=w.pause)
        self.menu.add_separator()
        self.add("reset", label="New conversation", command=w.reset)
        self.add("check_request", label="Check last request", command=w.check_request)
        self.add("back", label="←  Practice setup", command=w.back)
        self.menu.add_separator()
        self.add(
            "text",
            "checkbutton",
            label="Show question & response",
            variable=w.show_text,
            command=w.apply_layout,
        )
        self.add(
            "typing", "checkbutton", label="Show typed input", variable=w.show_typing, command=w.apply_layout
        )
        self.add(
            "camera",
            "checkbutton",
            label="Capture & show video",
            variable=w.camera_view.enabled,
            command=w.camera_view.toggle,
        )
        for number in range(10):
            self.camera_menu.add_radiobutton(
                label=f"Camera {number}" + ("  (built-in)" if number == 0 else ""),
                value=str(number),
                variable=w.camera_view.camera,
            )
        self.add("camera_index", "cascade", label="Camera number", menu=self.camera_menu)
        self.menu.add_separator()
        self.add("stream", "checkbutton", label="Stream response", variable=w.streaming)
        self.add(
            "speaker",
            "checkbutton",
            label="Speaker out",
            variable=w.speaker_output,
            command=w.apply_speaker_output,
        )
        self.add("mic_menu", "cascade", label="Microphone", menu=self.mic_menu)
        self.add("voice_menu", "cascade", label="Voice", menu=self.voice_menu)
        self.menu.add_separator()
        if w.settings.use_pms_models:
            self.add("models", label="Models…", command=w.open_models)
        self.add("history", label="History", command=w.open_history)
        self.add("sync", label="Retry pending recording sync", command=w.retry_sync)
        self.fill_choices()

    def fill_choices(self):
        w = self.window
        self.mic_menu.delete(0, "end")
        for label in w.microphones:
            self.mic_menu.add_radiobutton(
                label=label, value=label, variable=w.mic, command=w.check_microphone
            )
        self.mic_menu.add_separator()
        self.mic_menu.add_command(label="Check microphone", command=w.check_microphone)
        self.voice_menu.delete(0, "end")
        for label in w.voices:
            self.voice_menu.add_radiobutton(label=label, value=label, variable=w.voice, command=w.apply_voice)
        self.voice_menu.add_separator()
        self.voice_menu.add_command(label="Hear a sample", command=w.preview_voice)

    def state(self, key, enabled):
        self.menu.entryconfigure(self.index[key], state="normal" if enabled else "disabled")

    def refresh(self):
        """Mirror the widgets' current labels and enabled states; called on every open."""
        w = self.window
        locked = w.running
        talking = w.page == "talk" and bool(w.saved)
        self.menu.entryconfigure(self.index["mic"], label=w.start_button.cget("text"))
        self.state("mic", talking)
        self.state("send", w.listening)
        self.state("cancel", w.listening or w.running)
        self.state("reset", not locked)
        self.state("check_request", not locked and talking)
        self.state("back", not locked)
        for key in ("stream", "mic_menu", "voice_menu"):
            self.state(key, not locked)
        self.state("camera_index", not w.camera_view.enabled.get() and not w.camera_view.recorder.busy)
        self.state("camera", not w.closing and str(w.camera_view.checkbox.cget("state")) != "disabled")
        if "models" in self.index:
            self.state("models", not locked and not w.listening)
        self.state("history", bool(w.controller))
        self.state("sync", bool(getattr(w.controller, "sync", None)))
        self.mic_menu.entryconfigure("end", state="disabled" if locked or w.listening else "normal")
        self.voice_menu.entryconfigure("end", state="disabled" if locked or w.listening else "normal")

    def open(self, event=None):
        self.anchor.update_idletasks()
        x = self.anchor.winfo_rootx() + self.anchor.winfo_width()
        y = self.anchor.winfo_rooty() + self.anchor.winfo_height() + 2
        # Right-align the menu to the button once its width is known.
        self.menu.update_idletasks()
        width = self.menu.winfo_reqwidth()
        self.menu.tk_popup(max(0, x - width), y)
