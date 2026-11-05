"""Deterministic speech-only, occasional movement without devices or GUI timers."""

import subprocess
import sys
from pathlib import Path

import pytest

from human_test.gestures import (
    AUDIO_FRESH_SECONDS,
    HEAD_GESTURE_CHANCE,
    EyeBlink,
    IdleLegGesture,
    SpeechGesture,
)


def test_native_gesture_geometry_and_timer_lifecycle():
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("gesture_canvas_smoke.py"))],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


class Choice:
    def __init__(self, chance=0.1, kind="hand", side=1):
        self.chance, self.kind, self.side = chance, kind, side
        self.calls = 0

    def random(self):
        self.calls += 1
        return self.chance

    def choice(self, values):
        chosen = self.kind if isinstance(values[0], str) else self.side
        assert chosen in values
        return chosen

    def uniform(self, low, high):
        return low


def play_until(gesture, end, offset=0):
    poses = []
    for step in range(round(end * 10) + 1):
        now = step / 10
        gesture.update(True, offset + step + 1, now)
        poses.append(gesture.pose(now))
    return poses


@pytest.mark.parametrize("kind", ["hand", "head"])
def test_silent_text_preview_and_synthesis_waits_never_move_or_roll(kind):
    rng = Choice(kind=kind)
    gesture = SpeechGesture(rng, kinds=(kind,))
    gesture.update(True, 10, 0)  # No patient reply was armed (e.g. voice preview).
    assert gesture.pose(0) == (None, 0, 0.0) and rng.calls == 0
    gesture.prepare(10)
    for now in range(30):
        gesture.update(True, 10, now)  # Queued speech is not audio playback.
        assert gesture.pose(now) == (None, 0, 0.0)
    assert rng.calls == 0
    gesture.update(True, 11, 30)
    assert rng.calls == 1 and gesture.pose(30) == (None, 0, 0.0)
    gesture.update(False, 11, 30.2)  # Very short answer ends before the gesture.
    assert not gesture.armed and gesture.pose(31) == (None, 0, 0.0)


@pytest.mark.parametrize("chance,selected", [(0.249, True), (0.25, False), (0.99, False)])
def test_one_chance_per_reply_not_per_frame_or_sentence(chance, selected):
    rng = Choice(chance)
    gesture = SpeechGesture(rng)
    gesture.prepare(0)
    poses = play_until(gesture, 25)
    assert any(amount > 0 for _, _, amount in poses) is selected
    assert rng.calls == 1
    assert all(pose == (None, 0, 0.0) for pose in poses[23:])


@pytest.mark.parametrize("kind", ["hand", "finger", "head"])
@pytest.mark.parametrize("side", [1, -1])
def test_single_smooth_gesture_returns_to_rest_and_skips_next_reply(kind, side):
    rng = Choice(kind=kind, side=side)
    gesture = SpeechGesture(rng, kinds=(kind,))
    gesture.prepare(0)
    poses = play_until(gesture, 3)
    moving = [pose for pose in poses if pose[2] > 0]
    assert moving and all(pose[:2] == (kind, side) for pose in moving)
    amounts = [pose[2] for pose in moving]
    peak = amounts.index(max(amounts))
    assert amounts[: peak + 1] == sorted(amounts[: peak + 1])
    assert amounts[peak:] == sorted(amounts[peak:], reverse=True)
    assert max(amounts) == pytest.approx(1.0)
    assert poses[-1] == (None, 0, 0.0)
    assert rng.calls == 1
    gesture.prepare(100)
    assert all(pose == (None, 0, 0.0) for pose in play_until(gesture, 4, offset=100))
    assert rng.calls == 1, "The immediately following spoken reply is always still"
    gesture.prepare(200)
    assert any(pose[2] > 0 for pose in play_until(gesture, 2, offset=200))
    assert rng.calls == 2


@pytest.mark.parametrize("kind", ["hand", "finger", "head"])
def test_stop_or_audio_gap_clears_motion_without_restart_in_same_reply(kind):
    for explicit_stop in (True, False):
        rng = Choice(kind=kind)
        gesture = SpeechGesture(rng, kinds=(kind,))
        gesture.prepare(0)
        play_until(gesture, 1.4)
        assert gesture.pose(1.4)[2] == pytest.approx(1.0)
        if explicit_stop:
            assert gesture.stop()
        else:
            assert gesture.update(True, 15, 1.4 + AUDIO_FRESH_SECONDS + 0.01)
        assert gesture.pose(1.8) == (None, 0, 0.0)
        for step in range(20, 60):
            gesture.update(True, step, step / 10)
            assert gesture.pose(step / 10) == (None, 0, 0.0)
        assert rng.calls == 1


def test_a_stale_pose_is_still_even_before_the_next_ui_poll():
    gesture = SpeechGesture(Choice())
    gesture.prepare(0)
    play_until(gesture, 1)
    assert gesture.pose(1)[2] > 0
    assert gesture.pose(1 + AUDIO_FRESH_SECONDS + 0.01) == (None, 0, 0.0)


def test_synthesis_gap_before_scheduled_motion_drops_the_gesture():
    rng = Choice()
    gesture = SpeechGesture(rng)
    gesture.prepare(0)
    gesture.update(True, 1, 0)
    gesture.update(True, 1, 0.4)
    assert gesture.pose(0.8) == (None, 0, 0.0)
    assert all(pose == (None, 0, 0.0) for pose in play_until(gesture, 3, offset=1))
    assert rng.calls == 1 and not gesture.skip_next


