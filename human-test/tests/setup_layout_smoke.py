"""Native geometry regression for setup actions outside the scrolling content."""

import time
import tkinter as tk
from unittest.mock import patch

from human_test.app import Window
from human_test.config import Settings


def main():
    async def initialize(self):
        self.emit(
            "catalog",
            (
                {
                    "categories": [],
                    "patients": [],
                    "cases": [],
                    "scenarios": [
                        {
                            "id": "fixture",
                            "title": "Patient interview",
                            "version": 1,
                            "specialty": "Cardiology",
                            "languages": ["en"],
                            "vitals": {},
                        }
                    ],
                },
                None,
            ),
        )

    with patch.object(Window, "initialize", initialize), patch("human_test.app.microphones", return_value=[]):
        root = tk.Tk()
        failures = []
        root.report_callback_exception = lambda *error: failures.append(error)
        window = Window(root, Settings(_env_file=None, speaker_output=False))
        try:
            deadline = time.monotonic() + 5
            while window.running:
                root.update()
                assert time.monotonic() < deadline
                time.sleep(0.01)
            for size in ("1180x860", "1080x800", "1080x680"):
                root.geometry(size)
                root.update()
                window.setup_canvas.yview_moveto(0)
                root.update()
                button_y = window.save_button.winfo_rooty()
                for button in (window.save_button, window.reload_button):
                    assert button.winfo_ismapped()
                    assert (
                        button.winfo_rooty()
                        >= window.setup_canvas.winfo_rooty() + window.setup_canvas.winfo_height()
                    )
                    assert (
                        button.winfo_rooty() + button.winfo_height()
                        <= root.winfo_rooty() + root.winfo_height()
                    )
                    assert (
                        button.winfo_rootx() + button.winfo_width() <= root.winfo_rootx() + root.winfo_width()
                    )
                if size != "1080x680":
                    assert window.setup_canvas.yview() == (0.0, 1.0), (size, window.setup_canvas.yview())
                for field in (window.case_box, window.lang_box, *window.vital_entries):
                    assert field.winfo_rootx() >= window.setup_canvas.winfo_rootx()
                    assert field.winfo_rootx() + field.winfo_width() <= (
                        window.setup_canvas.winfo_rootx() + window.setup_canvas.winfo_width()
                    )
                # Long case histories may scroll, but the action bar must never move.
                window.case_summary.set("Long patient history.\n" * 35)
                root.update()
                for position in (0, 1):
                    window.setup_canvas.yview_moveto(position)
                    root.update()
                    assert window.save_button.winfo_rooty() == button_y
                window.case_summary.set("Patient interview")
            window.setup_frame.pack_forget()
            window.talk_frame.pack(fill="both", expand=True)
            window.page = "talk"
            window.show_typing.set(True)
            window.apply_layout()
            root.update()
            assert window.previous_button.winfo_ismapped()
            assert window.previous_button.winfo_rootx() < window.complete_button.winfo_rootx()
            assert window.complete_button.winfo_rootx() + window.complete_button.winfo_width() <= (
                root.winfo_rootx() + root.winfo_width()
            )
            window.previous_button.invoke()
            root.update()
            assert window.page == "setup" and window.save_button.winfo_ismapped()
            assert not failures, failures
        finally:
            window.close()
            root.mainloop()
    print(
        "Setup actions remain visible at 1180x860, 1080x800 and 1080x680; normal and long case text checked"
    )


if __name__ == "__main__":
    main()
