"""Launcher failure boundaries and real Windows descendant cleanup."""

import http.server
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "platform_web", ROOT / "start/platform_web.py"
)
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class Response(io.BytesIO):
    def __init__(self, data, status=200):
        super().__init__(json.dumps(data).encode())
        self.status = status


class LauncherTests(unittest.TestCase):
    def test_training_readiness_reports_restart_without_leaking_response(self):
        with patch.object(
            launcher.OPENER, "open", return_value=Response({"private": "do-not-print"})
        ):
            with self.assertRaisesRegex(
                launcher.StartupError, "Restart the existing API"
            ) as error:
                launcher.verify_training(8000)
            self.assertNotIn("do-not-print", str(error.exception))
        with patch.object(
            launcher.OPENER,
            "open",
            return_value=Response({"algorithm": "EdDSA", "public_key": "pem"}),
        ):
            launcher.verify_training(8000)

    def test_local_preflight_provisions_training_without_replacing_existing_configuration(
        self,
    ):
        from dotenv import dotenv_values
        from pms_api.security.training_keys import load_training_key

        # Windows key generation needs SystemRoot; keep application settings isolated.
        system_environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() == "SYSTEMROOT"
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, system_environment, clear=True),
        ):
            root = Path(directory)
            api = root / "platform/api"
            api.mkdir(parents=True)
            config = api / ".env"
            config.write_text(
                "PMS_ENVIRONMENT=local\nPMS_TOKEN_PEPPER="
                + "p" * 40
                + "\nPMS_MEDIA_SIGNING_KEY="
                + "m" * 40
                + "\n"
            )
            self.assertEqual(launcher.preflight(root, None, 3000), 8000)
            key = Path(dotenv_values(config)["PMS_TRAINING_KEY_FILE"])
            load_training_key(key)
            original = key.read_bytes()
            launcher.preflight(root, None, 3000)
            self.assertEqual(key.read_bytes(), original)

    def test_missing_configuration_has_actionable_message_and_does_not_start(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(launcher.subprocess, "Popen") as start,
        ):
            with self.assertRaisesRegex(launcher.StartupError, "init-local"):
                launcher.preflight(Path(directory), None, 3000)
            start.assert_not_called()

    def test_invalid_config_never_prints_rejected_values(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {}, clear=True),
        ):
            root = Path(directory)
            (root / "platform/api").mkdir(parents=True)
            (root / "platform/api/.env").write_text(
                "PMS_PORT=private-value-should-not-leak\n"
            )
            with self.assertRaises(launcher.StartupError) as error:
                launcher.preflight(root, None, 3000)
            self.assertIn("configuration is invalid", str(error.exception))
            self.assertNotIn("private-value", str(error.exception))

    def test_ui_gets_matching_api_url_without_inherited_pms_secrets(self):
        with patch.dict(
            os.environ,
            {
                "PMS_DATABASE_URL": "secret",
                "PGPASSWORD": "secret",
                "DATABASE_URL": "secret",
                "pms_TOKEN_PEPPER": "secret",
                "PMS_API_BASE_URL": "https://wrong.invalid",
            },
        ):
            env = launcher.child_environment("ui", 8055)
        self.assertEqual(env["PMS_API_BASE_URL"], "http://127.0.0.1:8055/api/v1")
        self.assertNotIn("PMS_DATABASE_URL", env)
        self.assertNotIn("PGPASSWORD", env)
        self.assertNotIn("DATABASE_URL", env)
        self.assertNotIn("pms_TOKEN_PEPPER", env)
        self.assertEqual(env["NODE_ENV"], "development")

    @unittest.skipUnless(sys.platform == "win32", "Windows launcher")
    def test_running_listener_is_detected_without_touching_owner(self):
        with socket.socket() as owner:
            owner.bind(("127.0.0.1", 0))
            owner.listen()
            self.assertTrue(launcher.is_running(owner.getsockname()[1]))
            self.assertGreater(owner.fileno(), 0)

    def test_free_port_is_not_blocked_by_closed_connections(self):
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen()
            port = server.getsockname()[1]
            with socket.create_connection(("127.0.0.1", port)) as client:
                connection, _ = server.accept()
                connection.close()
                self.assertEqual(client.recv(1), b"")
        self.assertFalse(launcher.is_running(port))

    def test_schema_mismatch_reports_upgrade_without_raw_response(self):
        response = Response(
            {"reason": "schema_mismatch", "private": "must-not-appear"}, 503
        )
        with (
            patch.object(launcher.OPENER, "open", return_value=response),
            self.assertRaisesRegex(launcher.StartupError, "init-database") as error,
        ):
            launcher.wait_ready("http://127.0.0.1/health/ready", [], api=True)
        self.assertNotIn("must-not-appear", str(error.exception))

    def test_ready_requires_api_identity(self):
        responses = [
            Response({"status": "ready", "service": "unrelated"}),
            Response({"status": "ready", "service": "pms_api"}),
        ]
        with (
            patch.object(launcher.OPENER, "open", side_effect=responses) as request,
            patch.object(launcher.time, "sleep"),
        ):
            launcher.wait_ready("http://127.0.0.1/health/ready", [], api=True)
        self.assertEqual(request.call_count, 2)

    def test_exited_service_aborts_before_polling_endpoint(self):
        process = Mock(returncode=2)
        process.poll.return_value = 2
        with patch.object(launcher.OPENER, "open") as request:
            with self.assertRaisesRegex(launcher.StartupError, "API exited"):
                launcher.wait_ready(
                    "http://127.0.0.1/health/ready", [("API", process)], api=True
                )
            request.assert_not_called()

    def test_second_service_startup_failure_stops_every_owned_process(self):
        api, ui, job = Mock(), Mock(), Mock()
        with (
            patch.object(sys, "argv", ["platform_web.py", "--check"]),
            patch.object(sys, "platform", "win32"),
            patch.object(launcher, "preflight", return_value=8000),
            patch.object(launcher, "verify_training"),
            patch.object(launcher, "is_running", return_value=False),
            patch.object(launcher, "ui_dependencies", return_value="node"),
            patch.object(launcher, "WindowsJob", return_value=job),
            patch.object(launcher, "start_child", side_effect=[api, ui]),
            patch.object(
                launcher,
                "wait_ready",
                side_effect=[None, launcher.StartupError("UI startup failed")],
            ),
            patch("sys.stdout", new=io.StringIO()) as output,
        ):
            self.assertEqual(launcher.main(), 1)
            self.assertIn("UI startup failed", output.getvalue())
        job.close.assert_called_once()
        api.wait.assert_called_once()
        ui.wait.assert_called_once()

    def test_successful_check_exits_and_stops_both_services(self):
        job = Mock()
        with (
            patch.object(sys, "argv", ["platform_web.py", "--check"]),
            patch.object(sys, "platform", "win32"),
            patch.object(launcher, "preflight", return_value=8000),
            patch.object(launcher, "verify_training"),
            patch.object(launcher, "is_running", return_value=False),
            patch.object(launcher, "ui_dependencies", return_value="node"),
            patch.object(launcher, "WindowsJob", return_value=job),
            patch.object(launcher, "start_child", side_effect=[Mock(), Mock()]),
            patch.object(launcher, "wait_ready") as ready,
            patch("sys.stdout", new=io.StringIO()),
        ):
            self.assertEqual(launcher.main(), 0)
        self.assertEqual(ready.call_count, 2)
        job.close.assert_called_once()

    def test_check_starts_only_missing_services_and_cleans_up_only_owned_processes(
        self,
    ):
        for api_running, ui_running in [
            (False, False),
            (True, False),
            (False, True),
            (True, True),
        ]:
            with self.subTest(api_running=api_running, ui_running=ui_running):
                job = Mock()
                owned = []

                def start_owned(*args, owned=owned):
                    process = Mock()
                    owned.append(process)
                    return process

                with (
                    patch.object(sys, "argv", ["platform_web.py", "--check"]),
                    patch.object(sys, "platform", "win32"),
                    patch.object(launcher, "preflight", return_value=8055),
                    patch.object(launcher, "verify_training"),
                    patch.object(
                        launcher, "is_running", side_effect=[api_running, ui_running]
                    ) as running,
                    patch.object(
                        launcher, "ui_dependencies", return_value="node"
                    ) as dependencies,
                    patch.object(
                        launcher, "WindowsJob", return_value=job
                    ) as create_job,
                    patch.object(
                        launcher, "start_child", side_effect=start_owned
                    ) as start,
                    patch.object(launcher, "wait_ready") as ready,
                    patch("sys.stdout", new=io.StringIO()),
                ):
                    self.assertEqual(launcher.main(), 0)
                expected = ([] if api_running else ["api"]) + (
                    [] if ui_running else ["ui"]
                )
                self.assertEqual(
                    [call.args[1] for call in start.call_args_list], expected
                )
                self.assertEqual(
                    [call.args[0] for call in running.call_args_list], [8055, 3000]
                )
                self.assertEqual(dependencies.call_count, int(not ui_running))
                self.assertEqual(create_job.call_count, int(bool(expected)))
                self.assertEqual(job.close.call_count, int(bool(expected)))
                self.assertEqual(
                    [call.args[0] for call in ready.call_args_list],
                    [
                        "http://127.0.0.1:8055/health/ready",
                        "http://127.0.0.1:3000/health/ready?api_port=8055",
                    ],
                )
                for process in owned:
                    process.wait.assert_called_once_with(timeout=10)

    def test_both_running_normal_launch_returns_without_owning_existing_services(self):
        with (
            patch.object(sys, "argv", ["platform_web.py"]),
            patch.object(sys, "platform", "win32"),
            patch.object(launcher, "preflight", return_value=8000),
            patch.object(launcher, "verify_training"),
            patch.object(launcher, "is_running", return_value=True),
            patch.object(launcher, "WindowsJob") as job,
            patch.object(launcher, "start_child") as start,
            patch.object(launcher, "wait_ready") as ready,
            patch("sys.stdout", new=io.StringIO()),
        ):
            self.assertEqual(launcher.main(), 0)
        self.assertEqual(ready.call_count, 2)
        job.assert_not_called()
        start.assert_not_called()

    def test_unhealthy_existing_api_is_not_restarted(self):
        with (
            patch.object(sys, "argv", ["platform_web.py", "--check"]),
            patch.object(sys, "platform", "win32"),
            patch.object(launcher, "preflight", return_value=8000),
            patch.object(launcher, "verify_training"),
            patch.object(launcher, "is_running", return_value=True),
            patch.object(launcher, "WindowsJob") as job,
            patch.object(launcher, "start_child") as start,
            patch.object(
                launcher,
                "wait_ready",
                side_effect=launcher.StartupError("API unavailable"),
            ),
            patch("sys.stdout", new=io.StringIO()),
        ):
            self.assertEqual(launcher.main(), 1)
        job.assert_not_called()
        start.assert_not_called()

    def test_ui_failure_with_reused_api_cleans_up_only_new_ui(self):
        ui, job = Mock(), Mock()
        with (
            patch.object(sys, "argv", ["platform_web.py", "--check"]),
            patch.object(sys, "platform", "win32"),
            patch.object(launcher, "preflight", return_value=8000),
            patch.object(launcher, "verify_training"),
            patch.object(launcher, "is_running", side_effect=[True, False]),
            patch.object(launcher, "ui_dependencies", return_value="node"),
            patch.object(launcher, "WindowsJob", return_value=job),
            patch.object(launcher, "start_child", return_value=ui) as start,
            patch.object(
                launcher,
                "wait_ready",
                side_effect=[None, launcher.StartupError("UI failed")],
            ),
            patch("sys.stdout", new=io.StringIO()),
        ):
            self.assertEqual(launcher.main(), 1)
        self.assertEqual(start.call_args.args[1], "ui")
        start.assert_called_once()
        job.close.assert_called_once()
        ui.wait.assert_called_once()

    def test_ctrl_c_stops_only_the_new_service(self):
        api, job = Mock(), Mock()
        with (
            patch.object(sys, "argv", ["platform_web.py"]),
            patch.object(sys, "platform", "win32"),
            patch.object(launcher, "preflight", return_value=8000),
            patch.object(launcher, "verify_training"),
            patch.object(launcher, "is_running", side_effect=[False, True]),
            patch.object(launcher, "WindowsJob", return_value=job),
            patch.object(launcher, "start_child", return_value=api) as start,
            patch.object(launcher, "wait_ready"),
            patch.object(launcher, "check_processes", side_effect=KeyboardInterrupt),
            patch("sys.stdout", new=io.StringIO()),
        ):
            self.assertEqual(launcher.main(), 0)
        self.assertEqual(start.call_args.args[1], "api")
        start.assert_called_once()
        job.close.assert_called_once()
        api.wait.assert_called_once()

    def test_ui_requires_matching_service_identity(self):
        for service, matches in [("pms_web", True), ("unrelated", False)]:
            with self.subTest(service=service):
                response = Response({"service": service, "status": "ready"})
                with patch.object(launcher.OPENER, "open", return_value=response):
                    if matches:
                        launcher.wait_ready(
                            "http://127.0.0.1:3000/health/ready?api_port=8000", []
                        )
                    else:
                        with self.assertRaisesRegex(
                            launcher.StartupError, "compatible platform web UI"
                        ):
                            launcher.wait_ready(
                                "http://127.0.0.1:3000/health/ready?api_port=8000", []
                            )

    def test_ui_api_mismatch_reports_actionable_error_without_raw_configuration(self):
        response = Response(
            {
                "service": "pms_web",
                "reason": "api_mismatch",
                "private": "must-not-appear",
            },
            503,
        )
        with (
            patch.object(launcher.OPENER, "open", return_value=response),
            self.assertRaisesRegex(
                launcher.StartupError, "matching PMS_API_BASE_URL"
            ) as error,
        ):
            launcher.wait_ready("http://127.0.0.1:3000/health/ready?api_port=8001", [])
        self.assertNotIn("must-not-appear", str(error.exception))

    def test_old_ui_without_health_route_is_not_reused(self):
        with (
            patch.object(launcher.OPENER, "open", return_value=Response({}, 404)),
            self.assertRaisesRegex(
                launcher.StartupError, "Restart its owner from this checkout"
            ),
        ):
            launcher.wait_ready("http://127.0.0.1:3000/health/ready?api_port=8000", [])

    def test_redirecting_listener_cannot_borrow_another_services_identity(self):
        paths = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                paths.append(self.path)
                self.send_response(302)
                self.send_header("Location", "/actual-platform-service")
                self.end_headers()

            def log_message(self, *args):
                pass

        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with self.assertRaisesRegex(launcher.StartupError, "redirected"):
                    launcher.wait_ready(
                        f"http://127.0.0.1:{server.server_port}/health/ready",
                        [],
                        api=True,
                    )
                self.assertEqual(paths, ["/health/ready"])
            finally:
                server.shutdown()
                thread.join(timeout=5)

    def test_non_object_api_response_does_not_crash_readiness_probe(self):
        with (
            patch.object(
                launcher.OPENER,
                "open",
                side_effect=[
                    Response([]),
                    Response({"status": "ready", "service": "pms_api"}),
                ],
            ),
            patch.object(launcher.time, "sleep"),
        ):
            launcher.wait_ready("http://127.0.0.1:8000/health/ready", [], api=True)

    @unittest.skipUnless(sys.platform == "win32", "Windows process jobs")
    def test_job_closes_descendants_and_leaves_unrelated_listener_alive(self):
        with socket.socket() as unrelated, socket.socket() as reservation:
            unrelated.bind(("127.0.0.1", 0))
            unrelated.listen()
            reservation.bind(("127.0.0.1", 0))
            child_port = reservation.getsockname()[1]
        # Reopen the unrelated listener to verify it survives job cleanup.
        with socket.socket() as unrelated:
            unrelated.bind(("127.0.0.1", 0))
            unrelated.listen()
            job = launcher.WindowsJob()
            command = (
                "import sys,subprocess,time; sys.stdin.buffer.read(1); "
                f"subprocess.Popen([sys.executable,'-m','http.server','{child_port}','--bind','127.0.0.1']); "
                "time.sleep(60)"
            )
            process = subprocess.Popen(
                [sys.executable, "-c", command],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            try:
                job.add(process)
                process.stdin.write(b"1")
                process.stdin.close()
                deadline = time.monotonic() + 10
                while True:
                    try:
                        with socket.create_connection(
                            ("127.0.0.1", child_port), timeout=0.2
                        ):
                            break
                    except OSError:
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(0.05)
                job.close()
                process.wait(timeout=10)
                deadline = time.monotonic() + 10
                while True:
                    try:
                        with socket.create_connection(
                            ("127.0.0.1", child_port), timeout=0.2
                        ):
                            pass
                    except OSError:
                        break
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.05)
                self.assertGreater(unrelated.fileno(), 0)
            finally:
                job.close()
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
