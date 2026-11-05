"""Small reference sender. Only needs websockets; the Pi does not install Whisper."""

import argparse
import asyncio
import json
import os
import ssl
import sys
import time
import wave
from pathlib import Path
from urllib.parse import urlsplit

from websockets.asyncio.client import connect


async def stream(args: argparse.Namespace) -> None:
    io_seconds = getattr(args, "io_timeout", 5)
    completion_seconds = getattr(args, "completion_timeout", 310)
    if not 0.01 <= io_seconds <= 60 or not 0.01 <= completion_seconds <= 1800:
        raise ValueError("invalid sender timeouts")
    token = os.environ.get("AUDIO_CLIENT_TOKEN", "")
    if not token:
        raise SystemExit("Set AUDIO_CLIENT_TOKEN without putting it on the command line.")
    uri = urlsplit(args.url)
    if uri.scheme not in {"ws", "wss"} or uri.username or uri.password or uri.query or uri.fragment:
        raise SystemExit("Use a ws/wss URL without credentials, query or fragment.")
    if uri.scheme == "ws" and uri.hostname not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("Wi-Fi connections require wss and certificate verification.")
    context = ssl.create_default_context(cafile=str(args.ca_file) if args.ca_file else None)
    with wave.open(str(args.audio), "rb") as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
            raise SystemExit("Audio must be mono 16 kHz PCM16 WAV.")
        async with connect(
            args.url,
            ssl=context if uri.scheme == "wss" else None,
            additional_headers={"Authorization": "Bearer " + token},
            max_size=256000,
            compression=None,
            proxy=None,
            open_timeout=io_seconds,
            close_timeout=io_seconds,
        ) as ws:
            await asyncio.wait_for(
                ws.send(json.dumps({"type": "start", "language": args.language})), io_seconds
            )
            ready = json.loads(await asyncio.wait_for(ws.recv(), io_seconds))
            if (
                not isinstance(ready, dict)
                or ready.get("type") != "ready"
                or not isinstance(ready.get("session_id"), str)
                or type(ready.get("max_frame_bytes")) is not int
                or not 2 <= ready["max_frame_bytes"] <= 32000
            ):
                raise RuntimeError("server did not accept stream")
            print(json.dumps(ready, ensure_ascii=False), flush=True)
            finished = asyncio.Event()
            completed = asyncio.Event()
            sent_bytes = 0

            async def send_audio() -> None:
                nonlocal sent_bytes
                began = time.monotonic()
                frame_samples = min(1600, ready["max_frame_bytes"] // 2)
                while pcm := audio.readframes(frame_samples):
                    await asyncio.sleep(max(0, began + sent_bytes / 32000 - time.monotonic()))
                    await asyncio.wait_for(ws.send(pcm), io_seconds)
                    sent_bytes += len(pcm)
                # Preserve the last frame's duration before asking for final output.
                await asyncio.sleep(max(0, began + sent_bytes / 32000 - time.monotonic()))
                finished.set()
                await asyncio.wait_for(ws.send('{"type":"finish"}'), io_seconds)

            async def receive_events() -> None:
                async for raw in ws:
                    event = json.loads(raw)
                    if not isinstance(event, dict):
                        raise RuntimeError("invalid server event")
                    if event.get("type") == "transcript":
                        print(event["text"], flush=True)
                    elif event.get("type") in {"error", "delivery", "complete"}:
                        print(json.dumps(event, ensure_ascii=False), flush=True)
                    if event.get("type") == "error":
                        raise RuntimeError("stream rejected")
                    if event.get("type") == "complete":
                        if not finished.is_set() or event.get("session_id") != ready["session_id"]:
                            raise RuntimeError("invalid completion")
                        completed.set()
                        return
                raise RuntimeError("connection closed before completion")

            async def completion_deadline() -> None:
                await finished.wait()
                await asyncio.wait_for(completed.wait(), completion_seconds)

            async with asyncio.TaskGroup() as group:
                group.create_task(send_audio())
                group.create_task(receive_events())
                group.create_task(completion_deadline())


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8765/v1/audio/stream")
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--language", choices=("auto", "hi", "en"), default="auto")
    parser.add_argument("--ca-file", type=Path)
    parser.add_argument("--io-timeout", type=float, default=5, help="connection/start/send deadline")
    parser.add_argument(
        "--completion-timeout", type=float, default=310, help="wait after finish for ASR completion"
    )
    try:
        asyncio.run(stream(parser.parse_args()))
    except Exception:
        parser.exit(
            1, "Audio sender failed; check the connection and session receipt before starting again.\n"
        )


if __name__ == "__main__":
    main()
