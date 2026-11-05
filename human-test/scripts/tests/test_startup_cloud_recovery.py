import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import connection_startup as model_startup  # noqa: E402
import demo  # noqa: E402, F401


def launcher(http):
    value = SimpleNamespace(
        http=http,
        pms_url="http://127.0.0.1:8055",
        token="fixture",
        config={"organization_id": "org"},
        route={
            "profile_id": "profile",
            "llm": {"mode": "cloud", "model": "answer", "connection_id": "llm"},
            "audio": {"mode": "cloud", "model": "speech"},
        },
    )
    value.verify_patient_access = lambda: model_startup.verify(value)
    return value


@pytest.mark.parametrize("code", ["llm_unavailable", "llm_timeout", "speech_busy", "llm_busy"])
def test_temporary_cloud_outage_opens_after_five_checks(monkeypatch, code):
    calls, notices, waits = [], [], []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/scenario-options"):
            return httpx.Response(200, json={"items": [], "selection": None, "default": None})
        return httpx.Response(503, json={"error": {"code": code, "message": "private-provider-detail"}})

    monkeypatch.setattr(model_startup.time, "sleep", waits.append)
    monkeypatch.setattr(model_startup, "message", lambda state, text: notices.append((state, text)))
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert model_startup.verify_with_retries(launcher(http)) is False
    assert len(calls) == 15 and waits == [1, 2, 4, 8]
    assert notices[-1][0] == "WARN"
    assert "Response model" in notices[-1][1] and "Cloud speech" in notices[-1][1]
    assert code in notices[-1][1] and "private-provider-detail" not in str(notices)


@pytest.mark.parametrize(
    "code,status",
    [
        ("external_calls_disabled", 503),
        ("llm_credentials_rejected", 502),
        ("permission_denied", 403),
        ("llm_deployment_not_found", 404),
        ("secret-value", 500),
    ],
)
def test_cloud_policy_and_configuration_errors_are_not_downgraded(code, status):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status, json={"error": {"code": code, "message": "private-provider-detail"}}
            )
        )
    ) as http:
        with pytest.raises(RuntimeError) as caught:
            model_startup.model_access(http, "https://fixture.test/status", "Cloud speech", {}, True)
    assert not isinstance(caught.value, model_startup.ReadinessFailure)
    assert "secret-value" not in str(caught.value) and "private-provider-detail" not in str(caught.value)


def test_practice_access_remains_required():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403))) as http:
        with pytest.raises(RuntimeError, match="Practice access"):
            model_startup.verify(launcher(http))


def test_launcher_waits_for_the_servers_default_readiness_retry_budget():
    seen = []

    def handler(request):
        seen.append(request.extensions["timeout"]["read"])
        return httpx.Response(200, json={"status": "ready", "model": "speech"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert (
            model_startup.model_access(http, "http://127.0.0.1/status", "Cloud speech", {}, True)["status"]
            == "ready"
        )
    # API defaults: two five-second probes plus 0.25 seconds of retry backoff.
    # The desktop environment deliberately has no backend package dependency.
    assert seen[0] > 10.25
