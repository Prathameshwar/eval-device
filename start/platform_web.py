"""Local Windows API + Next.js launcher. No provisioning or external services."""

import argparse
import ctypes
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StartupError(Exception):
    """Only deliberately safe messages are printed by the launcher."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise StartupError(
            "A service readiness endpoint redirected to another address. "
            "Check the selected ports; existing services were left untouched."
        )


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


class WindowsJob:
    """Closing the supervisor also closes its children and their descendants."""

    def __init__(self):
        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD),
                ("min_working_set", ctypes.c_size_t),
                ("max_working_set", ctypes.c_size_t),
                ("active_processes", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class Limits(ctypes.Structure):
            _fields_ = [
                ("basic", BasicLimits),
                ("io", ctypes.c_uint64 * 6),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process_memory", ctypes.c_size_t),
                ("peak_job_memory", ctypes.c_size_t),
            ]

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self.kernel.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
        ]
        self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        limits = Limits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.kernel.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            self.close()
            raise StartupError("Windows could not create the service cleanup group.")

    def add(self, process):
        if not self.kernel.AssignProcessToJobObject(
            self.handle, wintypes.HANDLE(process._handle)
        ):
            raise StartupError(
                "Windows could not attach the service to the cleanup group."
            )

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def is_running(port):
    with socket.socket() as probe:
        probe.settimeout(0.5)
        # A bind probe can reject a free port while old HTTP connections are in TIME_WAIT.
        # Check listeners instead; the service's own exclusive bind handles startup races.
        return probe.connect_ex(("127.0.0.1", port)) == 0


def preflight(root, api_port, ui_port):
    api = root / "platform/api"
    if not (api / ".env").is_file():
        raise StartupError(
            "Missing platform/api/.env. From platform/api run 'uv run pms-admin init-local', "
            "configure PostgreSQL, then run 'uv run pms-admin init-database' and apply "
            "deploy/grant-runtime-access.sql. See platform/api/README.md."
        )
    try:
        from pms_api.core.config import Settings

        settings = Settings(_env_file=api / ".env")
    except ImportError:
        raise StartupError(
            "API dependencies are missing. Run 'uv sync --frozen' from platform/api."
        ) from None
    except Exception:  # noqa: BLE001 - configuration exceptions can contain credentials
        raise StartupError(
            "API configuration is invalid. Check platform/api/.env against .env.example; secrets are not printed."
        ) from None
    if settings.environment not in {"local", "test"}:
        raise StartupError(
            "This development launcher requires PMS_ENVIRONMENT=local or test."
        )
    api_port = api_port or settings.port
    if api_port == ui_port:
        raise StartupError("API and UI must use different ports.")
    if settings.environment == "local":
        from pms_api.security.training_keys import (
            TrainingKeyError,
            prepare_local_training,
        )

        try:
            prepare_local_training(api / ".env")
        except TrainingKeyError as error:
            raise StartupError(str(error)) from None
    return api_port


def verify_training(api_port):
    try:
        with OPENER.open(
            f"http://127.0.0.1:{api_port}/api/v1/training/verification-key", timeout=5
        ) as response:
            value = json.loads(response.read(16384))
        if value.get("algorithm") != "EdDSA" or not value.get("public_key"):
            raise ValueError()
    except Exception:
        raise StartupError(
            "Training signing is not ready in the running API. Restart the existing API to load "
            "its training-key configuration, then retry; existing services were left running."
        ) from None


def ui_dependencies(root):
    node = shutil.which("node")
    if not node:
        raise StartupError(
            "Node.js is missing from PATH. Install a supported Node.js version, then reopen the terminal."
        )
    next_cli = root / "platform/ui/node_modules/next/dist/bin/next"
    if not next_cli.is_file():
        raise StartupError(
            "UI dependencies are missing. Run 'npm ci' from platform/ui."
        )
    return node


def child_environment(kind, api_port):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    if kind == "api":
        env.update(
            PMS_BIND_HOST="127.0.0.1",
            PMS_PORT=str(api_port),
            PMS_PUBLIC_BASE_URL=f"http://127.0.0.1:{api_port}",
        )
    else:
        # The web server needs the public API endpoint, not inherited database/provider secrets.
        env = {
            key: value
            for key, value in env.items()
            if not key.upper().startswith(("PMS_", "PG", "DATABASE_URL"))
        }
        env.update(
            PMS_API_BASE_URL=f"http://127.0.0.1:{api_port}/api/v1",
            NEXT_TELEMETRY_DISABLED="1",
            NODE_ENV="development",
        )
    return env


def start_child(job, kind, api_port, ui_port, node):
    command = [
        sys.executable,
        "-X",
        "utf8",
        str(Path(__file__).resolve()),
        "--child",
        kind,
        "--ui-port",
        str(ui_port),
    ]
    env = child_environment(kind, api_port)
    if kind == "ui":
        env["PMS_LAUNCH_NODE"] = node
        env["PMS_WEB_INSTANCE"] = str(ui_port)
    process = subprocess.Popen(
        command,
        cwd=ROOT / ("platform/api" if kind == "api" else "platform/ui/apps/web"),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    try:
        job.add(process)
        # The child cannot start a service or spawn descendants until it belongs to our job.
        process.stdin.write(b"1")
        process.stdin.close()
    except BaseException:
        process.kill()
        process.wait(timeout=10)
        raise
    return process


def check_processes(processes):
    for name, process in processes:
        if process.poll() is not None:
            raise StartupError(
                f"{name} exited (code {process.returncode}). Check its configuration/dependencies using the manual command in start/README.md."
            )


def wait_ready(url, processes, *, api=False, timeout=120):
    deadline = time.monotonic() + timeout
    reason = (
        "API database readiness did not complete; check PostgreSQL and the API database configuration"
        if api
        else "the web UI did not become ready; check Node.js and UI dependencies"
    )
    while time.monotonic() < deadline:
        check_processes(processes)
        try:
            response = OPENER.open(url, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
            continue
        with response:
            try:
                data = json.loads(response.read(4096))
            except (ValueError, OSError):
                data = {}
            if not isinstance(data, dict):
                data = {}
            service = "pms_api" if api else "pms_web"
            if (
                response.status == 200
                and data.get("status") == "ready"
                and data.get("service") == service
            ):
                return
            if not api:
                if data.get("service") == service and data.get("reason") in {
                    "api_mismatch",
                    "invalid_api_configuration",
                }:
                    raise StartupError(
                        "The running web UI is not configured for the selected API. "
                        "Restart its owner with the matching PMS_API_BASE_URL, or choose a free --ui-port. "
                        "Existing services were left untouched."
                    )
                if response.status in {200, 404}:
                    raise StartupError(
                        "The UI port did not identify a compatible platform web UI. "
                        "Restart its owner from this checkout or choose a free --ui-port. "
                        "Existing services were left untouched."
                    )
            if api:
                if data.get("reason") == "schema_mismatch":
                    raise StartupError(
                        "Database schema is not current. Run 'uv run pms-admin init-database' from platform/api and reapply deploy/grant-runtime-access.sql."
                    )
                if data.get("reason") == "database_unavailable":
                    reason = "PostgreSQL is unavailable; start PostgreSQL and check the API database URL and runtime grants"
        time.sleep(0.25)
    raise StartupError("Startup timed out: " + reason + ".")


def port(value):
    number = int(value)
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("Port must be between 1 and 65535")
    return number


def main():
    parser = argparse.ArgumentParser(
        description="Reuse the running local API and web UI, starting missing services."
    )
    parser.add_argument(
        "--api-port",
        type=port,
        help="Override PMS_PORT from API configuration (default 8000)",
    )
    parser.add_argument("--ui-port", type=port, default=3000)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check both services, starting missing ones, then stop only services started here",
    )
    parser.add_argument("--child", choices=["api", "ui"], help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        if sys.stdin.buffer.read(1) != b"1":
            return 1
        if args.child == "api":
            from pms_api.cli import serve

            serve()
            return 0
        return subprocess.call(
            [
                os.environ.pop("PMS_LAUNCH_NODE"),
                str(ROOT / "platform/ui/node_modules/next/dist/bin/next"),
                "dev",
                "--turbopack",
                "--hostname",
                "127.0.0.1",
                "--port",
                str(args.ui_port),
            ]
        )
    job = None
    processes = []
    try:
        if sys.platform != "win32":
            raise StartupError(
                "Use start-platform.bat on Windows; see the README for manual commands."
            )
        api_port = preflight(ROOT, args.api_port, args.ui_port)
        if is_running(api_port):
            print(
                f"[REUSE] API already running on http://127.0.0.1:{api_port}; checking readiness",
                flush=True,
            )
        else:
            job = WindowsJob()
            print(f"[START] API on http://127.0.0.1:{api_port}", flush=True)
            processes.append(
                ("API", start_child(job, "api", api_port, args.ui_port, None))
            )
        wait_ready(f"http://127.0.0.1:{api_port}/health/ready", processes, api=True)
        verify_training(api_port)
        print("[READY] API and database schema", flush=True)
        if is_running(args.ui_port):
            print(
                f"[REUSE] Web UI already running on http://127.0.0.1:{args.ui_port}; checking readiness",
                flush=True,
            )
        else:
            node = ui_dependencies(ROOT)
            if job is None:
                job = WindowsJob()
            print(f"[START] Web UI on http://127.0.0.1:{args.ui_port}", flush=True)
            processes.append(
                ("Web UI", start_child(job, "ui", api_port, args.ui_port, node))
            )
        wait_ready(
            f"http://127.0.0.1:{args.ui_port}/health/ready?api_port={api_port}",
            processes,
        )
        print(f"[READY] Open http://127.0.0.1:{args.ui_port}", flush=True)
        print(
            f"[INFO] API readiness: http://127.0.0.1:{api_port}/health/ready",
            flush=True,
        )
        if not processes:
            print(
                "[INFO] Both services were already running; no new processes were started.",
                flush=True,
            )
        elif not args.check:
            print(
                "[INFO] Keep this console open. Ctrl+C stops only services started here; reused services stay running.",
                flush=True,
            )
            while True:
                check_processes(processes)
                time.sleep(0.5)
        return 0
    except KeyboardInterrupt:
        print("\n[STOP] Stopped by operator.", flush=True)
        return 0
    except StartupError as error:
        print("[ERROR] " + str(error), flush=True)
        return 1
    except Exception as error:  # noqa: BLE001 - never print raw startup exceptions
        print(
            f"[ERROR] Launcher failed ({type(error).__name__}); sensitive exception details were omitted.",
            flush=True,
        )
        return 1
    finally:
        if job:
            job.close()
            for _, process in processes:
                process.wait(timeout=10)
            print("[STOP] Services started by this launcher have stopped.", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
