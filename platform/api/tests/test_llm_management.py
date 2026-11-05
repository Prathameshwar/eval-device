"""Real PostgreSQL connection management, with no provider network traffic."""

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from pms_api.modules.llm_schemas import ConnectionCreate


@pytest.mark.parametrize("field", ["name", "system_prompt"])
@pytest.mark.parametrize("value", [" \t\n", "null\x00character", "invalid\ud800"])
def test_invalid_connection_text_rejected(field, value):
    with pytest.raises(ValueError):
        ConnectionCreate(**{"name": "Test", "api_key": "test-only", field: value})


@pytest.fixture
def management(platform):
    h = platform
    h.settings.llm_enabled = True
    token, user = h.user("connection-admin")
    org = h.organization(token)["id"]
    h.sql("UPDATE device_platform.users SET platform_role='platform_admin' WHERE id=%s", (user["id"],))
    return h, token, org, f"/organizations/{org}/llm"


def create(h, token, base, name="Local connection"):
    return h.call(
        "POST",
        base + "/connections",
        token,
        expected=201,
        json={
            "name": name,
            "api_key": "management-test-only-key",
        },
    )


def update_body(row, **changes):
    fields = ConnectionCreate.model_fields.keys() - {"api_key"}
    return {**{key: row[key] for key in fields}, "expected_revision": row["revision"], **changes}


def test_management_crud_credentials_lifecycle_and_audit(management):
    h, token, org, base = management
    row = create(h, token, base, "  Local  ")
    path = base + "/connections/" + row["id"]
    assert row["name"] == "Local" and row["has_credentials"]
    cipher = h.sql(
        "SELECT encrypted_credentials FROM device_platform.llm_connections WHERE id=%s", (row["id"],)
    )[0][0]
    assert b"management-test-only-key" not in cipher
    assert h.call("GET", path, token) == row
    listing = h.call("GET", base + "/configurations", token)
    assert listing["items"] == [row] and listing["total"] == 1
    assert "encrypted_credentials" not in json.dumps(listing)
    assert "credential_key_id" not in json.dumps(listing)
    assert "management-test-only-key" not in json.dumps(listing)
    options = h.call("GET", base + "/configuration-options", token)
    assert row["base_url"] in options["local_endpoints"]
    check = h.call("GET", path + "/status", token)
    assert check["check"] == "configuration_only" and not check["inference_verified"]
    changed = h.call("PUT", path, token, json=update_body(row, name="Changed", is_active=False))
    assert changed["revision"] == 2 and not changed["is_active"]
    assert (
        cipher
        == h.sql(
            "SELECT encrypted_credentials FROM device_platform.llm_connections WHERE id=%s", (row["id"],)
        )[0][0]
    )
    assert h.call("GET", base + "/connections", token)["items"] == []
    assert h.call("GET", base + "/configurations?state=inactive", token)["total"] == 1
    h.call("PUT", path, token, expected=409, json=update_body(row))
    h.call("DELETE", path + "?expected_revision=1", token, expected=409)
    rotated = h.call("PUT", path, token, json=update_body(changed, api_key="rotated-test-key"))
    assert (
        cipher
        != h.sql(
            "SELECT encrypted_credentials FROM device_platform.llm_connections WHERE id=%s", (row["id"],)
        )[0][0]
    )
    archived = h.call("DELETE", path + f"?expected_revision={rotated['revision']}", token)
    assert archived["archived_at"] and not archived["is_active"]
    assert h.call("GET", base + "/configurations?state=archived", token)["total"] == 1
    h.call("PUT", path, token, expected=409, json=update_body(archived))
    h.call("POST", path + "/restore", token, expected=409, json={"expected_version": 1})
    restored = h.call("POST", path + "/restore", token, json={"expected_version": archived["revision"]})
    assert not restored["archived_at"] and not restored["is_active"]
    enabled = h.call("PUT", path, token, json=update_body(restored, is_active=True))
    assert enabled["is_active"]
    events = h.sql(
        "SELECT event_type FROM device_platform.activity_events WHERE organization_id=%s AND entity_id=%s",
        (org, row["id"]),
    )
    assert {item[0] for item in events} >= {
        "llm.connection.created",
        "llm.connection.updated",
        "llm.connection.archived",
        "llm.connection.restored",
    }


