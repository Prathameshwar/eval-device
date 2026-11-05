"""Resident Whisper/Qwen interview through the production listener, controller and Tk UI.

Only the microphone PCM source, PMS case publication and metrics destination are fixtures.
No cloud calls, app database writes, real microphone recordings or speaker playback.
Run with human-test/.venv/Scripts/python.exe from the repository root.
"""

import argparse
import asyncio
import json
import sys
import time
import tkinter as tk
import wave
from pathlib import Path
from uuid import uuid4

import numpy as np
import sounddevice as sd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "local-models/scripts"))
from human_test import app
from training_client import audio_client, local_turn
from training_client.capture import BLOCK_SAMPLES
from human_test.config import Settings
from training_client.controller import Controller
from training_client.listening import Listener
from training_client.speech import ManagerPlayback, selected_voice

QUESTIONS = [
    ("What is your name?", ["name"], "clean"),
    ("How old are you?", ["age"], "quiet"),
    ("What brings you here today?", ["complaint"], "clean"),
    ("When did your symptoms begin?", ["duration"], "clean"),
    ("What makes your symptoms worse or better?", ["symptom_details"], "noise"),
    ("What other symptoms have you noticed?", ["associated"], "clean"),
    ("Have you had any previous medical conditions?", ["past_history"], "clean"),
    ("What medicines are you taking?", ["medications"], "pause"),
    ("Do you have any allergies?", ["allergies"], "clean"),
    ("Do you smoke or drink alcohol?", ["social_history"], "clean"),
    ("What is your temperature?", ["temperature"], "clean"),
    ("What is the capital of France?", [], "clean"),
]
DEFAULT_CASES = ["alex_chest_discomfort", "alex_dry_cough"]


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def case_documents():
    source = ROOT / "platform/api/migrations/versions/0014_patient_case_templates.json"
    return {
        row["code"]: row["document"]
        for row in json.loads(source.read_text(encoding="utf-8"))
    }


def question_rows(path):
    if path is None:
        return [
            {"question": question, "expected_topics": topics, "condition": condition}
            for question, topics, condition in QUESTIONS
        ]
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise ValueError("Question file must contain 1 to 200 question objects")
    cases = case_documents()
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("question"), str)
            or not 1 <= len(row["question"].strip()) <= 500
            or row.get("case") not in cases
            or row.get("condition") not in {"clean", "quiet", "noise", "pause"}
            or not isinstance(row.get("expected_topics"), list)
            or not all(isinstance(topic, str) for topic in row["expected_topics"])
        ):
            raise ValueError("Invalid question, case, condition or expected topics")
        available = {topic["id"] for topic in cases[row["case"]]["dialogue"]["topics"]}
        if not set(row["expected_topics"]).issubset(available):
            raise ValueError("Expected topic is not present in the selected case")
        if row["condition"] == "pause":
            parts = row.get("segments")
            if (
                not isinstance(parts, list)
                or len(parts) != 2
                or not all(isinstance(part, str) and part.strip() for part in parts)
                or " ".join(parts) != row["question"]
            ):
                raise ValueError(
                    "Paused questions require two segments matching the question"
                )
    return rows


def inputs(folder, questions):
    folder.mkdir(exist_ok=True)
    engine = ManagerPlayback()
    chosen = selected_voice("en", "female")
    if not chosen:
        raise RuntimeError("An installed English Piper input voice is required")
    voice = engine.voice(*chosen)
    rng = np.random.default_rng(20260921)

    def synth(text):
        raw = b"".join(c.audio_int16_bytes for c in voice.synthesize(text, None))
        source = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
        positions = np.arange(round(len(source) * 16000 / voice.config.sample_rate))
        return np.interp(
            positions * voice.config.sample_rate / 16000, np.arange(len(source)), source
        )

    records = []
    try:
        for number, row in enumerate(questions, 1):
            question, condition = row["question"], row["condition"]
            if condition == "pause":
                parts = row.get("segments", ["What medicines", "are you taking?"])
                samples = np.concatenate(
                    [synth(parts[0]), np.zeros(5600), synth(parts[1])]
                )
            else:
                samples = synth(question)
            if condition == "quiet":
                samples *= 0.3
            samples = np.concatenate([np.zeros(8000), samples, np.zeros(19200)])
            if condition == "noise":
                samples += rng.normal(0, 180, len(samples))
            pcm = np.clip(samples, -32768, 32767).astype("<i2").tobytes()
            path = folder / f"q{number:02d}.wav"
            with wave.open(str(path), "wb") as output:
                output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                output.writeframes(pcm)
            records.append(
                {
                    **row,
                    "number": number,
                    "input": path.name,
                    "audio_seconds": len(pcm) / 32000,
                }
            )
    finally:
        engine.close()
    return records


