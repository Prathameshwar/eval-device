"""Local reset, installer boundaries and launcher handoff without real downloads."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import demo
import external_pms
from ownership import FileLock
from provisioning import reset_connection

from human_test.connection import read_connection


def test_reset_removes_credentials_preserves_history_and_suppresses_legacy(tmp_path):
    state = tmp_path / "human-test/.local/platform-client"
    state.mkdir(parents=True)
    for name in ("human.env", "audio.env", "video.env", "config.json", "launcher.json"):
        (state / name).write_text("private fixture")
    (state / "conversation-outbox").mkdir()
    (state / "conversation-outbox/turn.json").write_text("retained")
    (tmp_path / "human-test/.env").write_text("HUMAN_PMS_TOKEN=old-fixture")
    reset_connection(tmp_path)
    assert not (state / "human.env").exists()
    assert (state / "conversation-outbox/turn.json").read_text() == "retained"
    assert read_connection(tmp_path / "human-test/.local/platform-connection/connection.json") is None
    with pytest.raises(RuntimeError, match="provisioning was cleared"):
        external_pms.load_external(tmp_path / "human-test")
    reset_connection(tmp_path)  # A repeated explicit reset is safe.


def test_reset_is_blocked_while_launcher_owns_services(tmp_path):
    state = tmp_path / "human-test/.local/platform-client"
    state.mkdir(parents=True)
    with FileLock(state / "owner.lock", "busy"):
        with pytest.raises(RuntimeError, match="Close the running"):
            reset_connection(tmp_path)
    assert not (tmp_path / "human-test/.local/platform-connection/connection.json").exists()


def test_reopen_provisioning_stops_services_before_next_window(monkeypatch):
    import connection_window

    order = []
    app = SimpleNamespace(returncode=42, poll=lambda: 42)
    instance = SimpleNamespace(
        services=SimpleNamespace(), launch=lambda *args: app, close=lambda: order.append("closed")
    )

    def launch(factory, **options):
        order.append(("setup", options["manage"]))
        return (instance, {}) if len(order) == 1 else None

    monkeypatch.setattr(connection_window, "launch", launch)
    monkeypatch.setattr(sys, "argv", ["demo.py"])
    demo.main()
    assert order == [("setup", False), "closed", ("setup", True)]


def test_provisioning_icon_closes_cleanly_only_after_confirmation(monkeypatch):
    from human_test import app

    window = SimpleNamespace(closing=False, root=object(), close=Mock(), reopen_provisioning=False)
    monkeypatch.setattr(app.messagebox, "askyesno", lambda *args, **kwargs: False)
    app.Window.open_provisioning(window)
    assert not window.reopen_provisioning
    window.close.assert_not_called()
    monkeypatch.setattr(app.messagebox, "askyesno", lambda *args, **kwargs: True)
    app.Window.open_provisioning(window)
    assert window.reopen_provisioning
    window.close.assert_called_once()
