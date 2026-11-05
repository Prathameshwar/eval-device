"""Client/backend boundary: shared HTTP API, no database provisioning or credentials."""

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import connection_startup as model_startup
import demo
import external_pms

ORG = "11111111-1111-4111-8111-111111111111"
PROFILE = "22222222-2222-4222-8222-222222222222"


def test_launcher_and_api_client_share_hosted_default(monkeypatch):
    monkeypatch.delenv("HUMAN_PMS_URL", raising=False)
    settings = external_pms.ExternalPMS(_env_file=None, pms_token="fixture", organization_id=ORG)
    assert settings.pms_url == "https://eval.centralindia.cloudapp.azure.com"
    instance = demo.Demo()
    try:
        assert instance.pms_url == settings.pms_url
    finally:
        instance.close()


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.invalid",
        "http://user:secret@127.0.0.1",
        "https://host/api/v1",
        "https://host/?token=secret",
        "file:///private",
    ],
)
def test_reject_unsafe_origin_without_echoing_secrets(url):
    with pytest.raises(ValueError):
        external_pms.ExternalPMS(_env_file=None, pms_url=url, pms_token="fixture", organization_id=ORG)


def test_settings_error_hides_input_and_points_to_client_config(tmp_path, monkeypatch):
    for key in tuple(__import__("os").environ):
        if key.startswith("HUMAN_"):
            monkeypatch.delenv(key)
    (tmp_path / ".env").write_text("HUMAN_PMS_URL=http://user:private@127.0.0.1\n")
    with pytest.raises(RuntimeError, match="human-test/.env") as error:
        external_pms.load_external(tmp_path)
    assert "private" not in str(error.value)


def test_missing_device_has_no_tenant_default_fallback():
    value = SimpleNamespace(
        config={"organization_id": ORG}, external_settings=SimpleNamespace(device_id=None)
    )
    with pytest.raises(RuntimeError, match="HUMAN_DEVICE_ID"):
        external_pms.published_route(value, lambda *args: pytest.fail("Legacy endpoint requested"))


def test_device_selection_follows_its_assigned_profile():
    calls = []

    def call(method, path):
        calls.append((method, path))
        return {"default_profile_id": PROFILE} if "model-options" in path else {"profile_id": PROFILE}

    value = SimpleNamespace(
        config={"organization_id": ORG},
        external_settings=SimpleNamespace(device_id=UUID(PROFILE), processing_profile_id=None),
    )
    assert external_pms.published_route(value, call)["profile_id"] == PROFILE
    assert calls == [
        ("GET", f"/organizations/{ORG}/model-config?device_id={PROFILE}"),
    ]


def test_local_inventory_rejects_a_token_for_another_device(monkeypatch, tmp_path):
    from pydantic import SecretStr

    with httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"device_id": ORG}))
    ) as http:
        value = SimpleNamespace(
            http=http,
            pms_url="https://central.example",
            external_settings=SimpleNamespace(
                device_id=UUID(PROFILE), device_token=SecretStr("other-device-token")
            ),
        )
        with pytest.raises(RuntimeError, match="different device registration"):
            external_pms.report_local_models(value, {"models": []})


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"error": {"code": "local_host_required"}}, "Update the platform API"),
        ({"error": {"code": "invalid_local_inventory"}}, "installed model names"),
        ({"error": {"code": "device_mismatch"}}, "different registration"),
        ({"error": {"code": ["untrusted"]}}, "HTTP 422"),
        ({"error": "private response"}, "HTTP 422"),
        ({"detail": "private response"}, "HTTP 422"),
    ],
)
def test_inventory_error_is_actionable_and_redacted(monkeypatch, tmp_path, payload, expected):
    from pydantic import SecretStr

    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(422, json=payload))) as http:
        value = SimpleNamespace(
            http=http,
            pms_url="https://central.example",
            external_settings=SimpleNamespace(
                device_id=UUID(PROFILE), device_token=SecretStr("private-token")
            ),
        )
        with pytest.raises(RuntimeError, match=expected) as error:
            external_pms.report_local_models(value, {"models": []})
        assert "private" not in str(error.value)


@pytest.mark.parametrize("status", [200, 422])
def test_inventory_response_is_bounded(monkeypatch, tmp_path, status):
    from pydantic import SecretStr

    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, content=b"x" * 4097))
    ) as http:
        value = SimpleNamespace(
            http=http,
            pms_url="https://central.example",
            external_settings=SimpleNamespace(
                device_id=UUID(PROFILE), device_token=SecretStr("private-token")
            ),
        )
        with pytest.raises(RuntimeError, match="too large"):
            external_pms.report_local_models(value, {"models": []})


def test_missing_profile_does_not_bootstrap_a_tenant_or_profile():
    value = SimpleNamespace(
        config={"organization_id": ORG}, external_settings=SimpleNamespace(processing_profile_id=None)
    )
    calls = []

    def call(method, path):
        calls.append(method)
        return {}

    with pytest.raises(RuntimeError, match="HUMAN_DEVICE_ID"):
        external_pms.published_route(value, call)
    assert calls == []


