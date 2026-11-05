"""Send bounded microphone frames to the central inference manager."""

import time
from uuid import uuid4

from local_model_client import Connection, ConnectionError
from local_model_client.audio import recognition_ready
from local_model_client.audio import transcribe as recognize

from .pms_client import ClientError


def connection(settings):
    if settings.inference_url:
        from local_model_client.remote import RemoteConnection

        if not settings.inference_host_id:
            raise ClientError("Configure the remote inference host identity")
        return RemoteConnection(
            settings.inference_url,
            settings.inference_host_id,
            settings.pms_url,
            settings.pms_token.get_secret_value(),
            ca_file=settings.inference_ca_file,
            timeout=settings.timeout_seconds,
            journal_dir=settings.app_root / "inference-requests",
        )
    return Connection(
        state=settings.local_models_state_dir,
        port=settings.local_models_port,
        key=settings.local_models_key.get_secret_value() or None,
        timeout=settings.timeout_seconds,
        capabilities=settings.local_models_capabilities,
        inherit_defaults=False,
    )


def failure(error):
    return ClientError(
        str(error), code="speech_busy" if error.status == 429 else "local_models_" + error.code
    )


async def preflight(settings, *, inference=None):
    try:
        return await recognition_ready(
            inference or connection(settings), settings.audio_model, settings.language
        )
    except ConnectionError as error:
        raise failure(error) from None


async def transcribe(settings, frames, emit, *, inference=None):
    transport = inference or connection(settings)
    if getattr(transport, "remote", False) and getattr(transport, "stream_audio", False):
        from local_model_client.streams import audio_frames

        ended = None
        size = 0

        async def measured():
            nonlocal ended, size
            try:
                async for frame in frames:
                    size += len(frame)
                    yield frame
                ended = time.perf_counter()
            finally:
                await frames.aclose()

        emit("state", "Streaming utterance")
        try:
            result = await audio_frames(
                transport,
                measured(),
                settings.audio_model,
                settings.language,
                max_seconds=settings.max_question_seconds,
            )
        except ConnectionError as error:
            raise failure(error) from None
        emit("transcript", result["text"])
        return {
            "text": result["text"],
            "session_id": str(uuid4()),
            "bytes": size,
            "asr_finalize_ms": round((time.perf_counter() - ended) * 1000) if ended else 0,
        }
    pcm = bytearray()
    try:
        async for frame in frames:
            if not isinstance(frame, bytes) or not frame or len(frame) % 2:
                raise ClientError("Invalid microphone frame")
            pcm.extend(frame)
            if len(pcm) > min(settings.max_question_seconds, 30) * 32000:
                raise ClientError("Audio duration limit exceeded; question was not submitted")
    finally:
        await frames.aclose()
    ended = time.perf_counter()
    emit("state", "Transcribing")
    try:
        result = await recognize(transport, bytes(pcm), settings.audio_model, settings.language)
    except ConnectionError as error:
        raise failure(error) from None
    emit("transcript", result["text"])
    return {
        "text": result["text"],
        "session_id": str(uuid4()),
        "asr_finalize_ms": round((time.perf_counter() - ended) * 1000),
        "bytes": len(pcm),
    }
