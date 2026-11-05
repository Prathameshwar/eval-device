"""Small vector line icons drawn locally; no fonts, downloads or bitmap assets."""

import tkinter as tk

from .theme import TEAL


def app_icon(root):
    """Draw a small stack mark for the native title bar and task switcher."""
    picture = tk.PhotoImage(master=root, width=32, height=32)
    picture.put("#102D43", to=(0, 0, 32, 32))
    paths = (
        ((5, 10), (16, 5), (27, 10), (16, 15), (5, 10)),
        ((5, 16), (16, 21), (27, 16)),
        ((5, 22), (16, 27), (27, 22)),
    )
    for points in paths:
        for (x1, y1), (x2, y2) in zip(points, points[1:], strict=False):
            steps = max(abs(x2 - x1), abs(y2 - y1))
            for step in range(steps + 1):
                x = round(x1 + (x2 - x1) * step / steps)
                y = round(y1 + (y2 - y1) * step / steps)
                picture.put("#61D4C6", to=(x, y, x + 2, y + 2))
    return picture


class Icon(tk.Canvas):
    def __init__(self, parent, name, *, size=24, color=TEAL, bg=None):
        super().__init__(parent, width=size, height=size, bg=bg or parent.cget("bg"), highlightthickness=0)
        scale = size / 24

        def line(*points):
            self.create_line(*(p * scale for p in points), fill=color, width=1.6, capstyle="round")

        def box(x1, y1, x2, y2):
            self.create_rectangle(x1 * scale, y1 * scale, x2 * scale, y2 * scale, outline=color, width=1.5)

        def oval(x1, y1, x2, y2):
            self.create_oval(x1 * scale, y1 * scale, x2 * scale, y2 * scale, outline=color, width=1.5)

        if name == "overview":
            for x, y in ((3, 3), (14, 3), (3, 14), (14, 14)):
                box(x, y, x + 7, y + 7)
        elif name in ("models", "llm"):
            line(3, 7, 12, 3, 21, 7, 12, 11, 3, 7)
            line(3, 12, 12, 16, 21, 12)
            line(3, 17, 12, 21, 21, 17)
        elif name == "services":
            box(3, 3, 21, 10)
            box(3, 14, 21, 21)
            line(7, 6, 7, 7)
            line(7, 17, 7, 18)
            line(13, 6, 17, 6)
            line(13, 17, 17, 17)
        elif name == "logs":
            box(5, 3, 19, 21)
            for y in (8, 12, 16):
                line(8, y, 16, y)
        elif name == "settings":
            for y, x in ((5, 8), (12, 16), (19, 10)):
                line(3, y, 21, y)
                oval(x - 2, y - 2, x + 2, y + 2)
        elif name == "audio":
            oval(8, 3, 16, 15)
            line(5, 11, 5, 14, 8, 18, 16, 18, 19, 14, 19, 11)
            line(12, 18, 12, 22)
            line(8, 22, 16, 22)
        elif name == "voice":
            line(3, 9, 7, 9, 12, 4, 12, 20, 7, 15, 3, 15, 3, 9)
            line(16, 8, 18, 12, 16, 16)
            line(19, 5, 22, 12, 19, 19)
        elif name == "video":
            box(3, 6, 16, 18)
            line(16, 10, 21, 7, 21, 17, 16, 14)
        elif name == "gpu":
            box(6, 6, 18, 18)
            box(9, 9, 15, 15)
            for p in (8, 12, 16):
                line(p, 2, p, 5)
                line(p, 19, p, 22)
                line(2, p, 5, p)
                line(19, p, 22, p)
        elif name == "storage":
            box(3, 5, 21, 19)
            line(3, 14, 21, 14)
            line(16, 17, 18, 17)
        elif name == "download":
            line(12, 3, 12, 15)
            line(7, 10, 12, 15, 17, 10)
            line(3, 16, 3, 21, 21, 21, 21, 16)
        elif name == "info":
            oval(3, 3, 21, 21)
            line(12, 11, 12, 17)
            line(12, 7, 12, 8)
