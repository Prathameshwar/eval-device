"""Shared validation for private upload/download addresses."""

from urllib.parse import urlsplit

from .pms_client import ClientError


def media_url(value, platform):
    try:
        parsed, origin = urlsplit(value), urlsplit(platform)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        origin_port = origin.port or (443 if origin.scheme == "https" else 80)
        if (
            parsed.username
            or parsed.password
            or not parsed.hostname
            or any(character.isspace() or ord(character) < 32 for character in value)
            or (
                parsed.scheme != "https"
                and not (
                    parsed.scheme == origin.scheme == "http"
                    and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
                    and parsed.hostname == origin.hostname
                    and port == origin_port
                )
            )
        ):
            raise ValueError()
    except (ValueError, TypeError):
        raise ClientError("Invalid private media address", code="media_address") from None
    return value
