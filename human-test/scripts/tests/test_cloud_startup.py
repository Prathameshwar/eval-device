import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import connection_startup as model_startup  # noqa: E402
import demo  # noqa: E402


@pytest.mark.parametrize(
    "audio,llm", [("local", "local"), ("local", "cloud"), ("cloud", "local"), ("cloud", "cloud")]
)
def test_only_required_local_services(audio, llm):
    assert model_startup.required_services({"audio": {"mode": audio}, "llm": {"mode": llm}}) == {
        "audio": audio == "local",
        "llm": llm == "local",
    }


@pytest.mark.parametrize(
    "mode,provider", [("local", "local_whisper"), ("cloud", "azure_openai"), ("cloud", "aws")]
)
def test_disabled_speech_requires_no_companion_or_provider(mode, provider):
    selected = {
        "mode": "local",
        "cloud_allowed": False,
        "azure_enabled": False,
        "speech_enabled": False,
        "audio": {"mode": mode, "provider": provider, "enabled": False, "model": "uninstalled"},
        "llm": {"mode": "local", "provider": "local_llama_cpp", "requires_external": False},
    }
    assert model_startup.required_services(selected) == {"audio": False, "llm": True}
    model_startup.check_enablement(selected)
    assert model_startup.capture_language(selected) == "en"


@pytest.mark.parametrize("arguments,expected", [([], None), (["--processing-mode", "cloud"], "cloud")])
def test_startup_does_not_read_backend_presets(monkeypatch, tmp_path, arguments, expected):
    # Even invalid obsolete metadata must not prevent central API startup or --help.
    (tmp_path / "start").mkdir()
    (tmp_path / "start/cloud-models.json").write_text("not JSON")
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    monkeypatch.setenv("PMS_PROCESSING_MODE", "invalid-backend-value")
    monkeypatch.setattr(sys, "argv", ["demo.py", "--check", *arguments])
    selected = []

    def launcher(*args, **kwargs):
        selected.append(kwargs["processing_mode"])
        return SimpleNamespace(start=lambda: {}, close=lambda: None)

    monkeypatch.setattr(demo, "Demo", launcher)
    demo.main()
    assert selected == [expected]


def test_loopback_compatible_route_does_not_require_external_calls():
    route = {
        "mode": "custom",
        "cloud_allowed": False,
        "audio": {"mode": "local"},
        "llm": {"mode": "cloud", "provider": "openai_compatible", "requires_external": False},
    }
    model_startup.check_enablement(route)
    route["llm"]["requires_external"] = True
    with pytest.raises(RuntimeError, match="PMS_EXTERNAL_CALLS_ENABLED"):
        model_startup.check_enablement(route)


@pytest.mark.parametrize(
    "field,message",
    [
        ("cloud_allowed", "PMS_EXTERNAL_CALLS_ENABLED"),
        ("llm_enabled", "PMS_LLM_ENABLED"),
        ("speech_enabled", "PMS_SPEECH_ENABLED"),
        ("azure_enabled", "platform administrator"),
    ],
)
def test_disabled_online_path_gives_actionable_startup_error(field, message):
    route = {
        "mode": "cloud",
        "cloud_allowed": True,
        "llm_enabled": True,
        "speech_enabled": True,
        "azure_enabled": True,
        "audio": {"mode": "cloud"},
        "llm": {"provider": "azure_openai"},
    }
    route[field] = False
    with pytest.raises(RuntimeError, match=message):
        model_startup.check_enablement(route)


def test_language_comes_from_published_audio_not_launcher_preset():
    assert (
        model_startup.capture_language(
            {"audio": {"mode": "local", "model": "whisper-medical-v1", "language": "auto"}}
        )
        == "en"
    )
    assert (
        model_startup.capture_language({"audio": {"mode": "cloud", "model": "speech", "language": "en"}})
        == "en"
    )


def test_model_access_gets_five_attempts_without_inference(monkeypatch):
    calls, waits = [], []

    def check():
        calls.append(1)
        raise model_startup.ReadinessFailure("fixture")

    monkeypatch.setattr(model_startup.time, "sleep", waits.append)
    with pytest.raises(RuntimeError, match="5 attempts"):
        model_startup.verify_with_retries(SimpleNamespace(verify_patient_access=check))
    assert len(calls) == 5 and waits == [1, 2, 4, 8]


def test_desktop_does_not_inherit_provider_credentials(monkeypatch):
    for key in (
        "PMS_BOOTSTRAP_LLM_API_KEY",
        "PMS_BOOTSTRAP_SPEECH_API_KEY",
        "OPENAI_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_SPEECH_KEY",
        "AZURE_CLIENT_SECRET",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.setenv(key, "fixture-private")
    monkeypatch.setenv("HUMAN_PMS_TOKEN", "stale")
    values = model_startup.desktop_environment({"HUMAN_PMS_TOKEN": "selected-staff-token"})
    assert "fixture-private" not in values.values() and values["HUMAN_PMS_TOKEN"] == "selected-staff-token"


@pytest.mark.parametrize("explicit", [False, True])
def test_all_launched_children_exclude_bootstrap_provider_keys(monkeypatch, explicit):
    secrets = {
        "PMS_BOOTSTRAP_LLM_API_KEY": "fixture-private",
        "PMS_BOOTSTRAP_SPEECH_API_KEY": "fixture-private",
        "OPENAI_API_KEY": "fixture-private",
        "AZURE_OPENAI_API_KEY": "fixture-private",
        "AZURE_SPEECH_KEY": "fixture-private",
        "AWS_SECRET_ACCESS_KEY": "fixture-private",
        "AWS_SESSION_TOKEN": "fixture-private",
        "ANTHROPIC_API_KEY": "fixture-private",
    }
    for key, value in secrets.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("HUMAN_PMS_TOKEN", "desktop-only-secret")
    launches = []
    child = SimpleNamespace(pid=1234, stdout=None)
    monkeypatch.setattr(demo.subprocess, "Popen", lambda *args, **kwargs: launches.append(kwargs) or child)
    monkeypatch.setattr(demo, "ProcessGuard", lambda process: object())
    monkeypatch.setattr(demo, "Diagnostics", lambda stream: object())
    launcher = SimpleNamespace(children=[], diagnostics={})
    demo.Demo.launch(launcher, ["fixture-service"], {**secrets, "PMS_PORT": "8011"} if explicit else None)
    assert not any(key in launches[0]["env"] for key in secrets)
    assert "HUMAN_PMS_TOKEN" not in launches[0]["env"]
    if explicit:
        assert "PMS_PORT" not in launches[0]["env"]


@pytest.mark.parametrize("status", [429, 502, 504])
def test_cloud_access_transient_status_is_retryable(status):
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json={}))
    ) as client:
        assert (
            demo.checked_json(
                client, "http://127.0.0.1/status", "Models", transient_statuses=(429, 500, 502, 503, 504)
            )
            is None
        )


def test_startup_rejects_language_without_installed_conversation_pack():
    with pytest.raises(RuntimeError, match="installed conversation pack"):
        model_startup.capture_language({"audio": {"mode": "cloud", "model": "speech", "language": "hi"}})
