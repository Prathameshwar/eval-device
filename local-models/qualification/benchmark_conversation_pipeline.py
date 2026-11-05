"""Local fictional ASR -> Qwen -> durable journal -> Piper qualification.

Connects to running central services; never starts/stops them or calls PMS/cloud.
Default PCM sink measures component readiness, not physical audible latency.
--playback uses the actual output device; microphone input is always synthetic.
"""

# ruff: noqa: E402 - standalone CLI shares the installed native launcher.

import argparse
import asyncio
import json
import math
import statistics
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "local-models/scripts"))
from types import SimpleNamespace

import av
import httpx
import numpy as np
from training_client import audio_client
from human_test.config import Settings
from training_client.performance import PlaybackGate, TurnTiming
from training_client.session_sync import SessionSync
from training_client.speech import ManagerPlayback
from local_model_client import Connection, client_key, configure
from local_model_client.llm import LocalModel, new_client
from training_contracts.conversation.background import restore_starter_background
from training_contracts.conversation.engine import fit_conversation_prompt, run_conversation
from training_contracts.conversation.prompt import conversation_context
from training_contracts.localized_cases import review_localization
from training_contracts.privacy import private_directory


class RecordingLocalModel(LocalModel):
    """Capture fictional completion envelopes solely in private benchmark evidence."""

    async def complete(self, messages, max_tokens):
        self.last_reply = None
        self.dispatches += 1
        event = await super().complete(messages, max_tokens)
        self.last_reply = event["text"]
        return event


class PCMSink:
    """No sound device: qualify readiness and synthesis, never claim audible timing."""

    latency = None

    def start(self):
        pass

    def write(self, pcm):
        return False

    def stop(self):
        pass

    def abort(self):
        pass

    def close(self):
        pass


class Loopback:
    """Opt-in digital output monitoring. Stores no captured PCM or system audio.

    Detection includes the input callback delay; it is not acoustic onset.
    The operator must keep unrelated system audio silent during qualification.
    """

    def __init__(self):
        import sounddevice as sd

        devices = [
            (index, item)
            for index, item in enumerate(sd.query_devices())
            if item["max_input_channels"] and "stereo mix" in item["name"].lower()
        ]
        if not devices:
            raise RuntimeError("No Stereo Mix input available for digital loopback")
        self.timing = None
        self.detected = threading.Event()
        self.stream = sd.RawInputStream(
            device=devices[0][0],
            samplerate=16000,
            channels=1,
            dtype="int16",
            blocksize=320,
            callback=self._capture,
        )
        self.stream.start()

    def _capture(self, audio, frames, stamp, status):
        timing = self.timing
        if timing is None or self.detected.is_set() or status:
            return
        if timing.snapshot()["output_submission_ms"] is None:
            return
        samples = np.frombuffer(audio, dtype="<i2").astype(np.float32)
        if np.sqrt(np.mean(samples * samples)) >= 100:
            timing.mark("loopback")
            self.detected.set()

    def arm(self, timing):
        self.detected.clear()
        self.timing = timing

    def close(self):
        self.timing = None
        self.stream.stop()
        self.stream.close()


def percentile(values):
    values = sorted(values)
    return (
        {
            "samples": len(values),
            "p50_ms": statistics.median(values),
            "p95_ms": values[math.ceil(len(values) * 0.95) - 1],
            "max_ms": max(values),
        }
        if values
        else None
    )


def question_pcm(engine, text):
    voice = engine.load("en", "female")
    chunks = list(voice.synthesize(text))
    audio = np.frombuffer(b"".join(chunk.audio_int16_bytes for chunk in chunks), dtype="<i2")
    frame = av.AudioFrame.from_ndarray(audio.reshape(1, -1), format="s16", layout="mono")
    frame.sample_rate = voice.config.sample_rate
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    frames = resampler.resample(frame) + resampler.resample(None)
    return b"".join(item.to_ndarray().astype("<i2").tobytes() for item in frames)


