"""One resident inference adapter. No capture, playback, cloud or platform credentials."""

import base64
import io
import json
import sys
import threading
import time
import wave
from pathlib import Path

LOCAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL))

from service.assets import Assets  # noqa: E402
from service.catalog import Catalog  # noqa: E402
from service.errors import ManagerError, require  # noqa: E402
from service.http_server import JsonServer  # noqa: E402
from service.protocol import call  # noqa: E402
from service.security import checked  # noqa: E402


class Llm:
    def __init__(self, configuration):
        sys.path.insert(0, str(LOCAL / "scripts"))
        import common

        common.STATE = Path(configuration["native_state"])
        common.STATE.mkdir(parents=True, exist_ok=True)
        import run

        self.settings = {
            **common.config(),
            **configuration["options"],
            "model": configuration["model_id"],
            "gpu_enabled": configuration["device"] == "gpu",
            "port": configuration["port"] + 100,
        }
        self.settings.pop("drain_timeout_seconds", None)
        asset = Assets(Catalog())
        location = asset.verify(configuration["model_id"])
        original = common.model_profile

        def profile(settings):
            value = original(settings)
            value["path"] = location / value["path"].name
            return value

        common.model_profile = profile
        run.model_profile = profile
        executable = (
            LOCAL / ".runtime" / ("cuda" if self.settings["gpu_enabled"] else "cpu") / "llama-server.exe"
        )
        # Verify runtime independently here without the installer's network/download branch.
        manifest = json.loads(checked(executable.parent / "manifest.json").read_text(encoding="utf-8"))
        from service.assets import digest

        require("llama-server.exe" in manifest, "runtime_integrity", "Native runtime is incomplete")
        for name, expected in manifest.items():
            require(
                Path(name).name == name and digest(executable.parent / name) == expected,
                "runtime_integrity",
                "Native runtime verification failed",
            )
        run.verify_install = lambda *_: executable
        self.server = run.Server(self.settings)
        try:
            self.server.start()
        except BaseException:
            self.server.close()
            raise

    def status(self):
        return {
            "ready": self.server.process.poll() is None,
            "failed": self.server.process.poll() is not None,
            "device": self.server.metrics["device"],
            "offloaded_layers": self.server.metrics["offloaded_layers"],
        }

    def messages(self, messages):
        require(isinstance(messages, list) and 1 <= len(messages) <= 32, "input", "Invalid messages")
        size = 0
        for message in messages:
            require(
                isinstance(message, dict)
                and set(message) == {"role", "content"}
                and message["role"] in {"system", "developer", "user", "assistant"}
                and isinstance(message["content"], str)
                and len(message["content"].encode("utf-8")) <= 65536,
                "input",
                "Invalid message content",
            )
            size += len(message["content"].encode("utf-8"))
        require(size <= 262144, "input", "Prompt exceeded its limit")
        return messages

    def expected(self, value):
        require(
            value == self.server.profile["alias"],
            "model_mismatch",
            "Assigned model differs from the running model",
            409,
        )

    def inspect(self, request):
        require(
            isinstance(request, dict) and set(request) == {"model", "operation", "payload"},
            "input",
            "Invalid model inspection",
        )
        self.expected(request["model"])
        operation, payload = request["operation"], request["payload"]
        require(operation in {"props", "apply-template", "tokenize"}, "input", "Unsupported inspection")
        if operation == "props":
            require(payload is None, "input", "Props has no parameters")
            method = "GET"
        elif operation == "apply-template":
            require(
                isinstance(payload, dict)
                and set(payload) == {"messages", "chat_template_kwargs"}
                and payload["chat_template_kwargs"] == {"enable_thinking": False},
                "input",
                "Invalid template parameters",
            )
            self.messages(payload["messages"])
            method = "POST"
        else:
            require(
                isinstance(payload, dict)
                and set(payload) == {"content", "add_special", "parse_special"}
                and isinstance(payload["content"], str)
                and len(payload["content"].encode("utf-8")) <= 65536
                and payload["add_special"] is False
                and payload["parse_special"] is True,
                "input",
                "Invalid tokenization",
            )
            method = "POST"
        return call(self.settings["port"], self.server.key, method, "/" + operation, payload, timeout=10)

    def infer(self, payload):
        require(
            isinstance(payload, dict)
            and "messages" in payload
            and payload.keys() <= {"messages", "model", "max_tokens", "grammar"},
            "input",
            "Invalid completion fields",
        )
        self.expected(payload.get("model", self.server.profile["alias"]))
        messages = self.messages(payload["messages"])
        maximum = payload.get("max_tokens", self.settings["max_tokens"])
        require(
            type(maximum) is int and 1 <= maximum <= self.settings["max_tokens"],
            "input",
            "Output exceeds provisioned service limit",
        )
        parameters = {
            "model": self.server.profile["alias"],
            "messages": messages,
            "stream": False,
            "max_tokens": maximum,
            "temperature": 0,
            "seed": 42,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if "grammar" in payload:
            require(
                isinstance(payload["grammar"], str) and 0 < len(payload["grammar"].encode("utf-8")) <= 64000,
                "input",
                "Invalid selection grammar",
            )
            parameters["grammar"] = payload["grammar"]
        return call(
            self.settings["port"],
            self.server.key,
            "POST",
            "/v1/chat/completions",
            parameters,
            timeout=self.settings["request_timeout_seconds"],
        )

    def close(self):
        self.server.close()


class Recognition:
    def __init__(self, configuration):
        sys.path.insert(0, str(LOCAL.parent / "device/audio-process/src"))
        from device_audio.config import Settings
        from device_audio.engine import create_engine

        location = Assets(Catalog()).verify(configuration["model_id"])
        self.settings = Settings(
            _env_file=None,
            model_name=configuration["model_id"],
            model_path=location,
            gpu_enabled=configuration["device"] == "gpu",
            gpu_device_index=configuration["options"]["gpu_device_index"],
            cpu_threads=configuration["options"]["cpu_threads"],
            client_tokens={"manager": configuration["worker_key"]},
            console_output=False,
            recording_enabled=False,
        )
        self.model_id = configuration["model_id"]
        self.engine = create_engine(self.settings)

    def status(self):
        return {"ready": True, "device": self.settings.inference_device, "engine": self.settings.engine_name}

    def infer(self, payload):
        require(
            isinstance(payload, dict)
            and {"wav_base64", "language"} <= payload.keys()
            and payload.keys() <= {"wav_base64", "language", "model"},
            "input",
            "Supply WAV and language",
        )
        require(
            payload.get("model", self.model_id) == self.model_id,
            "model_mismatch",
            "Assigned recognition model differs from the running model",
            409,
        )
        require(payload["language"] in self.settings.supported_languages, "language", "Unsupported language")
        try:
            raw = base64.b64decode(payload["wav_base64"], validate=True)
            require(len(raw) <= 960_128, "input", "Audio exceeds 30 seconds")
            with wave.open(io.BytesIO(raw), "rb") as source:
                require(
                    (
                        source.getnchannels(),
                        source.getsampwidth(),
                        source.getframerate(),
                        source.getcomptype(),
                    )
                    == (1, 2, 16000, "NONE"),
                    "input",
                    "Use mono 16 kHz PCM16 WAV",
                )
                count = source.getnframes()
                require(0 < count <= 480000, "input", "Audio must contain at most 30 seconds")
                pcm = source.readframes(count)
                require(len(pcm) == count * 2, "input", "Audio is truncated")
        except (ValueError, TypeError, wave.Error, EOFError):
            raise ManagerError("input", "Invalid WAV audio") from None
        from device_audio.audio import AudioChunk

        result = self.engine.transcribe(AudioChunk(pcm, 0, count), payload["language"])
        return {"text": result.text, "language": result.language, "segments": result.segments}

    def close(self):
        pass


class Synthesis:
    """Bounded resident voices; all native model loading belongs to this worker."""

    def __init__(self, configuration):
        from collections import OrderedDict

        self.catalog, self.assets = Catalog(), Assets(Catalog())
        self.default = configuration["model_id"]
        self.voices = OrderedDict()
        self._load(self.default)
        model = self.catalog.get(self.default)
        for _ in self.voices[self.default].synthesize(
            "Hello." if model["spec"]["language"] == "en" else "नमस्ते।"
        ):
            pass

    def _load(self, model_id):
        if model_id in self.voices:
            self.voices.move_to_end(model_id)
            return self.voices[model_id]
        from service.voice_runtime import load_voice

        model = self.catalog.get(model_id)
        require(model["capability"] == "tts", "model", "Choose an installed voice")
        location = self.assets.verify(model_id)
        spec = model["spec"]
        if len(self.voices) >= 2:
            self.voices.popitem(last=False)
        voice = load_voice(str(location / spec["model"]), str(location / spec["config"]))
        self.voices[model_id] = voice
        return voice

    def status(self):
        return {"ready": True, "device": "cpu", "engine": "piper"}

    def infer(self, payload):
        require(
            isinstance(payload, dict)
            and "text" in payload
            and payload.keys() <= {"text", "language", "gender", "voice"}
            and isinstance(payload["text"], str)
            and 0 < len(payload["text"].strip()) <= 2000,
            "input",
            "Speech text must contain 1–2000 characters",
        )
        identifier = self.default
        if "voice" in payload:
            require(
                isinstance(payload["voice"], str) and len(payload["voice"]) <= 64,
                "input",
                "Invalid voice selection",
            )
            identifier = "piper-" + payload["voice"]
        model = self.catalog.get(identifier)
        require(model["capability"] == "tts", "model", "Unsupported voice")
        if "language" in payload:
            require(payload["language"] == model["spec"]["language"], "language", "Voice language mismatch")
        if "gender" in payload:
            require(payload["gender"] in {"male", "female"}, "input", "Invalid voice preference")
        voice = self._load(identifier)
        from dataclasses import fields

        from piper import SynthesisConfig

        values = model["spec"].get("synthesis") or {}
        allowed = {field.name for field in fields(SynthesisConfig)} - {"speaker_id"}
        tuning = (
            SynthesisConfig(**{key: value for key, value in values.items() if key in allowed})
            if values
            else None
        )
        output = io.BytesIO()
        with wave.open(output, "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(voice.config.sample_rate)
            total = 0
            for chunk in voice.synthesize(payload["text"], tuning):
                pcm = chunk.audio_int16_bytes
                total += len(pcm)
                require(
                    total <= 4_000_000 and len(pcm) % 2 == 0,
                    "output_limit",
                    "Synthesized audio exceeded its limit",
                )
                target.writeframesraw(pcm)
        return {
            "wav_base64": base64.b64encode(output.getvalue()).decode("ascii"),
            "sample_rate": voice.config.sample_rate,
        }

    def close(self):
        self.voices.clear()


class Worker:
    def __init__(self, config):
        self.config = config
        self.lock = threading.Lock()
        self.admission = threading.Lock()
        self.active = 0
        self.draining = False
        started = time.monotonic()
        self.adapter = {"llm": Llm, "asr": Recognition, "tts": Synthesis}[config["capability"]](config)
        self.load_seconds = time.monotonic() - started
        self.server = None

    def dispatch(self, method, path, payload, _query):
        if method == "GET" and path == "/v1/status":
            with self.admission:
                return {
                    **self.adapter.status(),
                    "model_id": self.config["model_id"],
                    "active": self.active,
                    "draining": self.draining,
                    "load_seconds": round(self.load_seconds, 3),
                }
        if method == "POST" and path in {"/v1/drain", "/v1/resume"}:
            with self.admission:
                self.draining = path == "/v1/drain"
                return {"active": self.active, "draining": self.draining}
        if method == "POST" and path == "/v1/shutdown":
            with self.admission:
                require(self.draining and self.active == 0, "busy", "Worker must drain before shutdown", 409)
            threading.Timer(0.1, self.server.shutdown).start()
            return {"stopping": True}
        if method == "POST" and path in {"/v1/infer", "/v1/inspect"}:
            with self.admission:
                require(not self.draining, "draining", "Service is draining", 409)
                require(self.active == 0, "capacity", "Inference worker is busy", 429)
                self.active = 1
            try:
                with self.lock:
                    if path == "/v1/inspect":
                        require(self.config["capability"] == "llm", "input", "Inspection requires LLM")
                        return self.adapter.inspect(payload)
                    return self.adapter.infer(payload)
            finally:
                with self.admission:
                    self.active = 0
        raise ManagerError("not_found", "Unknown worker operation", 404)


def main():
    config = json.loads(checked(Path(sys.argv[1])).read_text(encoding="utf-8"))
    worker = Worker(config)
    try:
        worker.server = JsonServer(("127.0.0.1", config["port"]), config["worker_key"], worker.dispatch)
        worker.server.serve_forever(poll_interval=0.1)
    finally:
        if worker.server:
            worker.server.server_close()
        worker.adapter.close()


if __name__ == "__main__":
    main()