def test_client_state_contains_only_client_credentials(tmp_path, monkeypatch):
    settings = external_pms.ExternalPMS(
        _env_file=None, pms_url="http://127.0.0.1:8055", pms_token="fixture", organization_id=ORG
    )
    monkeypatch.setattr(external_pms, "load_external", lambda _: settings)
    here = tmp_path / "human-test"
    here.mkdir()
    monkeypatch.setattr(demo, "HERE", here)
    monkeypatch.setattr(demo, "STATE", here / ".local/platform-client")
    instance = demo.Demo(include_video=True)
    try:
        instance.load_config()
        assert instance.pms_url == "http://127.0.0.1:8055"
        assert instance.token == "fixture"
        saved = json.loads((demo.STATE / "config.json").read_text())
        assert set(saved) == {"purpose"}
        assert not (demo.STATE / "pms.env").exists()
        assert not (demo.STATE / "identity.pem").exists()
        assert not instance.children
    finally:
        instance.close()


def test_no_client_script_imports_or_launches_database_or_api_runtime():
    root = Path(__file__).resolve().parents[1]
    paths = [*root.glob("*.py"), *(root.parent / "src").rglob("*.py")]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(
                name.split(".")[0] in {"psycopg", "sqlalchemy", "pms_api", "alembic"} for name in names
            ), path.name
        assert "pg_ctl.exe" not in path.read_text(encoding="utf-8"), path.name
        assert "postgres.exe" not in path.read_text(encoding="utf-8"), path.name


def test_client_children_do_not_inherit_database_secrets(monkeypatch):
    for name in ("PMS_DATABASE_URL", "PMS_MIGRATION_DATABASE_URL", "PGPASSWORD", "DATABASE_URL"):
        monkeypatch.setenv(name, "private-database-credential")
    for result in (
        model_startup.provider_free_environment(),
        model_startup.desktop_environment({"HUMAN_PMS_TOKEN": "staff"}),
    ):
        assert "private-database-credential" not in result.values()


def test_model_reads_use_configured_platform_origin():
    requests = []

    def reply(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    with httpx.Client(transport=httpx.MockTransport(reply)) as http:
        value = SimpleNamespace(
            pms_url="http://127.0.0.1:8055", config={"organization_id": ORG}, token="fixture", http=http
        )
        path = f"/organizations/{ORG}/model-config?device_id={PROFILE}"
        assert external_pms.platform_call(value, "GET", path) == {"ok": True}
    assert str(requests[0].url) == f"http://127.0.0.1:8055/api/v1{path}"


@pytest.mark.parametrize("port", [8790, 18900, 18901])
def test_shared_api_cannot_use_the_configured_manager_port(port):
    with pytest.raises(ValueError, match="separate"):
        external_pms.ExternalPMS(
            _env_file=None,
            pms_url=f"http://127.0.0.1:{port}",
            pms_token="fixture",
            organization_id=ORG,
            local_models_port=port,
        )


def test_dotenv_history_preference_is_respected(tmp_path, monkeypatch):
    monkeypatch.delenv("HUMAN_HISTORY_ENABLED", raising=False)
    (tmp_path / ".env").write_text("HUMAN_HISTORY_ENABLED=false\n")
    settings = external_pms.ExternalPMS(_env_file=tmp_path / ".env", pms_token="fixture", organization_id=ORG)
    assert settings.history_enabled is False
    monkeypatch.setenv("HUMAN_HISTORY_ENABLED", "true")
    assert external_pms.ExternalPMS(
        _env_file=tmp_path / ".env", pms_token="fixture", organization_id=ORG
    ).history_enabled


@pytest.mark.parametrize(
    "status,content",
    [
        (401, b"private token"),
        (403, b"private token"),
        (302, b"private token"),
        (500, b"private token"),
        (200, b"private token"),
        (200, b"[]"),
        (200, b"x" * 131073),
    ],
    ids=["unauthorized", "forbidden", "redirect", "server-error", "invalid-json", "wrong-shape", "oversized"],
)
def test_central_configuration_responses_are_bounded_and_redacted(status, content):
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, content=content))
    ) as http:
        value = SimpleNamespace(http=http, pms_url="https://central.example", token="staff")
        with pytest.raises(RuntimeError) as error:
            external_pms.platform_call(value, "GET", "/organizations/" + ORG + "/model-options")
        assert "private token" not in str(error.value)


