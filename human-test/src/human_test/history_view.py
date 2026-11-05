"""Read-only recent local exchanges; no inference or playback actions."""

import asyncio
import tkinter as tk
from datetime import datetime
from tkinter import ttk

STATUS = {
    "pending_local_save": "Waiting to save locally",
    "saved_locally": "Saved locally; upload pending",
    "saved_to_pms": "Saved to PMS",
    "not_saved": "History was not saved",
    "upload_rejected": "Saved locally; PMS rejected upload",
    "authentication_required": "Saved locally; sign in again to upload",
    "pending_expired": "An expired pending record was removed",
    "incomplete_files": "An incomplete history file was detected",
    "cleanup_failed": "History cleanup needs attention",
    "flush_incomplete": "Some queued history may not have been saved",
    "metrics_not_saved": "Turn metrics were not saved",
}


def display_record(row):
    return (
        f"Input\n{row['input_text']}\n\nResponse\n{row.get('response_text') or '(No completed answer)'}\n\n"
        f"Source: {row.get('answer_source', '')}   Language: {row.get('language', '')}\n"
        f"{STATUS.get(row.get('save_status'), row.get('save_status', ''))}"
    )


class HistoryView:
    def __init__(self, parent, loop, controller):
        self.window = tk.Toplevel(parent)
        self.window.title("Local conversation history")
        self.window.geometry("900x610")
        self.loop, self.controller, self.future = loop, controller, None
        self.rows = {}
        bar = ttk.Frame(self.window, padding=10)
        bar.pack(fill="x")
        self.message = tk.StringVar(value="Loading history...")
        ttk.Label(bar, textvariable=self.message).pack(side="left")
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="right")
        self.table = ttk.Treeview(
            self.window, columns=("time", "model", "status"), show="headings", height=10
        )
        for column, width in (("time", 190), ("model", 210), ("status", 350)):
            self.table.heading(column, text=column.title())
            self.table.column(column, width=width)
        self.table.pack(fill="x", padx=10)
        self.table.bind("<<TreeviewSelect>>", self.selected)
        frame = ttk.Frame(self.window, padding=10)
        frame.pack(fill="both", expand=True)
        self.text = tk.Text(frame, wrap="word", state="disabled", font=("Segoe UI", 11))
        scroll = ttk.Scrollbar(frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

    def refresh(self):
        if self.future and not self.future.done():
            return
        self.message.set("Loading history...")
        self.future = asyncio.run_coroutine_threadsafe(self.controller.history_items(), self.loop)
        self.window.after(50, self.poll)

    def poll(self):
        if not self.window.winfo_exists():
            return
        if not self.future.done():
            self.window.after(50, self.poll)
            return
        try:
            result = self.future.result()
            self.message.set(result["message"])
            self.rows = {row["turn_key"]: row for row in result["items"]}
            for item in self.table.get_children():
                self.table.delete(item)
            for key, row in self.rows.items():
                when = datetime.fromisoformat(row["occurred_at"]).astimezone().strftime("%d %b %H:%M:%S")
                self.table.insert(
                    "",
                    "end",
                    iid=key,
                    values=(when, row["model"], STATUS.get(row["save_status"], row["save_status"])),
                )
            if self.rows:
                self.table.selection_set(next(iter(self.rows)))
            else:
                self.replace("No retained completed local exchanges.")
        except Exception:
            self.message.set("History could not be loaded")

    def replace(self, value):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self.text.configure(state="disabled")

    def selected(self, event=None):
        selected = self.table.selection()
        if selected:
            self.replace(display_record(self.rows[selected[0]]))

    def close(self):
        if self.future and not self.future.done():
            self.future.cancel()
        self.window.destroy()
