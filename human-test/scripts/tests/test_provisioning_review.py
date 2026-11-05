"""Provisioning concurrency, damaged downloads and safe actionable failures."""

import queue
import threading
from types import SimpleNamespace
from unittest.mock import Mock

from test_provisioning import demo


def test_active_session_blocks_pairing_before_any_network_request(tmp_path, monkeypatch):
    import connection_window

    here = tmp_path / "human-test"
    here.mkdir()
    monkeypatch.setattr(demo, "HERE", here)
    monkeypatch.setattr(demo, "STATE", here / ".local/platform-client")
    current = demo.Demo()
    current.acquire_ownership()
    client = Mock()
    monkeypatch.setattr(connection_window, "PairingClient", client)
    events = queue.Queue()
    window = SimpleNamespace(cancelled=threading.Event(), factory=demo.Demo, events=events, emit=Mock())
    try:
        current.acquire_ownership()  # Startup keeps the existing ownership, without a gap.
        connection_window.ConnectionWindow.work(
            window, "https://example.com", "Desk", "enr_fixture", None, None
        )
        client.assert_not_called()
        assert any(kind == "error" and "already owns" in value for kind, value in events.queue)
        assert current.locked
    finally:
        current.close()
    with demo.FileLock(demo.STATE / "owner.lock", "busy"):
        pass  # All locks are released on failure/shutdown.
