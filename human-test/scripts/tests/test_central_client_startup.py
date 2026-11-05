"""Client startup only reads central inventory/readiness and never manages engines."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import connection_startup  # noqa: E402
import demo  # noqa: E402
import external_pms  # noqa: E402
import startup  # noqa: E402


@pytest.mark.parametrize("local", [True, False])
def test_startup_only_connects_and_cloud_works_when_manager_is_down(tmp_path, monkeypatch, local):
    import subprocess

    mode = "local" if local else "cloud"
    route = {
        "mode": mode,
        "profile_id": "fixture-profile",
        "cloud_allowed": True,
        "llm": {
            "mode": mode,
            "execution": "caller" if local else "platform",
            "model": "qwen3-1.7b-local",
            "connection_id": "fixture-llm",
        },
        "audio": {"mode": mode, "model": "large-v3", "language": "en"},
    }
    calls = []
    state = tmp_path / "central"

    class ReadOnly:
        key = "fixture-inference-only-key"

        def __init__(self, *, state, port):
            self.state = state
            assert port == 8790

        def capabilities(self):
            calls.append("capabilities")
            if not local:
                raise connection_startup.ConnectionError("Manager is stopped")
            return {"version": 1, "revision": 0, "models": [], "services": {"asr": {"device": "cuda"}}}

        def require(self, capability, model):
            calls.append((capability, model))

    settings = SimpleNamespace(
        local_models_state_dir=state,
        local_models_port=8790,
        device_token=None,
        history_enabled=True,
        department_id=None,
        device_id=None,
    )
    launcher = SimpleNamespace(
        load_config=Mock(),
        pms_ready=Mock(return_value=True),
        services=SimpleNamespace(watch=Mock(), cancelled=None),
        external_settings=settings,
        pms_url="http://fixture.invalid",
        token="fixture-platform-key",
        config={"organization_id": "fixture-org"},
        status=Mock(),
    )
    monkeypatch.setattr(connection_startup, "Connection", ReadOnly)
    monkeypatch.setattr(connection_startup, "verify_with_retries", lambda _: True)
    monkeypatch.setattr(external_pms, "published_route", lambda *_: route)
    monkeypatch.setattr(
        external_pms, "report_local_models", Mock(side_effect=AssertionError("No device credentials"))
    )
    monkeypatch.setattr(startup, "wait_ready", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(demo, "STATE", tmp_path)
    monkeypatch.setattr(demo, "env_file", Mock())
    spawn = Mock(side_effect=AssertionError("Connection startup must never spawn a model"))
    monkeypatch.setattr(subprocess, "Popen", spawn)
    values = connection_startup.start(launcher)
    assert values["HUMAN_DESKTOP_PREPARED"] == "true"
    assert values["HUMAN_LOCAL_MODELS_PORT"] == "8790"
    assert all(isinstance(value, str) for value in values.values())
    assert not any(
        name in values
        for name in ("HUMAN_LOCAL_LLM_KEY", "HUMAN_AUDIO_TOKEN", "HUMAN_MANAGED_LOCAL_SERVICES")
    )
    if local:
        assert values["HUMAN_LOCAL_MODELS_KEY"] == "fixture-inference-only-key"
        assert calls == [
            "capabilities",
            ("llm", "qwen3-1.7b-local"),
            "capabilities",
            ("asr", "large-v3"),
            "capabilities",
        ]
    else:
        assert "HUMAN_LOCAL_MODELS_KEY" not in values
        assert calls == ["capabilities"]
    launcher.services.watch.assert_called_once_with("PMS API", launcher.pms_ready)
    spawn.assert_not_called()


def test_real_launcher_status_does_not_need_removed_compute_ownership(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(demo, "STATE", tmp_path)
    launcher = demo.Demo()
    try:
        launcher.locked = True
        launcher.audio_device = "cuda"  # readiness metadata supplied by the manager
        launcher.status("ready")
        value = json.loads((tmp_path / "launcher.json").read_text(encoding="utf8"))
        assert value["state"] == "ready" and value["audio_device"] == "cuda"
        assert "audio_gpu_index" not in value
    finally:
        launcher.http.close()


def test_real_desktop_loop_only_monitors_external_connections(monkeypatch):
    import connection_window

    launcher = demo.Demo()
    polls = iter((None, None, 0))
    child = SimpleNamespace(poll=lambda: next(polls), returncode=0)
    launch = Mock(return_value=child)
    monkeypatch.setattr(launcher, "launch", launch)
    launcher.services.watch("PMS API", lambda: True)
    monkeypatch.setattr(
        connection_window, "launch", lambda *_args, **_kwargs: (launcher, {"HUMAN_DESKTOP_PREPARED": "true"})
    )
    monkeypatch.setattr(demo.time, "sleep", lambda _: None)
    result = demo.run_desktop(SimpleNamespace(check=False, connect=False), lambda: launcher)
    assert result is None and not launcher.children
    launch.assert_called_once()
    assert launcher.services.services[0].bad_checks == 0
    assert not hasattr(launcher.services, "ensure")


@pytest.mark.parametrize("port", [8790, "8790"])
def test_desktop_environment_starts_real_process_with_numeric_port(monkeypatch, tmp_path, port):
    import subprocess

    from runtime_environment import desktop_environment

    monkeypatch.setenv("OPENAI_API_KEY", "fixture-backend-secret")
    monkeypatch.setenv("PMS_DATABASE_URL", "fixture-backend-dsn")
    monkeypatch.setenv("HUMAN_LOCAL_MODELS_PORT", "old-port")
    env = desktop_environment(
        {
            "HUMAN_LOCAL_MODELS_PORT": port,
            "HUMAN_DESKTOP_PREPARED": True,
            "HUMAN_HISTORY_DIR": tmp_path,
            "HUMAN_OPTIONAL_VALUE": None,
        }
    )
    assert env["HUMAN_DESKTOP_PREPARED"] == "true"
    assert env["HUMAN_HISTORY_DIR"] == str(tmp_path)
    assert "HUMAN_OPTIONAL_VALUE" not in env
    assert "OPENAI_API_KEY" not in env and "PMS_DATABASE_URL" not in env
    result = subprocess.run(
        [sys.executable, "-c", "import os; print(os.environ['HUMAN_LOCAL_MODELS_PORT'])"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    assert result.stdout.strip() == "8790"
