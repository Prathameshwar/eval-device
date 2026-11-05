import io
import json
import os
import stat
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import client
import common
import install
import run


class Response(io.BytesIO):
    def __init__(self, data, status=206, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}


class ConfigAndLaunchTests(unittest.TestCase):
    def test_validated_overrides_and_explicit_device_arguments(self):
        original = common.config()
        with tempfile.TemporaryDirectory() as tmp, patch.object(common, "ROOT", Path(tmp)):
            root = Path(tmp)
            (root / "config.json").write_text(json.dumps(original))
            (root / "config.local.json").write_text(json.dumps({"gpu_enabled": False, "port": 8799}))
            settings = common.config()
            self.assertFalse(settings["gpu_enabled"])
            args = run.Server(settings).arguments(Path("server.exe"), Path("private/key.txt"))
            self.assertEqual(args[args.index("--device") + 1], "none")
            self.assertEqual(args[args.index("--gpu-layers") + 1], "0")
            self.assertEqual(args[args.index("--host") + 1], "127.0.0.1")
            self.assertIn("--offline", args)
            self.assertIn("--no-agent", args)
            self.assertIn("--no-context-shift", args)
            self.assertNotIn("--api-key", args)
            settings["gpu_enabled"] = True
            args = run.Server(settings).arguments(Path("server.exe"), Path("private/key.txt"))
            self.assertEqual(args[args.index("--device") + 1], "CUDA0")
            self.assertEqual(
                json.loads(args[args.index("--chat-template-kwargs") + 1]), {"enable_thinking": False}
            )

    def test_invalid_settings_are_rejected(self):
        original = common.config()
        for bad in (
            {"gpu_enabled": "false"},
            {"port": True},
            {"context_size": 10},
            {"gpu_layers": 0},
            {"host": "0.0.0.0"},
            {"system_prompt": ""},
            {"context_size": 512, "max_tokens": 512},
        ):
            with (
                self.subTest(bad=bad),
                tempfile.TemporaryDirectory() as tmp,
                patch.object(common, "ROOT", Path(tmp)),
            ):
                (Path(tmp) / "config.json").write_text(json.dumps(original))
                (Path(tmp) / "config.local.json").write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    common.config()

    def test_credentials_are_reused_and_never_in_commands(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(common, "STATE", Path(tmp) / "state"),
            patch.object(common, "private_directory"),
        ):
            path, first = common.credentials()
            self.assertGreaterEqual(len(first), 48)
            self.assertEqual(common.credentials(), (path, first))
            args = run.Server(common.config()).arguments(Path("server.exe"), path)
            self.assertNotIn(first, " ".join(args))
            path.write_text("bad")
            with self.assertRaises(ValueError):
                common.credentials()

    def test_hardlinked_credentials_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "one"
            source.write_text("fixture")
            target = Path(tmp) / "two"
            os.link(source, target)
            with self.assertRaises(RuntimeError):
                common.no_link(target)

    def test_duplicate_windows_lock_is_rejected_before_reading_or_loading(self):
        import msvcrt

        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            with (state / "instance.lock").open("a+b") as held:
                msvcrt.locking(held.fileno(), msvcrt.LK_NBLCK, 1)
                try:
                    with (
                        patch.object(run, "STATE", state),
                        patch.object(run, "credentials", return_value=(state / "key", "fixture")),
                        patch.object(run, "verify_install") as verify,
                    ):
                        with self.assertRaisesRegex(RuntimeError, "already running"):
                            with run.Server(common.config()):
                                self.fail("Duplicate instance was accepted")
                        verify.assert_not_called()
                finally:
                    held.seek(0)
                    msvcrt.locking(held.fileno(), msvcrt.LK_UNLCK, 1)

    def test_native_metrics_only_capture_numeric_execution_details(self):
        server = run.Server(common.config())
        secret = "never record this patient text"
        server.process = type(
            "P",
            (),
            {
                "stdout": io.BytesIO(
                    (
                        "offloaded 37/37 layers to GPU\nCUDA0 model buffer size = 2200.50 MiB\n"
                        + secret
                        + "\n"
                    ).encode()
                )
            },
        )()
        server.read_metrics()
        self.assertEqual(server.metrics["offloaded_layers"], 37)
        self.assertEqual(server.metrics["model_buffer_mib"], 2200.5)
        self.assertNotIn(secret, json.dumps(server.metrics))


