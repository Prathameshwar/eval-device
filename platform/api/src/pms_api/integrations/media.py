import asyncio
import json
import subprocess
import tempfile
from pathlib import Path

from pms_api.core.common import AppError, require


async def inspect_media(data: bytes, extension: str, settings, policy: dict) -> dict:
    require(
        0 < len(data) <= policy["capture_limits"]["max_upload_bytes"],
        "media_too_large",
        "Media is empty or exceeds policy",
        413,
    )
    signatures = {
        "wav": data[:4] == b"RIFF" and data[8:12] == b"WAVE",
        "mp4": data[4:8] == b"ftyp",
        "flac": data[:4] == b"fLaC",
        "ogg": data[:4] == b"OggS",
        "mp3": data[:3] == b"ID3" or (len(data) > 1 and data[0] == 255 and data[1] & 224 == 224),
    }
    require(
        signatures.get(extension, False),
        "invalid_media",
        "Container does not match the requested media format",
    )
    # ffprobe validates the actual container/streams rather than trusting HTTP metadata.
    with tempfile.TemporaryDirectory(prefix="pms-media-") as temporary:
        path = Path(temporary) / ("input." + extension)
        await asyncio.to_thread(path.write_bytes, data)
        try:
            process = await asyncio.to_thread(
                subprocess.run,
                [
                    settings.ffprobe_path,
                    "-protocol_whitelist",
                    "file,pipe",
                    "-format_whitelist",
                    "wav,mp3,mov,flac,ogg",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration,format_name:stream=codec_type,width,height,avg_frame_rate",
                    "-of",
                    "json",
                    str(path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
        except FileNotFoundError as error:
            raise AppError(
                503, "media_inspector_unavailable", "Install ffprobe before enabling media processing"
            ) from error
        except subprocess.TimeoutExpired:
            raise AppError(422, "invalid_media", "Media inspection timed out") from None
        require(
            process.returncode == 0 and len(process.stdout) <= 1048576,
            "invalid_media",
            "Media could not be decoded",
        )
        output = process.stdout
        try:
            info = json.loads(output)
            duration = float(info["format"]["duration"])
        except (ValueError, KeyError, TypeError) as error:
            raise AppError(422, "invalid_media", "Media must have a finite duration") from error
        import math

        require(math.isfinite(duration) and duration > 0, "invalid_media", "Invalid media duration")
        videos = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
        audio = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
        limit = policy["capture_limits"]["max_video_seconds" if videos else "max_audio_seconds"]
        require(duration <= limit, "capture_limit", "Media duration exceeds policy")
        for stream in videos:
            require(
                stream.get("width", 0) <= policy["capture_limits"]["max_width"]
                and stream.get("height", 0) <= policy["capture_limits"]["max_height"],
                "capture_limit",
                "Video dimensions exceed policy",
            )
            numerator, denominator = stream.get("avg_frame_rate", "0/1").split("/")
            fps = float(numerator) / max(float(denominator), 1)
            require(
                fps <= policy["capture_limits"]["max_fps"], "capture_limit", "Video frame rate exceeds policy"
            )
        require(bool(videos or audio), "invalid_media", "No supported media stream found")
        return {
            "duration_seconds": duration,
            "has_video": bool(videos),
            "has_audio": bool(audio),
            "size": len(data),
            "format": info["format"].get("format_name"),
        }
