"""One admitted utterance per Azure transcription session; no uncertain audio replay."""

import asyncio
import base64
import io
import ipaddress
import json
import logging
import socket
import ssl
import sys
import time
import wave
from array import array
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus, WebSocketException

from pms_api.core.common import AppError, require
from pms_api.integrations.llm.client import LLMError

MODEL = "gpt-realtime-whisper"
# WebSocket debug logs include authentication headers and audio. Never propagate them.
TRANSPORT_LOG = logging.Logger("pms.realtime.private", level=logging.CRITICAL)
TRANSPORT_LOG.addHandler(logging.NullHandler())
TRANSPORT_LOG.propagate = False


class NoRedirect(connect):
    def process_redirect(self, exc: Exception) -> Exception | str:
        return exc


@asynccontextmanager
async def websocket(endpoint, key):
    """Pin an allowed public DNS address; retain the original TLS hostname and Host header."""
    host = urlsplit(endpoint).hostname
    loop = asyncio.get_running_loop()
    addresses = await loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    require(bool(addresses), "llm_endpoint_invalid", "No public provider address", 422)
    for _, _, _, _, address in addresses:
        ip = ipaddress.ip_address(address[0])
        require(
            ip.is_global and not ip.is_multicast and not ip.is_reserved,
            "llm_endpoint_invalid",
            "Provider address must be public",
            422,
        )
    family, kind, protocol, _, address = addresses[0]
    sock = socket.socket(family, kind, protocol)
    sock.setblocking(False)
    try:
        await loop.sock_connect(sock, address)
        async with NoRedirect(
            endpoint.replace("https://", "wss://", 1) + "/realtime?intent=transcription",
            sock=sock,
            ssl=ssl.create_default_context(),
            server_hostname=host,
            additional_headers={"api-key": key},
            proxy=None,
            open_timeout=10,
            close_timeout=1,
            max_size=65536,
            max_queue=16,
            compression=None,
            logger=TRANSPORT_LOG,
        ) as ws:
            yield ws
    finally:
        sock.close()


def pcm24(data):
    # Admission already verifies the WAV; retain a bound when this adapter is called directly.
    from pms_api.integrations.whisper_cloud import wav_info

    wav_info(data, 60)
    with wave.open(io.BytesIO(data), "rb") as audio:
        samples = array("h", audio.readframes(audio.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    output = array("h")
    for index in range((len(samples) * 3 + 1) // 2):
        left, fraction = divmod(index * 2, 3)
        right = min(left + 1, len(samples) - 1)
        output.append(round((samples[left] * (3 - fraction) + samples[right] * fraction) / 3))
    if sys.byteorder != "little":
        output.byteswap()
    return output.tobytes()


class Events:
    def __init__(self, ws):
        self.ws, self.count, self.size = ws, 0, 0

    async def next(self):
        raw = await self.ws.recv()
        self.count += 1
        self.size += len(raw)
        require(
            self.count <= 2048 and self.size <= 1048576,
            "speech_response_limit",
            "Transcription response exceeded its bound",
            502,
        )
        value = json.loads(raw)
        require(
            isinstance(value, dict) and isinstance(value.get("type"), str),
            "speech_invalid_response",
            "Invalid transcription event",
            502,
        )
        return value


def provider_error(value):
    error = value.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    if not isinstance(code, str):
        code = None
    if code in {"rate_limit_exceeded", "server_error", "service_unavailable"}:
        raise LLMError("speech_busy", 503)
    if code in {"invalid_api_key", "authentication_error"}:
        raise LLMError("llm_credentials_rejected", 502)
    if code in {"model_not_found", "DeploymentNotFound"}:
        raise LLMError("llm_deployment_not_found", 502)
    raise LLMError("llm_invalid_parameters", 422)


async def configure(events, deployment, language):
    transcription = {"model": deployment, "delay": "low"}
    if language != "auto":
        transcription["language"] = language
    await events.ws.send(
        json.dumps(
            {
                "type": "session.update",
                "session": {
                    "type": "transcription",
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcm", "rate": 24000},
                            "turn_detection": None,
                            "transcription": transcription,
                        }
                    },
                },
            }
        )
    )
    while True:
        event = await events.next()
        if event["type"] == "error":
            provider_error(event)
        if event["type"] == "session.updated":
            session = event.get("session", {})
            require(
                isinstance(session, dict) and session.get("type") == "transcription",
                "speech_invalid_response",
                "Wrong realtime session type",
                502,
            )
            return


async def result(events):
    item_id = None
    committed = False
    while True:
        event = await events.next()
        kind = event["type"]
        if kind == "error" or kind.endswith(".failed"):
            # After any audio was sent, even a rate-limit error is not safe to replay.
            raise AppError(502, "speech_submission_unknown", "Transcription did not complete; no replay")
        if kind == "input_audio_buffer.committed" or kind.startswith(
            "conversation.item.input_audio_transcription."
        ):
            current = event.get("item_id")
            require(
                isinstance(current, str)
                and 0 < len(current) <= 200
                and (item_id is None or item_id == current),
                "speech_invalid_response",
                "Transcription item did not match",
                502,
            )
            item_id = current
        if kind == "input_audio_buffer.committed":
            committed = True
        if kind == "conversation.item.input_audio_transcription.completed":
            text = event.get("transcript")
            require(
                committed and isinstance(text, str) and len(text) <= 8000,
                "speech_invalid_response",
                "Invalid final transcript",
                502,
            )
            return text.strip()


async def run(settings, connection, key, data=None, language="auto"):
    from pms_api.integrations.whisper_cloud import speech_endpoint

    endpoint = speech_endpoint(connection, settings)
    deployment = connection.settings["deployment"]
    require(language in {"en", "hi", "auto"}, "unsupported_language", "Use English, Hindi or auto")
    pcm = await asyncio.to_thread(pcm24, data) if data is not None else None
    started = time.monotonic()
    submitted = False
    timeout = settings.provider_timeout_seconds if pcm is not None else settings.health_timeout_seconds
    try:
        async with asyncio.timeout(timeout):
            async with websocket(endpoint, key) as ws:
                events = Events(ws)
                await configure(events, deployment, language)
                if pcm is None:
                    return None  # Authenticated session configuration, no audio/inference.
                submitted = True  # Sending can fail after bytes leave this process.
                async with asyncio.TaskGroup() as group:
                    pending = group.create_task(result(events))
                    for offset in range(0, len(pcm), 4800):
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "input_audio_buffer.append",
                                    "audio": base64.b64encode(pcm[offset : offset + 4800]).decode(),
                                }
                            )
                        )
                    await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                return {
                    "text": pending.result(),
                    "language": language,
                    "model": deployment,
                    "provider": "azure_openai",
                    "provider_ms": round((time.monotonic() - started) * 1000),
                }
    except InvalidStatus as error:
        status = error.response.status_code
        if status in {429, 500, 502, 503, 504}:
            raise LLMError("speech_busy", 503) from None
        if status in {401, 403}:
            raise LLMError("llm_credentials_rejected", 502) from None
        raise LLMError("llm_invalid_parameters", 422) from None
    except (
        TimeoutError,
        OSError,
        WebSocketException,
        ValueError,
        RecursionError,
        AppError,
        ExceptionGroup,
    ) as error:
        if submitted:
            raise AppError(
                502, "speech_submission_unknown", "Transcription interrupted; audio was not replayed"
            ) from None
        if isinstance(error, AppError):
            raise
        if isinstance(error, (ValueError, RecursionError, ExceptionGroup)):
            raise LLMError("speech_invalid_response", 502) from None
        raise LLMError("speech_busy", 503) from None
