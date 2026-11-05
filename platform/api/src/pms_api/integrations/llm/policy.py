"""Explicit destinations only. Remote DNS is checked again at socket creation."""

import ipaddress
import re
from urllib.parse import urlsplit

from pms_api.core.common import AppError

OPENAI_URL = "https://api.openai.com/v1"
ANTHROPIC_URL = "https://api.anthropic.com/v1"


def endpoint(value: str, ports: list[int], provider="local_llama_cpp", allowed_urls=()) -> str:
    try:
        if not value.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise ValueError()
        url = urlsplit(value)
        if (
            url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or any(c in value for c in "\\%?#")
            or not url.hostname
            or any(p in (".", "..") for p in url.path.split("/"))
            or not re.fullmatch(r"[A-Za-z0-9/_.-]*", url.path)
        ):
            raise ValueError()
        local = url.hostname == "127.0.0.1" and url.scheme == "http" and url.port in ports
        if provider == "local_llama_cpp":
            if not local or url.path not in ("", "/"):
                raise ValueError()
            return f"http://127.0.0.1:{url.port}"
        normalized = value.rstrip("/")
        if provider == "openai":
            if normalized != OPENAI_URL or normalized not in allowed_urls:
                raise ValueError()
        elif provider == "anthropic":
            if normalized != ANTHROPIC_URL or normalized not in allowed_urls:
                raise ValueError()
        elif provider in {"openai_compatible", "azure_openai"}:
            # No loopback exception: a platform-executed call only ever leaves for a public
            # destination. A model on the caller's own machine is published as local instead.
            if normalized not in allowed_urls:
                raise ValueError()
            if url.scheme != "https" or not re.fullmatch(r"[a-z0-9.-]+", url.hostname):
                raise ValueError()
            try:
                address = ipaddress.ip_address(url.hostname)
            except ValueError:
                if "." not in url.hostname or url.hostname.endswith("."):
                    raise ValueError() from None
            else:
                if not address.is_global or address.is_multicast or address.is_reserved:
                    raise ValueError()
            if provider == "azure_openai" and (
                url.scheme != "https"
                or url.port not in (None, 443)
                or not url.hostname.endswith((".openai.azure.com", ".services.ai.azure.com"))
                or url.path.rstrip("/") != "/openai/v1"
            ):
                raise ValueError()
        else:
            raise ValueError()
        # Force port parsing to reject malformed/out-of-range values.
        _ = url.port
        return normalized
    except ValueError:
        raise AppError(422, "llm_endpoint_invalid", "Choose an explicitly allowed LLM endpoint") from None


def api_base(base_url, provider):
    return base_url + "/v1" if provider == "local_llama_cpp" else base_url


def configured_endpoint(connection, settings, *, dispatch=False):
    url = endpoint(
        connection.base_url, settings.llm_allowed_ports, connection.provider, settings.llm_allowed_base_urls
    )
    if dispatch and not url.startswith("http://127.0.0.1:") and not settings.external_calls_enabled:
        raise AppError(503, "external_calls_disabled", "External model calls are disabled")
    return url
