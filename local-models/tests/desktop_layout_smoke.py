"""Explicit native UI check; no models, installers or background services are used.

Run: python local-models/tests/desktop_layout_smoke.py
"""

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop.app import ModelManager  # noqa: E402
from desktop.preview import MODELS, SERVICES  # noqa: E402


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def main():
    if "--live" in sys.argv:
        from desktop_live_smoke import main as live_main

        live_main()
        return
    root = tk.Tk()
    failures = []
    root.report_callback_exception = lambda *error: failures.append(error)
    app = ModelManager(root)
    checks = 0
    try:
        for size in ("1280x820", "1040x700", "1600x1000"):
            root.geometry(size)
            for page in app.PAGES:
                app.nav_buttons[page].invoke()
                root.update()
                assert app.page == page
                canvas = app.scroll.canvas
                assert canvas.winfo_width() > 700
                assert app.body.winfo_reqwidth() <= canvas.winfo_width(), (size, page)
                assert app.scroll.canvas.bbox("all")[2] <= canvas.winfo_width()
                for frame in descendants(app.body):
                    if isinstance(frame, tk.Frame) and frame.grid_slaves():
                        cards = [
                            w
                            for w in frame.grid_slaves()
                            if isinstance(w, tk.Frame) and int(w.cget("highlightthickness")) == 1
                        ]
                        if cards and all(int(w.grid_info()["column"]) == 0 for w in cards):
                            assert all(w.winfo_width() >= frame.winfo_width() - 4 for w in cards)
                for control in descendants(app.body):
                    if isinstance(control, ttk.Button) and str(control.cget("text")) in (
                        "Download",
                        "Download video model",
                        "Start Service",
                        "Stop Service",
                        "Export Logs",
                        "Follow latest",
                        "Save settings",
                    ):
                        assert control.instate(["disabled"]), control.cget("text")
                checks += 1
            app.show_page("Models")
            root.update()
            for category in ("LLM", "Audio", "Video", "Installed", "All"):
                app.tab_buttons[category].invoke()
                root.update()
                # Empty/planned categories must not retain a destroyed card-grid callback.
                root.geometry("1040x700" if category in ("Video", "Installed") else size)
                root.update()
                checks += 1
            app.search.set("does not match")
            root.update()
            assert any(
                isinstance(w, tk.Label) and w.cget("text") == "No matching models"
                for w in descendants(app.model_results)
            )
            app._open_logs("Speech recognition")
            root.update()
            content = app.log_text.get("1.0", "end")
            assert "Worker stopped" in content and "Model loaded" not in content
            app.log_level.set("ERROR")
            app._render_logs()
            assert "No sample events" in app.log_text.get("1.0", "end")
            assert app.log_text.cget("state") == "disabled"
            checks += 3
        for show in (
            lambda: app._model_detail(MODELS[0]),
            lambda: app._service_detail(SERVICES[0]),
            app._provision,
        ):
            show()
            root.update()
            app.dialog.geometry("560x520")
            root.update()
            for widget in descendants(app.dialog):
                if isinstance(widget, ttk.Button):
                    if widget.cget("text") != "Close":
                        assert widget.instate(["disabled"])
                    assert widget.winfo_rooty() + widget.winfo_height() <= (
                        app.dialog.winfo_rooty() + app.dialog.winfo_height()
                    )
            app.dialog.destroy()
            root.update()
            checks += 1
        assert not failures, failures
    finally:
        root.destroy()
    print(f"{checks} native UI checks passed: pages, resizing, filters, dialogs and disabled operations.")


if __name__ == "__main__":
    main()
