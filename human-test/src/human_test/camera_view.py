"""Tk-only preview controls; capture and disk I/O live in the isolated video worker.

The controls (checkbox, camera number, recording path, status) are one compact widget that
lives in the drawer. The preview canvas is hosted elsewhere - on the conversation stage as a
picture-in-picture corner - so the operator sees the camera even with the drawer closed.
"""

import tkinter as tk
from tkinter import ttk

from training_client.recording import CameraRecording
from training_client.video import PREVIEW_HEIGHT, PREVIEW_WIDTH, Options, VideoError

from . import theme


class CameraView(ttk.Frame):
    def __init__(self, parent, settings, preview_host=None, *, recording=None):
        super().__init__(parent, style="Card.TFrame")
        self.settings = settings
        self.sync_provider = lambda: None
        self.recorder = recording or CameraRecording()
        self.closing = False
        self.recording = False
        self.enabled = tk.BooleanVar(value=False)
        self.camera = tk.StringVar(value=str(settings.camera_index))
        self.status = tk.StringVar(value="Camera off. Video saves on this computer.")
        self.path = tk.StringVar(value=str(Options.from_settings(settings, settings.camera_index).directory))
        self.photo = None
        self.columnconfigure(0, weight=1)
        controls = ttk.Frame(self, style="Card.TFrame")
        controls.grid(row=0, column=0, sticky="ew")
        self.checkbox = ttk.Checkbutton(
            controls, text="Capture & show video", variable=self.enabled, command=self.toggle
        )
        self.checkbox.pack(side="left")
        ttk.Label(controls, text="Camera", style="Muted.TLabel").pack(side="left", padx=(12, 4))
        # Do not probe camera devices at startup: even probing can light the camera LED.
        self.selector = ttk.Spinbox(controls, from_=0, to=9, textvariable=self.camera, width=3)
        self.selector.pack(side="left")
        # Selectable path directly below the capture controls, across the whole panel.
        self.path_entry = ttk.Entry(self, textvariable=self.path, state="readonly", width=12)
        self.path_entry.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.status_label = ttk.Label(
            self, textvariable=self.status, style="Muted.TLabel", wraplength=180, justify="left"
        )
        self.status_label.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self.bind("<Configure>", lambda event: self.status_label.configure(wraplength=max(120, event.width)))
        # The preview is a child of its host so it can float over the stage; hidden until capture.
        self.preview_host = preview_host if preview_host is not None else self
        self.preview = tk.Canvas(
            self.preview_host,
            width=PREVIEW_WIDTH,
            height=PREVIEW_HEIGHT,
            bg=theme.NAVY,
            highlightthickness=1,
            highlightbackground=theme.SURFACE,
        )
        self.image_id = self.preview.create_image(PREVIEW_WIDTH // 2, PREVIEW_HEIGHT // 2, anchor="center")
        if self.preview_host is self:
            self.preview.grid(row=3, column=0, sticky="w", pady=(8, 0))
            self.preview.grid_remove()

    def show_preview(self):
        if self.preview_host is self:
            self.preview.grid()
        else:
            self.preview.place(
                relx=1.0, rely=1.0, anchor="se", x=-theme.PREVIEW_INSET, y=-theme.PREVIEW_INSET
            )
        # Canvas.lift() targets canvas items; raise the widget itself above the manikin.
        tk.Misc.lift(self.preview)

    def hide_preview(self):
        if self.preview_host is self:
            self.preview.grid_remove()
        else:
            self.preview.place_forget()

    def toggle(self):
        if self.closing:
            return
        if not self.enabled.get():
            self.stop()
            return
        try:
            camera = int(self.camera.get())
            if not 0 <= camera <= 9:
                raise ValueError
        except ValueError:
            self.enabled.set(False)
            self.status.set("Choose a camera number from 0 to 9 (0 is usually the built-in camera).")
            return
        try:
            sync = self.sync_provider()
            options = Options.from_settings(self.settings, camera)
            self.recorder.start(options, sync=sync)
        except VideoError as error:
            self.enabled.set(False)
            self.status.set(str(error))
            return
        self.selector.configure(state="disabled")
        self.status.set("Opening camera and preparing local recording…")
        self.show_preview()

    def stop(self):
        self.enabled.set(False)
        self.recording = False
        self.recorder.stop()
        self.hide_preview()
        self.preview.itemconfigure(self.image_id, image="")
        self.photo = None
        if self.recorder.busy:
            self.checkbox.configure(state="disabled")
            self.status.set("Stopping camera and finishing the video file…")

    def close(self):
        self.closing = True
        self.stop()
        self.checkbox.configure(state="disabled")
        self.selector.configure(state="disabled")

    def poll(self):
        events, preview = self.recorder.poll()
        for kind, value in events:
            if kind == "started":
                self.path.set(value)
                if self.enabled.get():
                    self.recording = True
                    self.status.set("● Recording video · saved locally · microphone audio is separate")
            elif kind == "finished":
                self.stop()
                if value["path"]:
                    self.path.set(value["path"])
                saved = (
                    f" {value['segments']} video file(s) saved."
                    if value["segments"]
                    else " No completed video."
                )
                self.status.set(value["message"] + saved)
            elif kind == "interrupted":
                self.stop()
                self.status.set(
                    "Camera worker stopped responding. Completed files are kept; the last segment may be incomplete."
                )
            elif kind == "idle":
                self.enabled.set(False)
                self.recording = False
                if not self.closing:
                    self.checkbox.configure(state="normal")
                    self.selector.configure(state="normal")
        if preview is not None and self.enabled.get():
            try:
                self.photo = tk.PhotoImage(master=self, data=preview, format="PPM")
                self.preview.itemconfigure(self.image_id, image=self.photo)
            except tk.TclError:
                self.stop()
                self.status.set("Could not display camera frames; stopping video capture.")
