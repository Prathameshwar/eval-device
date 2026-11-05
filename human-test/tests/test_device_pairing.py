"""Pairing failures cannot silently enroll/retry or expose a saved credential."""

from uuid import uuid4

import httpx
import pytest

from human_test.connection import ConnectionError, PairingClient, platform_origin, read_connection


def test_incomplete_saved_identity_shows_pairing_error(tmp_path):
    path = tmp_path / "connection.json"
    path.write_text('{"version":1,"credential":"dev_fixture","pms_url":"https://platform.example"}')
    with pytest.raises(ConnectionError, match="Pair this desktop again"):
        read_connection(path)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://example.com/setup",
        "https://u:p@example.com",
        "https://example.com/?token=x",
        "http://127.0.0.1:8787",
    ],
)
def test_pairing_requires_trusted_origin(url):
    with pytest.raises(ConnectionError):
        platform_origin(url)


def test_saved_pairing_resumes_without_enrollment_or_tenant_input(tmp_path):
    device, org = str(uuid4()), str(uuid4())
    identity = {
        "device_id": device,
        "device_unique_id": "Desk01",
        "device_name": "Desk",
        "organization_id": org,
        "organization_name": "Tenant",
        "department_id": None,
    }
    requests = []

    def reply(request):
        requests.append(request)
        if request.url.path.endswith("health/ready"):
            assert "authorization" not in request.headers
            return httpx.Response(200, json={"status": "ready", "service": "pms_api"})
        if request.method == "POST":
            return httpx.Response(200, json={**identity, "credential": "dev_private_fixture"})
        assert request.headers["authorization"] == "Bearer dev_private_fixture"
        return httpx.Response(200, json=identity)

    client = PairingClient(
        "https://platform.example",
        transport=httpx.MockTransport(reply),
        path=tmp_path / "state" / "connection.json",
    )
    try:
        saved = client.pair("Desk01", "enr_" + "x" * 32)
        assert saved == read_connection(client.path)
        assert saved == client.resume(saved)
        assert len([req for req in requests if req.method == "POST"]) == 1
        assert "enr_" not in client.path.read_text()
    finally:
        client.close()


def test_uncertain_enrollment_is_not_retried_or_saved(tmp_path):
    calls = []

    def reply(request):
        if request.method == "POST":
            calls.append(request)
            raise httpx.ReadTimeout("private-server-details")
        return httpx.Response(200, json={"status": "ready", "service": "pms_api"})

    client = PairingClient(
        "https://platform.example",
        transport=httpx.MockTransport(reply),
        path=tmp_path / "state" / "connection.json",
    )
    try:
        with pytest.raises(ConnectionError, match="response was lost") as error:
            client.pair("Desk01", "enr_" + "x" * 32)
        assert "private-server-details" not in str(error.value)
        assert len(calls) == 1 and not client.path.exists()
    finally:
        client.close()


def test_redirect_and_old_api_do_not_receive_enrollment_secret(tmp_path):
    requests = []

    def reply(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://elsewhere.example"})

    client = PairingClient(
        "https://platform.example", transport=httpx.MockTransport(reply), path=tmp_path / "connection.json"
    )
    try:
        with pytest.raises(ConnectionError):
            client.pair("Desk01", "enr_" + "x" * 32)
        assert len(requests) == 1 and requests[0].method == "GET"
    finally:
        client.close()


@pytest.mark.parametrize("after_enrollment", [False, True])
def test_cancellation_before_enrollment_stops_request_but_completed_enrollment_is_saved(
    tmp_path, after_enrollment
):
    import threading

    cancelled = threading.Event()
    requests = []
    identity = dict(
        device_id=str(uuid4()),
        organization_id=str(uuid4()),
        department_id=None,
        device_unique_id="Desk01",
        device_name="Desk",
        organization_name="Tenant",
    )

    def reply(request):
        requests.append(request.method)
        if request.method == "POST":
            cancelled.set()
            return httpx.Response(200, json={**identity, "credential": "dev_fixture"})
        if not after_enrollment:
            cancelled.set()
        return httpx.Response(200, json={"service": "pms_api", "status": "ready"})

    client = PairingClient(
        "https://platform.example",
        transport=httpx.MockTransport(reply),
        path=tmp_path / "state/connection.json",
    )
    client.cancelled = cancelled.is_set
    try:
        if after_enrollment:
            assert client.pair("Desk01", "enr_" + "x" * 32) == read_connection(client.path)
            assert requests == ["GET", "POST"]
        else:
            with pytest.raises(ConnectionError, match="cancelled"):
                client.pair("Desk01", "enr_" + "x" * 32)
            assert requests == ["GET"] and not client.path.exists()
    finally:
        client.close()


def test_malformed_platform_error_is_safe(tmp_path):
    client = PairingClient(
        "https://platform.example",
        path=tmp_path / "connection.json",
        transport=httpx.MockTransport(lambda req: httpx.Response(400, json={"error": {"code": []}})),
    )
    try:
        with pytest.raises(ConnectionError, match="HTTP 400"):
            client.check()
    finally:
        client.close()
