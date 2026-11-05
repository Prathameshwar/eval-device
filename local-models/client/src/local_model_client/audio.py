"""Recognition and synthesis over the manager; no physical audio or native engines."""

import base64
import io
import wave
from types import SimpleNamespace

from .connection import ConnectionError


def encode(pcm):
    if not pcm or len(pcm) % 2 or len(pcm) > 960000:
        raise ConnectionError("Use at most 30 seconds of mono PCM16 audio", "input", 422)
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)
    return base64.b64encode(output.getvalue()).decode("ascii")


async def recognition_ready(connection, model, language):
    info = connection.remember(await connection.async_request("GET", "/v1/capabilities"))
    service = info["services"].get("asr", {})
    if service.get("ready") is not True or service.get("state") != "Ready":
        raise ConnectionError("Start speech recognition in Manage Local Models", "not_running", 409)
    if service.get("model_id") != model:
        raise ConnectionError(
            "Assigned recognition model differs from Manage Local Models", "model_mismatch", 409
        )
    from training_contracts.languages.speech_models import recognition_languages

    if language not in recognition_languages(model):
        raise ConnectionError("Recognition model does not support this language", "language", 422)
    return service


async def transcribe(connection, pcm, model, language):
    if getattr(connection, "stream_audio", False):
        from .streams import audio

        result = await audio(connection, pcm, model, language)
    else:
        result = await connection.async_request(
            "POST", "/v1/infer/asr", {"model": model, "language": language, "wav_base64": encode(pcm)}
        )
    return validate_transcript(result, language)


def validate_transcript(result, language):
    if not isinstance(result, dict):
        raise ConnectionError("Invalid recognition result", "invalid_response")
    text = result.get("text")
    if not isinstance(text, str) or len(text) > 8000 or result.get("language") not in {language, None}:
        raise ConnectionError("Invalid recognition result", "invalid_response")
    return result


class RemoteVoice:
    def __init__(self, connection, key, language, gender):
        self.connection, self.key, self.language, self.gender = connection, key, language, gender
        self.config = SimpleNamespace(sample_rate=22050)

    def synthesize(self, text, _tuning=None):
        result = self.connection.request(
            "POST",
            "/v1/infer/tts",
            {"text": text, "language": self.language, "gender": self.gender, "voice": self.key},
        )
        try:
            encoded = result["wav_base64"]
            if not isinstance(encoded, str) or len(encoded) > 5_400_000:
                raise ValueError()
            raw = base64.b64decode(encoded, validate=True)
            with wave.open(io.BytesIO(raw), "rb") as wav:
                rate = wav.getframerate()
                if (
                    wav.getnchannels() != 1
                    or wav.getsampwidth() != 2
                    or wav.getcomptype() != "NONE"
                    or not 8000 <= rate <= 48000
                    or rate != result["sample_rate"]
                    or not 0 < wav.getnframes() * 2 <= 4_000_000
                ):
                    raise ValueError()
                pcm = wav.readframes(wav.getnframes())
                if len(pcm) != wav.getnframes() * 2:
                    raise ValueError()
            self.config.sample_rate = rate
        except (KeyError, ValueError, TypeError, wave.Error, EOFError):
            raise ConnectionError("Invalid synthesized audio", "invalid_response") from None
        for start in range(0, len(pcm), 32768):
            yield SimpleNamespace(audio_int16_bytes=pcm[start : start + 32768])