class PCMDevice:
    """Replace only PortAudio input; paced PCM traverses the real gate and callback queue."""

    def __init__(self):
        self.callback = None
        self.opens = self.closes = 0

    def stream(self, **kwargs):
        device = self

        class Stream:
            def __enter__(self):
                device.callback = kwargs["callback"]
                device.opens += 1
                return self

            def __exit__(self, *args):
                device.closes += 1

        return Stream()

    async def feed(self, pcm):
        began = time.monotonic()
        size = BLOCK_SAMPLES * 2
        for offset in range(0, len(pcm), size):
            self.callback(
                pcm[offset : offset + size].ljust(size, b"\0"),
                BLOCK_SAMPLES,
                None,
                False,
            )
            await asyncio.sleep(
                max(0, began + (offset + size) / 32000 - time.monotonic())
            )


async def interview(output, token, port, records, llm_settings, answer_mode):
    route = json.loads(
        (ROOT / "human-test/.local/demo/launcher.json").read_text(encoding="utf-8")
    )["model_route"]
    if route["llm"].get("execution") != "caller" or route["audio"]["mode"] != "local":
        raise RuntimeError("The saved profile must select local ASR and local LLM")
    route["llm"]["local_port"] = llm_settings["port"]
    if answer_mode:
        route["llm"]["model_options"]["patient_answer_mode"] = answer_mode
    settings = Settings(
        _env_file=None,
        pms_token="simulation-no-platform-calls",
        local_models_key=token,
        local_models_port=port,
        local_models_capabilities=llm_settings["capabilities"],
        organization_id=uuid4(),
        connection_id=uuid4(),
        language="en",
        speaker_output=False,
        audio_device="cuda",
    )
    status = await audio_client.preflight(settings)
    cases = case_documents()
    selected_codes = list(
        dict.fromkeys(row["case"] for row in records if "case" in row)
    )
    selected_codes = selected_codes or DEFAULT_CASES
    root = tk.Tk()
    root.withdraw()
    ui_errors = []
    root.report_callback_exception = lambda kind, value, tb: ui_errors.append(
        {"type": kind.__name__, "error": str(value)}
    )

    class Window(app.Window):
        async def initialize(self):
            pass

    original_mics = app.microphones
    app.microphones = list
    window = Window(root, settings)
    app.microphones = original_mics
    window.page = "talk"
    window.running = window.listening = True
    current = None
    metrics = []

    def emit(kind, value):
        if current is not None and kind in {
            "state",
            "transcript",
            "metrics",
            "turn_failed",
            "mic",
        }:
            current["events"].append(
                {
                    "seconds": round(time.monotonic() - current["started"], 3),
                    "kind": kind,
                    "value": value,
                }
            )
        window.emit(kind, value)

    controller = Controller(settings, emit)
    controller.pms.model_route = route

    async def collect_metric(event):
        metrics.append(event)

    controller.metrics_reporter.send = collect_metric
    await local_turn.health(controller.local_model())
    device = PCMDevice()
    original = sd.RawInputStream, sd.check_input_settings, sd.query_devices
    sd.RawInputStream = device.stream
    sd.check_input_settings = lambda **kwargs: None
    sd.query_devices = lambda *args, **kwargs: [
        {"name": "Synthetic PCM", "max_input_channels": 1}
    ]
    settings.microphone = 0
    listener = Listener(settings, emit)
    listener_task = asyncio.create_task(listener.run())
    processing = False
    completed = []
    stop = False

    async def pump_ui():
        while not stop:
            root.update()
            await asyncio.sleep(0.01)

    async def worker():
        nonlocal processing
        while True:
            item = await listener.ready.get()
            if item is None:
                raise listener.failure or RuntimeError("Input ended")
            processing = True
            window.capture_quality = item.quality
            before = len(metrics)
            try:
                result = await controller.turn(item.frames())
                await asyncio.sleep(0.05)
                result.update(
                    quality=item.quality.snapshot(),
                    local_metrics=metrics[before:],
                    ui_state=window.state.get(),
                )
                completed.append(result)
            except Exception as error:  # noqa: BLE001 - retain failed turns as simulation evidence
                emit("turn_failed", str(error))
                completed.append(
                    {
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "quality": item.quality.snapshot(),
                    }
                )
            finally:
                processing = False
                listener.ready.task_done()

    pump = asyncio.create_task(pump_ui())
    consumer = asyncio.create_task(worker())
    result = {
        "models": {
            "asr": status["model"],
            "device": status["device"],
            "llm": route["llm"]["model"],
            "context_tokens": route["llm"]["local_context_tokens"],
            "history_messages": route["llm"].get("history_messages"),
            "answer_mode": local_turn.published_mode(route, "patient_answer_mode"),
        },
        "boundary": "Real local ASR, Qwen, listener, controller and hidden Tk UI; generated PCM replaces the microphone; fixture case publication and local metrics sink; no PMS writes or speaker playback",
        "cases": [
            {
                "code": code,
                "category": cases[code]["specialty"],
                "title": cases[code]["title"],
            }
            for code in selected_codes
        ],
        "turns": [],
        "stress": [],
        "ui_errors": ui_errors,
    }
    try:
        while device.callback is None:
            if listener_task.done():
                await listener_task
            await asyncio.sleep(0.02)
        # Silence must never submit a question.
        await device.feed(bytes(32000 * 2))
        result["idle_silence_submissions"] = len(completed)
        for code in selected_codes:
            category = cases[code]["specialty"]
            controller.use_selection(
                {
                    "id": str(uuid4()),
                    "revision": 1,
                    "language": "en",
                    "document": cases[code],
                }
            )
            for row in records:
                if row.get("case", code) != code:
                    continue
                current = {
                    **row,
                    "category": category,
                    "case": code,
                    "case_title": cases[code]["title"],
                    "started": time.monotonic(),
                    "events": [],
                }
                print(
                    f"RUN {category} {row['number']:02d}: {row['question']} [{row['condition']}]",
                    flush=True,
                )
                before = len(completed)
                with wave.open(str(output / "inputs" / row["input"]), "rb") as source:
                    await device.feed(source.readframes(source.getnframes()))
                deadline = time.monotonic() + 190
                while (
                    processing
                    or not listener.ready.empty()
                    or listener.active is not None
                ):
                    if consumer.done():
                        await consumer
                    if time.monotonic() > deadline:
                        raise TimeoutError(
                            "Interview turn did not finish within the simulation deadline"
                        )
                    await asyncio.sleep(0.05)
                await asyncio.sleep(0.08)
                current["results"] = completed[before:]
                current["elapsed_seconds"] = round(
                    time.monotonic() - current.pop("started"), 3
                )
                outcomes = current["results"]
                topics = [
                    t
                    for outcome in outcomes
                    for metric in outcome.get("local_metrics", [])
                    for t in metric["topics"]
                ]
                current["topic_match"] = (
                    len(outcomes) == 1
                    and not outcomes[0].get("error")
                    and (
                        set(row["expected_topics"]) == set(topics)
                        if row["expected_topics"]
                        else any(
                            m["answer_source"] == "case_clarification"
                            for m in outcomes[0].get("local_metrics", [])
                        )
                    )
                )
                result["turns"].append(current)
                print(
                    f"DONE inputs={len(outcomes)} topics={topics} match={current['topic_match']} "
                    f"seconds={current['elapsed_seconds']}",
                    flush=True,
                )
                write(output / "result.json", result)
                current = None

        # A real empty recognition exercises the no-answer timing branch in the native UI.
        async def silence():
            yield bytes(32000)

        empty = await controller.turn(silence())
        await asyncio.sleep(0.15)
        result["stress"].append(
            {
                "name": "empty_asr",
                "result": empty,
                "ui_state": window.state.get(),
                "pending_ui_events": window.events.qsize(),
                "ui_errors": list(ui_errors),
            }
        )
        # Check that the next local turn and display still work after empty recognition.
        recovery = await controller.text_turn("What is your name?")
        await asyncio.sleep(0.15)
        result["stress"].append(
            {
                "name": "after_empty_asr",
                "result": recovery,
                "ui_state": window.state.get(),
                "pending_ui_events": window.events.qsize(),
            }
        )
        result["input_stream_opens"] = device.opens
    finally:
        current = None
        for task in (consumer, listener_task):
            task.cancel()
        await asyncio.gather(consumer, listener_task, return_exceptions=True)
        sd.RawInputStream, sd.check_input_settings, sd.query_devices = original
        await controller.close()
        result["input_stream_closes"] = device.closes
        write(output / "result.json", result)
        stop = True
        await pump
        window.close()
        until = time.monotonic() + 10
        while window.worker.is_alive() and time.monotonic() < until:
            root.update()
            await asyncio.sleep(0.02)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--answer-mode", choices=["authored", "generated"])
    parser.add_argument(
        "--questions",
        type=Path,
        help="Optional JSON questions assigned to specific cases",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if (output / "result.json").exists():
        raise ValueError(
            "Use a new output directory to preserve previous simulation evidence"
        )
    output.mkdir(parents=True, exist_ok=True)
    from local_model_client import Connection, client_key, configure

    configure(capabilities=Connection().capabilities(), key=client_key())
    records = inputs(output / "inputs", question_rows(args.questions))
    write(output / "questions.json", records)
    from local_model_client import Connection, client_key, configure

    connection = Connection()
    info = connection.capabilities()
    connection.require("llm")
    connection.require("asr", "large-v3")
    connection.require("tts")
    configure(capabilities=info, key=client_key())
    result = asyncio.run(
        interview(
            output,
            client_key(),
            connection.port,
            records,
            {"port": connection.port, "capabilities": info},
            args.answer_mode,
        )
    )
    print(
        json.dumps({"turns": len(result["turns"]), "ui_errors": result["ui_errors"]}),
        flush=True,
    )


if __name__ == "__main__":
    main()
