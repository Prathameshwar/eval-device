"""Check compressed image headers before allocating decoder output buffers."""


def jpeg_dimensions(raw, *, max_width=640, max_height=480):
    if not isinstance(raw, bytes) or not raw.startswith(b"\xff\xd8") or not raw.endswith(b"\xff\xd9"):
        raise ValueError("Invalid JPEG")
    offset, dimensions = 2, None
    while offset + 4 <= len(raw):
        if raw[offset] != 255:
            break
        while offset < len(raw) and raw[offset] == 255:
            offset += 1
        if offset >= len(raw):
            break
        marker = raw[offset]
        offset += 1
        length = int.from_bytes(raw[offset : offset + 2], "big")
        if length < 2 or offset + length > len(raw):
            break
        if marker == 0xDA:
            if dimensions:
                return dimensions
            break
        if marker in {0xD8, 0xD9}:
            break
        if marker in {0xC0, 0xC1, 0xC2}:
            if dimensions or length < 8:
                break
            height = int.from_bytes(raw[offset + 3 : offset + 5], "big")
            width = int.from_bytes(raw[offset + 5 : offset + 7], "big")
            if not 1 <= width <= max_width or not 1 <= height <= max_height:
                break
            dimensions = (width, height)
        offset += length
    raise ValueError("Invalid or oversized JPEG")
