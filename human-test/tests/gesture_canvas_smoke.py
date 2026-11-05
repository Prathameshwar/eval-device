"""Native canvas checks with simulated playback; no services or audio devices."""

import tkinter as tk
from types import SimpleNamespace

from human_test import manikin as drawing
from human_test.gestures import HEAD_GESTURE_CHANCE, EyeBlink, IdleLegGesture, SpeechGesture


class ChooseGesture:
    def __init__(self, kind, side, chance=0.0):
        self.kind, self.side = kind, side
        self.chance = chance

    def random(self):
        return self.chance

    def choice(self, values):
        chosen = self.kind if isinstance(values[0], str) else self.side
        assert chosen in values
        return chosen

    def uniform(self, low, high):
        return low


def main():
    clock = [100.0]
    drawing.time = SimpleNamespace(monotonic=lambda: clock[0])
    root = tk.Tk()
    root.attributes("-alpha", 0.0)
    root.geometry("638x425")
    patient = drawing.Manikin(root)
    patient.pack(fill="both", expand=True)
    root.update()

    def geometry():
        return [tuple(patient.canvas.coords(item)) for item in patient.canvas.find_all()]

    try:
        for kind in ("hand", "finger", "leg", "head"):
            for side in (1, -1):
                clock[0] = 100.0
                patient.head_gesture = SpeechGesture(
                    ChooseGesture("head", side, chance=0.0 if kind == "head" else 1.0),
                    chance=HEAD_GESTURE_CHANCE,
                    kinds=("head",),
                )
                if kind == "leg":
                    patient.idle_leg = IdleLegGesture(ChooseGesture(kind, side))
                else:
                    patient.gestures = SpeechGesture(
                        ChooseGesture(
                            "hand" if kind == "head" else kind, side, chance=1.0 if kind == "head" else 0.0
                        )
                    )
                    patient.speak("An answer long enough to exercise a small gesture during speech.")
                patient.frame = 2
                patient.draw()
                baseline = geometry()
                timers = root.tk.call("after", "info")
                if kind == "leg":
                    for now in (100, 115, 115.8):
                        clock[0] = now
                        patient.update_idle_gesture(True)
                else:
                    patient.prepare_speech_gesture(0)
                    for step in range(15):
                        clock[0] = 100 + step / 10
                        patient.update_speech_gesture(True, step + 1)
                patient.draw()
                moved = geometry()
                changed = [
                    i
                    for i, (before, after) in enumerate(zip(baseline, moved, strict=True))
                    if before != after
                ]
                # Only the selected limb changes; leg motion shares the trouser outline
                # with the stationary thigh and opposite leg.
                head_items = [
                    i
                    for i, item in enumerate(patient.canvas.find_all())
                    if "head" in patient.canvas.gettags(item)
                ]
                assert len(changed) == {"finger": 8, "hand": 14, "leg": 6, "head": len(head_items)}[kind], (
                    kind,
                    changed,
                )
                if kind == "head":
                    assert changed == head_items, (
                        "The whole head must move together, with the neck and body fixed"
                    )
                displacement = max(
                    ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
                    for before, after in zip(baseline, moved, strict=True)
                    for x0, y0, x1, y1 in zip(before[::2], before[1::2], after[::2], after[1::2], strict=True)
                )
                assert displacement >= {"finger": 5, "hand": 8, "leg": 10, "head": 2}[kind], (
                    kind,
                    displacement,
                )
                if kind == "head":
                    assert displacement <= 5, "Head movement must stay restrained"
                center = patient.canvas.winfo_width() / 2
                for index in changed:
                    for x0, y0, x1, y1 in zip(
                        baseline[index][::2],
                        baseline[index][1::2],
                        moved[index][::2],
                        moved[index][1::2],
                        strict=True,
                    ):
                        if (x0, y0) != (x1, y1):
                            if kind != "head":
                                assert (x1 < center) if side == 1 else (x1 > center)
                            if kind == "leg":
                                # The seat, thigh and knee stay fixed above local y=230.
                                reserve = drawing.FOOTER_RESERVE + drawing.TOP_OFFSET
                                scale = min(
                                    (patient.canvas.winfo_width() - 24) / 500,
                                    (patient.canvas.winfo_height() - reserve) / 342,
                                )
                                knee_y = (
                                    drawing.TOP_OFFSET
                                    + (patient.canvas.winfo_height() - reserve - 342 * scale) / 2
                                    + 230 * scale
                                )
                                assert y0 > knee_y and y1 > knee_y
                assert patient.frame == 2 and root.tk.call("after", "info") == timers
                if kind == "leg":
                    patient.update_idle_gesture(False)
                else:
                    patient.update_speech_gesture(False, 15)
                assert geometry() == baseline, "Playback completion must restore rest immediately"
                patient.stop_animation()
                assert patient.animation_job is None and not root.tk.call("after", "info")
        # Head and hand controllers must both update/reset, even if one reports a change.
        for stop in ("stop_speech_gesture", "prepare_speech_gesture", "Ready", "Answering", "Retrying"):
            clock[0] = 100.0
            patient.gestures = SpeechGesture(ChooseGesture("hand", 1))
            patient.head_gesture = SpeechGesture(ChooseGesture("head", -1), kinds=("head",))
            patient.speak("A longer answer with a head tilt and hand movement.")
            patient.frame = 10
            patient.blink.closed = True  # Blink shapes must also follow the head.
            patient.draw()
            baseline = geometry()
            patient.prepare_speech_gesture(0)
            for step in range(15):
                clock[0] = 100 + step / 10
                patient.update_speech_gesture(True, step + 1)
            assert patient.head_gesture.pose(clock[0])[2] > 0
            assert patient.gestures.pose(clock[0])[2] > 0
            patient.draw()
            assert geometry() != baseline
            if stop == "prepare_speech_gesture":
                patient.prepare_speech_gesture(15)
            elif stop == "stop_speech_gesture":
                patient.stop_speech_gesture()
            else:
                patient.set_status(stop)
            assert patient.head_gesture.pose(clock[0]) == (None, 0, 0.0)
            assert patient.gestures.pose(clock[0]) == (None, 0, 0.0)
            if stop in {"stop_speech_gesture", "prepare_speech_gesture"}:
                assert geometry() == baseline
            patient.stop_animation()
            assert not root.tk.call("after", "info")
        patient.blink.closed = False
        # The smoother gesture redraw must not speed up lip movement.
        clock[0] = 100.0
        patient.speak("Check the unchanged face timing alongside smoother gestures.")
        for tick in range(1, 9):
            clock[0] = 100 + tick * 0.06
            patient.after_cancel(patient.animation_job)
            patient.animate()
            assert patient.frame == 1 + tick // 2
            assert len(root.tk.call("after", "info")) == 1
        patient.stop_animation()
        # Cancellation/status transitions must also clear an in-flight gesture.
        for status in ("Ready", "Answering", "Retrying", "speak", "hold_speaking"):
            clock[0] = 100.0
            patient.idle_leg = IdleLegGesture(ChooseGesture("leg", 1))
            for now in (100, 115, 115.8):
                clock[0] = now
                patient.update_idle_gesture(True)
            assert patient.idle_leg.pose(clock[0])[2] > 0
            if status == "speak":
                patient.speak("Speaking must stop a quiet leg shift.")
            elif status == "hold_speaking":
                patient.hold_speaking()
            else:
                patient.set_status(status)
            assert patient.idle_leg.pose(clock[0]) == (None, 0, 0.0)
            patient.update_idle_gesture(True)
            assert patient.idle_leg.pose(clock[0] + 15.8) == (None, 0, 0.0)
            patient.stop_animation()
            assert patient.animation_job is None and not root.tk.call("after", "info")

        def without_eyes():
            return [
                (patient.canvas.type(item), tuple(patient.canvas.coords(item)))
                for item in patient.canvas.find_all()
                if "eyes" not in patient.canvas.gettags(item)
            ]

        # Blinking is independent of speaking, never starts lip motion or adds a timer,
        # and creates no redraws during the waiting interval or the closed-eye hold.
        for status in ("Ready", "Listening", "Answering", "Retrying"):
            clock[0] = 200.0
            patient.blink = EyeBlink(ChooseGesture("unused", 1))
            patient.set_status(status)
            baseline = geometry()
            body = without_eyes()
            identifiers = patient.canvas.find_all()
            for step in range(167):
                clock[0] = 200 + step * 0.03
                patient.update_blink(True)
                assert patient.canvas.find_all() == identifiers
            clock[0] = 205.0
            patient.update_blink(True)
            assert patient.blink.closed and len(patient.canvas.find_withtag("eyes")) == 2
            assert without_eyes() == body, "Idle blinking must leave lips, body and labels unchanged"
            identifiers = patient.canvas.find_all()
            clock[0] = 205.1
            patient.update_blink(True)
            assert patient.canvas.find_all() == identifiers
            clock[0] = 205.17
            patient.update_blink(True)
            assert not patient.blink.closed and geometry() == baseline
            assert patient.frame == 0 and patient.animation_job is None
            assert not root.tk.call("after", "info")
        # The speech timer still advances lips while the independent blink finishes.
        patient.hold_speaking(20)
        clock[0] = 210.17
        patient.update_blink(True)
        assert patient.blink.closed
        frame = patient.frame
        patient.after_cancel(patient.animation_job)
        patient.animate()
        patient.after_cancel(patient.animation_job)
        patient.animate()
        assert patient.frame > frame and patient.blink.closed
        clock[0] = 210.34
        patient.update_blink(True)
        assert not patient.blink.closed and patient.animation_job is not None
        patient.stop_animation()
        print(
            "Gestures and independent blinking verified; no idle lip movement, no waiting redraws or extra timers"
        )
    finally:
        patient.stop_animation(redraw=False)
        root.destroy()


if __name__ == "__main__":
    main()
