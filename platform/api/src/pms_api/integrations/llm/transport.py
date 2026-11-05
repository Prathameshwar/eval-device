"""HTTPX adapter with DNS-pinned public HTTPS connections and normal TLS/SNI.

The pool retains the original hostname: neither certificates nor connection reuse
are keyed by a substituted IP. No proxies, redirects, or connect/POST retries.
"""

import asyncio
import ipaddress
import socket
from contextlib import contextmanager

import anyio
import httpcore
import httpx


@contextmanager
def mapped_errors():
    try:
        yield
    except (
        httpcore.TimeoutException,
        httpcore.NetworkError,
        httpcore.ProtocolError,
        httpcore.ProxyError,
        httpcore.UnsupportedProtocol,
    ) as error:
        kind = getattr(httpx, type(error).__name__, httpx.TransportError)
        raise kind("LLM transport failed") from None


class PublicNetwork(httpcore.AsyncNetworkBackend):
    """Public destinations only.

    A model published as local runs on the caller's own machine, which this service cannot
    reach and must not try to: the caller executes that turn itself. So there is no loopback
    allowance here, and a deployed platform cannot be steered into dialling its own host.
    """

    def __init__(self):
        self.backend = httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        try:
            async with asyncio.timeout(timeout):
                records = await anyio.getaddrinfo(host, port, type=socket.SOCK_STREAM)
                addresses = [str(record[4][0]) for record in records]
                parsed = [ipaddress.ip_address(ip) for ip in addresses]
                if not parsed or any(not ip.is_global or ip.is_multicast or ip.is_reserved for ip in parsed):
                    raise httpcore.ConnectError("LLM destination is not public")
                return await self.backend.connect_tcp(
                    addresses[0], port, timeout, local_address, socket_options
                )
        except TimeoutError:
            raise httpcore.ConnectTimeout("LLM connection timed out") from None
        except (OSError, ValueError):
            raise httpcore.ConnectError("LLM destination unavailable") from None

    async def sleep(self, seconds):
        await anyio.sleep(seconds)


class ResponseStream(httpx.AsyncByteStream):
    def __init__(self, response):
        self.response = response

    async def __aiter__(self):
        with mapped_errors():
            async for block in self.response.aiter_stream():
                yield block

    async def aclose(self):
        with mapped_errors():
            await self.response.aclose()


class GuardedTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.pool = httpcore.AsyncConnectionPool(
            ssl_context=httpcore.default_ssl_context(),
            max_connections=4,
            max_keepalive_connections=2,
            retries=0,
            network_backend=PublicNetwork(),
        )

    async def handle_async_request(self, request):
        upstream = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        with mapped_errors():
            response = await self.pool.handle_async_request(upstream)
        return httpx.Response(
            response.status,
            headers=response.headers,
            stream=ResponseStream(response),
            extensions=response.extensions,
        )

    async def aclose(self):
        await self.pool.aclose()
