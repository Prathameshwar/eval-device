"""Read-only device model summary. Assignment is managed by Platform Admin."""

import asyncio
import tkinter as tk
from tkinter import ttk

from training_client.model_route import interactive_speech


class ModelDialog:
    def __init__(self, owner):
        self.owner = owner
        self.closed = False
        self.task = None
        self.window = tk.Toplevel(owner.root)
        self.window.title("Device models")
        self.window.geometry("620x520")
        self.window.minsize(560, 520)
        self.window.transient(owner.root)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        panel = ttk.Frame(self.window, padding=24)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Device models", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(
            panel, text="Platform Admin manages models and assigns them on Devices.", wraplength=490
        ).pack(anchor="w", pady=(12, 16))
        self.summary = tk.StringVar(value="Loading assigned models...")
        ttk.Label(panel, textvariable=self.summary, wraplength=490).pack(fill="x", pady=12)
        self.refresh = ttk.Button(panel, text="Reload assigned models", command=self.reload)
        self.refresh.pack(side="bottom", fill="x", pady=8)
        self.reload()

    async def load(self):
        if self.closed:
            return
        self.task = asyncio.current_task()
        try:
            route = await self.owner.runtime.reload_models()
        except asyncio.CancelledError:
            self.owner.emit("model_dialog", (self, "cancelled", None))
            raise
        except Exception:
            self.owner.emit("model_dialog", (self, "failed", None))
            raise
        finally:
            self.task = None
        self.owner.emit("model_dialog", (self, "loaded", route))

    def reload(self):
        if not self.owner.running and not getattr(self.owner, "listening", False):
            self.summary.set("Loading assigned models...")
            self.refresh.configure(state="disabled")
            self.owner.submit(self.load(), "checked")

    def handle(self, event):
        source, kind, route = event
        if source is not self or self.closed or not self.window.winfo_exists():
            return False
        self.refresh.configure(state="normal")
        if kind != "loaded":
            self.summary.set(
                "Model reload cancelled. You can retry."
                if kind == "cancelled"
                else "Unable to reload assigned models. Check the main window for details and retry."
            )
            return False
        audio = route.get("audio", {})
        llm = route.get("llm", {})
        speech = audio.get("model", "None") if audio.get("enabled", True) else "None"
        if not interactive_speech(route) and audio.get("enabled", True):
            speech += " (device jobs only; use typing here)"
        media = route.get("platform_media", {})

        def assigned(section):
            settings = media.get(section, {}).get("settings", {})
            return settings.get("engine", "Assigned") if settings.get("enabled") else "None"

        self.summary.set(
            f"Run on: {route.get('mode', '').title()}\n"
            f"Conversation: {llm.get('model', 'None')}\n"
            f"Speech recognition: {speech}\n"
            f"Device speech output: {assigned('audio_output')}\n"
            f"Device video: {assigned('video')}\n\n"
            "Desktop playback uses central synthesis; its camera records locally.\n"
            "Start assigned local services in Manage Local Models, then reload here."
        )
        return True

    def close(self):
        self.closed = True
        if self.task is not None:
            self.owner.loop.call_soon_threadsafe(self.task.cancel)
        self.owner.model_dialog = None
        self.window.destroy()