@pytest.mark.parametrize("chance,selected", [(0.25, True), (0.399, True), (0.40, False), (0.99, False)])
def test_head_is_more_frequent_but_still_only_once_per_eligible_spoken_reply(chance, selected):
    rng = Choice(chance=chance, kind="head")
    gesture = SpeechGesture(rng, chance=HEAD_GESTURE_CHANCE, kinds=("head",))
    gesture.prepare(0)
    poses = play_until(gesture, 25)
    assert any(amount > 0 for _, _, amount in poses) is selected
    assert rng.calls == 1
    assert all(pose == (None, 0, 0.0) for pose in poses[23:])


class IdleChoice(Choice):
    def __init__(self, delays=(15, 30, 22), side=1):
        super().__init__(side=side)
        self.delays = iter(delays)
        self.delay_calls = 0

    def uniform(self, low, high):
        assert (low, high) == (15, 30)
        self.delay_calls += 1
        return next(self.delays)


@pytest.mark.parametrize("delay", [15, 22.5, 30])
def test_idle_leg_waits_for_a_random_quiet_interval_without_redrawing(delay):
    rng = IdleChoice(delays=(delay,))
    gesture = IdleLegGesture(rng)
    for now in (0, 1, 5, 14.9, delay - 0.01):
        assert not gesture.update(True, now)
        assert gesture.pose(now) == (None, 0, 0.0)
    assert rng.delay_calls == 1
    assert gesture.update(True, delay)
    assert gesture.pose(delay + 0.8)[0] == "leg"


@pytest.mark.parametrize("side", [1, -1])
def test_idle_leg_smooth_return_and_fresh_random_pause_after_each_movement(side):
    rng = IdleChoice(side=side)
    gesture = IdleLegGesture(rng)
    gesture.update(True, 0)
    gesture.update(True, 15)
    amounts = [gesture.pose(15 + step / 10)[2] for step in range(17)]
    assert gesture.pose(15.8)[:2] == ("leg", side)
    assert amounts[0] == 0 and amounts[-1] == pytest.approx(0)
    assert amounts[:9] == sorted(amounts[:9])
    assert amounts[8:] == sorted(amounts[8:], reverse=True)
    assert max(amounts) == pytest.approx(1)
    assert gesture.update(True, 16.6)
    assert rng.delay_calls == 2
    assert not gesture.update(True, 46.5)
    assert gesture.pose(46.5) == (None, 0, 0.0)
    assert gesture.update(True, 46.6)
    assert gesture.update(True, 48.2)
    assert rng.delay_calls == 3
    assert gesture.next_start == pytest.approx(70.2)


def test_idle_leg_interruption_requires_a_fresh_quiet_interval_and_never_catches_up():
    rng = IdleChoice()
    gesture = IdleLegGesture(rng)
    gesture.update(True, 0)
    gesture.update(True, 15)
    assert gesture.pose(15.8)[2] > 0
    assert gesture.update(False, 15.8)
    assert gesture.pose(15.8) == (None, 0, 0.0)
    for now in range(16, 40):
        gesture.update(False, now)
    assert rng.delay_calls == 1
    gesture.update(True, 40)
    assert not gesture.update(True, 69.9)
    assert gesture.pose(69.9) == (None, 0, 0.0)
    assert gesture.update(True, 200)
    assert gesture.start == 200
    assert rng.delay_calls == 2, "A delayed poll must never replay missed movements"


class BlinkChoice:
    def __init__(self, *delays):
        self.delays = iter(delays)
        self.calls = 0

    def uniform(self, low, high):
        assert (low, high) == (5, 9)
        self.calls += 1
        return next(self.delays)


@pytest.mark.parametrize("delay", [5, 7, 9])
def test_blink_waits_without_redraw_then_closes_briefly_and_resamples(delay):
    rng = BlinkChoice(delay, 9)
    blink = EyeBlink(rng)
    for now in (0, 1, 4.9, delay - 0.01):
        assert not blink.update(True, now) and not blink.closed
    assert rng.calls == 1
    assert blink.update(True, delay) and blink.closed
    assert not blink.update(True, delay + 0.1) and blink.closed
    assert blink.update(True, delay + 0.161) and not blink.closed
    assert rng.calls == 2
    assert blink.next_change == pytest.approx(delay + 0.161 + 9)


def test_hidden_blink_resets_and_starts_a_fresh_wait_on_return():
    rng = BlinkChoice(5, 9)
    blink = EyeBlink(rng)
    assert not blink.update(False, 0)
    blink.update(True, 10)
    assert blink.update(True, 15) and blink.closed
    assert blink.update(False, 15.1) and not blink.closed
    assert blink.next_change is None
    assert not blink.update(False, 500)
    assert rng.calls == 1
    assert not blink.update(True, 501)
    assert blink.next_change == 510


def test_delayed_blink_poll_never_replays_missed_cycles():
    rng = BlinkChoice(5, 7)
    blink = EyeBlink(rng)
    blink.update(True, 0)
    assert blink.update(True, 100) and blink.closed
    assert not blink.update(True, 100.01)
    assert blink.update(True, 200) and not blink.closed
    assert blink.next_change == 207 and rng.calls == 2