class DownloadTests(unittest.TestCase):
    def spec(self, data):
        import hashlib

        return {
            "name": "fixture.bin",
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "url": "https://example.invalid/model",
        }

    def test_download_checks_ranges_hash_and_reuses_verified_file(self):
        data = b"fixture" * 20
        spec = self.spec(data)
        requests = []

        def fetch(request, timeout):
            requests.append(request)
            self.assertEqual(timeout, 45)
            start, end = map(int, request.get_header("Range")[6:].split("-"))
            return Response(
                data[start : end + 1], headers={"Content-Range": f"bytes {start}-{end}/{len(data)}"}
            )

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(install.urllib.request, "urlopen", fetch),
            patch.object(install, "STEP", 32),
        ):
            path = install.download(spec, Path(tmp))
            self.assertEqual(path.read_bytes(), data)
            count = len(requests)
            self.assertGreater(count, 1)
            self.assertEqual(install.download(spec, Path(tmp)), path)
            self.assertEqual(len(requests), count)
            self.assertTrue(all(not req.has_header("Authorization") for req in requests))
            path.write_bytes(b"corrupt")
            with self.assertRaises(ValueError):
                install.download(spec, Path(tmp))

    def test_integrity_and_range_failures_never_publish(self):
        data = b"test"
        for failure in ("checksum", "range", "oversize"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                spec = self.spec(data)
                returned = data
                header = "bytes 0-3/4"
                if failure == "checksum":
                    spec["sha256"] = "0" * 64
                if failure == "range":
                    header = "bytes 1-4/4"
                if failure == "oversize":
                    returned = data + b"x"

                def fetch(*args, **kwargs):
                    return Response(returned, headers={"Content-Range": header})

                with (
                    patch.object(install.urllib.request, "urlopen", fetch),
                    patch.object(install.time, "sleep"),
                ):
                    with self.assertRaises((ValueError, RuntimeError)):
                        install.download(spec, Path(tmp))
                self.assertFalse((Path(tmp) / spec["name"]).exists())

    def test_permanent_refusal_and_bounded_transient_retries(self):
        for error, expected in (
            (urllib.error.HTTPError("https://example.invalid", 403, "denied", None, None), 1),
            (TimeoutError(), 3),
        ):
            with (
                tempfile.TemporaryDirectory() as tmp,
                patch.object(install.urllib.request, "urlopen", side_effect=error) as fetch,
                patch.object(install.time, "sleep"),
            ):
                with self.assertRaises(RuntimeError):
                    install.download(self.spec(b"test"), Path(tmp))
                self.assertEqual(fetch.call_count, expected)

    def test_runtime_extraction_does_not_escape_and_rejects_links(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(install.subprocess, "run"):
            root = Path(tmp)
            archive = root / "runtime.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("../../llama-server.exe", b"fixture")
                z.writestr("../../skip.txt", b"skip")
                z.writestr("sub/backend.dll", b"library")
            target = root / "runtime"
            install.extract_runtime([archive], target)
            self.assertEqual((target / "llama-server.exe").read_bytes(), b"fixture")
            self.assertFalse((root / "skip.txt").exists())
            install.extract_runtime([archive], target)
            (target / "backend.dll").write_bytes(b"bad")
            with self.assertRaises(ValueError):
                install.extract_runtime([archive], target)
            with zipfile.ZipFile(archive, "w") as z:
                member = zipfile.ZipInfo("llama-server.exe")
                member.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(member, b"somewhere")
            with self.assertRaises(ValueError):
                install.extract_runtime([archive], root / "unsafe")

    def test_cpu_setup_does_not_install_cuda(self):
        specs = json.loads((install.ROOT / "assets.lock.json").read_text())
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(install, "ROOT", Path(tmp)),
            patch.object(sys, "argv", ["install.py", "--cpu"]),
        ):
            root = Path(tmp)
            (root / "assets.lock.json").write_text(json.dumps(specs))
            (root / ".models").mkdir()
            with (
                patch.object(install, "download", return_value=root / "fixture") as download,
                patch.object(install, "extract_runtime"),
            ):
                install.main()
            self.assertEqual(
                [call.args[0]["name"] for call in download.call_args_list],
                [
                    specs["cpu"]["name"],
                    (
                        specs["model"]
                        if install.DEFAULT_MODEL == "qwen3-4b"
                        else specs["models"][install.DEFAULT_MODEL]
                    )["name"],
                ],
            )


class ClientTests(unittest.TestCase):
    def test_long_conversations_have_no_message_count_cap(self):
        settings = common.config()
        wire = b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n'
        for pairs in (12, 50):
            messages = [{"role": "system", "content": settings["system_prompt"]}]
            for _ in range(pairs):
                messages.extend(
                    [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
                )
            messages.append({"role": "user", "content": "continue"})
            original = [dict(message) for message in messages]
            with (
                self.subTest(count=len(messages)),
                patch.object(client, "request", return_value=Response(wire)) as request,
            ):
                result = client.infer(settings, "fixture-token", messages)
                self.assertEqual(result["text"], "ok")
                request.assert_called_once()
                self.assertEqual(request.call_args.args[3]["messages"], original)
                self.assertEqual(messages, original)

    def test_stream_accumulates_once_and_disables_thinking(self):
        events = [
            {"choices": [{"delta": {"content": "hello "}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": "there"}, "finish_reason": "stop"}]},
        ]
        wire = b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events) + b"data: [DONE]\n"
        pieces = []
        with patch.object(client, "request", return_value=Response(wire)) as request:
            result = client.infer(
                common.config(), "fixture-token", [{"role": "user", "content": "hi"}], pieces.append
            )
        self.assertEqual(result["text"], "hello there")
        self.assertEqual(pieces, ["hello ", "there"])
        self.assertEqual(request.call_count, 1)
        self.assertFalse(request.call_args.args[3]["chat_template_kwargs"]["enable_thinking"])

    def test_uncertain_failure_is_not_retried_or_reported_complete(self):
        settings = common.config()
        for wire in (b"", b"data: [DONE]\n", b"data: " + b"x" * 65537):
            with patch.object(client, "request", return_value=Response(wire)) as request:
                with self.assertRaises(RuntimeError):
                    client.infer(settings, "fixture-token", [{"role": "user", "content": "hi"}])
            self.assertEqual(request.call_count, 1)
        with patch.object(client, "request", side_effect=TimeoutError()) as request:
            with self.assertRaises(TimeoutError):
                client.infer(settings, "fixture-token", [{"role": "user", "content": "hi"}])
        self.assertEqual(request.call_count, 1)

    def test_input_bounds_prevent_network_call(self):
        for messages in ([{"role": "user", "content": "x" * 8001}], [{"role": "tool", "content": "x"}], []):
            with patch.object(client, "request") as request:
                with self.assertRaises(ValueError):
                    client.infer(common.config(), "fixture-token", messages)
                request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
