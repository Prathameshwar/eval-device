"""Manual Tk smoke check for the read-only device model summary."""

import asyncio
import tkinter as tk
from types import SimpleNamespace

from human_test.model_dialog import ModelDialog


def main():
    root = tk.Tk()
    root.withdraw()
    events, applied = [], []
    route = {
        "mode": "local",
        "llm": {"model": "qwen3-4b-local"},
        "audio": {"enabled": False, "model": "large-v3"},
    }

    async def assigned():
        applied.append(route)
        return route

    owner = SimpleNamespace(
        root=root,
        running=False,
        model_dialog=None,
        controller=SimpleNamespace(pms=SimpleNamespace(model_config=assigned), use_models=applied.append),
        runtime=SimpleNamespace(reload_models=assigned),
        emit=lambda kind, value: events.append(value),
        submit=lambda action, _: asyncio.run(action),
    )
    dialog = ModelDialog(owner)
    owner.model_dialog = dialog
    root.update()
    dialog.handle(events.pop())
    assert "qwen3-4b-local" in dialog.summary.get()
    assert "Speech recognition: None" in dialog.summary.get()
    assert applied == [route]

    def widgets(parent):
        for child in parent.winfo_children():
            yield child
            yield from widgets(child)

    assert not any(widget.winfo_class() == "TCombobox" for widget in widgets(dialog.window))
    buttons = [widget.cget("text") for widget in widgets(dialog.window) if widget.winfo_class() == "TButton"]
    assert buttons == ["Reload assigned models"]
    dialog.window.geometry("560x520")
    root.update()
    for widget in widgets(dialog.window):
        if widget.winfo_class() in {"TLabel", "TButton"}:
            left = widget.winfo_rootx() - dialog.window.winfo_rootx()
            top = widget.winfo_rooty() - dialog.window.winfo_rooty()
            assert left >= 0 and top >= 0
            assert left + widget.winfo_width() <= dialog.window.winfo_width()
            assert top + widget.winfo_height() <= dialog.window.winfo_height()
    dialog.close()
    root.destroy()
    print("Read-only device model summary passed")


if __name__ == "__main__":
    main()
