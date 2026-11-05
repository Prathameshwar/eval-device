"""Run in its own Tcl interpreter to avoid multiple Tk roots in the pytest process.

Checks the real window's speaker controls: the checkbox and voice picker exist, default
correctly, drive the real Speaker, and stay usable while a turn is running.
"""

import tkinter as tk
from uuid import uuid4

from training_client.speech import Speaker, catalogue

from human_test import app as app_module
from human_test.config import Settings


def settings():
    return Settings(
        _env_file=None,
        pms_token="fixture",
        audio_token="fixture",
        organization_id=uuid4(),
        connection_id=uuid4(),
    )


def main():
    app_module.microphones = lambda: []
    app_module.microphone = lambda *args: (_ for _ in ()).throw(
        AssertionError("Microphone started automatically")
    )
    root = tk.Tk()
    root.withdraw()
    window = app_module.Window(root, settings())
    try:
        assert isinstance(window.speaker, Speaker), "the window must own a real Speaker"

        assert window.speaker_box.cget("text") == "Speaker out"
        assert window.speaker_output.get() is True, "speaker output must default to checked"

        # Every installed voice is offered, plus the patient default.
        labels = list(window.voices)
        assert labels[0] == app_module.DEFAULT_VOICE_CHOICE
        installed = [entry["label"] for entry in catalogue()]
        assert labels[1:] == installed, (labels, installed)
        assert window.voice.get() == app_module.DEFAULT_VOICE_CHOICE
        assert list(window.voice_box.cget("values")) == labels

        # Choosing a voice records it for that voice's language only.
        if installed:
            entry = catalogue()[0]
            window.voice.set(entry["label"])
            window.apply_voice()
            assert window.settings.voice == entry["key"]
            assert window.speaker.preference(entry["language"]) == entry["key"]
            other = "hi" if entry["language"] == "en" else "en"
            assert window.speaker.preference(other) is None
            window.voice.set(app_module.DEFAULT_VOICE_CHOICE)
            window.apply_voice()
            assert window.settings.voice is None and not window.speaker.preference(entry["language"])

        # Speaker out and the voice picker behave differently while a turn runs: muting must
        # stay possible, but the voice must not change under an answer being spoken.
        window.lock_options(True)
        assert str(window.speaker_box.cget("state")) == "normal"
        assert str(window.voice_box.cget("state")) == "disabled"
        assert str(window.preview_button.cget("state")) == "disabled"
        window.lock_options(False)
        assert str(window.voice_box.cget("state")) == "readonly"

        # Previewing refuses while the microphone is open, so it cannot be recorded.
        window.running = False
        window.listening = True
        window.preview_voice()
        assert "Pause the microphone" in window.state.get()
        window.listening = False

        # Unchecking stops playback and keeps the setting in step.
        window.speaker_output.set(False)
        window.apply_speaker_output()
        assert window.speaker.enabled is False and window.settings.speaker_output is False
        window.preview_voice()
        assert "Speaker out" in window.state.get()
    finally:
        window.close()
        for _ in range(20):
            root.update()
    print("speaker controls verified")


if __name__ == "__main__":
    main()
