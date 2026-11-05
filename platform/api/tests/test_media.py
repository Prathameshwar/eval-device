import io
import shutil
import subprocess
import wave

import pytest
from test_unit import settings

from pms_api.core.common import AppError
from pms_api.integrations.media import inspect_media
from pms_api.modules.schemas import Policy


def wav_bytes(seconds=1):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0" * (32000 * seconds))
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_actual_media_inspection_and_protocol_rejection(tmp_path):
    if not shutil.which("ffprobe"):
        pytest.skip("ffprobe is required for media integration verification")
    policy = Policy().model_dump()
    config = settings()
    result = await inspect_media(wav_bytes(), "wav", config, policy)
    assert result["duration_seconds"] == 1 and result["has_audio"] and not result["has_video"]
    with pytest.raises(AppError):
        await inspect_media(b"#EXTM3U\nhttp://127.0.0.1/private", "mp4", config, policy)
    with pytest.raises(AppError):
        await inspect_media(wav_bytes(), "mp4", config, policy)
    if shutil.which("ffmpeg"):
        video = tmp_path / "clip.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=160x120:r=10",
                "-t",
                "1",
                "-an",
                "-c:v",
                "mpeg4",
                str(video),
            ],
            check=True,
            timeout=30,
        )
        info = await inspect_media(video.read_bytes(), "mp4", config, policy)
        assert info["has_video"] and not info["has_audio"]
