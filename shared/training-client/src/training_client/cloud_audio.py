"""One utterance through PMS; provider keys never enter the desktop process."""

import io
import time
import wave
from uuid import uuid4

import httpx

from .capture import block_levels
from .pms_client import BUSY_CODES, ClientError, retry_busy


async def transcribe(settings, pms, frames, emit):
    if not pms.model_route:
        raise ClientError("Ask Platform Admin to assign models to this device")
    pcm = bytearray()
    voiced = False
    async for frame in frames:
        if len(frame) % 2 or len(pcm) + len(frame) > settings.max_question_seconds * 32000:
            raise ClientError("Question exceeds the configured audio limit")
        pcm.extend(frame)
        # A coarse "was anything said at all" check, not endpointing: the capture gate already
        # decided where the question ended. One RMS implementation, shared with capture.
        if block_levels(frame)[0] >= settings.energy_threshold:
            voiced = True
    # Release the microphone before any network attempt or retry wait.
    await frames.aclose()
    if not pcm or not voiced:
        return {"text": "", "asr_finalize_ms": 0}
    began = time.monotonic()
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        audio.writeframes(pcm)
    pms.last_request = None
    emit("state", "Transcribing with " + settings.audio_model)
    data = output.getvalue()
    parameters = {
        "profile_revision_id": pms.model_route["profile_revision_id"],
        "configuration_hash": pms.model_route["configuration_hash"],
        "language": settings.language,
    }

    async def submit():
        pms.last_speech_request = str(uuid4())
        return await pms.json(
            "POST",
            pms.organization_base + "/speech/transcriptions",
            params={**parameters, "request_key": pms.last_speech_request},
            headers={"Content-Type": "audio/wav"},
            content=data,
        )

    try:
        result = await retry_busy(
            submit,
            emit,
            "Speech service",
            "audio",
            rounds=settings.speech_retry_rounds,
            round_pause_seconds=settings.speech_retry_round_pause_seconds,
        )
    except (httpx.HTTPError, TimeoutError):
        pms.recovery_request = ("speech", pms.last_speech_request)
        raise ClientError(
            "Speech connection interrupted; use Check last request before submitting again"
        ) from None
    except (ClientError, ValueError) as error:
        if not isinstance(error, ClientError) or error.code not in BUSY_CODES:
            pms.recovery_request = ("speech", pms.last_speech_request)
        raise
    if (
        result.get("request_key") != pms.last_speech_request
        or result.get("status") != "succeeded"
        or not isinstance(result.get("result"), dict)
    ):
        pms.recovery_request = ("speech", pms.last_speech_request)
        raise ClientError("Transcription did not complete; check its request status before submitting again")
    transcript = result["result"]
    if not isinstance(transcript.get("text"), str) or len(transcript["text"]) > 8000:
        pms.recovery_request = ("speech", pms.last_speech_request)
        raise ClientError("PMS returned an invalid transcript")
    transcript["asr_finalize_ms"] = round((time.monotonic() - began) * 1000)
    transcript["recording_status"] = result.get("recording_status")
    transcript["request_key"] = pms.last_speech_request
    emit("transcript", transcript["text"])
    if result.get("recording_status") == "failed":
        emit("state", "Transcript ready; audio recording could not be saved")
    return transcript
