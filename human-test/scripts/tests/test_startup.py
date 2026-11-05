import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import demo  # noqa: E402
import startup  # noqa: E402


def test_failed_child_is_reported_immediately():
    child = SimpleNamespace(poll=lambda: 7, returncode=7)
    with pytest.raises(RuntimeError, match="Video exited during startup.*7"):
        startup.wait_ready(lambda: False, name="Video", process=child)


@pytest.mark.parametrize(
    "status,body",
    [
        (401, b"private secret"),
        (302, b"private redirect"),
        (200, b"not json"),
        (200, b"[]"),
        (200, b"x" * 131073),
    ],
    ids=["unauthorized", "redirect", "invalid-json", "wrong-shape", "oversized"],
)
def test_incompatible_http_response_fails_without_disclosing_body(status, body):
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(status, content=body))
    ) as client:
        with pytest.raises(RuntimeError) as error:
            startup.checked_json(client, "http://127.0.0.1/health", "Audio")
        assert "private" not in str(error.value)


def test_warming_http_response_can_be_rechecked():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as client:
        assert startup.checked_json(client, "http://127.0.0.1/health", "Qwen") is None


def test_close_stops_only_owned_processes():
    instance = demo.Demo()
    stopped = []
    process = SimpleNamespace(pid=100, wait=lambda timeout: None)
    instance.children = [(process, SimpleNamespace(close=lambda: stopped.append("owned")))]
    instance.close()
    assert stopped and set(stopped) == {"owned"}


def test_cleanup_continues_after_one_stop_error_and_closes_log(monkeypatch, tmp_path):
    instance = demo.Demo()
    monkeypatch.setattr(demo, "STATE", tmp_path)
    instance.locked = True
    released = []
    instance.lock = SimpleNamespace(__exit__=lambda *args: released.append(True))
    instance.open_log()
    calls = []

    def close_guard():
        calls.append(1)
        if len(calls) == 1:
            raise OSError("fixture")

    instance.children = [
        (SimpleNamespace(pid=100, wait=lambda timeout: None), SimpleNamespace(close=close_guard))
    ]
    instance.close()
    assert released == [True] and not instance.children and len(calls) == 2
    assert startup.reporter is None and instance.log_handler.stream is None


def test_second_launch_reports_stopped_owner_without_waiting(monkeypatch, tmp_path):
    instance = demo.Demo()
    monkeypatch.setattr(demo, "STATE", tmp_path)
    try:
        with pytest.raises(RuntimeError, match="first launcher stopped"):
            instance.reuse_running()
    finally:
        instance.close()


def test_client_has_no_database_provisioning_or_access():
    instance = demo.Demo()
    try:
        assert not hasattr(instance, "database")
        assert not hasattr(instance, "db_url")
        assert not hasattr(instance, "verify_database")
        assert not instance.children
    finally:
        instance.close()


def test_desktop_crash_during_recovery_is_not_reported_as_success(monkeypatch):
    import connection_window

    app = SimpleNamespace(returncode=9, poll=lambda: None)
    closed = []
    services = SimpleNamespace(monitor=lambda: (_ for _ in ()).throw(startup.StopRequested()))
    instance = SimpleNamespace(
        start=lambda: {},
        services=services,
        launch=lambda *a: app,
        check_children=lambda **kw: None,
        close=lambda: closed.append(True),
        failed=False,
    )
    monkeypatch.setattr(demo, "Demo", lambda *a, **kw: instance)
    monkeypatch.setattr(connection_window, "launch", lambda *a, **kw: (instance, {}))
    monkeypatch.setattr(sys, "argv", ["demo.py"])
    with pytest.raises(RuntimeError, match="Human-test exited unexpectedly"):
        demo.main()
    assert instance.failed and closed == [True]
