"""A seated vector patient in an OPD room, with capture and inference status."""

import time
import tkinter as tk
from math import cos, pi, sin
from tkinter import ttk

from .gestures import HEAD_GESTURE_CHANCE, EyeBlink, IdleLegGesture, SpeechGesture

ANIMATION_INTERVAL_MS = 60
# Canvas space kept clear of the room: a caption above, and name, status and observations
# below. Smaller reserves than the first layout, so the figure grows with the stage.
TOP_OFFSET = 28
FOOTER_RESERVE = 84
HAND_ROTATION_RADIANS = 0.45
FINGER_CURL = (0.4, 0.55, 0.75, 1.0)
LEG_SWING_RADIANS = 0.18
HEAD_TILT_RADIANS = 0.06

# Badge phases, keyed by the status a caller reports. Everything a caller can report is
# either one of these or prose for the status line; the badge must never turn prose into
# "Ready", because an idle-looking patient while the machine is working reads as a fault.
PHASES = {
    "Ready": "Ready",
    "Listening": "Listening",
    "Transcribing": "Transcribing",
    "Answering": "Preparing reply",
    "Preparing audio": "Preparing reply",
    "Preparing voice and model…": "Preparing models",
    "Speaking": "Responding",
    "Audio stopped": "Ready",
    "Retrying": "Waiting for model",
    "Complete": "Ready",
}
# Progress phases are also reported with detail appended, e.g. the engine or queue depth.
PREFIXES = (("Transcribing", "Transcribing"), ("Queued", "Question queued"))


def phase_for(state):
    """The badge phase a reported status means, or None when it is prose to be shown as-is."""
    if state in PHASES:
        return PHASES[state]
    for prefix, phase in PREFIXES:
        if state.startswith(prefix):
            return phase
    return None


