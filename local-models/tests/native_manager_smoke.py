# ruff: noqa: E402 - standalone native qualification imports
"""Opt-in native qualification with existing verified assets; never downloads.

Run explicitly on Windows: python local-models/tests/native_manager_smoke.py
Owns an isolated daemon and ports, and stops only the workers it provisions.
"""

import argparse
import asyncio
import base64
import io
import json
import socket
import sys
import tempfile
import time
import tkinter as tk
import uuid
import wave
from pathlib import Path

LOCAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL))
sys.path.insert(0, str(LOCAL / "client/src"))
sys.path.insert(0, str(LOCAL.parent / "shared/training-contracts/src"))

from local_model_client import Connection, client_key
from local_model_client.audio import RemoteVoice, recognition_ready, transcribe
from local_model_client.llm import LocalModel, new_client
from training_contracts.conversation.sources import selection_prompt
from training_contracts.patient_turn import fit_patient_prompt

from desktop.live import LiveModelManager  # noqa: E402
from desktop.manager_client import Client  # noqa: E402
from service.errors import ManagerError  # noqa: E402
from service.protocol import call  # noqa: E402


def port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gpu", action="store_true", help="Qualify LLM/recognition on the available NVIDIA GPU"
    )
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Native qualification targets Windows")
    with tempfile.TemporaryDirectory(dir=LOCAL.parent / ".test_artifacts") as name:
        root = Path(name)
        client = Client(root, port())
        client.connect()
        kinds = []
        skipped = []
        checked = []

        def status():
            return client.request("GET", "/v1/status")

        def action(name, payload):
            identifier = str(uuid.uuid4())
            client.request("POST", "/v1/actions/" + name, {**payload, "request_id": identifier})
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                op = client.request("GET", "/v1/operations/" + identifier)
                if op["state"] == "succeeded":
                    return
                if op["state"] in {"failed", "interrupted"}:
                    raise AssertionError(json.dumps(op))
                time.sleep(0.1)
            raise AssertionError("Operation deadline exceeded")

        try:
            until = time.monotonic() + 120
            data = status()
            while any(m["status"] == "Checking" for m in data["models"]) and time.monotonic() < until:
                time.sleep(0.2)
                data = status()
            installed = {m["id"] for m in data["models"] if m["status"] == "Installed"}
            print("Verified installed catalog:", sorted(installed), flush=True)
            for kind, model in (("llm", "qwen3-1.7b"), ("tts", "piper-en-male"), ("asr", "large-v3")):
                if model not in installed:
                    skipped.append(kind + ": no verified " + model + " asset")
                    continue
                outer = port()
                while outer > 64000 or outer + 100 > 65000:
                    outer = port()
                action(
                    "provision",
                    {
                        "capability": kind,
                        "model_id": model,
                        "device": "gpu" if args.gpu and kind != "tts" else "cpu",
                        "port": outer,
                        "start_at_boot": False,
                        "revision": status()["revision"],
                        "options": {"startup_timeout_seconds": 180, "max_tokens": 32},
                    },
                )
                kinds.append(kind)
                action("start", {"capability": kind, "revision": status()["revision"]})
                service = next(s for s in status()["services"] if s["capability"] == kind)
                assert service["device"] == ("cuda" if args.gpu and kind != "tts" else "cpu")
                print(kind, "ready on", service["device"], flush=True)
                if kind == "llm":
                    payload = {"messages": [{"role": "user", "content": "Reply with a short greeting."}]}
                elif kind == "tts":
                    payload = {"text": "Hello. This is a local inference check."}
                else:
                    source = io.BytesIO()
                    with wave.open(source, "wb") as target:
                        target.setnchannels(1)
                        target.setsampwidth(2)
                        target.setframerate(16000)
                        target.writeframes(b"\0" * 32000)
                    payload = {
                        "wav_base64": base64.b64encode(source.getvalue()).decode("ascii"),
                        "language": "en",
                    }
                result = call(client.port, client.key(), "POST", "/v1/infer/" + kind, payload, timeout=180)
                inference = Connection(state=root, port=client.port, key=client_key(root))
                assert inference.require(kind, model)["ready"]
                if kind == "llm":

                    async def client_turn():
                        async with new_client(180) as http:
                            runner = LocalModel(
                                client.port,
                                client_key(root),
                                "qwen3-1.7b-local",
                                context_cap=2048,
                                client=http,
                            )
                            await runner.health()
                            sources = {"f1": {"subject": "chief_complaint", "text": "I have a dry cough."}}
                            messages = [
                                {"role": "system", "content": selection_prompt(sources)},
                                {"role": "user", "content": "What problem brought you here?"},
                            ]
                            fitted, budget = await fit_patient_prompt(runner, messages, 32)
                            completion = await runner.complete(fitted, 32)
                            assert json.loads(completion["text"]) in (
                                ["f1"],
                                ["unknown"],
                                ["clarify"],
                                ["boundary"],
                            )
                            assert budget["prompt_tokens"] > 0

                    asyncio.run(client_turn())
                    print(
                        "Shared client: readiness, native template/token budget and constrained completion passed",
                        flush=True,
                    )
                    assert result["choices"][0]["message"]["content"].strip()
                    window = tk.Tk()
                    window.withdraw()
                    app = LiveModelManager(window, client)
                    until = time.monotonic() + 10
                    while not app.connected and time.monotonic() < until:
                        window.update()
                        time.sleep(0.02)
                    assert app.connected
                    app.close()
                    # A new client can infer through the same resident worker after actual desktop closure.
                    replacement = Client(root, client.port)
                    second = call(
                        replacement.port, replacement.key(), "POST", "/v1/infer/llm", payload, timeout=180
                    )
                    assert second["choices"][0]["message"]["content"].strip()
                    print("Desktop closed; resident LLM inference still available", flush=True)
                elif kind == "tts":
                    remote = RemoteVoice(inference, "en-male", "en", "male")
                    chunks = list(remote.synthesize("Hello. Central synthesis is ready."))
                    assert chunks and remote.config.sample_rate >= 8000
                    print("Shared client: bounded TTS WAV decoding passed", flush=True)
                    raw = base64.b64decode(result["wav_base64"], validate=True)
                    with wave.open(io.BytesIO(raw), "rb") as source:
                        assert source.getnframes() > 0
                else:

                    async def client_asr():
                        await recognition_ready(inference, "large-v3", "en")
                        answer = await transcribe(inference, bytes(32000), "large-v3", "en")
                        assert isinstance(answer["text"], str)

                    asyncio.run(client_asr())
                    print("Shared client: pinned recognition passed", flush=True)
                    assert isinstance(result["text"], str)
                assert payload.get("text", "never") not in (root / "state.json").read_text(encoding="utf-8")
                action("stop", {"capability": kind, "revision": status()["revision"]})
                assert not any(s.get("ready", False) for s in status()["services"] if s["capability"] == kind)
                checked.append(kind)
                print(kind, "native inference and stop passed", flush=True)
            print(
                "Native",
                "GPU/CPU" if args.gpu else "CPU",
                "checks:",
                checked,
                "Skipped:",
                skipped,
                flush=True,
            )
        finally:
            for kind in kinds:
                try:
                    action("stop", {"capability": kind, "revision": status()["revision"]})
                except (ManagerError, AssertionError):
                    pass
            client.request("POST", "/v1/shutdown", {})
            for _ in range(60):
                try:
                    status()
                except ManagerError:
                    break
                time.sleep(0.1)
            if client.launched is not None:
                client.launched.wait(timeout=20)  # Port closure can precede final process/lock cleanup.


if __name__ == "__main__":
    main()
