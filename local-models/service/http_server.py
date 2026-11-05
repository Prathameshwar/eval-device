"""Bounded native-only authenticated loopback management/worker HTTP server."""

import hmac
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .errors import ManagerError, require


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "invalid_json", "Duplicate JSON fields")
        result[key] = value
    return result


class JsonServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = False
    request_seconds = 10

    def __init__(self, address, key, dispatch, *, client_key=None):
        require(address[0] == "127.0.0.1", "binding", "Management binds to loopback only")
        self.key, self.dispatch = key, dispatch
        self.client_key = client_key
        self.slots = threading.BoundedSemaphore(12)
        super().__init__(address, Handler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(self.request_seconds)
        return connection, address

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        pass  # Exceptions may contain private inference input; never dump request traces.


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def handle(self):
        def expire():
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        self.body_deadline = threading.Timer(self.server.request_seconds, expire)
        self.body_deadline.daemon = True
        self.body_deadline.start()
        try:
            super().handle()
        finally:
            self.body_deadline.cancel()

    def log_message(self, *_):
        pass

    def do_GET(self):
        self.handle_json("GET")

    def do_POST(self):
        self.handle_json("POST")

    def handle_json(self, method):
        self.close_connection = True
        try:
            require(self.client_address[0] == "127.0.0.1", "unauthorized", "Local clients only", 401)
            require(
                self.headers.get("Origin") is None and self.headers.get("Cookie") is None,
                "unauthorized",
                "Native operator clients only",
                401,
            )
            require(
                self.headers.get_all("Host") == [f"127.0.0.1:{self.server.server_port}"],
                "host",
                "Invalid management host",
                400,
            )
            authorization = self.headers.get_all("Authorization") or []
            require(
                len(authorization) == 1 and len(authorization[0]) <= 160, "unauthorized", "Unauthorized", 401
            )
            supplied = authorization[0].encode("utf-8")
            operator = hmac.compare_digest(supplied, ("Bearer " + self.server.key).encode("ascii"))
            client = bool(self.server.client_key) and hmac.compare_digest(
                supplied, ("Bearer " + self.server.client_key).encode("ascii")
            )
            require(
                operator or client,
                "unauthorized",
                "Unauthorized",
                401,
            )
            parsed = urlsplit(self.path)
            require(
                not parsed.scheme and not parsed.netloc and not parsed.fragment,
                "path",
                "Invalid request path",
            )
            payload = None
            if method == "POST":
                require(not parsed.query, "path", "POST query strings are unsupported")
                require(
                    self.headers.get("Transfer-Encoding") is None, "body", "Chunked requests are unsupported"
                )
                lengths = self.headers.get_all("Content-Length") or []
                require(
                    len(lengths) == 1 and lengths[0].isdigit(), "body", "A bounded content length is required"
                )
                size = int(lengths[0])
                require(size > 0, "body", "A JSON body is required", 400)
                require(size <= 2 * 1024 * 1024, "body", "Request exceeds its limit", 413)
                require(
                    self.headers.get_content_type() == "application/json", "body", "Use application/json", 415
                )
                raw = self.rfile.read(size)
                require(len(raw) == size, "body", "Truncated request body")
                payload = json.loads(
                    raw,
                    object_pairs_hook=unique_object,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid number")),
                )
                require(isinstance(payload, dict), "body", "Request must be a JSON object")
            if not operator:
                require(
                    (method, parsed.path)
                    in {
                        ("GET", "/v1/capabilities"),
                        ("POST", "/v1/infer/llm"),
                        ("POST", "/v1/infer/asr"),
                        ("POST", "/v1/infer/tts"),
                        ("POST", "/v1/llm/inspect"),
                    },
                    "permission_denied",
                    "Inference clients cannot manage services",
                    403,
                )
            query = parse_qs(parsed.query, max_num_fields=8, strict_parsing=True)
            self.body_deadline.cancel()  # Authenticated bounded input was read; inference has its own deadline.
            result = self.server.dispatch(method, parsed.path, payload, query)
            self.reply(200, result)
        except ManagerError as error:
            self.reply(error.status, {"code": error.code, "message": error.message})
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            self.reply(400, {"code": "invalid_request", "message": "Invalid request"})
        except (TimeoutError, socket.timeout):
            self.reply(408, {"code": "timeout", "message": "Request deadline exceeded"})
        except Exception:
            self.reply(500, {"code": "internal", "message": "Operation failed; inspect manager status"})

    def reply(self, status, result):
        raw = json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(raw)
        except (OSError, TimeoutError):
            pass
