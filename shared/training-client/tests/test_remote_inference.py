import hashlib
import json
from uuid import uuid4

import httpx
import pytest
from local_model_client import ConnectionError
from local_model_client.journal import Requests
from local_model_client.remote import RemoteConnection, https_origin


@pytest.mark.parametrize(
    "origin", ["http://gpu", "https://gpu/path", "https://u:secret@gpu", "https://gpu?token=secret"]
)
def test_remote_endpoint_rejects_insecure_or_credential_urls(origin):
    with pytest.raises(ValueError):
        https_origin(origin)


async def test_platform_credentials_never_reach_gpu_and_unknowns_survive_restart(tmp_path):
    calls, grants = [], []

    def handle(request):
        calls.append(request)
        if request.url.host == "platform.test":
            assert request.headers["Authorization"] == "Bearer dev_private"
            grants.append(json.loads(request.content))
            return httpx.Response(200, json={"grant": "signed_" + "x" * 64})
        assert request.url.host == "gpu.test"
        assert request.headers["Authorization"] == "Bearer signed_" + "x" * 64
        assert "dev_private" not in str(request.headers)
        assert grants[-1]["body_sha256"] == hashlib.sha256(request.content).hexdigest()
        raise httpx.ReadTimeout("Do not expose this URL or credential")

    connection = RemoteConnection(
        "https://gpu.test",
        uuid4(),
        "https://platform.test",
        "dev_private",
        async_transport=httpx.MockTransport(handle),
        journal_dir=tmp_path / "journal",
    )
    with pytest.raises(ConnectionError, match="not replayed"):
        await connection.async_request("POST", "/v1/infer/llm", {"model": "chosen", "messages": []})
    assert len(calls) == 2
    assert Requests(tmp_path / "journal").recent() == [connection.last_request]
    assert connection.last_request["status"] == "unknown"


def test_remote_sync_synthesis_uses_its_own_grant():
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.host == "platform.test":
            return httpx.Response(200, json={"grant": "signed_" + "x" * 64})
        return httpx.Response(200, json={"wav_base64": "fixture"})

    connection = RemoteConnection(
        "https://gpu.test",
        uuid4(),
        "https://platform.test",
        "dev_private",
        transport=httpx.MockTransport(handle),
    )
    assert connection.request("POST", "/v1/infer/tts", {"voice": "v", "text": "hello"}) == {
        "wav_base64": "fixture"
    }
    assert len(requests) == 2 and connection.last_request["status"] == "completed"


@pytest.mark.parametrize("raw", [b"[]", b"null", b"not-json", b'{"grant":42}'])
def test_malformed_grants_fail_before_contacting_gpu(raw):
    calls = []

    def handle(request):
        calls.append(request)
        assert request.url.host == "platform.test"
        return httpx.Response(200, content=raw)

    connection = RemoteConnection(
        "https://gpu.test",
        uuid4(),
        "https://platform.test",
        "dev_private",
        transport=httpx.MockTransport(handle),
    )
    with pytest.raises(ConnectionError, match="Invalid platform grant"):
        connection.request("POST", "/v1/infer/tts", {"voice": "v", "text": "hello"})
    assert len(calls) == 1