async def exercise(server, args, token):
    rows = json.loads(
        (ROOT / "platform/api/migrations/versions/0014_patient_case_templates.json").read_text(
            encoding="utf-8"
        )
    )
    document = review_localization(
        restore_starter_background(next(row["document"] for row in rows if row["code"] == args.scenario)),
        "en",
    )
    context = conversation_context(document, "en", "", seed=f"qualification-{args.scenario}")
    (args.output / "fixture.json").write_text(json.dumps(document, indent=2), encoding="utf-8")
    if args.matrix.stat().st_size > 131072:
        raise ValueError("Question matrix exceeds its budget")
    matrix = json.loads(args.matrix.read_text(encoding="utf-8"))["questions"]
    if (
        not isinstance(matrix, list)
        or not 10 <= len(matrix) <= 25
        or any(
            not isinstance(probe, dict)
            or not isinstance(probe.get("question"), str)
            or not 1 <= len(probe["question"]) <= 500
            or "\0" in probe["question"]
            for probe in matrix
        )
    ):
        raise ValueError("Use 10 to 25 bounded fictional questions")
    sid = str(uuid4())
    settings = Settings(
        _env_file=None,
        organization_id=uuid4(),
        device_id=uuid4(),
        session_sync_dir=args.output / "journal",
        session_sync_background=False,
        local_models_port=args.manager_port,
        local_models_key=token,
        local_models_state_dir=args.manager_state,
        local_models_capabilities=args.capabilities,
        audio_model=args.asr,
        audio_device=args.asr_device,
        language="en",
    )
    sync = SessionSync(
        settings, lambda *_: None, transport=httpx.MockTransport(lambda _: httpx.Response(503))
    )
    sync.busy(True)
    sync.activate({"context": {"conversation_id": sid}, "snapshot": context})
    engine, question_voice = ManagerPlayback(), ManagerPlayback()
    loopback = None
    if not args.playback:
        engine._output = lambda _: PCMSink()
    results = []
    try:
        if args.loopback:
            loopback = Loopback()
        voice_started = time.perf_counter()
        engine.warm("en")
        voice_prepare_ms = round((time.perf_counter() - voice_started) * 1000, 2)
        # Pre-generate input: excludes question synthesis from response timing.
        inputs = [question_pcm(question_voice, probe["question"]) for probe in matrix]
        async with new_client(120) as client:
            model = RecordingLocalModel(
                args.manager_port, server.key, server.profile["alias"], context_cap=2048, client=client
            )
            model.last_reply = None
            model.dispatches = 0
            await model.health()
            await audio_client.preflight(settings)
            for repeat in range(args.rounds):
                history = []
                for index, (probe, pcm) in enumerate(zip(matrix, inputs, strict=True)):
                    timing = TurnTiming()
                    timing.mark("worker")
                    item = {
                        "scenario": args.scenario,
                        "round": repeat + 1,
                        "index": index + 1,
                        "question": probe["question"],
                        "expected": probe.get("expected"),
                    }
                    model.last_reply = None
                    dispatches_before = model.dispatches

                    async def frames(audio=pcm, measured=timing):
                        deadline = time.perf_counter()
                        for start in range(0, len(audio), 1600):
                            frame = audio[start : start + 1600]
                            yield frame
                            deadline += len(frame) / 32000
                            if args.realtime:
                                await asyncio.sleep(max(0, deadline - time.perf_counter()))
                        measured.mark("speech_end")
                        # Simulated desktop quiet interval; not a physical VAD test.
                        for _ in range(args.silence_ms // 50):
                            yield b"\0" * 1600
                            deadline += 0.05
                            if args.realtime:
                                await asyncio.sleep(max(0, deadline - time.perf_counter()))
                        measured.mark("endpoint")

                    try:
                        transcript = await audio_client.transcribe(settings, frames(), lambda *_: None)
                        timing.mark("transcript")
                        item["transcript"] = transcript["text"]
                        messages, budget = await fit_conversation_prompt(
                            model,
                            [
                                {"role": "system", "content": context["system"]},
                                *([] if probe.get("history") == "empty" else history[-4:]),
                                {"role": "user", "content": transcript["text"]},
                            ],
                            128,
                            context=context,
                        )
                        timing.mark("model_start")
                        answer = await run_conversation(model, context, messages, 128)
                        timing.mark("answer")
                        item.update(
                            answer=answer["text"], provider_calls=answer["provider_calls"], budget=budget
                        )
                        gate = PlaybackGate()
                        if loopback:
                            loopback.arm(timing)
                        playback_errors = []

                        def play(text=answer["text"], measured=timing, release=gate, errors=playback_errors):
                            stream_id = str(uuid4())
                            sync.audio_start(sid, stream_id)
                            try:
                                engine.play(
                                    text,
                                    "en",
                                    lambda: True,
                                    gate=release,
                                    performance=measured,
                                    on_audio=lambda audio_slice, rate: sync.audio(
                                        sid, stream_id, audio_slice, rate, "patient_audio"
                                    ),
                                )
                            except Exception as error:
                                errors.append(type(error).__name__)
                            finally:
                                sync.audio_end(sid, stream_id)

                        playback = threading.Thread(target=play, daemon=True)
                        playback.start()
                        saved = False
                        timing.mark("save_start")
                        try:
                            saved = await sync.save_turn(
                                sid,
                                {
                                    "turn_key": str(uuid4()),
                                    "input_text": transcript["text"],
                                    "response_text": answer["text"],
                                    "outcome": "completed",
                                    "input_source": "speech",
                                    "execution": "local",
                                },
                            )
                            if saved:
                                timing.mark("saved")
                        finally:
                            gate.resolve(saved)
                            await asyncio.to_thread(playback.join, 45)
                        if playback.is_alive() or playback_errors or not saved:
                            raise RuntimeError("Playback/persistence qualification failed")
                        item["timings"] = timing.snapshot()
                        item["asr_finalize_ms"] = transcript["asr_finalize_ms"]
                        history.extend(
                            [
                                {"role": "user", "content": transcript["text"]},
                                {"role": "assistant", "content": answer["text"]},
                            ]
                        )
                    except Exception as error:
                        item["error"] = getattr(error, "code", type(error).__name__)
                    item["raw_reply"] = model.last_reply
                    item["provider_dispatches"] = model.dispatches - dispatches_before
                    results.append(item)
                    (args.output / "answers.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
                    duration = item.get("timings", {}).get(
                        "estimated_audible_ms" if args.playback else "output_submission_ms"
                    )
                    print(
                        f"Round {repeat + 1}, question {index + 1}: {duration} ms; {item.get('error', 'completed')}",
                        flush=True,
                    )
    finally:
        engine.close()
        question_voice.close()
        if loopback:
            loopback.close()
        sync.end()
        await sync.close()
    warm = [item for item in results if item["index"] > 1 and "timings" in item]
    field = "estimated_audible_ms" if args.playback else "output_submission_ms"
    values = [item["timings"][field] for item in warm if item["timings"][field] is not None]
    summary = {
        "scenario": args.scenario,
        "compiler_version": context["compiler_version"],
        "beam_size": args.beam_size,
        "model": server.profile["name"],
        "asr": args.asr,
        "asr_device": args.asr_device,
        "gpu_layers": args.gpu_layers,
        "actual_offloaded_layers": server.metrics["offloaded_layers"],
        "playback": args.playback,
        "realtime_input": args.realtime,
        "simulated_silence_ms": args.silence_ms,
        "acoustic_loopback_measured": False,
        "digital_loopback_enabled": args.loopback,
        "digital_loopback_detection": percentile(
            [
                item["timings"]["loopback_detection_ms"]
                for item in warm
                if item["timings"]["loopback_detection_ms"] is not None
            ]
        ),
        "physical_microphone_measured": False,
        "voice_prepare_ms": voice_prepare_ms,
        "model_startup_seconds": server.metrics["startup_seconds"],
        "one_generation_per_answer": all(
            item.get("provider_calls") == 1 for item in results if "timings" in item
        ),
        "all_fitted_prompts_within_context": all(
            item["budget"]["prompt_tokens"] + 256 <= 2048 for item in results if "budget" in item
        ),
        "completed": sum("timings" in item for item in results),
        "errors": sum("error" in item for item in results),
        "first_audio": percentile(values),
        "over_5_seconds": sum(value > 5000 for value in values),
        "stage_timings": {
            field: percentile([item["timings"][field] for item in warm if item["timings"][field] is not None])
            for field in ("transcript_ms", "preparation_ms", "model_ms", "save_ms", "first_pcm_ms")
        },
        "latency_gate_passed": bool(
            args.playback
            and args.realtime
            and values
            and not any("error" in item for item in results)
            and len(values) == (len(matrix) - 1) * args.rounds
            and statistics.median(values) <= 3000
            and sorted(values)[math.ceil(len(values) * 0.95) - 1] <= 5000
        ),
        "quality_gate": "Manual transcript/answer review required; timing alone is insufficient",
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    templates = json.loads(
        (ROOT / "platform/api/migrations/versions/0014_patient_case_templates.json").read_text(
            encoding="utf-8"
        )
    )
    parser.add_argument(
        "--scenario", choices=[row["code"] for row in templates], default="alex_chest_discomfort"
    )
    parser.add_argument("--manager-port", type=int, default=8790)
    parser.add_argument("--manager-state", type=Path)
    parser.add_argument(
        "--matrix",
        type=Path,
        help="Fictional question matrix; defaults to the selected scenario's matrix",
    )
    parser.add_argument(
        "--asr",
        choices=("small", "medium", "large-v3", "large-v3-turbo", "nemotron-3.5-asr-streaming-0.6b"),
        default="large-v3",
    )
    parser.add_argument("--rounds", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--silence-ms", type=int, choices=(600, 800), default=800)
    parser.add_argument("--realtime", action="store_true")
    parser.add_argument("--playback", action="store_true")
    parser.add_argument("--loopback", action="store_true")
    parser.add_argument(
        "--require-latency",
        action="store_true",
        help="Exit unsuccessfully when the measured warm latency gate fails",
    )
    args = parser.parse_args()
    if args.matrix is None:
        args.matrix = (
            ROOT / "docs/simulations/patient-background/qualification-questions.json"
            if args.scenario == "alex_chest_discomfort"
            else ROOT / "docs/simulations/conversation-scenarios" / (args.scenario + ".json")
        )
    if args.matrix.stat().st_size > 131072:
        parser.error("Question matrix exceeds its budget")
    matrix_document = json.loads(args.matrix.read_text(encoding="utf-8"))
    if matrix_document.get("scenario", args.scenario) != args.scenario:
        parser.error("Question matrix belongs to a different scenario")
    if args.loopback and not args.playback:
        parser.error("--loopback requires --playback")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    private_directory(args.output)
    connection = Connection(state=args.manager_state, port=args.manager_port)
    info = connection.capabilities()
    connection.require("llm")
    connection.require("asr", args.asr)
    connection.require("tts")
    args.capabilities = info
    configure(
        state=args.manager_state,
        port=args.manager_port,
        key=client_key(args.manager_state),
        capabilities=info,
    )
    llm = info["services"]["llm"]
    model = next(m for m in info["models"] if m["id"] == llm["model_id"])
    args.asr_device = info["services"]["asr"]["device"]
    args.gpu_layers = llm["options"].get("gpu_layers", 0)
    args.beam_size = None
    server = SimpleNamespace(
        key=client_key(args.manager_state),
        profile={"alias": model["alias"], "name": model["name"]},
        metrics={"offloaded_layers": None, "startup_seconds": None},
    )
    summary = asyncio.run(exercise(server, args, server.key))
    if args.require_latency and not summary["latency_gate_passed"]:
        raise SystemExit("Warm latency gate failed; inspect the recorded stage timings")


if __name__ == "__main__":
    main()
