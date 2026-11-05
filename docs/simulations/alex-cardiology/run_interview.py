"""Real desktop, real cloud ASR/LLM, generated WAV input in place of the microphone.

No API, provider, retry, quota, response or conversation-history behavior is mocked.
Only the source of PCM frames is replaced with the production paced WAV reader.
Artifacts contain fictional questions, answers and allowlisted diagnostics only.
"""

import argparse
import asyncio
import csv
import json
import time
import tkinter as tk
import traceback
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from human_test import app
from training_client.capture import wav_frames
from human_test.config import Settings
from training_client.pms_client import BUSY_DELAYS, ClientError
from training_client.speech import ManagerPlayback, selected_voice
from review_results import safe_error_code

HERE = Path(__file__).resolve().parent
OUT = None
QUESTIONS = []  # Loaded from the editable questions.json.


def utc():
    return datetime.now(timezone.utc).isoformat()


def turn_timeout_seconds(settings):
    # Budget both stages, plus capture and preflight; the driver must not interrupt
    # an allowed speech retry round. Playback has its own deadline.
    rounds = settings.speech_retry_rounds
    attempts = (1 + rounds * len(BUSY_DELAYS)) + (1 + len(BUSY_DELAYS))
    waits = (rounds + 1) * sum(BUSY_DELAYS)
    waits += (rounds - 1) * settings.speech_retry_round_pause_seconds
    return (
        (attempts + 2) * settings.timeout_seconds
        + waits
        + settings.max_question_seconds
        + 60
    )