def test_management_pagination_scope_filters_and_permissions(management):
    h, token, org, base = management
    first = create(h, token, base, "A_local")
    create(h, token, base, "B local")
    page = h.call("GET", base + "/configurations?limit=1", token)
    assert page["total"] == 2 and page["has_more"] and page["items"][0]["id"] == first["id"]
    params = {"cursor": page["next_cursor"], "limit": 1}
    second = h.call("GET", base + "/configurations", token, params=params)
    assert len(second["items"]) == 1 and not second["has_more"]
    assert second["items"][0]["id"] != first["id"]
    h.call("GET", base + "/configurations", token, expected=422, params={**params, "state": "active"})
    assert h.call("GET", base + "/configurations?q=_", token)["total"] == 1
    assert h.call("GET", base + "/configurations?provider=openai", token)["total"] == 0
    h.call("GET", base + "/configurations?limit=101", token, expected=422)
    h.call("GET", base + "/configurations?state=invalid", token, expected=422)
    h.call("GET", base + "/configurations", token, expected=422, params={"q": "\x00"})
    h.call("GET", base + "/configurations", expected=401)
    outsider, _ = h.admin("connection-platform-admin")
    other_org = h.organization(outsider)["id"]
    assert h.call("GET", base + "/configurations", outsider)["total"] == 2
    h.call("GET", f"/organizations/{other_org}/llm/configurations", outsider, expected=422, params=params)
    h.call("GET", f"/organizations/{other_org}/llm/connections/{first['id']}", outsider, expected=404)
    learner, _ = h.user("connection-learner")
    tenant_admin, _ = h.user("connection-tenant-admin")
    h.organization(tenant_admin, "Tenant-only connection admin")
    for suffix in ("/configurations", "/configuration-options", "/connections/" + first["id"]):
        h.call("GET", base + suffix, tenant_admin, expected=403)
    h.call(
        "POST",
        base + "/connections",
        tenant_admin,
        expected=403,
        json={"name": "Denied", "api_key": "test-only"},
    )
    invitation = h.call(
        "POST",
        f"/organizations/{org}/invitations",
        token,
        expected=201,
        json={"email": "connection-learner@example.com", "role": "org_user"},
    )
    h.call("POST", "/invitations/accept", learner, json={"token": invitation["invitation_token"]})
    for suffix in ("/configurations", "/configuration-options", "/connections/" + first["id"]):
        h.call("GET", base + suffix, learner, expected=403)
    h.call("POST", base + "/connections", learner, expected=403, json={"name": "No", "api_key": "test-only"})
    h.call("PUT", base + "/connections/" + first["id"], learner, expected=403, json=update_body(first))
    h.call("DELETE", base + "/connections/" + first["id"], learner, expected=403)
    h.call(
        "POST",
        base + "/connections/" + first["id"] + "/restore",
        learner,
        expected=403,
        json={"expected_version": 1},
    )
    h.settings.llm_enabled = False
    h.call("GET", base + "/configurations", token, expected=503)


def test_management_concurrent_stale_archive_and_edit(management):
    h, token, _, base = management
    row = create(h, token, base)
    path = "/api/v1" + base + "/connections/" + row["id"]

    def change(method):
        return h.client.request(
            method,
            path + ("?expected_revision=1" if method == "DELETE" else ""),
            headers=h.headers(token),
            **({"json": update_body(row, name="Renamed")} if method == "PUT" else {}),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(change, ["PUT", "DELETE"]))
    assert sorted(result.status_code for result in results) == [200, 409]


def test_management_endpoint_change_requires_fresh_key(management):
    h, token, _, base = management
    row = create(h, token, base)
    h.settings.llm_allowed_ports = [8787, 8788]
    path = base + "/connections/" + row["id"]
    h.call("PUT", path, token, expected=422, json=update_body(row, base_url="http://127.0.0.1:8788"))
    changed = h.call(
        "PUT", path, token, json=update_body(row, base_url="http://127.0.0.1:8788", api_key="fresh-key")
    )
    assert changed["revision"] == 2
    h.call(
        "PUT",
        path,
        token,
        expected=422,
        json=update_body(changed, base_url="http://127.0.0.1:9999", api_key="fresh-key"),
    )


def test_archive_cannot_race_profile_publication(management, monkeypatch):
    from pms_api.modules import configuration

    h, token, org, base = management
    row = create(h, token, base)
    profile = h.call(
        "POST",
        f"/organizations/{org}/profiles",
        token,
        expected=201,
        json={
            "name": "Conversation",
            "draft_llm_connection_id": row["id"],
            "draft_settings": {"conversation": {"enabled": True, "execution_mode": "local"}},
        },
    )
    validated = threading.Event()
    proceed = threading.Event()
    original = configuration.validate_profile

    async def paused(*args, **kwargs):
        result = await original(*args, **kwargs)
        validated.set()
        assert await asyncio.to_thread(proceed.wait, 10)
        return result

    monkeypatch.setattr(configuration, "validate_profile", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        publication = pool.submit(
            h.client.post,
            f"/api/v1/organizations/{org}/profiles/{profile['id']}/publish",
            headers=h.headers(token),
            json={},
        )
        try:
            assert validated.wait(5)
            archival = pool.submit(
                h.client.delete, "/api/v1" + base + "/connections/" + row["id"], headers=h.headers(token)
            )
            with pytest.raises(TimeoutError):
                archival.result(timeout=0.15)
        finally:
            proceed.set()
        assert publication.result().status_code == 200
        response = archival.result()
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "dependency_conflict"
