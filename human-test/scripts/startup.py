"""Bounded local startup checks; never terminate an existing listener."""

import json
import re
import socket
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

import httpx


class AlreadyRunning(RuntimeError):
    pass


class ReadinessFailure(RuntimeError):
    pass


class StopRequested(Exception):
    pass


reporter = None
progress_reporter = None
failure_reporter = None


def failure_details(error):
    """Structural traces only: never exception messages, source lines or locals."""
    root = Path(__file__).resolve().parents[2]
    seen = set()
    details = []
    while error is not None and id(error) not in seen and len(seen) < 4:
        seen.add(id(error))
        kind = re.sub(r"[^A-Za-z0-9_.]", "_", type(error).__name__)[:80]
        codes = "".join(
            f" {name}={value}"
            for name in ("errno", "winerror")
            if isinstance(value := getattr(error, name, None), int)
        )
        details.append(f"exception={kind}{codes}")
        for frame in traceback.extract_tb(error.__traceback__)[-24:]:
            path = Path(frame.filename)
            try:
                relative = path.relative_to(root) if path.is_absolute() else path
            except ValueError:
                relative = Path(path.name)
            # Omit unknown filenames; a user-controlled filename may contain a secret.
            if relative.suffix in (".py", ".pyx") and all(
                re.fullmatch(r"[A-Za-z0-9_.-]+", part) and part != ".." for part in relative.parts
            ):
                function = re.sub(r"[^A-Za-z0-9_.<>]", "_", frame.name)[:80]
                details.append(f"  at {relative.as_posix()}:{frame.lineno} in {function}")
        error = error.__cause__ or error.__context__
    return "\n".join(details)


def record_failure(stage, error):
    if failure_reporter is not None:
        failure_reporter(stage, failure_details(error))


@contextmanager
def phase(name):
    started = time.monotonic()
    message("CHECK", name)
    try:
        yield
    except StopRequested:
        message("STOP", f"{name}: cancelled after {time.monotonic() - started:.2f}s")
        raise
    except Exception as error:
        record_failure(name, error)
        message("ERROR", f"{name}: failed after {time.monotonic() - started:.2f}s; see launcher.log")
        raise
    else:
        message("PASS", f"{name}: completed in {time.monotonic() - started:.2f}s")


def message(state, detail):
    # ANSI escape codes for professional, mature product aesthetics
    colors = {
        "READY": "\033[1;32m",  # Bold Green
        "PASS": "\033[1;32m",  # Bold Green
        "REUSE": "\033[36m",  # Cyan
        "CHECK": "\033[36m",  # Cyan
        "START": "\033[1;34m",  # Bold Blue
        "OPEN": "\033[1;35m",  # Bold Magenta
        "WAIT": "\033[33m",  # Yellow
        "WARN": "\033[1;33m",  # Bold Yellow
        "ERROR": "\033[1;31m",  # Bold Red
        "STOP": "\033[1;31m",  # Bold Red
        "DONE": "\033[1;32m",  # Bold Green
        "INFO": "\033[90m",  # Muted Gray
    }
    reset = "\033[0m"
    color = colors.get(state, "")
    aligned_state = f"{state:<7}"
    print(f"{color}[{aligned_state}]{reset} {detail}", flush=True)
    if reporter is not None:
        reporter(state, detail)
    if progress_reporter is not None:
        progress_reporter(state, detail)


def occupied(port):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return True
    return False


def wait_ready(check, seconds=180, name="Local service", process=None, cancelled=None):
    deadline = time.monotonic() + seconds
    notice = time.monotonic() + 5
    last_error = None
    while time.monotonic() < deadline:
        if cancelled and cancelled():
            raise StopRequested()
        if process is not None and process.poll() is not None:
            raise ReadinessFailure(
                f"{name} exited during startup (code {process.returncode}); check its setup"
            )
        try:
            if check():
                return
        except (OSError, httpx.HTTPError) as error:
            last_error = error
        if time.monotonic() >= notice:
            message("WAIT", f"{name} is still starting...")
            notice = time.monotonic() + 10
        time.sleep(0.25)
    raise ReadinessFailure(
        f"{name} did not become ready within {seconds} seconds; check its setup and port"
    ) from last_error


def checked_json(client, url, name, headers=None, *, transient_statuses=(503,)):
    # Local services only; disable redirects and bound even an incompatible listener's body.
    deadline = time.monotonic() + 8
    with client.stream("GET", url, headers=headers, timeout=5) as response:
        if response.status_code in transient_statuses:
            return None
        if response.status_code != 200:
            raise RuntimeError(
                f"{name} check returned HTTP {response.status_code}; existing service left running"
            )
        data = bytearray()
        for block in response.iter_bytes():
            data.extend(block)
            if len(data) > 131072 or time.monotonic() >= deadline:
                raise RuntimeError(f"{name} returned an unexpected response; existing service left running")
    try:
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, TypeError, RecursionError):
        raise RuntimeError(f"{name} returned invalid status data; existing service left running") from None
