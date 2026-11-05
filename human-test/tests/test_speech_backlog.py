"""Rapid setup changes must not leave obsolete model loads ahead of a new reply."""

import threading
import time

from test_speech import installed_voice
from training_client.speech import Speaker


def wait_until(predicate):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class SlowLoad:
    def __init__(self):
        self.entered, self.release = threading.Event(), threading.Event()
        self.loaded, self.played = [], []

    def load(self, language, gender="male", preferred=None):
        self.loaded.append(language)
        self.entered.set()
        assert self.release.wait(5)

    def play(self, text, language, still_current, **kwargs):
        if still_current():
            self.played.append(text)

    def interrupt(self):
        pass

    def close(self):
        pass


def test_repeated_setup_warmups_cannot_drop_or_delay_latest_answer(tmp_path, monkeypatch):
    installed_voice(tmp_path, monkeypatch, ("en", "hi"))
    engine = SlowLoad()
    speaker = Speaker(engine=engine)
    try:
        speaker.warm("en")
        assert engine.entered.wait(2)
        for _ in range(12):
            speaker.stop()
            speaker.warm("hi")
        assert speaker._requests.qsize() == 1
        assert speaker.speak("Latest patient answer", "hi")
        speaker.warm("en")  # optional warmup cannot displace an accepted answer
        assert speaker.speaking
        engine.release.set()
        assert wait_until(lambda: engine.played == ["Latest patient answer"])
        assert wait_until(lambda: not speaker.speaking)
        assert engine.loaded == ["en"]
    finally:
        engine.release.set()
        speaker.close()


def test_back_or_pause_discards_obsolete_queued_warmups(tmp_path, monkeypatch):
    installed_voice(tmp_path, monkeypatch, ("en", "hi"))
    engine = SlowLoad()
    speaker = Speaker(engine=engine)
    try:
        speaker.warm("en")
        assert engine.entered.wait(2)
        speaker.warm("hi")
        speaker.stop()
        assert speaker._requests.empty()
        engine.release.set()
    finally:
        engine.release.set()
        worker = speaker._worker
        speaker.close()
        assert worker is not None and not worker.is_alive()