@pytest.mark.parametrize("changed", [None, "profile_id", "profile_revision_id", "configuration_hash"])
def test_reuse_requires_current_central_profile_and_revision(changed):
    route = {"profile_id": PROFILE, "profile_revision_id": ORG, "configuration_hash": "current"}
    running = dict(route)
    if changed:
        running[changed] = "stale"
    seen = []

    def reply(request):
        seen.append(request)
        return httpx.Response(200, json=route)

    with httpx.Client(transport=httpx.MockTransport(reply)) as http:
        value = SimpleNamespace(
            http=http,
            pms_url="https://central.example",
            token="staff",
            route=running,
            config={"organization_id": ORG},
            external_settings=SimpleNamespace(device_id=UUID(PROFILE)),
        )
        if changed:
            with pytest.raises(RuntimeError, match="differ"):
                external_pms.check_running_profile(value)
        else:
            external_pms.check_running_profile(value)
        assert http.headers.get("Authorization") is None
    assert len(seen) == 1 and seen[0].method == "GET"
    assert seen[0].url.host == "central.example"
    assert seen[0].headers["Authorization"] == "Bearer staff"


def test_unconfigured_children_never_receive_platform_or_desktop_credentials(monkeypatch):
    import runtime_environment

    values = {
        name: "private-fixture"
        for name in (
            "HUMAN_PMS_TOKEN",
            "HUMAN_LOCAL_CONTROL_TOKEN",
            "PMS_DATABASE_URL",
            "PGPASSWORD",
            "OPENAI_API_KEY",
            "AUDIO_CLIENT_TOKENS",
            "VIDEO_CLIENT_TOKENS",
        )
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("PATH", "runtime-path")
    env = runtime_environment.client_environment()
    assert "private-fixture" not in env.values() and env["PATH"] == "runtime-path"
    desktop = runtime_environment.desktop_environment({"HUMAN_PMS_TOKEN": "current-staff"})
    assert desktop["HUMAN_PMS_TOKEN"] == "current-staff" and "private-fixture" not in desktop.values()


def test_running_session_binding_changes_with_login_or_department():
    settings = external_pms.ExternalPMS(_env_file=None, pms_token="first-private", organization_id=ORG)
    first = external_pms.session_binding(settings)
    assert "first-private" not in first and len(first) == 64
    assert first == external_pms.session_binding(settings.model_copy())
    assert first != external_pms.session_binding(settings.model_copy(update={"department_id": UUID(PROFILE)}))
    assert first != external_pms.session_binding(settings.model_copy(update={"device_id": UUID(PROFILE)}))
    from pydantic import SecretStr

    assert first != external_pms.session_binding(
        settings.model_copy(update={"pms_token": SecretStr("renewed")})
    )


@pytest.mark.parametrize("change", ["token", "department"])
def test_second_launcher_cannot_reuse_another_login_or_department(tmp_path, monkeypatch, change):
    from pydantic import SecretStr

    initial = external_pms.ExternalPMS(_env_file=None, pms_token="first-login", organization_id=ORG)
    current = initial.model_copy(
        update={"pms_token": SecretStr("second-login")}
        if change == "token"
        else {"department_id": UUID(PROFILE)}
    )
    status = {
        "profile": "standard",
        "video": False,
        "external_api": True,
        "pms_url": initial.pms_url,
        "organization_id": ORG,
        "state": "ready",
        "session_binding": external_pms.session_binding(initial),
    }
    (tmp_path / "launcher.json").write_text(json.dumps(status))
    monkeypatch.setattr(demo, "STATE", tmp_path)

    class OwnedLock:
        def __init__(self, *args):
            pass

        def __enter__(self):
            raise RuntimeError("already owned")

    monkeypatch.setattr(demo, "FileLock", OwnedLock)
    instance = demo.Demo()
    instance.external_settings = current
    instance.session_binding = external_pms.session_binding(current)
    try:
        with pytest.raises(RuntimeError, match="another login, department or device"):
            instance.reuse_running()
        assert not instance.children
    finally:
        instance.close()


def test_paired_laptop_reports_only_central_verified_models():
    from pydantic import SecretStr

    requests = []

    def reply(request):
        requests.append(request)
        return httpx.Response(200, json={"device_id": PROFILE})

    with httpx.Client(transport=httpx.MockTransport(reply)) as http:
        value = SimpleNamespace(
            http=http,
            pms_url="https://central.example",
            external_settings=SimpleNamespace(
                device_id=UUID(PROFILE), device_token=SecretStr("device-secret")
            ),
        )
        info = {
            "models": [
                {"capability": "llm", "alias": "qwen3-4b-local"},
                {"capability": "asr", "id": "large-v3", "platform_speech": True},
                {"capability": "asr", "id": "nemotron-3.5-asr-streaming-0.6b", "platform_speech": False},
            ]
        }
        assert external_pms.report_local_models(value, info)
    assert requests[0].headers["authorization"] == "Bearer device-secret"
    assert json.loads(requests[0].content) == {
        "device_id": PROFILE,
        "llm": ["qwen3-4b-local"],
        "speech": ["large-v3"],
    }


def test_local_execution_requires_caller_but_does_not_dial_published_engine_port():
    model_startup.validate_local_route({"llm": {"mode": "local", "local_port": 11434, "execution": "caller"}})
    with pytest.raises(RuntimeError, match="caller execution"):
        model_startup.validate_local_route({"llm": {"mode": "local", "execution": "server"}})
