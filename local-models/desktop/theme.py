"""Independent desktop design tokens and shared widgets."""

import tkinter as tk
from tkinter import ttk

BG = "#EDF3F7"
WHITE = "#FFFFFF"
INK = "#183248"
MUTED = "#627788"
LINE = "#D5E2E9"
NAVY = "#102D43"
NAV_HOVER = "#1A4058"
TEAL = "#007F82"
TEAL_DARK = "#006669"
TEAL_BG = "#E8F5F3"
SOFT = "#F5F8FA"
DISABLED = "#8295A2"
FONT = "Segoe UI"
STATUS = {
    "Ready": ("#176A4D", "#EAF7F0"),
    "Installed": ("#176A4D", "#EAF7F0"),
    "Stopped": (MUTED, BG),
    "Available": (TEAL, TEAL_BG),
    "Planned": (MUTED, BG),
    "Not provisioned": (MUTED, BG),
    "Starting": ("#835B12", "#FFF5DE"),
    "Failed": ("#AA302B", "#FDEEEB"),
}


def font(size=10, weight="normal"):
    return FONT, size, weight


def label(parent, text, *, size=10, color=INK, bold=False, bg=None, **options):
    return tk.Label(
        parent,
        text=text,
        font=font(size, "bold" if bold else "normal"),
        fg=color,
        bg=bg or parent.cget("bg"),
        anchor="w",
        **options,
    )


def badge(parent, text, *, status=None):
    fg, bg = STATUS.get(status or text, (TEAL, TEAL_BG))
    return label(parent, text, size=9, color=fg, bold=True, bg=bg, padx=10, pady=5)


def card(parent, **options):
    return tk.Frame(parent, bg=WHITE, highlightbackground=LINE, highlightthickness=1, **options)


def button(parent, text, command=None, *, primary=False, disabled=False):
    return ttk.Button(
        parent,
        text=text,
        command=command,
        style="Primary.TButton" if primary else "TButton",
        state="disabled" if disabled else "normal",
    )


def configure(root):
    root.configure(bg=BG)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TButton", font=font(), padding=(12, 8), background=WHITE, foreground=INK)
    style.map(
        "TButton",
        background=[("disabled", SOFT), ("active", BG)],
        foreground=[("disabled", DISABLED)],
    )
    style.configure("Primary.TButton", background=TEAL, foreground=WHITE, borderwidth=0)
    style.map(
        "Primary.TButton",
        background=[("disabled", "#DDE8EA"), ("active", TEAL_DARK)],
        foreground=[("disabled", "#617C87"), ("active", WHITE)],
    )
    style.configure("TEntry", font=font(), padding=8, fieldbackground=WHITE)
    style.configure("TCombobox", font=font(), padding=7, fieldbackground=WHITE)
    style.map("TCombobox", fieldbackground=[("readonly", WHITE)])
    style.configure("TCheckbutton", font=font(), background=WHITE, foreground=INK, padding=5)
    style.configure("Horizontal.TProgressbar", background=TEAL, troughcolor=BG, borderwidth=0)
    style.configure("Vertical.TScrollbar", background=LINE, troughcolor=BG, borderwidth=0, arrowsize=12)


class ScrollArea(tk.Frame):
    """A keyboard-accessible vertical viewport, scoped to one root/toplevel."""

    def __init__(self, parent, *, bg=BG):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, takefocus=True)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=bg)
        self.item = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._region)
        self.canvas.bind("<Configure>", self._width)
        self._top = self.winfo_toplevel()
        self._wheel_binding = self._top.bind("<MouseWheel>", self._wheel, add="+")
        self.bind("<Destroy>", self._detach, add="+")
        self.canvas.bind("<Prior>", lambda _: self.canvas.yview_scroll(-1, "pages"))
        self.canvas.bind("<Next>", lambda _: self.canvas.yview_scroll(1, "pages"))
        self.canvas.bind("<Home>", lambda _: self.canvas.yview_moveto(0))
        self.canvas.bind("<End>", lambda _: self.canvas.yview_moveto(1))

    def _region(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _width(self, event):
        self.canvas.itemconfigure(self.item, width=event.width)

    def _wheel(self, event):
        target = event.widget
        while target is not None and target is not self:
            target = getattr(target, "master", None)
        if target is self and self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _detach(self, event):
        if event.widget is self:
            self._top.unbind("<MouseWheel>", self._wheel_binding)
