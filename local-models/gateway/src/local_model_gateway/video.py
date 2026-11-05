"""The platform's local video.motion operation, executed on the remote host only."""

from training_contracts.media import jpeg_dimensions

from .security import Rejected


def dimensions(raw):
    """Read JPEG dimensions before allocating a decoder output buffer."""
    try:
        return jpeg_dimensions(raw)
    except ValueError:
        raise Rejected("input", 422) from None


class Motion:
    def __init__(self):
        self.previous = None
        self.frames = self.moving = 0
        self.maximum = 0.0

    def accept(self, raw):
        import cv2
        import numpy

        width, height = dimensions(raw)
        frame = cv2.imdecode(numpy.frombuffer(raw, dtype=numpy.uint8), cv2.IMREAD_GRAYSCALE)
        if frame is None or frame.shape != (height, width):
            raise Rejected("input", 422)
        frame = cv2.resize(frame, (160, 120))
        frame = cv2.GaussianBlur(frame, (5, 5), 0)
        if self.previous is not None:
            fraction = float(numpy.count_nonzero(cv2.absdiff(frame, self.previous) >= 25)) / frame.size
            self.maximum = max(self.maximum, fraction)
            self.moving += int(fraction >= 0.02)
        self.previous = frame
        self.frames += 1

    def result(self):
        if self.frames < 2:
            raise Rejected("input", 422)
        return {
            "operation": "video.motion",
            "engine": "opencv_motion",
            "frames": self.frames,
            "motion_detected": self.moving > 0,
            "moving_frames": self.moving,
            "maximum_changed_fraction": round(self.maximum, 4),
        }
