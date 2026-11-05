"""Occasional speech and quiet seated gestures; no timers, threads or audio processing."""

import math
import random

GESTURE_CHANCE = 0.25
HEAD_GESTURE_CHANCE = 0.40
GESTURE_SECONDS = 1.6
IDLE_LEG_DELAY_SECONDS = (15.0, 30.0)
BLINK_PAUSE_SECONDS = (5.0, 9.0)
BLINK_CLOSED_SECONDS = 0.16
# Audio is written in roughly 93 ms slices. Stop movement across synthesis stalls.
AUDIO_FRESH_SECONDS = 0.3


class SpeechGesture:
    def __init__(self, rng=None, *, chance=GESTURE_CHANCE, kinds=("hand", "finger")):
        self.rng = rng if rng is not None else random.Random()
        self.chance, self.kinds = chance, kinds
        self.skip_next = False
        self.armed = self.decided = self.started = False
        self.progress = 0
        self.last_audio = None
        self.kind = None
        self.side = 1
        self.start = 0.0

    def stop(self):
        """Return whether a visible gesture needs resetting; keep the reply cooldown."""
        changed = self.started
        self.armed = self.decided = self.started = False
        self.kind = self.last_audio = None
        return changed

    def prepare(self, progress):
        changed = self.stop()
        self.armed = True
        self.progress = progress
        return changed

    def update(self, speaking, progress, now):
        """Called by the existing UI poll; a queued/synthesizing answer cannot start motion."""
        if not self.armed:
            return False
        if not speaking:
            return self.stop()
        if progress != self.progress:
            self.progress, self.last_audio = progress, now
            if not self.decided:
                self.decided = True
                skip, self.skip_next = self.skip_next, False
                if not skip and self.rng.random() < self.chance:
                    self.kind = self.rng.choice(self.kinds)
                    self.side = self.rng.choice((1, -1))
                    self.start = now + self.rng.uniform(0.6, 1.3)
        if self.kind is None:
            return False
        if (
            self.last_audio is None
            or now - self.last_audio > AUDIO_FRESH_SECONDS
            or now >= self.start + GESTURE_SECONDS
        ):
            changed = self.started
            self.kind, self.started = None, False
            return changed
        if now > self.start:
            self.started = self.skip_next = True
        return False

    def pose(self, now):
        """Smoothly leave and return to rest within the existing animation frames."""
        if self.started and self.kind and self.last_audio is not None:
            phase = (now - self.start) / GESTURE_SECONDS
            if 0 < phase < 1 and now - self.last_audio <= AUDIO_FRESH_SECONDS:
                return self.kind, self.side, math.sin(math.pi * phase) ** 2
        return None, 0, 0.0


class IdleLegGesture:
    """An occasional seated leg shift while quiet, driven by the existing UI poll."""

    def __init__(self, rng=None):
        self.rng = rng if rng is not None else random.Random()
        self.next_start = None
        self.start = None
        self.side = 1

    def stop(self):
        changed = self.start is not None
        self.start = self.next_start = None
        return changed

    def update(self, allowed, now):
        """Return whether a transition needs drawing; never catch up missed movements."""
        if not allowed:
            return self.stop()
        if self.start is not None:
            if now >= self.start + GESTURE_SECONDS:
                self.start = None
                self.next_start = now + self.rng.uniform(*IDLE_LEG_DELAY_SECONDS)
                return True
            return False
        if self.next_start is None:
            self.next_start = now + self.rng.uniform(*IDLE_LEG_DELAY_SECONDS)
        elif now >= self.next_start:
            self.side = self.rng.choice((1, -1))
            self.start = now
            self.next_start = None
            return True
        return False

    def pose(self, now):
        if self.start is not None:
            phase = (now - self.start) / GESTURE_SECONDS
            if 0 <= phase < 1:
                return "leg", self.side, math.sin(math.pi * phase) ** 2
        return None, 0, 0.0


class EyeBlink:
    """Wall-clock blinking independent of speech; redraw only on open/closed changes."""

    def __init__(self, rng=None):
        self.rng = rng if rng is not None else random.Random()
        self.closed = False
        self.next_change = None

    def update(self, visible, now):
        if not visible:
            changed = self.closed
            self.closed = False
            self.next_change = None
            return changed
        if self.next_change is None:
            self.next_change = now + self.rng.uniform(*BLINK_PAUSE_SECONDS)
        elif now >= self.next_change:
            self.closed = not self.closed
            self.next_change = now + (
                BLINK_CLOSED_SECONDS if self.closed else self.rng.uniform(*BLINK_PAUSE_SECONDS)
            )
            return True
        return False
