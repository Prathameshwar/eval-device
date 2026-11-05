"""Regressions for the follow-up review; local sockets and disposable state only."""

import concurrent.futures
import http.client
import io
import json
import socketserver
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import client
import common
import install
import run


class ConfigurationTests(unittest.TestCase):
    def test_base_config_rejects_unknown_keys_and_non_objects(self):
        original = common.config()
        for bad in ({**original, "host": "0.0.0.0"}, [], None):
            with self.subTest(bad=type(bad)), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "config.json").write_text(json.dumps(bad))
                with patch.object(common, "ROOT", root), self.assertRaises(ValueError):
                    common.config()

    def test_concurrent_first_credentials_share_one_complete_key(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(common, "STATE", Path(tmp) / "state"),
            patch.object(common, "private_directory"),
        ):
            barrier = threading.Barrier(8)

            def create():
                barrier.wait(timeout=5)
                return common.credentials()

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: create(), range(8)))
            self.assertEqual(len(set(results)), 1)
            self.assertGreaterEqual(len(results[0][1]), 48)

    def test_cleanup_releases_job_and_lock_when_termination_fails(self):
        server = run.Server(common.config())
        server.process = Mock()
        server.process.poll.return_value = None
        server.process.terminate.side_effect = OSError("synthetic termination failure")
        server.process.stdout = io.BytesIO()
        server.guard = Mock()
        server.guard.close.side_effect = lambda: setattr(server.process.poll, "return_value", 0)
        server.reader = Mock()
        server.reader.is_alive.return_value = False
        server.lock = io.BytesIO()
        lock = server.lock
        guard = server.guard
        server.close()
        guard.close.assert_called_once()
        self.assertTrue(lock.closed)
        self.assertTrue(server.process.stdout.closed)
        server.close()
        guard.close.assert_called_once()

    def test_full_partial_and_cpu_offload_must_match_request(self):
        settings = common.config()
        for gpu, requested, actual, total, valid in (
            (True, 99, 37, 37, True),
            (True, 99, 17, 37, False),
            (True, 17, 17, 37, True),
            (True, 17, 16, 37, False),
            (True, 99, 0, None, False),
            (False, 99, 0, None, True),
            (False, 99, 1, 37, False),
        ):
            with self.subTest(gpu=gpu, requested=requested, actual=actual):
                server = run.Server({**settings, "gpu_enabled": gpu, "gpu_layers": requested})
                server.metrics.update(offloaded_layers=actual, total_layers=total)
                if valid:
                    server.validate_device()
                else:
                    with self.assertRaises(RuntimeError):
                        server.validate_device()

    def test_cleanup_releases_lock_even_if_pipe_close_fails(self):
        server = run.Server(common.config())
        server.process = Mock()
        server.process.poll.return_value = 0
        server.process.stdout.close.side_effect = OSError("fixture pipe failure")
        server.lock = io.BytesIO()
        held = server.lock
        with self.assertRaises(OSError):
            server.close()
        self.assertTrue(held.closed)
        self.assertIsNone(server.lock)

    def test_duplicate_install_stops_before_download(self):
        specs = json.loads((install.ROOT / "assets.lock.json").read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets.lock.json").write_text(json.dumps(specs))
            (root / ".models").mkdir()
            import msvcrt

            with (root / ".install.lock").open("a+b") as held:
                msvcrt.locking(held.fileno(), msvcrt.LK_NBLCK, 1)
                try:
                    with (
                        patch.object(install, "ROOT", root),
                        patch.object(sys, "argv", ["install.py", "--cpu"]),
                        patch.object(install, "download", return_value=root / "fixture") as download,
                        patch.object(install, "extract_runtime"),
                    ):
                        with self.assertRaisesRegex(RuntimeError, "already running"):
                            install.main()
                        download.assert_not_called()
                finally:
                    held.seek(0)
                    msvcrt.locking(held.fileno(), msvcrt.LK_UNLCK, 1)


class TransportTests(unittest.TestCase):
    def test_deadline_interrupts_slow_headers_and_unterminated_events(self):
        for slow_headers in (False, True):
            with self.subTest(slow_headers=slow_headers):
                calls = []
                stop = threading.Event()

                class Handler(socketserver.BaseRequestHandler):
                    def handle(self):
                        self.request.settimeout(2)
                        self.request.recv(65536)
                        calls.append(1)
                        prefix = (
                            b"HTTP/1.1 200 OK\r\nX-Test: "
                            if slow_headers
                            else b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n\r\n"
                        )
                        try:
                            self.request.sendall(prefix)
                            for _ in range(20):
                                if stop.wait(0.08):
                                    return
                                self.request.sendall(b":")
                        except OSError:
                            pass

                with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler) as http:
                    worker = threading.Thread(target=http.serve_forever, kwargs={"poll_interval": 0.02})
                    worker.start()
                    settings = {
                        **common.config(),
                        "port": http.server_address[1],
                        "request_timeout_seconds": 0.3,
                    }
                    started = time.monotonic()
                    try:
                        with self.assertRaises(TimeoutError):
                            client.infer(settings, "fixture", [{"role": "user", "content": "hello"}])
                        elapsed = time.monotonic() - started
                        self.assertLess(elapsed, 0.8, "Deadline did not interrupt an in-progress read")
                        self.assertEqual(len(calls), 1, "Inference POST must never be replayed")
                    finally:
                        stop.set()
                        http.shutdown()
                        worker.join(3)

    def test_malformed_messages_fail_before_transport(self):
        for message in (None, 12, ["role", "content"], {"role": [], "content": "x"}):
            with self.subTest(message=message), patch.object(client, "request") as request:
                with self.assertRaises(ValueError):
                    client.infer(common.config(), "fixture", [message])
                request.assert_not_called()

    def test_malformed_response_shapes_fail_cleanly(self):
        for event in ([], {"choices": None}, {"choices": [None]}, {"choices": [{"delta": []}]}):
            with self.subTest(event=event):
                wire = b"data: " + json.dumps(event).encode() + b"\n\ndata: [DONE]\n"
                with patch.object(client, "request", return_value=io.BytesIO(wire)) as request:
                    with self.assertRaises(RuntimeError):
                        client.infer(common.config(), "fixture", [{"role": "user", "content": "hi"}])
                    request.assert_called_once()

    def test_redirect_never_forwards_credentials_or_replays_post(self):
        calls = []

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(2)
                self.request.recv(65536)
                calls.append(1)
                self.request.sendall(
                    b"HTTP/1.1 307 Temporary Redirect\r\nLocation: http://127.0.0.1:1/other"
                    b"\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                )

        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler) as http:
            worker = threading.Thread(target=http.serve_forever, kwargs={"poll_interval": 0.02})
            worker.start()
            try:
                settings = {**common.config(), "port": http.server_address[1]}
                with self.assertRaises(client.urllib.error.HTTPError) as caught:
                    client.infer(settings, "fixture", [{"role": "user", "content": "hello"}])
                self.assertEqual(caught.exception.code, 307)
                self.assertEqual(len(calls), 1)
            finally:
                http.shutdown()
                worker.join(3)

    def test_chunked_disconnect_is_handled_without_replaying_post(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.readline.side_effect = http.client.IncompleteRead(b"partial")
        with patch.object(client, "request", return_value=response) as request:
            with self.assertRaises(RuntimeError):
                client.infer(common.config(), "fixture", [{"role": "user", "content": "hi"}])
            request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
