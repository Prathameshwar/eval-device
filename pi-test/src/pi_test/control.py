"""One bounded command per connection. Unix permissions are the production boundary."""

import asyncio
import hmac
import json
import os
import secrets
import socket
import stat
import struct
from functools import partial
from pathlib import Path

from training_contracts.privacy import no_link

from .config import private_dir

LIMIT = 32768


async def close_writer(writer):
    writer.close()
    try:
        async with asyncio.timeout(1):
            await writer.wait_closed()
    except (ConnectionError, OSError, TimeoutError):
        writer.transport.abort()


class Control:
    def __init__(self, directory, dispatch):
        self.directory, self.dispatch = Path(directory), dispatch
        self.server = None
        self.clients = set()
        self.closing = False
        self.secret = secrets.token_urlsafe(48)

    async def start(self):
        private_dir(self.directory)
        self.path = self.directory / ("control.json" if os.name == "nt" else "control.sock")
        if self.path.exists() or self.path.is_symlink():
            no_link(self.path)
        if self.path.exists():
            # A second daemon must never replace a live control socket.
            if os.name == "nt":
                raise ValueError("Control descriptor exists; check the running service")
            if not stat.S_ISSOCK(self.path.stat().st_mode):
                raise ValueError("Control path is not a socket")
            probe = socket.socket(socket.AF_UNIX)
            probe.settimeout(1)
            try:
                probe.connect(str(self.path))
            except ConnectionRefusedError:
                self.path.unlink()
            else:
                raise ValueError("Service is already running")
            finally:
                probe.close()
        if os.name == "nt":
            self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0, limit=LIMIT)
            data = {"port": self.server.sockets[0].getsockname()[1], "token": self.secret}
            # Windows development only. Shared privacy helper applies an account ACL.
            from training_contracts.privacy import private_directory

            with self.path.open("x", encoding="utf-8") as target:
                private_directory(self.path)
                json.dump(data, target)
        else:
            self.server = await asyncio.start_unix_server(self.handle, self.path, limit=LIMIT)
            self.path.chmod(0o600)

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        if self.closing or len(self.clients) >= 8:
            writer.close()
            return
        self.clients.add(task)
        try:
            if os.name != "nt" and hasattr(socket, "SO_PEERCRED"):
                peer = writer.get_extra_info("socket")
                _, uid, _ = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid not in {os.getuid(), 0}:
                    return
            async with asyncio.timeout(5):
                raw = await reader.readline()
            if not raw.endswith(b"\n") or len(raw) > LIMIT:
                raise ValueError()
            request = json.loads(raw)
            if not isinstance(request, dict):
                raise ValueError()
            token = request.pop("token", "")
            if os.name == "nt" and (
                not isinstance(token, str) or not hmac.compare_digest(token, self.secret)
            ):
                raise ValueError()
            async with asyncio.timeout(20):
                result = await self.dispatch(request)
            response = {"ok": True, "result": result}
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Never serialize exception messages: HTTP errors may contain signed URLs.
            response = {"ok": False, "error": type(error).__name__}
        finally:
            try:
                if "response" in locals():
                    raw = json.dumps(response, default=str, ensure_ascii=False).encode()
                    if len(raw) + 1 > LIMIT:
                        raw = b'{"ok":false,"error":"response_limit"}'
                    try:
                        async with asyncio.timeout(5):
                            writer.write(raw + b"\n")
                            await writer.drain()
                    except (ConnectionError, OSError, TimeoutError):
                        pass
            finally:
                try:
                    await close_writer(writer)
                finally:
                    self.clients.discard(task)

    async def close(self):
        self.closing = True
        if self.server:
            server = self.server
            server.close()
            pending = tuple(self.clients)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            # Python 3.12+ waits for clients as well as the listening socket.
            await server.wait_closed()
            self.path.unlink(missing_ok=True)
            self.server = None


async def send(directory, request):
    directory = Path(directory)
    path = directory / ("control.json" if os.name == "nt" else "control.sock")
    no_link(directory)
    no_link(path)
    if os.name == "nt":
        if path.stat().st_size > 1024:
            raise ValueError("Invalid control descriptor")
        descriptor = json.loads(path.read_text())
        request = {**request, "token": descriptor["token"]}
        connect = partial(asyncio.open_connection, "127.0.0.1", descriptor["port"], limit=LIMIT)
    else:
        connect = partial(asyncio.open_unix_connection, path, limit=LIMIT)
    raw = json.dumps(request, ensure_ascii=False).encode() + b"\n"
    if len(raw) > LIMIT:
        raise ValueError("Command exceeds its byte limit")
    async with asyncio.timeout(5):
        reader, writer = await connect()
    try:
        async with asyncio.timeout(30):
            writer.write(raw)
            await writer.drain()
            return json.loads(await reader.readline())
    finally:
        await close_writer(writer)
