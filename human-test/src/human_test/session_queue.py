"""Tk presentation and operator controls for the shared session supervisor."""

import asyncio
from tkinter import ttk


class SessionQueue:
    def __init__(self, window, parent):
        self.window = window
        self.preview_id = None
        self.frame = ttk.Frame(parent, padding=(26, 8))
        self.label = ttk.Label(self.frame, text="Standalone practice · No trainee assigned", wraplength=750)
        self.label.pack(side="left")
        self.begin_button = ttk.Button(self.frame, text="▶ Begin session", command=self.begin)
        window.root.after(1000, self.tick)

    @property
    def core(self):
        return self.window.runtime.sessions

    @property
    def active(self):
        return self.core.active if self.core else None

    @property
    def next(self):
        return self.core.next if self.core else None

    @property
    def starting(self):
        return bool(self.core and self.core.starting)

    @property
    def finishing(self):
        return bool(self.core and self.core.finishing)

    @property
    def remote_busy(self):
        return bool(self.core and self.core.remote_busy)

    def assigned(self):
        return bool(self.core and self.core.assigned())

    def standalone_active(self):
        return not self.active and (
            self.window.page == "talk" or bool(self.core and self.core.standalone_active())
        )

    def blocks_setup(self):
        return self.assigned() or self.remote_busy or (self.next is not None and not self.standalone_active())

    def tick(self):
        # This timer draws a countdown only. The shared asyncio task owns leases,
        # expiry, capture shutdown and remote-stop handling even if Tk stops pumping.
        if self.window.closing:
            return
        if self.active and not self.starting and not self.finishing:
            remaining = self.core.remaining()
            self.label.configure(
                text=f"Assigned session · {self.active['learner_name']} · "
                f"{self.active['scenario_title']} · {remaining // 60:02}:{remaining % 60:02} remaining"
            )
        self.window.root.after(2000, self.tick)

    def received(self, data):
        w = self.window
        remote = data.get("active")
        if remote or self.next or self.active:
            self.frame.pack(fill="x", before=w.body)
        else:
            self.frame.pack_forget()
        if self.active:
            self.begin_button.pack_forget()
            return
        if self.next and not self.standalone_active() and w.page == "setup" and not w.running:
            self.preview()
        elif not self.next and not remote and self.preview_id and not w.running:
            self.preview_id = None
            w.apply_catalog(w.catalog_data, w.saved)
            w.lock_options(False)
            w.save_button.configure(text="Save & continue")
        if remote:
            self.label.configure(
                text="An assigned session is running on this device · Waiting for it to finish"
            )
        elif self.next:
            if self.standalone_active():
                self.label.configure(text="Assigned session waiting · Finish this practice to continue")
                if w.page == "setup":
                    w.save_button.configure(text="Return to current practice")
            else:
                self.label.configure(
                    text=f"Next: {self.next['learner_name']} · {self.next['scenario_title']} · "
                    f"{self.next['language'].upper()} · {self.next['duration_seconds'] / 60:g} min"
                )
                self.begin_button.pack(side="right")
                self.begin_button.configure(
                    state="disabled" if w.running or self.unavailable_language() else "normal"
                )
                return
        else:
            suffix = " · Queue paused" if data.get("paused") else ""
            self.label.configure(text="Standalone practice · No trainee assigned" + suffix)
        self.begin_button.pack_forget()

    def unavailable_language(self):
        return self.next and self.next["language"] not in self.window.settings.language_choices

    def preview(self):
        """Show assigned choices before Begin without persisting or starting a conversation."""
        w = self.window
        if not self.next or not w.catalog_data:
            return
        identity = (
            self.next["id"],
            self.next["scenario_id"],
            self.next["language"],
            self.next["duration_seconds"],
            tuple(w.settings.language_choices),
        )
        if self.preview_id == identity:
            return
        if self.unavailable_language():
            self.preview_id = identity
            w.clear_case()
            w.case_choice.set(self.next["scenario_title"])
            w.language.set(self.next["language"].upper())
            w.lock_options(False)
            w.save_button.configure(text="Assigned language unavailable", state="disabled")
            w.state.set(
                "The assigned language is unavailable on this device. Update its language setup or the queued assignment."
            )
            return
        if not any(row["id"] == self.next["scenario_id"] for row in w.catalog_data.get("scenarios", [])):
            w.clear_case()
            w.case_choice.set(self.next["scenario_title"])
            w.language.set(self.next["language"].upper())
            w.lock_options(False)
            w.save_button.configure(text="Begin assigned session", state="normal")
            w.state.set("The assigned case will load from the platform when you begin.")
            self.preview_id = identity
            return
        saved = w.saved
        original_catalog = w.catalog_data
        catalog = {
            **original_catalog,
            "default": {"scenario_id": self.next["scenario_id"], "language": self.next["language"]},
        }
        w.apply_catalog(catalog, None)
        w.catalog_data = original_catalog
        w.saved = saved  # Preserve the standalone selection revision until Begin commits its replacement.
        self.preview_id = identity
        w.lock_options(False)
        w.save_button.configure(text="Begin assigned session")
        w.state.set("Assigned practice is selected. Begin when the trainee is ready.")

    def begin(self):
        if self.window.running or self.standalone_active() or not self.next or self.assigned():
            return
        if self.unavailable_language():
            self.preview()
            return
        self.begin_button.configure(state="disabled")
        self.window.submit(self.core.begin(), "setup_saved")

    def begun(self, result, saved):
        self.window.practice_identity.set(f"Assigned session · {result['learner_name']}")
        self.window.save_button.configure(text="Return to session")
        self.window.emit("saved", saved)
        self.label.configure(text=f"Assigned session · {result['learner_name']} · {result['scenario_title']}")
        self.begin_button.pack_forget()

    def stopping(self):
        self.window.listening = False
        self.label.configure(text="Ending session · Waiting for platform confirmation")

    def finish(self, outcome="completed"):
        if not self.core or self.finishing or self.starting:
            return
        # Finishing cancels active work itself; it must not wait on the UI's
        # operation lock held by a continuous microphone session.
        future = asyncio.run_coroutine_threadsafe(self.core.finish(outcome), self.window.loop)

        def completed(task):
            try:
                task.result()
            except Exception:
                pass  # The core emits the failure and retains ownership for retry.

        future.add_done_callback(completed)

    def finished(self):
        if self.window.running:
            self.window.root.after(100, self.finished)
            return
        self.preview_id = None
        self.window.practice_identity.set("Standalone practice · No trainee assigned")
        self.window.back()
        self.window.lock_options(False)
        self.window.save_button.configure(text="Save & continue")
        self.label.configure(text="Practice completed · Checking for the next trainee")

    async def close(self):
        if self.core:
            await self.core.close()