class Manikin(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, style="Card.TFrame")
        self.mode = "Ready"
        self.resting_mode = "Ready"
        self.speaking_until = 0.0
        self.animation_job = None
        self.frame = 0
        self.animation_tick = 0
        self.spoken_text = ""
        self.gestures = SpeechGesture()
        self.head_gesture = SpeechGesture(chance=HEAD_GESTURE_CHANCE, kinds=("head",))
        self.idle_leg = IdleLegGesture()
        self.blink = EyeBlink()
        self.idle_last_draw = 0.0
        self.patient_name = "Patient"
        self.observations = "Initial observations from saved setup"
        self.canvas = tk.Canvas(self, width=340, height=460, background="#f6fafb", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda event: self.draw())

    def configure_patient(self, selection):
        doc = selection["document"]
        self.patient_name = doc["patient"]["name"]
        vital = doc["vitals"]
        self.observations = f"{vital['temperature_c']:g} °C   ·   HR {vital['heart_rate_bpm']:g}   ·   SpO₂ {vital['spo2_percent']:g}%"
        self.set_status("Ready")

    def set_status(self, state):
        phase = phase_for(state)
        if phase is None:
            # Prose: the status line reports it. Leaving the badge alone is deliberate -
            # resetting it here is what made "Transcribing" and a failed turn both show Ready.
            return
        # Only the end of a turn defers to playback. An explicit Ready is a reset and must
        # stop the animation, which is why this is keyed on the reported state, not the phase.
        if state == "Complete" and self.speaking_until > time.monotonic():
            return
        if phase == "Listening" and self.speaking_until > time.monotonic():
            # Continuous capture resumes independently; expression must not delay input.
            self.resting_mode = "Listening"
            return
        self.stop_animation(redraw=False)
        self.mode = phase
        self.draw()

    def speak(self, text):
        if self.idle_leg.stop():
            self.draw()
        if not text.strip():
            self.stop_animation()
            return
        if text == self.spoken_text and self.speaking_until > time.monotonic():
            return
        self.spoken_text = text
        # Estimated from the text; real speech extends this through hold_speaking().
        self.speaking_until = time.monotonic() + min(12, max(2, len(text.split()) * 0.3))
        self.mode = "Responding"
        if self.animation_job is None:
            self.animate()

    def hold_speaking(self, seconds=0.25):
        """Keep the mouth moving while speech audio is still playing."""
        if self.idle_leg.stop():
            self.draw()
        self.speaking_until = max(self.speaking_until, time.monotonic() + seconds)
        self.mode = "Responding"
        if self.animation_job is None:
            self.animate()

    def animate(self):
        self.animation_job = None
        if time.monotonic() >= self.speaking_until:
            resting_mode = self.resting_mode
            self.stop_animation()
            self.mode = resting_mode
            self.draw()
            return
        self.animation_tick += 1
        # Gestures draw twice as often; retain the existing 120 ms lip cadence.
        if self.animation_tick % 2:
            self.frame += 1
        self.draw()
        self.animation_job = self.after(ANIMATION_INTERVAL_MS, self.animate)

    def stop_animation(self, redraw=True):
        if self.animation_job is not None:
            self.after_cancel(self.animation_job)
            self.animation_job = None
        self.speaking_until, self.frame, self.spoken_text = 0.0, 0, ""
        self.animation_tick = 0
        self.gestures.stop()
        self.head_gesture.stop()
        self.idle_leg.stop()
        self.mode = "Ready"
        self.resting_mode = "Ready"
        if redraw:
            self.draw()

    def prepare_speech_gesture(self, progress):
        changed = False
        for gesture in (self.gestures, self.head_gesture):
            changed = gesture.prepare(progress) or changed
        if changed:
            self.draw()

    def update_speech_gesture(self, speaking, progress):
        now = time.monotonic()
        changed = False
        for gesture in (self.gestures, self.head_gesture):
            changed = gesture.update(speaking, progress, now) or changed
        if changed:
            self.draw()

    def stop_speech_gesture(self):
        changed = False
        for gesture in (self.gestures, self.head_gesture):
            changed = gesture.stop() or changed
        if changed:
            self.draw()

    def update_idle_gesture(self, allowed):
        now = time.monotonic()
        allowed = allowed and self.mode in {"Ready", "Listening"} and now >= self.speaking_until
        changed = self.idle_leg.update(allowed, now)
        if changed or (
            self.idle_leg.start is not None and now - self.idle_last_draw >= ANIMATION_INTERVAL_MS / 1000
        ):
            self.idle_last_draw = now
            self.draw()

    def update_blink(self, visible):
        # The existing UI poll drives this even while silent or processing a reply.
        # Suspend the countdown when the patient/window is not on screen.
        if self.blink.update(visible and bool(self.winfo_viewable()), time.monotonic()):
            self.draw()

    def draw(self):
        c = self.canvas
        c.delete("all")
        width, height = max(c.winfo_width(), 200), max(c.winfo_height(), 240)
        # One coordinate system keeps the room, chair and patient aligned on resize.
        # The room spans x=-110..390, with the patient centred at x=140.
        scale = min((width - 24) / 500, (height - FOOTER_RESERVE - TOP_OFFSET) / 342)
        x0 = width / 2 - 140 * scale
        y0 = TOP_OFFSET + (height - FOOTER_RESERVE - TOP_OFFSET - 342 * scale) / 2
        # Captions grow with the figure, clamped so small windows keep the original sizes.
        name_size = min(20, max(14, round(11 * scale)))
        badge_size = min(13, max(10, round(7.5 * scale)))
        detail_size = min(11, max(9, round(6.5 * scale)))
        _, head_side, head_amount = self.head_gesture.pose(time.monotonic())
        head_angle = HEAD_TILT_RADIANS * head_side * head_amount
        head_cosine, head_sine = cos(head_angle), sin(head_angle)
        drawing_head = False
        ink = "#183248"
        accent = (
            "#007f82"
            if self.mode in {"Listening", "Responding"}
            # Work in progress reads as amber; only a genuinely idle patient is grey.
            else "#936414"
            if self.mode in {"Preparing reply", "Transcribing", "Question queued", "Waiting for model"}
            else "#78919d"
        )

        def points(values):
            if drawing_head and head_angle:
                # Rotate every facial feature together around the base of the head.
                values = [
                    value
                    for x, y in zip(values[::2], values[1::2], strict=True)
                    for dx, dy in ((x - 140, y - 84),)
                    for value in (
                        140 + dx * head_cosine - dy * head_sine,
                        84 + dx * head_sine + dy * head_cosine,
                    )
                ]
            return [v * scale + (x0 if i % 2 == 0 else y0) for i, v in enumerate(values)]

        def oval(coords, **options):
            if drawing_head:
                # Tk ovals cannot rotate. A smooth ellipse outline keeps eyes, mouth
                # and ears aligned with the face through the entire head movement.
                left, top, right, bottom = coords
                values = [
                    value
                    for step in range(16)
                    for angle in (2 * pi * step / 16,)
                    for value in (
                        (left + right) / 2 + (right - left) / 2 * cos(angle),
                        (top + bottom) / 2 + (bottom - top) / 2 * sin(angle),
                    )
                ]
                return poly(values, **options)
            return c.create_oval(*points(coords), **options)

        def rect(coords, **options):
            return c.create_rectangle(*points(coords), **options)

        def line(coords, **options):
            if drawing_head:
                options["tags"] = ("head", *options.get("tags", ()))
            return c.create_line(*points(coords), **options)

        def poly(coords, smooth=True, **options):
            if drawing_head:
                options["tags"] = ("head", *options.get("tags", ()))
            return c.create_polygon(*points(coords), smooth=smooth, splinesteps=24, **options)

        c.create_text(width / 2, 14, text="VIRTUAL PATIENT", fill="#627788", font=("Segoe UI", 9, "bold"))
        # Calm consultation-room wall with a washable lower panel and skirting.
        rect((-110, 0, 390, 342), fill="#f5f7f4", outline="")
        rect((-110, 176, 390, 264), fill="#e5eeeb", outline="")
        line((-110, 176, 390, 176), fill="#d5e1dd", width=1)
        rect((-110, 264, 390, 272), fill="#cad7d3", outline="")
        # The floor recedes behind the chair; its quiet seams meet the wall.
        rect((-110, 272, 390, 342), fill="#e1e7e8", outline="")
        line((-110, 272, 390, 272), fill="#b9c9c7", width=1)
        line((50, 272, -30, 342), fill="#d2dcdd", width=1)
        line((230, 272, 310, 342), fill="#d2dcdd", width=1)
        rect((-110, 0, 390, 342), fill="", outline="#d6e0de", width=1)
        # Small, subdued details stay outside the patient's central space.
        rect((-56, 74, -8, 132), fill="#e2e9e5", outline="")
        rect((-58, 72, -10, 130), fill="#fafcf9", outline="#afbfbc", width=1)
        rect((-53, 77, -15, 125), fill="#f0f5f3", outline="")
        rect((-38, 84, -30, 106), fill="#8ba7a1", outline="")
        rect((-45, 91, -23, 99), fill="#8ba7a1", outline="")
        c.create_text(
            *points((-34, 117)),
            text="OPD",
            fill="#7b928d",
            font=("Segoe UI", max(6, round(8 * scale)), "bold"),
        )
        # Compact split AC high on the wall; the patient keeps the same scale.
        poly(
            (252, 25, 342, 25, 346, 29, 346, 49, 342, 53, 252, 53, 248, 49, 248, 29),
            fill="#e2e9e5",
            outline="",
        )
        poly(
            (250, 22, 340, 22, 344, 26, 344, 46, 340, 50, 250, 50, 246, 46, 246, 26),
            fill="#fafcf9",
            outline="#b3c2bf",
            width=1,
        )
        line((251, 37, 339, 37), fill="#e0e7e3", width=1)
        line((255, 42, 335, 42), fill="#aebfba", width=1)
        line((258, 46, 332, 46), fill="#c4d1cd", width=1)
        rect((327, 29, 331, 31), fill="#9eb9ad", outline="")
        # Chair and feet share a contact shadow on the foreground floor.
        oval((58, 311, 222, 330), fill="#c7d4d6", outline="")
        # Chair behind the patient: backrest, four legs, then the seat cushion.
        chair_edge, chair_frame = "#506e7a", "#77929d"
        for coords in (
            (87, 175, 94, 175, 79, 317, 72, 317),
            (186, 175, 193, 175, 208, 317, 201, 317),
            (76, 214, 84, 214, 86, 322, 78, 322),
            (196, 214, 204, 214, 202, 322, 194, 322),
        ):
            poly(coords, smooth=False, fill=chair_frame, outline=chair_edge)
        poly(
            (82, 89, 82, 78, 94, 72, 186, 72, 198, 78, 198, 89, 194, 181, 86, 181),
            fill="#aac8ca",
            outline=chair_edge,
            width=1.5,
        )
        line((93, 89, 91, 163), fill="#c9dedf", width=2)
        line((187, 89, 189, 163), fill="#c9dedf", width=2)
        poly(
            (91, 177, 189, 177, 207, 212, 73, 212),
            smooth=False,
            fill="#9cbdc0",
            outline=chair_edge,
        )
        poly(
            (73, 210, 207, 210, 207, 220, 73, 220),
            smooth=False,
            fill="#6e989e",
            outline=chair_edge,
        )
        skin, skin_edge, skin_shade = "#deb093", "#b38369", "#ca977b"
        shirt, shirt_edge = "#b2dff3", "#7caac0"
        trousers, trouser_edge = "#d4d8dc", "#9ca6ae"
        gesture, gesture_side, amount = self.gestures.pose(time.monotonic())
        if (
            gesture is None
            and self.speaking_until <= time.monotonic()
            and self.mode in {"Ready", "Listening"}
        ):
            gesture, gesture_side, amount = self.idle_leg.pose(time.monotonic())
        leg_angle = gesture_side * LEG_SWING_RADIANS * amount if gesture == "leg" else 0.0
        leg_cosine, leg_sine = (cos(leg_angle), sin(leg_angle)) if leg_angle else (1.0, 0.0)

        def leg_points(coords):
            # Swing one lower leg outward at the knee, keeping the seated thighs fixed.
            # Apply the same transform to trousers, hems and shoes to keep them attached.
            if not leg_angle:
                return coords
            knee_x, knee_y = 140 - 28 * gesture_side, 230
            transformed = []
            for x, y in zip(coords[::2], coords[1::2], strict=True):
                if y > knee_y and (140 - x) * gesture_side > 0:
                    dx, dy = x - knee_x, y - knee_y
                    x = knee_x + dx * leg_cosine - dy * leg_sine
                    y = knee_y + dx * leg_sine + dy * leg_cosine
                transformed.extend((x, y))
            return transformed

        # Low shoes rest flat on the floor, underneath the trouser hems.
        for shoe, vamp, sole in (
            (
                (99, 297, 123, 297, 129, 308, 132, 321, 89, 323, 89, 316, 95, 307),
                (98, 310, 110, 307, 125, 312),
                (91, 321, 130, 321),
            ),
            (
                (157, 297, 181, 297, 185, 307, 191, 316, 191, 323, 148, 321, 151, 308),
                (155, 312, 170, 307, 182, 310),
                (150, 321, 189, 321),
            ),
        ):
            poly(leg_points(shoe), fill="#53616c", outline="#46525c")
            line(leg_points(vamp), fill="#77838b", width=1, smooth=True)
            line(leg_points(sole), fill="#b8c1c6", width=2)
        # Continuous trouser silhouette: fabric bends over the thighs and knees.
        poly(
            leg_points(
                (
                    110,
                    174,
                    170,
                    174,
                    182,
                    196,
                    186,
                    222,
                    184,
                    262,
                    181,
                    305,
                    151,
                    305,
                    150,
                    258,
                    151,
                    222,
                    140,
                    204,
                    129,
                    222,
                    130,
                    258,
                    129,
                    305,
                    98,
                    305,
                    95,
                    262,
                    94,
                    222,
                    98,
                    196,
                )
            ),
            fill=trousers,
            outline=trouser_edge,
            width=1,
        )
        for fold, crease, hem in (
            (
                (103, 193, 122, 184, 132, 196, 122, 220, 101, 230, 98, 221),
                (101, 226, 113, 223, 123, 227),
                (100, 299, 113, 301, 127, 299),
            ),
            (
                (158, 184, 177, 193, 182, 221, 179, 230, 158, 220, 148, 196),
                (157, 227, 167, 223, 179, 226),
                (153, 299, 167, 301, 180, 299),
            ),
        ):
            poly(fold, fill="#e0e3e6", outline="")
            line(crease, fill="#b4bdc5", width=1, smooth=True)
            line(leg_points(hem), fill=trouser_edge, width=1, smooth=True)
        line((140, 192, 140, 204, 131, 215), fill=trouser_edge, width=1, smooth=True)
        line(leg_points((104, 237, 106, 261, 106, 290)), fill="#c0c8ce", width=1, smooth=True)
        line(leg_points((176, 237, 174, 261, 174, 290)), fill="#c0c8ce", width=1, smooth=True)
        # Bare forearms have a continuous contour, with no segmented elbow joints.
        for arm in (
            (87, 117, 103, 122, 103, 143, 107, 160, 118, 181, 120, 192, 109, 198, 99, 182, 86, 164, 82, 144),
            (
                177,
                122,
                193,
                117,
                198,
                144,
                194,
                164,
                181,
                182,
                171,
                198,
                160,
                192,
                162,
                181,
                173,
                160,
                177,
                143,
            ),
        ):
            poly(arm, fill=skin, outline=skin_edge, width=1)
        # Short-sleeve sky-blue T-shirt, with a soft hem and restrained fabric folds.
        poly(
            (
                123,
                82,
                111,
                84,
                94,
                90,
                88,
                99,
                81,
                125,
                101,
                133,
                109,
                119,
                109,
                158,
                105,
                185,
                140,
                194,
                175,
                185,
                171,
                158,
                171,
                119,
                179,
                133,
                199,
                125,
                192,
                99,
                186,
                90,
                169,
                84,
                157,
                82,
            ),
            fill=shirt,
            outline=shirt_edge,
            width=1,
        )
        poly((110, 131, 118, 153, 117, 178, 135, 187, 109, 182), fill="#9acbe1", outline="")
        poly((169, 132, 170, 166, 173, 183, 152, 187, 162, 174), fill="#a1d0e5", outline="")
        line((84, 124, 99, 130), fill=shirt_edge, width=1)
        line((181, 130, 196, 124), fill=shirt_edge, width=1)
        line((116, 173, 129, 177, 144, 175), fill="#94c2d7", width=1, smooth=True)
        line((112, 184, 140, 190, 168, 184), fill=shirt_edge, width=1, smooth=True)

        # Hands lie palm-down on the thighs, angled gently toward the knees.
        # Mirror the anatomy so both thumbs face inward toward the patient's lap.
        angle = HAND_ROTATION_RADIANS * amount if gesture == "hand" else 0.0
        cosine, sine = (cos(angle), sin(angle)) if angle else (1.0, 0.0)

        def hand_points(coords, side, curl=0.0):
            if amount and side == gesture_side:
                if gesture == "hand":
                    # A small rotation about the wrist keeps it attached to the arm.
                    coords = [
                        value
                        for u, v in zip(coords[::2], coords[1::2], strict=True)
                        for value in (u * cosine - v * sine, u * sine + v * cosine)
                    ]
                elif gesture == "finger" and curl:
                    # A graduated curl across all fingertips reads clearly at normal window size.
                    # Keep the knuckles and palm fixed so the fingers stay attached.
                    coords = [
                        value
                        for u, v in zip(coords[::2], coords[1::2], strict=True)
                        for bend in (amount * curl * max(0, v - 18) / 17,)
                        for value in (u + 2.4 * bend, v - 10 * bend)
                    ]
            return [
                value
                for u, v in zip(coords[::2], coords[1::2], strict=True)
                for value in (140 - 27 * side + side * (u - 0.12 * v), 181 + v)
            ]

        for side in (1, -1):
            # Four separate, rounded fingertips of different lengths. Their roots
            # are covered by the palm, while small gaps make the silhouette readable.
            for index, finger in enumerate(
                (
                    (-11, 16, -7, 16, -7, 26, -7.5, 30, -10, 30, -11.5, 26),
                    (-5.5, 16, -1.5, 16, -1, 30, -2, 35, -4.5, 35, -6, 30),
                    (0, 16, 4, 16, 4.5, 33, 3.5, 38, 1, 38, -0.5, 33),
                    (5.5, 15, 9.5, 15, 10, 29, 9, 35, 6.5, 35, 5, 30),
                )
            ):
                poly(
                    hand_points(finger, side, curl=FINGER_CURL[index]),
                    fill=skin,
                    outline=skin_edge,
                    width=0.8,
                )
            poly(
                hand_points((7, 7, 12, 9, 18, 17, 18, 22, 15, 24, 12, 21, 10, 17, 7, 16), side),
                fill=skin,
                outline=skin_edge,
                width=0.8,
            )
            # A tapered wrist blends into the palm without a seam across the knuckles.
            poly(
                hand_points((-5, 0, 5, 0, 7, 5, 11, 12, 9, 19, 5, 21, -5, 21, -11, 18, -10, 10, -7, 5), side),
                fill=skin,
                outline="",
            )
            for contour in ((-5, 0, -9, 9, -11, 17, -10, 22), (5, 0, 7, 6, 10, 10)):
                line(hand_points(contour, side), fill=skin_edge, width=0.8, smooth=True)
            for index, crease in enumerate(
                (
                    (0, 8, -1, 16),
                    (8, 12, 11, 17),
                    (-9.5, 24, -8, 24),
                    (-4, 27, -2.5, 27),
                    (1.5, 29, 3, 29),
                    (7, 27, 8.5, 27),
                )
            ):
                line(
                    hand_points(crease, side, curl=FINGER_CURL[index - 2] if index >= 2 else 0.0),
                    fill=skin_shade,
                    width=0.7,
                    smooth=True,
                )
        # Neck and crew neckline sit naturally under the jaw.
        poly(
            (128, 68, 152, 68, 152, 81, 159, 85, 153, 95, 140, 99, 127, 95, 121, 85, 128, 81),
            fill=skin,
            outline=skin_edge,
        )
        poly((129, 69, 151, 69, 151, 80, 140, 85, 129, 80), fill=skin_shade, outline="")
        line((121, 85, 126, 98, 140, 102, 154, 98, 159, 85), fill=shirt_edge, width=2, smooth=True)
        # Ears, tapered jaw and subtle facial shading replace the round manikin head.
        drawing_head = True
        oval((109, 40, 120, 60), fill=skin, outline=skin_edge)
        oval((160, 40, 171, 60), fill=skin, outline=skin_edge)
        line((113, 45, 116, 49, 114, 55), fill=skin_shade, width=1, smooth=True)
        line((167, 45, 164, 49, 166, 55), fill=skin_shade, width=1, smooth=True)
        poly(
            (
                116,
                31,
                119,
                22,
                132,
                17,
                149,
                18,
                162,
                27,
                165,
                42,
                162,
                59,
                156,
                72,
                146,
                79,
                134,
                78,
                123,
                71,
                117,
                57,
            ),
            fill=skin,
            outline=skin_edge,
            width=1,
        )
        poly((158, 36, 163, 43, 160, 61, 151, 73, 140, 76, 152, 65), fill="#d5a487", outline="")
        # Short, side-parted hair follows the forehead and temples.
        poly(
            (
                114,
                46,
                112,
                29,
                117,
                18,
                127,
                12,
                147,
                11,
                160,
                17,
                166,
                28,
                166,
                46,
                161,
                39,
                158,
                29,
                148,
                28,
                140,
                24,
                129,
                32,
                120,
                32,
                118,
                44,
            ),
            fill="#463a33",
            outline="#3e342e",
            width=1,
        )
        line((120, 24, 130, 19, 143, 18), fill="#655246", width=1, smooth=True)
        line((148, 18, 157, 23, 161, 30), fill="#655246", width=1, smooth=True)
        line((122, 39, 128, 37, 133, 39), fill="#655044", width=1.5, smooth=True)
        line((147, 39, 152, 37, 158, 39), fill="#655044", width=1.5, smooth=True)
        speaking = self.speaking_until > time.monotonic()
        if self.blink.closed:
            line((122, 45, 127, 46, 133, 45), fill="#604b40", width=1, smooth=True, tags=("eyes",))
            line((147, 45, 153, 46, 158, 45), fill="#604b40", width=1, smooth=True, tags=("eyes",))
        else:
            for eye, iris, lid in (
                ((122, 43, 133, 48), (126, 43, 130, 48), (122, 44, 127, 42, 133, 44)),
                ((147, 43, 158, 48), (151, 43, 155, 48), (147, 44, 152, 42, 158, 44)),
            ):
                oval(eye, fill="#f5eee7", outline="", tags=("eyes",))
                oval(iris, fill="#4b4940", outline="", tags=("eyes",))
                line(lid, fill="#775c4b", width=1, smooth=True, tags=("eyes",))
        line((140, 45, 137, 55, 141, 57, 144, 55), fill=skin_edge, width=1, smooth=True)
        if speaking:
            opening = (1, 3, 5, 3, 2, 1)[self.frame % 6]
            oval((132, 65 - opening / 2, 148, 65 + opening / 2), fill="#795047", outline="#a87567")
        else:
            line((132, 64, 140, 65, 148, 64), fill="#986c5f", width=1, smooth=True)
        line((135, 69, 140, 70, 145, 69), fill="#cb947f", width=1, smooth=True)
        drawing_head = False
        c.create_text(
            width / 2, height - 60, text=self.patient_name, fill=ink, font=("Segoe UI", name_size, "bold")
        )
        c.create_text(
            width / 2, height - 37, text="●  " + self.mode, fill=accent, font=("Segoe UI", badge_size, "bold")
        )
        c.create_text(
            width / 2, height - 16, text=self.observations, fill="#627788", font=("Segoe UI", detail_size)
        )
