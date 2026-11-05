"""Launcher readiness uses the same learner access boundary as web Practice."""

import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import connection_startup as model_startup  # noqa: E402
import demo  # noqa: E402, F401 - initializes shared launcher module paths


@pytest.mark.parametrize("authorized", [True, False])
def test_published_practice_readiness_does_not_require_author_catalog(authorized):
    paths = []

    def respond(request):
        paths.append(request.url.path)
        assert request.headers["Authorization"] == "Bearer fixture"
        if request.url.path.endswith("/scenario-options"):
            return httpx.Response(
                200 if authorized else 403,
                json={"items": [], "selection": None, "default": None}
                if authorized
                else {"error": {"code": "permission_denied"}},
            )
        assert request.url.path.endswith("/llm/models/response/status")
        return httpx.Response(200, json={"model": "local-test"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        launcher = SimpleNamespace(
            http=client,
            token="fixture",
            pms_url="http://127.0.0.1:8000",
            config={"organization_id": "tenant"},
            route={
                "llm": {"connection_id": "response", "model": "local-test", "mode": "local"},
                "audio": {"mode": "local"},
            },
        )
        if authorized:
            model_startup.verify(launcher)
            assert len(paths) == 2
        else:
            with pytest.raises(RuntimeError):
                model_startup.verify(launcher)
            assert len(paths) == 1
        assert not any(path.endswith("/catalog") for path in paths)


@pytest.mark.parametrize("provider,enabled", [("azure_openai", False), ("aws", True), ("azure", True)])
def test_readiness_never_probes_noninteractive_speech(provider, enabled):
    paths = []

    def respond(request):
        paths.append(request.url.path)
        assert "/speech/" not in request.url.path
        return httpx.Response(
            200,
            json={"items": []} if request.url.path.endswith("/scenario-options") else {"model": "local-test"},
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        model_startup.verify(
            SimpleNamespace(
                http=client,
                token="fixture",
                pms_url="http://127.0.0.1:8000",
                config={"organization_id": "tenant"},
                route={
                    "llm": {"connection_id": "response", "model": "local-test", "mode": "local"},
                    "audio": {"mode": "cloud", "provider": provider, "enabled": enabled},
                },
            )
        )
    assert len(paths) == 2
