"""Native layout and lifecycle with generated frames, or explicit --physical webcam testing."""

import argparse
import time
import tkinter as tk
from pathlib import Path
from tempfile import TemporaryDirectory

from training_client import video

from human_test import app
from human_test.config import Settings


class Frames:
    def read(self):
        import numpy as np

        return True, np.full((480, 640, 3), (80, 120, 180), dtype=np.uint8)

    def release(self):
        pass


def synthetic_worker(options, stop, previews, events, heartbeat):
    video.record(options, stop, previews, events, heartbeat, camera_factory=lambda _: Frames())


async def initialize(self):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--physical", action="store_true", help="Explicitly test webcam 0; never used by pytest"
    )
    args = parser.parse_args()
    app.Window.initialize = initialize
    app.microphones = lambda: []
    if not args.physical:
        video.record = synthetic_worker
    with TemporaryDirectory() as directory:
        root = tk.Tk()
        root.withdraw()
        window = app.Window(
            root,
            Settings(
                _env_file=None, use_pms_models=True, speaker_output=False, video_recording_dir=Path(directory)
            ),
        )
        root.geometry("1080x800")
        root.attributes("-alpha", 1.0 if args.physical else 0.0)
        root.deiconify()
        window.setup_frame.pack_forget()
        window.talk_frame.pack(fill="both", expand=True)
        window.page = "talk"
        window.camera_view.checkbox.invoke()

        def until(predicate):
            deadline = time.monotonic() + 10
            while not predicate() and time.monotonic() < deadline:
                root.update()
                time.sleep(0.02)
            assert predicate(), window.camera_view.status.get()

        def inside(widget, parent):
            x, y = widget.winfo_rootx(), widget.winfo_rooty()
            assert widget.winfo_ismapped()
            assert (
                parent.winfo_rootx()
                <= x
                < x + widget.winfo_width()
                <= (parent.winfo_rootx() + parent.winfo_width())
            ), str(widget)
            assert (
                parent.winfo_rooty()
                <= y
                < y + widget.winfo_height()
                <= (parent.winfo_rooty() + parent.winfo_height())
            ), str(widget)

        try:
            until(lambda: window.camera_view.photo is not None and not window.running)
            if args.physical:
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.02)
            for geometry in ("1080x800", "1180x860", "1440x900"):
                root.geometry(geometry)
                root.update()
                root.update_idletasks()
                stage, drawer, dock = window.patient_panel, window.interview_panel, window.conversation_header
                page = window.conversation_panel
                # Drawer closed by default: the stage spans the page and the dock sits below it.
                assert not window.show_text.get() and not drawer.winfo_ismapped()
                assert not window.typed_frame.winfo_ismapped()
                assert abs(stage.winfo_width() - page.winfo_width()) <= 2
                assert stage.winfo_rooty() + stage.winfo_height() <= dock.winfo_rooty()
                assert window.manikin.winfo_height() >= 450, window.manikin.winfo_height()
                assert window.manikin.winfo_width() >= 900
                for widget in (stage, dock):
                    inside(widget, window.talk_frame)
                for widget in (window.stage_head, window.manikin, window.menu_button):
                    inside(widget, stage)
                for widget in (window.start_button,):
                    inside(widget, dock)
                # The preview floats over the stage's bottom-right corner while capturing.
                preview = window.camera_view.preview
                inside(preview, stage)
                assert (
                    preview.winfo_rootx() + preview.winfo_width() <= stage.winfo_rootx() + stage.winfo_width()
                )
                assert (
                    preview.winfo_rooty() > window.stage_head.winfo_rooty() + window.stage_head.winfo_height()
                )
                # Opening the drawer from the menu narrows the stage by exactly the drawer's width.
                window.show_text.set(True)
                window.show_typing.set(True)
                window.apply_layout()
                root.update()
                root.update_idletasks()
                assert drawer.winfo_ismapped() and window.typed_frame.winfo_ismapped()
                assert stage.winfo_rootx() + stage.winfo_width() < drawer.winfo_rootx()
                assert stage.winfo_rooty() == drawer.winfo_rooty()
                assert stage.winfo_height() == drawer.winfo_height()
                assert stage.winfo_width() >= drawer.winfo_width() * 1.3
                assert window.question.winfo_height() >= 40
                assert window.answer.winfo_height() >= 60
                for widget in (
                    window.camera_view,
                    window.question,
                    window.answer,
                    window.back_button,
                    window.mic_box,
                    window.voice_box,
                ):
                    inside(widget, drawer)
                for button in window.back_button.master.winfo_children():
                    assert button.winfo_width() >= button.winfo_reqwidth(), button.cget("text")
                for widget in (window.start_button, window.question_entry, window.ask_button):
                    inside(widget, dock)
                for widget in (window.camera_view.path_entry, window.camera_view.selector):
                    inside(widget, window.camera_view)
                path, checkbox = window.camera_view.path_entry, window.camera_view.checkbox
                assert checkbox.winfo_rooty() + checkbox.winfo_height() <= path.winfo_rooty()
                assert path.winfo_width() == window.camera_view.winfo_width()
                inside(preview, stage)
                window.show_text.set(False)
                window.show_typing.set(False)
                window.apply_layout()
                root.update()
                root.update_idletasks()
                assert not drawer.winfo_ismapped()
                assert abs(stage.winfo_width() - page.winfo_width()) <= 2
                print(geometry, "stage-first layout, drawer toggles, floating camera preview verified")
            # Camera off hides the floating preview without moving the patient.
            patient_height = window.manikin.winfo_height()
            window.camera_view.checkbox.invoke()
            until(lambda: not window.camera_view.recorder.busy)
            root.update()
            assert window.manikin.winfo_height() == patient_height
            assert not window.camera_view.preview.winfo_ismapped()
            window.camera_view.checkbox.invoke()
            until(lambda: window.camera_view.photo is not None)
            window.back()
            until(lambda: not window.camera_view.recorder.busy)
            assert not window.camera_view.enabled.get()
            window.camera_view.checkbox.invoke()
            until(lambda: window.camera_view.photo is not None)
            window.close()
            until(lambda: not window.worker.is_alive() and not window.camera_view.recorder.busy)
            assert not root.tk.splitlist(root.tk.call("after", "info")), "Shutdown left Tk callbacks pending"
            files = list(Path(directory).rglob("*.mkv"))
            assert len(files) == 3
            import av

            for path in files:
                with av.open(str(path)) as container:
                    frames = list(container.decode(video=0))
                    assert frames and all(frame.width <= 640 and frame.height <= 480 for frame in frames)
        finally:
            if not window.closing:
                window.close()
                until(lambda: not window.worker.is_alive())
    print(
        "Physical webcam" if args.physical else "Generated frames",
        "layout, playable recordings, Back and Close verified",
    )


if __name__ == "__main__":
    main()
