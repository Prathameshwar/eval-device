"""Human-test client: platform enrollment and existing inference connections."""

import argparse
import json
import logging
import os
import secrets
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx
from training_contracts.privacy import no_link, private_directory

from human_test.connection import DEFAULT_PLATFORM

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "human-test"
STATE = HERE / ".local/platform-client"

sys.path.insert(0, str(HERE / "scripts"))
import startup  # noqa: E402
from diagnostics import Diagnostics  # noqa: E402
from ownership import FileLock  # noqa: E402
from process_guard import ProcessGuard  # noqa: E402
from startup import AlreadyRunning, StopRequested, checked_json, message, wait_ready  # noqa: E402
from supervisor import Supervisor  # noqa: E402


def private_file(path, content):
    if path.exists():
        no_link(path)
    with path.open("w", encoding="utf-8") as stream:
        private_directory(path)
        stream.write(content)


def env_file(path, values):
    private_file(
        path, "".join(k + "=" + json.dumps(str(v), ensure_ascii=False) + "\n" for k, v in values.items())
    )


class Demo:
    def __init__(self, profile="standard", include_video=False, audio_device="auto", processing_mode=None):
        if profile not in ("standard", "medical"):
            raise ValueError("Unsupported demo profile")
        self.profile = profile
        self.external_api = True
        self.pms_url = DEFAULT_PLATFORM
        self.external_settings = None
        self.session_binding = None
        self.processing_mode = processing_mode
        self.route = None
        self.include_video = include_video
        self.audio_model = "whisper-medical-v1" if profile == "medical" else "large-v3"
        self.audio_device = None
        self.children = []
        self.http = httpx.Client(trust_env=False, follow_redirects=False, timeout=5)
        self.locked = False
        self.lock = None
        self.config = None
        self.diagnostics = {}
        self.logger = self.log_handler = None
        self.last_status = None
        self.failed = False
        self.services = Supervisor(state=self.status)

    def status(self, state, phase=None):
        if not self.locked or self.last_status == (state, phase):
            return
        private_file(
            STATE / "launcher.json",
            json.dumps(
                {
                    "version": 1,
                    "pid": os.getpid(),
                    "profile": self.profile,
                    "video": self.include_video,
                    "audio_device": self.audio_device,
                    "processing_mode": self.processing_mode,
                    "model_route": self.route,
                    "external_api": self.external_api,
                    "session_binding": self.session_binding,
                    "pms_url": self.pms_url,
                    "organization_id": self.config.get("organization_id") if self.config else None,
                    "state": state,
                    "phase": phase,
                    "updated_at": time.time(),
                }
            ),
        )
        self.last_status = (state, phase)

    def open_log(self):
        if self.log_handler is not None:
            return
        path = STATE / "launcher.log"
        for candidate in (path, path.with_name("launcher.log.1"), path.with_name("launcher.log.2")):
            if candidate.exists():
                no_link(candidate)
                private_directory(candidate)
        self.log_handler = RotatingFileHandler(path, maxBytes=262144, backupCount=2, encoding="utf-8")
        private_directory(path)
        session = secrets.token_hex(6)
        self.log_handler.setFormatter(
            logging.Formatter(f"%(asctime)s %(levelname)s session={session} %(message)s")
        )
        self.logger = logging.getLogger(f"human_test.launcher.{os.getpid()}")
        self.logger.propagate = False
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(self.log_handler)
        startup.reporter = lambda state, detail: self.logger.log(
            logging.ERROR
            if state in ("ERROR", "FAIL")
            else logging.WARNING
            if state == "WARN"
            else logging.INFO,
            "[%s] %s",
            state,
            detail,
        )
        startup.failure_reporter = lambda stage, trace: self.logger.error("Failure in %s\n%s", stage, trace)
        self.logger.info(
            "Desktop runtime Python %s; private_runtime=%s",
            sys.version.split()[0],
            Path(sys.executable).is_relative_to(HERE / ".venv"),
        )

    def launch(self, args, env=None):
        from runtime_environment import client_environment, provider_free_environment

        process = subprocess.Popen(
            [str(a) for a in args],
            cwd=HERE,
            env=client_environment() if env is None else provider_free_environment(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            guard = ProcessGuard(process)
        except BaseException:
            try:
                process.terminate()
                process.wait(10)
            finally:
                if process.poll() is not None and process.stdout:
                    process.stdout.close()
            raise
        self.children.append((process, guard))
        self.diagnostics[process.pid] = Diagnostics(process.stdout)
        return process

    def diagnose(self, process):
        diagnostic = self.diagnostics[process.pid]
        result = diagnostic.failure(process)
        if self.logger:
            self.logger.error("Service pid=%s category=%s\n%s", process.pid, result[0], diagnostic.trace())
        return result

    def stop_child(self, process):
        child = next((item for item in self.children if item[0] is process), None)
        if child is None:
            raise RuntimeError("Refusing to stop a process not owned by this launcher")
        stop_group = getattr(child[1], "terminate_and_wait", child[1].close)
        stop_group()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Could not confirm an owned process stopped; recovery was cancelled") from None
        diagnostic = self.diagnostics.pop(process.pid, None)
        if diagnostic:
            diagnostic.close()
        self.children.remove(child)

    def load_config(self):
        from external_pms import load_external, session_binding

        self.external_settings = self.external_settings or load_external(HERE)
        self.pms_url = self.external_settings.pms_url
        self.session_binding = session_binding(self.external_settings)
        self.acquire_ownership()
        self.open_log()
        self.status("starting")
        message("INFO", "Private operational log: human-test/.local/platform-client/launcher.log")
        path = STATE / "config.json"
        if path.exists():
            no_link(path)
            self.config = json.loads(path.read_text(encoding="utf-8"))
            if self.config.get("purpose") != "external-human-test-v1":
                raise RuntimeError("Unexpected Human-test desktop state")
        else:
            self.config = {"purpose": "external-human-test-v1"}
            private_file(path, json.dumps(self.config, indent=2))
        self.token = self.external_settings.pms_token.get_secret_value()
        self.config["organization_id"] = str(self.external_settings.organization_id)

    def acquire_ownership(self):
        """Own the desktop connection before enrollment can replace credentials."""
        if self.locked:
            return
        for folder in (HERE / ".local", STATE):
            if folder.exists():
                no_link(folder)
            folder.mkdir(exist_ok=True)
            private_directory(folder)
        self.lock = FileLock(STATE / "owner.lock", "Human-test is already running")
        try:
            self.lock.__enter__()
        except RuntimeError:
            raise AlreadyRunning("A Human-test window already owns this device connection") from None
        self.locked = True
        self.open_log()

    def model_ready(self):
        from local_model_client import Connection

        Connection(
            state=self.external_settings.local_models_state_dir, port=self.external_settings.local_models_port
        ).require("llm", self.route["llm"]["model"])
        return True

    def audio_ready(self):
        from local_model_client import Connection

        Connection(
            state=self.external_settings.local_models_state_dir, port=self.external_settings.local_models_port
        ).require("asr", self.route["audio"]["model"])
        return True

    def pms_ready(self):
        data = checked_json(self.http, self.pms_url + "/api/v1/health/ready", "PMS API")
        return data is not None and data.get("status") == "ready" and data.get("service") == "pms_api"

    def verify_patient_access(self):
        from connection_startup import verify

        return verify(self)

    def start(self):
        """Connect to the services selected by the published platform profile."""
        from connection_startup import start

        return start(self)

    def reuse_running(self):
        message("REUSE", "A Human-test window already owns this connection. Waiting for readiness.")

        def existing_ready():
            owner = FileLock(STATE / "owner.lock", "busy")
            try:
                owner.__enter__()
            except RuntimeError:
                pass
            else:
                owner.__exit__(None, None, None)
                raise RuntimeError(
                    "The first launcher stopped before readiness; review its error and launch again"
                )
            path = STATE / "launcher.json"
            if not path.exists():
                return False
            no_link(path)
            if path.stat().st_size > 131072:
                raise RuntimeError("Unexpected launcher status; existing processes were left running")
            try:
                status = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                return False  # Owner may be replacing its bounded status document.
            if status.get("profile") != self.profile or (self.include_video and not status.get("video")):
                raise RuntimeError(
                    "Existing launcher uses a different profile; use its window or close it first"
                )
            if self.external_api and (
                not status.get("external_api")
                or status.get("pms_url") != self.pms_url
                or status.get("organization_id") != str(self.external_settings.organization_id)
            ):
                raise RuntimeError("Existing Human-test uses another API or tenant; close its window first")
            if not self.session_binding or status.get("session_binding") != self.session_binding:
                raise RuntimeError(
                    "Existing Human-test uses another login, department or device; close its window first"
                )
            if status.get("state") != "ready":
                return False
            device = status.get("audio_device")
            if device not in {"cpu", "cuda", "cloud"}:
                raise RuntimeError("Close the older Human-test window and reconnect")
            self.audio_device = device
            self.route = status.get("model_route")
            if self.route:
                self.processing_mode = self.route["mode"]
                self.audio_model = self.route["audio"]["model"]
            return True

        # A second launch must allow the owner to finish its connection readiness budget.
        wait_ready(
            existing_ready,
            30,
            "Existing launcher",
        )
        for filename in ("config.json", "human.env"):
            no_link(STATE / filename)
        self.config = json.loads((STATE / "config.json").read_text(encoding="utf-8"))
        self.token = self.external_settings.pms_token.get_secret_value()
        self.config["organization_id"] = str(self.external_settings.organization_id)
        from external_pms import check_running_profile

        check_running_profile(self)
        from connection_startup import required_services

        required = required_services(self.route) if self.route else {"llm": True, "audio": True}
        for name, check in (
            ("LLM model server", self.model_ready),
            ("Audio API", self.audio_ready),
            ("PMS API", self.pms_ready),
        ):
            if (name == "LLM model server" and not required["llm"]) or (
                name == "Audio API" and not required["audio"]
            ):
                continue
            wait_ready(check, 15, name)
            message("REUSE", name + " verified; no restart")
        self.verify_patient_access()
        message("READY", "All requested services are already running. Use the existing human-test window.")

    def check_children(self, ignore=None):
        for process, _ in self.children:
            if process is not ignore and process.poll() is not None:
                code, _, hint = self.diagnose(process)
                raise RuntimeError(f"Human-test window exited: {code}. {hint}")

    def close(self):
        errors = []
        if self.locked:
            message("STOP", "Closing the Human-test window; central model services continue running")
        for process, _ in list(reversed(self.children)):
            try:
                self.stop_child(process)
            except Exception as error:
                startup.record_failure("Stop owned desktop window", error)
                errors.append("Could not confirm an owned desktop process stopped")
        for process, _ in list(reversed(self.children)):
            try:
                self.stop_child(process)
            except Exception as error:
                startup.record_failure("Retry stopping desktop process", error)
                errors.append("Could not confirm an owned process stopped")
        if errors and not self.children:
            message("WARN", "Cleanup completed after retrying an owned process stop")
            errors.clear()
        try:
            self.http.close()
        except Exception as error:
            startup.record_failure("Close desktop HTTP client", error)
            errors.append("Could not close the desktop HTTP client")
        if self.locked:
            try:
                try:
                    self.status("failed" if self.failed or errors else "stopped")
                except Exception as error:
                    startup.record_failure("Update launcher status", error)
                    errors.append("Could not update the private launcher status")
                try:
                    self.lock.__exit__(None, None, None)
                except Exception as error:
                    startup.record_failure("Release launcher lock", error)
                    errors.append("Could not release the launcher lock")
                message(
                    "ERROR" if errors or self.failed else "DONE",
                    errors[0]
                    if errors
                    else "Local launch failed; see diagnostic entries above"
                    if self.failed
                    else "Local launch session closed",
                )
            finally:
                self.locked = False
                startup.reporter = None
                startup.failure_reporter = None
                if self.log_handler:
                    self.logger.removeHandler(self.log_handler)
                    self.log_handler.close()
        if errors:
            raise RuntimeError("Cleanup could not confirm every owned process stopped; check launcher.log")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("standard", "medical"), default="standard")
    parser.add_argument("--connect", action="store_true", help="Pair this desktop with a device")
    parser.add_argument(
        "--all-services",
        action="store_true",
        help="Deprecated compatibility option; camera capture remains in Human-test",
    )
    parser.add_argument(
        "--external-api",
        action="store_true",
        help="Use human-test/.env; never start or configure PostgreSQL, PMS API or retention",
    )
    parser.add_argument(
        "--processing-mode",
        choices=("local", "cloud", "custom"),
        default=None,
        help="Deprecated, ignored; select models through the central API published profile",
    )
    parser.add_argument(
        "--audio-device",
        choices=("auto", "cpu", "cuda"),
        default="auto",
        help="Deprecated; choose compute in Manage Local Models",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify connections without opening the screen or changing model services",
    )
    args = parser.parse_args()

    def factory():
        return Demo(
            args.profile,
            include_video=args.all_services,
            audio_device=args.audio_device,
            processing_mode=args.processing_mode,
        )

    manage = False
    while True:
        if not run_desktop(args, factory, manage=manage):
            return
        manage = True


def run_desktop(args, factory, *, manage=False):
    prepared = None
    if not args.check:
        from connection_window import launch

        prepared = launch(factory, force=args.connect and not manage, manage=manage)
        if prepared is None:
            return
    demo = prepared[0] if prepared else factory()
    app = None
    try:
        try:
            values = prepared[1] if prepared else demo.start()
        except AlreadyRunning:
            demo.reuse_running()
            return
        if args.check:
            message(
                "PASS", "All assigned model connections passed readiness checks; human-test was not opened"
            )
            return
        from connection_startup import desktop_environment

        env = desktop_environment(values)
        message("OPEN", "Human-test: choose the practice setup, save, then start the microphone")
        message(
            "INFO",
            "Keep this console open. Closing Human-test leaves central inference running; Ctrl+C closes this client.",
        )
        app = demo.launch([HERE / ".venv/Scripts/python.exe", "-X", "utf8", "-m", "human_test.app"], env)
        demo.services.cancelled = lambda: app.poll() is not None
        while app.poll() is None:
            demo.check_children(ignore=app)
            demo.services.monitor()
            time.sleep(0.5)
        if app.returncode == 42:
            return True
        if app.returncode:
            raise RuntimeError(
                "Human-test exited unexpectedly; check human-test dependencies and configuration"
            )
    except StopRequested:
        if app is not None and app.returncode == 42:
            return True
        if app is not None and app.returncode not in (None, 0):
            demo.failed = True
            message("ERROR", "Human-test exited unexpectedly during connection monitoring")
            raise RuntimeError(
                "Human-test exited unexpectedly; inspect the desktop setup before relaunching"
            ) from None
        message("STOP", "Human-test closed during connection monitoring")
    except Exception as error:
        demo.failed = True
        startup.record_failure("Desktop startup or connection monitoring", error)
        message("ERROR", str(error) if isinstance(error, RuntimeError) else type(error).__name__)
        raise
    finally:
        active_error = sys.exc_info()[0] is not None
        try:
            demo.close()
        except Exception:
            if not active_error:
                raise
            message("ERROR", "Cleanup also encountered an error; the original failure is preserved above")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print(
            "Human-test startup failed: "
            + (str(error) if isinstance(error, RuntimeError) else type(error).__name__),
            flush=True,
        )
        raise SystemExit(1) from None
