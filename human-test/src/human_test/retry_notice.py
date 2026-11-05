"""Centered, non-modal retry status; updated only on the Tk thread."""

import time
import tkinter as tk
from math import ceil, cos, sin
from tkinter import ttk


class RetryNotice(tk.Frame):
    def __init__(self, parent, cancel, toolbar):
        super().__init__(
            parent, bg="white", highlightbackground="#b7cbd5", highlightthickness=1, padx=28, pady=24
        )
        self.started = None
        self.deadline = 0.0
        self.phase = "waiting"
        self.job = None
        self.toolbar = toolbar
        self.title = tk.StringVar(self)
        self.detail = tk.StringVar(self)
        self.position = tk.StringVar(self)
        self.countdown = tk.StringVar(self)
        self.elapsed = tk.StringVar(self)
        self.clock = tk.Canvas(self, width=56, height=56, bg="white", highlightthickness=0)
        self.clock.pack(pady=(0, 12))
        self.clock.create_oval(3, 3, 53, 53, fill="#edf7f6", outline="#b4d9d6", width=1)
        self.clock.create_line(28, 28, 28, 15, fill="#183248", width=3, capstyle="round")
        self.hand = self.clock.create_line(28, 28, 42, 28, fill="#007f82", width=2, capstyle="round")
        self.clock.create_oval(25, 25, 31, 31, fill="#007f82", outline="")
        self.label(self.title, ("Segoe UI", 17, "bold"), "#183248").pack()
        self.label(self.detail, ("Segoe UI", 10), "#627788").pack(pady=(8, 16))
        self.position_label = tk.Label(
            self,
            textvariable=self.position,
            font=("Segoe UI", 10, "bold"),
            bg="#f2f7fa",
            fg="#183248",
            padx=14,
            pady=9,
            highlightbackground="#d5e2e9",
            highlightthickness=1,
        )
        self.position_label.pack(fill="x")
        self.label(self.countdown, ("Segoe UI", 19, "bold"), "#007f82").pack(pady=(16, 4))
        self.label(self.elapsed, ("Segoe UI", 10), "#627788").pack()
        tk.Label(
            self,
            text="Microphone and speaker are paused.",
            bg="white",
            fg="#627788",
            font=("Segoe UI", 10),
        ).pack(pady=(12, 16))
        self.cancel_button = ttk.Button(self, text="Cancel queued question", command=cancel)
        self.cancel_button.pack()
        self.bind("<Destroy>", self.destroyed, add="+")
        parent.bind("<Configure>", self.layout, add="+")

    def label(self, variable, font, color):
        return tk.Label(
            self, textvariable=variable, bg="white", fg=color, font=font, wraplength=400, justify="center"
        )

    def show(self, status):
        now = time.monotonic()
        if self.started is None:
            self.started = now
        self.phase = status["phase"]
        self.deadline = now + status["wait_seconds"]
        speech = status["label"] == "Speech service"
        service = "speech service" if speech else "response model"
        self.title.set(
            f"Retrying {service}" if self.phase == "submitting" else f"{service.capitalize()} is busy"
        )
        self.detail.set(
            "Your recorded question is retained.\nYou do not need to speak again."
            if speech
            else "Your question is retained.\nYou do not need to send it again."
        )
        self.position.set(
            f"Next: round {status['round']} of {status['rounds']}"
            if self.phase == "between_rounds"
            else f"Round {status['round']} of {status['rounds']}  ·  Retry {status['retry']} of {status['retries']}"
        )
        self.layout()
        if self.job is not None:
            self.after_cancel(self.job)
        self.tick()

    def layout(self, event=None):
        if self.started is not None:
            # Center over the interview, keeping the microphone toolbar accessible.
            top = self.toolbar.winfo_y() + self.toolbar.winfo_height() + 12
            position = self.place_info()
            if not position or int(position["y"]) != round(top / 2):
                self.place(relx=0.5, rely=0.5, y=round(top / 2), anchor="center", width=464)
            self.lift()

    def tick(self):
        self.job = None
        if self.started is None:
            return
        now = time.monotonic()
        seconds = max(0, ceil(self.deadline - now))
        if self.phase == "submitting":
            self.countdown.set("Retry request in progress…")
        elif seconds:
            next_step = "Next round" if self.phase == "between_rounds" else "Next attempt"
            self.countdown.set(f"{next_step} in {seconds} s")
        else:
            self.countdown.set("Preparing next attempt…")
        waited = max(0, int(now - self.started))
        self.elapsed.set(f"Waiting {waited // 60:02d}:{waited % 60:02d}")
        angle = (now - self.started) * 1.5
        self.clock.coords(self.hand, 28, 28, 28 + 17 * sin(angle), 28 - 17 * cos(angle))
        self.job = self.after(200, self.tick)

    def hide(self):
        if self.job is not None:
            self.after_cancel(self.job)
            self.job = None
        self.started = None
        self.place_forget()

    def destroyed(self, event):
        if event.widget is self:
            if self.job is not None:
                self.after_cancel(self.job)
                self.job = None
            self.started = None
