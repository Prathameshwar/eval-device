"""One-attempt loopback JSON transport with wall-clock deadlines and size bounds."""

import http.client
import json
import socket
import threading

from .errors import ManagerError, require


def call(port, key, method, path, payload=None, timeout=8, max_bytes=8 * 1024 * 1024):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    timer = None
    expired = threading.Event()
    try:
        connection.connect()
        connection.auto_open = 0
        sock = connection.sock

        def expire():
            expired.set()
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        timer = threading.Timer(timeout, expire)
        timer.daemon = True
        timer.start()
        body = (
            json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if payload is not None
            else None
        )
        connection.request(
            method,
            path,
            body,
            {"Authorization": "Bearer " + key, "Content-Type": "application/json", "Connection": "close"},
        )
        response = connection.getresponse()
        raw = response.read(max_bytes + 1)
        require(len(raw) <= max_bytes, "response_size", "Manager response exceeded its limit", 502)
        result = json.loads(raw)
        require(isinstance(result, dict), "response_invalid", "Invalid manager response", 502)
        if response.status >= 300:
            raise ManagerError(
                result.get("code", "request_failed"), result.get("message", "Request failed"), response.status
            )
        require(not expired.is_set(), "timeout", "Request deadline exceeded", 504)
        return result
    except ManagerError:
        raise
    except (OSError, ValueError, http.client.HTTPException):
        raise ManagerError(
            "unavailable", "Unable to reach the local manager. The request outcome may be unknown.", 503
        ) from None
    finally:
        if timer:
            timer.cancel()
        connection.close()
