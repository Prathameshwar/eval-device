"""Native regression: drawer/video/title changes never obscure the stage menu."""

import argparse
import time
import tkinter as tk
from unittest.mock import patch

from human_test.app import Window
from human_test.config import Settings


def bounds(widget):
    return (
        widget.winfo_rootx(),
        widget.winfo_rooty(),
        widget.winfo_rootx() + widget.winfo_width(),
        widget.winfo_rooty() + widget.winfo_height(),
    )


def inside(widget, parent):
    x, y, right, bottom = bounds(widget)
    px, py, pright, pbottom = bounds(parent)
    assert widget.winfo_ismapped(), str(widget)
    assert px <= x < right <= pright and py <= y < bottom <= pbottom, (str(widget), bounds(widget))


def visible_bounds(widget):
    """Account for native clipping at each ancestor, including tiny patient areas."""
    x, y, right, bottom = bounds(widget)
    while widget.winfo_parent():
        widget = widget.nametowidget(widget.winfo_parent())
        px, py, pright, pbottom = bounds(widget)
        x, y, right, bottom = max(x, px), max(y, py), min(right, pright), min(bottom, pbottom)
    return x, y, right, bottom


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scaling", type=float, default=4 / 3)
    args = parser.parse_args()

    async def initialize(self):
        pass

    with (
        patch.object(Window, "initialize", initialize),
        patch("human_test.app.microphones", return_value=[]),
    ):
        root = tk.Tk()
        root.withdraw()
        root.attributes("-alpha", 0.0)
        root.tk.call("tk", "scaling", args.scaling)
        window = Window(root, Settings(_env_file=None, speaker_output=False))
        root.deiconify()
        failures = []
        root.report_callback_exception = lambda *error: failures.append(error)
        cases = 0
        try:
            deadline = time.monotonic() + 5
            while window.running:
                root.update()
                assert time.monotonic() < deadline
                time.sleep(0.01)
            window.setup_frame.pack_forget()
            window.talk_frame.pack(fill="both", expand=True)
            window.page = "talk"
            # 500/600px intentionally stress the layout below the normal minimum.
            root.minsize(1080, 500)
            for size in ("1180x860", "1080x680", "1366x680", "1080x600", "1080x500"):
                root.geometry(size)
                for title in (
                    "Alex",
                    "Alex — Clinical interview with a long patient presentation and scenario title",
                ):
                    window.active_case.set(title)
                    for show_text in (False, True):
                        window.show_text.set(show_text)
                        for show_typing in (False, True):
                            window.show_typing.set(show_typing)
                            window.apply_layout()
                            for show_preview in (False, True):
                                if show_preview:
                                    window.camera_view.show_preview()
                                else:
                                    window.camera_view.hide_preview()
                                root.update()
                                root.update_idletasks()
                                inside(window.menu_button, window.stage_head)
                                inside(window.menu_button, window.patient_panel)
                                inside(window.menu_button, root)
                                assert window.menu_button.cget("command")
                                if show_preview and window.camera_view.preview.winfo_ismapped():
                                    x, y, right, bottom = bounds(window.menu_button)
                                    px, py, pright, pbottom = visible_bounds(window.camera_view.preview)
                                    assert not (
                                        max(x, px) < min(right, pright) and max(y, py) < min(bottom, pbottom)
                                    ), "Camera preview covers the conversation menu"
                                assert bool(window.interview_panel.winfo_ismapped()) == show_text
                                cases += 1
            # The same menu command can close and reopen the drawer while preview is shown.
            window.menu.menu.invoke(window.menu.index["text"])
            root.update()
            assert not window.show_text.get() and not window.interview_panel.winfo_ismapped()
            window.menu.menu.invoke(window.menu.index["text"])
            root.update()
            assert window.show_text.get() and window.interview_panel.winfo_ismapped()
            assert not failures, failures
        finally:
            window.close()
            root.mainloop()
    print(f"Conversation menu stays visible: {cases} layouts at Tk scaling {args.scaling:.3f}")


if __name__ == "__main__":
    main()
