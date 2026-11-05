"""Development sender for a local MJPEG Matroska recording, paced over WebSocket.

No camera adapter, cloud connection, audio track, live analysis or automatic replay.
"""

import argparse
import asyncio
import json
import ssl
from pathlib import Path
from urllib.parse import urlsplit

import av
from websockets.asyncio.client import connect

from device_video.config import Settings
from device_video.protocol import Frame
from device_video.sender import Limits, send_frames


async def stream_file(
    source: Path, url: str, client_id: str, ca_file: str | None, limits: Limits | None = None
) -> None:
    limits = limits or Limits()
    target = urlsplit(url)
    if (
        target.scheme not in {"ws", "wss"}
        or target.username
        or target.password
        or target.query
        or target.fragment
        or (target.scheme == "ws" and target.hostname not in {"localhost", "127.0.0.1", "::1"})
    ):
        raise ValueError("use loopback ws:// or a trusted wss:// URL without credentials/query")
    settings = Settings()
    token = settings.client_tokens[client_id].get_secret_value()
    context = ssl.create_default_context(cafile=ca_file) if target.scheme == "wss" else None
    with source.open("rb") as local_file, av.open(local_file, format="matroska") as container:
        video = container.streams.video[0]
        if video.codec_context.name != "mjpeg":
            raise ValueError("sender requires an MJPEG Matroska file")
        fps = round(video.average_rate or video.base_rate or 10)
        async with connect(
            url,
            additional_headers={"Authorization": f"Bearer {token}"},
            ssl=context,
            compression=None,
            max_size=16384,
            max_queue=2,
            open_timeout=5,
            close_timeout=5,
            ping_interval=20,
            ping_timeout=20,
            proxy=None,
        ) as socket:
            await asyncio.wait_for(
                socket.send(
                    json.dumps(
                        dict(
                            type="start",
                            version=1,
                            format="jpeg",
                            width=video.width,
                            height=video.height,
                            fps=fps,
                        )
                    )
                ),
                limits.ack_seconds,
            )
            ready = json.loads(await asyncio.wait_for(socket.recv(), limits.ack_seconds))
            if ready.get("type") != "ready":
                raise RuntimeError("receiver did not accept recording")
            print(json.dumps(ready), flush=True)

            def frames():
                sequence, origin = 0, None
                for packet in container.demux(video=0):
                    if not packet.size:
                        continue
                    timestamp = (
                        round(float(packet.pts * packet.time_base) * 1e6)
                        if packet.pts is not None
                        else round(sequence * 1e6 / fps)
                    )
                    origin = timestamp if origin is None else origin
                    yield Frame(sequence, timestamp - origin, bytes(packet))
                    sequence += 1

            complete = await send_frames(
                socket, frames(), ready["recording_id"], ready["max_frame_bytes"], limits
            )
            print(json.dumps(complete), flush=True)
            if complete["recording"]["status"] == "incomplete":
                raise RuntimeError(
                    "recording is incomplete; query its receipt before starting another session"
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--url", default="ws://127.0.0.1:8766/v1/video/stream")
    parser.add_argument("--client-id", default="pi-1")
    parser.add_argument("--ca-file")
    parser.add_argument(
        "--max-in-flight", type=int, default=4, help="bounded unacknowledged frame window (1-16)"
    )
    parser.add_argument(
        "--ack-timeout", type=float, default=5, help="deadline for the oldest unacknowledged frame"
    )
    parser.add_argument("--completion-timeout", type=float, default=15)
    parser.add_argument(
        "--max-lag", type=float, default=2, help="stop instead of building a stale frame backlog"
    )
    args = parser.parse_args()
    try:
        limits = Limits(args.max_in_flight, args.ack_timeout, args.completion_timeout, args.max_lag)
        asyncio.run(stream_file(args.input, args.url, args.client_id, args.ca_file, limits))
    except Exception:
        parser.exit(
            1, "Video sender failed; check input format, authenticated TLS connection and recording status.\n"
        )


if __name__ == "__main__":
    main()