def write_json(name, value):
    (OUT / name).write_text(
        json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def progress(message):
    write_json("progress.json", {"at": utc(), "message": message})


def generate_inputs():
    folder = OUT / "inputs"
    folder.mkdir(exist_ok=True)
    chosen = selected_voice("en", "female")
    if not chosen:
        raise RuntimeError("No installed English input voice")
    engine = ManagerPlayback()
    voice = engine.voice(*chosen)
    records = []
    for i, (question, topics) in enumerate(QUESTIONS, 1):
        progress(f"Preparing spoken input {i}/25")
        pcm = b"".join(
            chunk.audio_int16_bytes for chunk in voice.synthesize(question, None)
        )
        source = np.frombuffer(pcm, dtype=np.int16).astype(np.float64)
        positions = (
            np.arange(round(len(source) * 16000 / voice.config.sample_rate))
            * voice.config.sample_rate
            / 16000
        )
        samples = np.interp(positions, np.arange(len(source)), source).astype(np.int16)
        # Bounded quiet padding; fixtures contain only the requested fictional question.
        audio = b"\0" * 6400 + samples.tobytes() + b"\0" * 25600
        path = folder / f"q{i:02d}.wav"
        with wave.open(str(path), "wb") as output:
            output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            output.writeframes(audio)
        records.append(
            {
                "number": i,
                "question": question,
                "expected_topics": topics,
                "input_audio": str(path.relative_to(OUT)),
                "audio_seconds": len(audio) / 32000,
            }
        )
    engine.close()
    write_json("questions.json", records)
    return records, chosen[0]


class Interview:
    def __init__(self, records, voice, args):
        self.records = records
        self.voice = voice
        self.gap_seconds = args.gap_seconds
        self.current = None
        self.results = []
        self.stage = "initialize"
        self.deadline = time.monotonic() + 90
        self.next_at = 0
        self.meta = {
            "started_at": utc(),
            "input_voice": voice,
            "input_type": "Piper generated mono PCM16 WAV",
            "input_boundary": "production paced WAV reader replaces physical microphone",
            "live_cloud": True,
            "speaker_output": not args.mute,
            "inter_question_gap_seconds": args.gap_seconds,
            "streaming": True,
            "case_code": "alex_chest_discomfort",
        }
        self.root = tk.Tk()
        interview = self

        class ObservedWindow(app.Window):
            def emit(self, kind, value):
                interview.observe(kind, value)
                super().emit(kind, value)

            def resume_after_speech(self, progress=None, stalled=0):
                # The driver queues the next numbered fixture after playback, including
                # when normal continuous listening stops on a failure.
                return

        self.window = ObservedWindow(
            self.root,
            Settings(_env_file=None, language="en", speaker_output=not args.mute),
        )
        self.root.title("Alex - LIVE 25-question audio failure collection")
        app.microphone = self.audio_frames
        self.root.after(100, self.tick)

    def observe(self, kind, value):
        if self.current is None:
            return
        if kind in {
            "state",
            "error",
            "retrying",
            "retry_status",
            "transcript",
            "metrics",
            "ready",
            "speak",
            "turn_complete",
            "cancelled",
        }:
            event = {
                "at": utc(),
                "elapsed_ms": round((time.monotonic() - self.current["_began"]) * 1000),
                "kind": kind,
                "value": value,
            }
            self.current["events"].append(event)
            with (OUT / "events.jsonl").open("a", encoding="utf-8") as output:
                output.write(
                    json.dumps(
                        {"question_number": self.current["number"], **event},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        if kind == "transcript":
            self.current["transcript"] = value
        elif kind == "answer":
            self.current["answer"] = value
        elif kind == "answer_delta":
            self.current["answer"] = self.current.get("answer", "") + value
        elif kind == "error":
            self.current["error"] = value
        elif kind == "metrics":
            self.current["metrics"] = value
        elif kind == "speak":
            self.current["answer"] = value["text"]
        elif kind == "state" and isinstance(value, str) and "Retry " in value:
            self.current["retries"] += 1

    async def audio_frames(self, settings, send_now):
        self.current["audio_entered_pipeline"] = True
        async for frame in wav_frames(OUT / self.current["input_audio"], paced=True):
            yield frame
        self.current["audio_source_finished"] = True

    async def install_http_observers(self):
        client = self.window.controller.pms.http

        async def request(request):
            if self.current is None or request.method != "POST":
                return
            kind = (
                "speech"
                if request.url.path.endswith("/speech/transcriptions")
                else "llm"
                if request.url.path.endswith("/llm/completions")
                else None
            )
            if kind is None:
                return
            key = (
                request.url.params.get("request_key")
                if kind == "speech"
                else json.loads(request.content).get("request_key")
            )
            attempt = {
                "stage": kind,
                "request_key": key,
                "sent_at": utc(),
                "_began": time.monotonic(),
            }
            self.current["attempts"].append(attempt)
            request.extensions["interview_attempt"] = attempt

        async def response(response):
            attempt = response.request.extensions.get("interview_attempt")
            if attempt is not None:
                attempt["http_status"] = response.status_code
                attempt["headers_ms"] = round(
                    (time.monotonic() - attempt["_began"]) * 1000
                )
                if response.status_code >= 400:
                    # Capture only the controlled identifier, not provider bodies/credentials.
                    # Admission failures have no stored request to recover afterwards.
                    await response.aread()
                    try:
                        payload = response.json()
                    except ValueError:
                        return
                    error = payload.get("error") if isinstance(payload, dict) else None
                    code = (
                        safe_error_code(error.get("code"))
                        if isinstance(error, dict)
                        else None
                    )
                    if code:
                        attempt["error_code"] = code

        client.event_hooks["request"].append(request)
        client.event_hooks["response"].append(response)

    async def recover_statuses(self, row):
        pms = self.window.controller.pms
        for attempt in row["attempts"]:
            suffix = (
                "/speech/requests/"
                if attempt["stage"] == "speech"
                else "/llm/requests/"
            )
            try:
                value = await pms.json(
                    "GET", pms.organization_base + suffix + attempt["request_key"]
                )
                attempt["stored"] = {
                    k: value.get(k)
                    for k in ("status", "error_code", "result", "recording_status")
                }
            except ClientError as error:
                attempt["status_lookup_error"] = error.code or str(error)
            except Exception as error:  # noqa: BLE001 - retain safe diagnostics and finish cleanup
                attempt["status_lookup_error"] = type(error).__name__
        return row

    def snapshot(self, name):
        try:
            from window_capture import save_window

            save_window(self.root.winfo_id(), OUT / name)
        except Exception as error:  # noqa: BLE001 - retain safe diagnostics and finish cleanup
            self.meta.setdefault("screenshot_errors", []).append(type(error).__name__)

    def persist(self):
        write_json("results.json", {"metadata": self.meta, "results": self.results})
        fields = [
            "number",
            "question",
            "transcript",
            "answer",
            "outcome",
            "error",
            "retries",
            "wall_seconds",
            "audio_seconds",
        ]
        with (OUT / "results.csv").open(
            "w", newline="", encoding="utf-8-sig"
        ) as output:
            writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.results)

    def fail(self, error):
        write_json(
            "driver-error.json",
            {
                "at": utc(),
                "stage": self.stage,
                "type": type(error).__name__,
                "safe_message": str(error)
                if isinstance(error, (ClientError, RuntimeError))
                else None,
                "frames": [
                    {"file": Path(x.filename).name, "line": x.lineno, "name": x.name}
                    for x in traceback.extract_tb(error.__traceback__)
                ],
            },
        )
        progress(
            "Driver stopped: " + type(error).__name__ + "; inspect driver-error.json"
        )
        self.persist()
        self.window.close()

    def tick(self):
        try:
            self.advance()
        except Exception as error:  # noqa: BLE001 - retain safe diagnostics and finish cleanup
            self.fail(error)
            return
        if not self.window.closing:
            self.root.after(50, self.tick)

    def advance(self):
        w = self.window
        now = time.monotonic()
        if self.stage == "initialize":
            if now > self.deadline:
                raise RuntimeError("PMS desktop initialization timed out")
            if w.running:
                return
            if not w.catalog_data:
                raise RuntimeError("Desktop initialization failed: " + w.state.get())
            route = w.controller.pms.model_route
            if route["audio"]["mode"] != "cloud" or route["llm"]["mode"] != "cloud":
                raise RuntimeError("Online profile required")
            self.meta["models"] = {
                stage: {
                    key: route[stage].get(key)
                    for key in (
                        "mode",
                        "provider",
                        "model",
                        "model_options",
                        "max_tokens",
                        "context_tokens",
                    )
                }
                for stage in ("audio", "llm")
            }
            self.meta["original_selection"] = {
                k: (w.saved or {}).get(k)
                for k in ("template_id", "revision", "language")
            }
            chosen = next(
                c
                for c in w.catalog_data["cases"]
                if c["code"] == "alex_chest_discomfort"
            )
            if not chosen.get("is_synthetic"):
                raise RuntimeError("Only fictional scenarios may be captured")
            category = next(
                c
                for c in w.catalog_data["categories"]
                if c["id"] == chosen["category_id"]
            )
            w.category.set(category["name"])
            w.category_changed(load=False)
            w.case_choice.set(chosen["title"])
            w.language.set("English")
            w.load_case()
            self.stage = "case"
        elif self.stage == "case":
            if w.running:
                return
            if not w.loaded_case or w.loaded_case["code"] != "alex_chest_discomfort":
                raise RuntimeError("Selected case failed to load")
            w.save_setup()
            self.stage = "save"
        elif self.stage == "save":
            if w.running:
                return
            if w.page != "talk":
                raise RuntimeError("Patient setup did not save: " + w.state.get())
            write_json("case-snapshot.json", w.saved["document"])
            self.meta["practice_revision"] = w.saved["revision"]
            self.observer_future = asyncio.run_coroutine_threadsafe(
                self.install_http_observers(), w.loop
            )
            self.stage = "ready"
            self.next_at = now + self.gap_seconds
            progress("Cloud profile ready; beginning all 25 audio questions")
        elif self.stage == "ready":
            if now < self.next_at or w.speaker.speaking:
                return
            self.observer_future.result()
            index = len(self.results)
            if index == len(self.records):
                self.meta["completed_at"] = utc()
                self.meta["completed_questions"] = len(self.results)
                self.meta["successful_answers"] = sum(
                    r["outcome"] == "answered" for r in self.results
                )
                self.persist()
                self.snapshot("completed.png")
                progress(
                    f"Completed 25/25: {self.meta['successful_answers']} answers, {25 - self.meta['successful_answers']} failed turns"
                )
                self.stage = "finished"
                self.root.after(1000, w.close)
                return
            w.pause()
            self.current = {
                **self.records[index],
                "started_at": utc(),
                "_began": now,
                "events": [],
                "attempts": [],
                "retries": 0,
                "transcript": "",
                "answer": "",
                "error": "",
                "audio_entered_pipeline": False,
                "history_messages_before": len(w.controller.history),
            }
            progress(f"Question {index + 1}/25 running: {self.current['question']}")
            w.start_button.invoke()
            self.stage = "turn"
            self.deadline = now + turn_timeout_seconds(w.settings)
        elif self.stage == "turn":
            if w.speaker.last_error:
                self.current.setdefault("speaker_errors", []).append(
                    w.speaker.last_error
                )
            if w.running:
                if now > self.deadline:
                    self.current["driver_timeout"] = True
                    w.pause()
                return
            self.current["pipeline_finished_at"] = utc()
            self.current["pipeline_seconds"] = round(now - self.current["_began"], 3)
            self.current["displayed_answer"] = w.answer.get("1.0", "end-1c")
            self.current["displayed_state"] = w.state.get()
            self.current["history_messages_after"] = len(w.controller.history)
            self.current["outcome"] = (
                "answered"
                if self.current.get("metrics") and not self.current["error"]
                else "failed"
            )
            self.current["speaker_progress_at_finish"] = w.speaker.progress
            self.status_future = asyncio.run_coroutine_threadsafe(
                self.recover_statuses(self.current), w.loop
            )
            if self.current["outcome"] == "failed" or self.current["number"] in (
                1,
                13,
                20,
                25,
            ):
                self.snapshot(f"q{self.current['number']:02d}.png")
            self.stage = "playback"
            self.deadline = now + 65
        elif self.stage == "playback":
            if not self.status_future.done():
                return
            self.status_future.result()
            if w.speaker.speaking and now < self.deadline:
                return
            if w.speaker.speaking:
                self.current["speaker_timeout"] = True
                w.speaker.stop()
            self.current["speaker_progress_after"] = w.speaker.progress
            self.current["wall_seconds"] = round(now - self.current.pop("_began"), 3)
            self.current["completed_at"] = utc()
            for attempt in self.current["attempts"]:
                attempt.pop("_began", None)
            self.results.append(self.current)
            self.persist()
            progress(
                f"Question {len(self.results)}/25 {self.current['outcome']}; {self.current['retries']} retries; {self.current['wall_seconds']} s"
            )
            self.current = None
            self.next_at = now + self.gap_seconds
            self.stage = "ready"

    def run(self):
        self.root.mainloop()
        return len(self.results) == 25


def main():
    global OUT, QUESTIONS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gap-seconds", type=float, default=1.0)
    parser.add_argument("--mute", action="store_true")
    args = parser.parse_args()
    from local_model_client import Connection, client_key, configure

    configure(capabilities=Connection().capabilities(), key=client_key())
    OUT = args.output.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    write_json("suite.json", source)
    QUESTIONS = [(item["question"], item["expected_topics"]) for item in source]
    if len(QUESTIONS) != 25:
        raise RuntimeError("This suite requires exactly 25 questions")
    records, voice = generate_inputs()
    interview = Interview(records, voice, args)
    if not interview.run():
        raise SystemExit(1)
    from review_results import review

    summary = review(OUT)
    if summary["failed_turns"] or summary["needs_review"]:
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 - retain safe diagnostics and finish cleanup
        write_json(
            "driver-start-error.json",
            {
                "type": type(error).__name__,
                "frames": [
                    {"file": Path(x.filename).name, "line": x.lineno, "name": x.name}
                    for x in traceback.extract_tb(error.__traceback__)
                ],
            },
        )
        raise SystemExit(1) from None
