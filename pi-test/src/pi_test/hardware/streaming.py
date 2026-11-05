"""Send bounded low-resolution camera frames without owning capture or the archive."""

import asyncio
import time


async def frames(camera, seconds=30):
    import cv2
    import numpy

    deadline = time.monotonic() + seconds
    last_frame = time.monotonic()
    while camera.busy and time.monotonic() < deadline:
        _, preview = camera.poll()
        if preview:
            pixels = cv2.imdecode(numpy.frombuffer(preview, dtype=numpy.uint8), cv2.IMREAD_COLOR)
            if pixels is None:
                raise ValueError("Invalid preview frame")
            ok, jpeg = cv2.imencode(".jpg", pixels, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not ok:
                raise ValueError("Cannot encode preview frame")
            last_frame = time.monotonic()
            yield jpeg.tobytes()
        elif time.monotonic() - last_frame > 3:
            raise ValueError("Camera stopped producing frames")
        await asyncio.sleep(0.2)
    if not camera.busy and time.monotonic() < deadline:
        raise ValueError("Camera stopped before the clip completed")


async def video(camera, connection):
    from local_model_client.streams import transmit

    return await transmit(connection, "video", {"format": "jpeg", "max_seconds": 30}, frames(camera))
