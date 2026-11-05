"""Startup failures remain diagnosable without retaining credentials or media."""

import io
import json
import queue
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import connection_window  # noqa: E402
import demo  # noqa: E402
import startup  # noqa: E402
from diagnostics import Diagnostics  # noqa: E402


def test_structural_trace_preserves_cause_and_codes_without_sensitive_text():
    secret = "Bearer private-credential https://private.example/signed?sig=private patient words"
    try:
        try:
            raise PermissionError(13, secret, secret)
        except PermissionError as error:
            raise RuntimeError(secret) from error
    except RuntimeError as error:
        trace = startup.failure_details(error)
    assert "RuntimeError" in trace and "PermissionError errno=13" in trace
    assert "test_setup_diagnostics.py:" in trace
    assert "private" not in trace and "Bearer" not in trace and "patient words" not in trace


def test_rotated_log_records_real_levels_and_failure_state(monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "STATE", tmp_path)
    instance = demo.Demo()
    instance.locked = True
    instance.lock = SimpleNamespace(__exit__=lambda *args: None)
    instance.open_log()
    handler = instance.log_handler
    instance.open_log()
    assert instance.log_handler is handler and instance.logger.handlers.count(handler) == 1
    startup.message("WARN", "Safe warning")
    try:
        with startup.phase("Validate assigned assets"):
            raise ValueError("private-token-should-not-be-logged")
    except ValueError:
        instance.failed = True
    instance.close()
    log = (tmp_path / "launcher.log").read_text(encoding="utf-8")
    assert "WARNING session=" in log and "ERROR session=" in log
    assert "Validate assigned assets: failed after" in log and "exception=ValueError" in log
    assert "private-token" not in log and "Local launch session closed" not in log
    assert json.loads((tmp_path / "launcher.json").read_text())["state"] == "failed"
    assert startup.reporter is None and startup.failure_reporter is None


def test_child_trace_is_bounded_and_discards_messages_paths_and_source():
    data = b'  File "C:\\private-user\\service.py", line 12, in start\n'
    data += b'    token = "private-token"\nModuleNotFoundError: private-token\n'
    data += b"private patient transcript signed-url\n"
    value = Diagnostics(io.BytesIO(data))
    process = SimpleNamespace(poll=lambda: 1)
    assert value.failure(process)[0] == "dependency_missing"
    trace = value.trace()
    assert "service.py:12 in start" in trace and "exception=ModuleNotFoundError" in trace
    assert "private" not in trace and "token" not in trace
    value.close()


def test_http_cleanup_failure_still_releases_owner_and_closes_log(monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "STATE", tmp_path)
    instance = demo.Demo()
    instance.locked = True
    released = []
    instance.lock = SimpleNamespace(__exit__=lambda *args: released.append(True))
    instance.open_log()
    instance.http.close()

    def fail():
        raise OSError(13, "private-client-token")

    instance.http = SimpleNamespace(close=fail)
    with pytest.raises(RuntimeError, match="Cleanup"):
        instance.close()
    assert released == [True] and not instance.locked and instance.log_handler.stream is None
    text = (tmp_path / "launcher.log").read_text(encoding="utf-8")
    assert "Close desktop HTTP client" in text and "errno=13" in text
    assert "private-client-token" not in text


@pytest.mark.parametrize("cancel", [False, True])
def test_setup_worker_records_failure_and_cleanup_cannot_replace_ui_error(monkeypatch, cancel):
    logs = []
    monkeypatch.setattr(startup, "failure_reporter", lambda stage, trace: logs.append((stage, trace)))
    closed = []
    value = SimpleNamespace(acquire_ownership=lambda: None, services=SimpleNamespace(), failed=False)

    def fail():
        if cancel:
            raise startup.StopRequested()
        raise ValueError("private-token")

    value.start = fail
    value.close = lambda: (closed.append(True), startup.message("DONE", "Local launch session closed"))
    window = connection_window.ConnectionWindow.__new__(connection_window.ConnectionWindow)
    window.cancelled = threading.Event()
    window.factory = lambda: value
    window.events = queue.Queue()
    window.emit = lambda detail: window.events.put(("progress", detail))
    window.work("", "", "", None, SimpleNamespace())
    events = list(window.events.queue)
    assert closed == [True] and events[-1] == ("finished", None)
    assert ("progress", "Local launch session closed") not in events
    if cancel:
        assert not value.failed and not logs and not any(kind == "error" for kind, _ in events)
    else:
        assert value.failed and "exception=ValueError" in logs[0][1]
        assert "launcher.log" in next(text for kind, text in events if kind == "error")
        assert not any("private-token" in str(event) for event in events)
