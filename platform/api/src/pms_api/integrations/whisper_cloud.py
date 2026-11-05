"""Azure OpenAI Whisper (v1 or explicit deployment API version): one bounded file, no automatic POST replay."""

import asyncio
import io
import time
import wave
from types import SimpleNamespace
from urllib.parse import quote

import httpx

from pms_api.core.common import AppError, require
from pms_api.integrations.llm.client import LLMClient, LLMError, credential_headers, object_json
from pms_api.integrations.llm.policy import configured_endpoint


def wav_info(data: bytes, max_seconds: int):
    try:
        require(
            len(data) <= max_seconds * 32000 + 4096,
            "audio_too_large",
            "Audio exceeds duration/size limit",
            413,
        )
        with wave.open(io.BytesIO(data), "rb") as audio:
            require(
                (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype())
                == (1, 2, 16000, "NONE"),
                "invalid_audio",
                "Use mono 16 kHz PCM16 WAV",
            )
            frames = audio.getnframes()
            require(
                0 < frames <= max_seconds * 16000,
                "audio_duration_limit",
                "Audio duration exceeds policy",
                413,
            )
            require(len(audio.readframes(frames)) == frames * 2, "invalid_audio", "Audio file is truncated")
        return max(1, (frames * 1000 + 15999) // 16000)
    except (wave.Error, EOFError, OSError):
        raise AppError(422, "invalid_audio", "Supply a valid PCM WAV utterance") from None


def speech_endpoint(connection, settings):
    return configured_endpoint(
        SimpleNamespace(base_url=connection.settings["endpoint"], provider="azure_openai"),
        settings,
        dispatch=True,
    )


async def transcribe(client, settings, connection, key, data, language, request_id):
    if connection.settings.get("model") == "gpt-realtime-whisper":
        from pms_api.integrations.realtime_whisper import run

        return await run(settings, connection, key, data, language)
    endpoint = speech_endpoint(connection, settings)
    require(language in {"en", "hi", "auto"}, "unsupported_language", "Use English, Hindi or auto")
    deployment = connection.settings["deployment"]
    version = connection.settings.get("api_version")
    if version:
        url = (
            endpoint.removesuffix("/v1")
            + "/deployments/"
            + quote(deployment, safe="")
            + "/audio/transcriptions"
        )
        params = {"api-version": version}
        fields = {"response_format": "json"}
    else:
        url, params = endpoint + "/audio/transcriptions", None
        fields = {"model": deployment, "response_format": "json"}
    if language != "auto":
        fields["language"] = language
    started = time.monotonic()
    try:
        async with asyncio.timeout(settings.provider_timeout_seconds):
            async with client.client.stream(
                "POST",
                url,
                params=params,
                headers={**credential_headers(key, "azure_openai"), "X-Client-Request-Id": str(request_id)},
                data=fields,
                files={"file": ("utterance.wav", data, "audio/wav")},
            ) as response:
                raw = bytearray()
                async for block in response.aiter_bytes():
                    raw.extend(block)
                    if len(raw) > 65536:
                        raise LLMError("speech_response_limit")
                # Bounded error parsing, without exposing provider messages or credentials.
                checked = httpx.Response(response.status_code, content=bytes(raw))
                client.check(checked)
                result = object_json(bytes(raw))
                text = result.get("text")
                require(
                    isinstance(text, str) and len(text) <= 8000,
                    "speech_invalid_response",
                    "Transcription response is invalid",
                    502,
                )
                return {
                    "text": text.strip(),
                    "language": language,
                    "model": connection.settings["deployment"],
                    "provider": "azure_openai",
                    "provider_ms": round((time.monotonic() - started) * 1000),
                }
    except TimeoutError:
        raise AppError(
            504, "speech_submission_unknown", "Transcription timed out; it was not replayed"
        ) from None
    except httpx.HTTPError:
        raise AppError(
            502, "speech_submission_unknown", "Transcription connection failed; it was not replayed"
        ) from None


async def speech_health(client, settings, connection, key):
    endpoint = speech_endpoint(connection, settings)
    if connection.settings.get("model") == "gpt-realtime-whisper":
        from pms_api.integrations.realtime_whisper import run

        await run(settings, connection, key)
    else:
        await client.health(endpoint, connection.settings["deployment"], key, provider="azure_openai")


class AzureWhisperProvider:
    def __init__(self, settings, connection, credentials):
        self.settings, self.connection, self.credentials = settings, connection, credentials

    async def validate(self, operation, sample=False):
        require(operation == "audio.transcribe", "unsupported_operation", "Whisper only transcribes audio")
        client = LLMClient(
            self.settings.provider_timeout_seconds,
            health_timeout=self.settings.health_timeout_seconds,
            health_attempts=self.settings.health_attempts,
        )
        try:
            if sample:
                output = io.BytesIO()
                with wave.open(output, "wb") as audio:
                    audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                    audio.writeframes(b"\x00\x00" * 4000)
                await transcribe(
                    client,
                    self.settings,
                    self.connection,
                    self.credentials["api_key"],
                    output.getvalue(),
                    "en",
                    "configuration-validation",
                )
            else:
                await speech_health(client, self.settings, self.connection, self.credentials["api_key"])
            return True
        finally:
            await client.close()

    async def submit(self, run_id, operation, request, section):
        # Interactive speech has its own fenced admission/recording path. Do not
        # accidentally send a queued signed URL as an audio file or change semantics.
        raise AppError(
            422, "interactive_speech_required", "Use the interactive speech endpoint for Azure Whisper"
        )
