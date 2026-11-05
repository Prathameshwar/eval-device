"""Native Tk handoff of two assigned trainees, using an in-memory platform double."""

import asyncio
import time
import tkinter as tk
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from human_test.app import LANGUAGES, Window
from human_test.config import Settings


def main():
    vitals = dict(
        temperature_c=37,
        heart_rate_bpm=80,
        pulse_bpm=80,
        respirations_per_minute=16,
        systolic_mmhg=120,
        diastolic_mmhg=80,
        spo2_percent=98,
        pain_0_10=2,
    )
    cases = [
        {
            "id": str(uuid4()),
            "title": title,
            "version": 1,
            "specialty": "Respiratory medicine",
            "languages": ["en", "hi"],
            "vitals": vitals,
        }
        for title in ("First practice case", "Assigned respiratory case")
    ]
    assignments = [
        {
            "id": str(uuid4()),
            "learner_name": name,
            "scenario_title": cases[1]["title"],
            "scenario_id": cases[1]["id"],
            "language": "en",
            "duration_seconds": 300,
            "expires_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
            "status": "queued",
        }
        for name in ("Rahul Mehta", "Ananya Rao")
    ]

    class Platform:
        conversation = assigned_session_id = selection = active = None
        begins = 0

        def state(self):
            return {
                "active": deepcopy(self.active),
                "next": deepcopy(assignments[0]) if assignments and not self.active else None,
                "paused": False,
                "waiting": len(assignments),
            }

        async def json(self, method, path, **kwargs):
            if path.endswith("/poll"):
                return self.state()
            if path.endswith("/begin"):
                self.active = assignments.pop(0)
                self.active.update(status="active", started_at=datetime.now(UTC).isoformat())
                self.begins += 1
                return deepcopy(self.active)
            if path.endswith("/finish"):
                self.active = None
                self.conversation = None
                return {}
            raise AssertionError(path)

        async def scenario_options(self):
            return {"items": cases, "selection": self.selection}

        async def save_scenario_selection(self, body):
            self.selection = {
                "id": str(uuid4()),
                "scenario_id": body["scenario_id"],
                "language": body["language"],
                "revision": 1,
                "template_revision": 1,
                "document": {
                    "patient": {
                        "name": "Alex",
                        "sex": "male",
                        "age_years": 35,
                        "occupation": {"en": "Teacher", "hi": "Teacher"},
                    },
                    "vitals": vitals,
                    "presentation": {"en": "Fictional case"},
                },
            }
            return self.selection

        async def ensure_conversation(self):
            assert self.assigned_session_id == self.active["id"]
            self.conversation = {"context": {"conversation_id": str(uuid4())}}

    platform = Platform()

    class Controller:
        pms = platform

        def use_selection(self, saved):
            window.settings.language = saved["language"]

        def reset(self):
            self.pms.conversation = None

        def runs_locally(self):
            return False

        def speech_available(self):
            return False

        async def close(self):
            pass

    async def initialize(self):
        self.controller = Controller()
        self.runtime.controller = self.controller
        await self.runtime.initialize()
        self.emit("catalog", ({"scenarios": cases, "categories": [], "patients": [], "cases": []}, None))

    with patch.object(Window, "initialize", initialize), patch("human_test.app.microphones", return_value=[]):
        root = tk.Tk()
        errors = []
        root.report_callback_exception = lambda *error: errors.append(error)
        window = Window(
            root,
            Settings(_env_file=None, speaker_output=False, speech_input_enabled=False, device_id=uuid4()),
        )

        def settle(check):
            deadline = time.monotonic() + 8
            while not check():
                root.update()
                assert not errors, errors
                assert time.monotonic() < deadline, window.state.get()
                time.sleep(0.01)
            root.update()

        def refresh_queue():
            future = asyncio.run_coroutine_threadsafe(
                window.runtime.sessions.receive(platform.state()), window.loop
            )
            settle(future.done)
            future.result()
            root.update()

        try:
            settle(lambda: not window.running)
            refresh_queue()
            assert window.loaded_case["id"] == cases[1]["id"]
            assert LANGUAGES[window.language.get()] == "en", window.language.get()
            assert str(window.case_box["state"]) == "disabled"
            assert platform.begins == 0
            window.save_button.invoke()
            settle(lambda: window.page == "talk" and not window.running)
            assert "Rahul Mehta" in window.practice_identity.get()
            assert "Assigned respiratory case" in window.active_case.get()
            assert not window.listening
            window.previous_button.invoke()
            assert window.page == "setup"
            window.save_button.invoke()
            settle(lambda: window.page == "talk")
            assert platform.begins == 1
            with patch("human_test.app.messagebox.askyesno", return_value=False) as confirmation:
                window.complete_button.invoke()
                confirmation.assert_called_once()
            assert window.page == "talk" and not window.session_queue.finishing
            with patch("human_test.app.messagebox.askyesno", return_value=True) as confirmation:
                window.complete_button.invoke()
                confirmation.assert_called_once()
            settle(lambda: window.page == "setup" and not window.session_queue.finishing)
            refresh_queue()
            assert window.session_queue.next["learner_name"] == "Ananya Rao"
            window.save_button.invoke()
            settle(lambda: window.page == "talk" and not window.running)
            assert "Ananya Rao" in window.practice_identity.get()
            platform.active["status"] = "stopping"
            refresh_queue()
            settle(lambda: window.page == "setup" and not window.session_queue.finishing)
            assert "No trainee assigned" in window.practice_identity.get()
            assert platform.begins == 2 and not errors
            print(
                "Native assigned defaults, Previous, sequential trainees, desktop completion and web stop passed."
            )
        finally:
            window.close()
            deadline = time.monotonic() + 10
            while window.worker.is_alive() and time.monotonic() < deadline:
                root.update()
                time.sleep(0.02)


if __name__ == "__main__":
    main()
