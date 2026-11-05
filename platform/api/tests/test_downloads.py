import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from pms_api.core.config import Settings
from pms_api.database.session import session_dependency
from pms_api.main import create_app
from pms_api.modules.downloads import catalog
from pms_api.security.access import Principal, authentication


@pytest.fixture
def downloads(tmp_path):
    data = b"PK\x03\x04portable-fixture-data"
    filename = "Human-test-windows-x64-cpu-protected-test.zip"
    (tmp_path / filename).write_bytes(data)
    release = {
        "id": "desktop-cpu",
        "filename": filename,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    (tmp_path / "catalog.json").write_text(json.dumps([release]))
    settings = Settings(
        environment="test",
        downloads_root=tmp_path,
        token_pepper=SecretStr("p" * 32),
        media_signing_key=SecretStr("m" * 32),
    )
    app = create_app(settings)
    user = SimpleNamespace(id=uuid4(), platform_role="platform_admin", is_active=True, archived_at=None)
    principal = Principal(user=user)
    session = AsyncMock()
    session.scalar.return_value = None
    app.dependency_overrides[authentication] = lambda: principal
    app.dependency_overrides[session_dependency] = lambda: session
    return TestClient(app), user, principal, session, tmp_path, data


def test_download_stream_head_and_resume(downloads):
    client, _, _, session, _, data = downloads
    response = client.get("/api/v1/downloads/desktop-cpu")
    assert response.content == data
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["etag"] == '"' + hashlib.sha256(data).hexdigest() + '"'
    response = client.head("/api/v1/downloads/desktop-cpu")
    assert not response.content
    assert int(response.headers["content-length"]) == len(data)
    response = client.get("/api/v1/downloads/desktop-cpu", headers={"Range": "bytes=4-9"})
    assert response.status_code == 206
    assert response.content == data[4:10]
    assert response.headers["content-range"] == f"bytes 4-9/{len(data)}"
    assert client.get("/api/v1/downloads/desktop-cpu", headers={"Range": "bytes=1000-"}).status_code == 416
    session.scalar.assert_not_called()
    assert session.commit.await_count == 4


@pytest.mark.parametrize(
    "edition,filename",
    [("cpu", "Desktop-App-CPU.zip"), ("cuda", "Desktop-App-GPU.zip"), ("runtime", "Desktop-App.zip")],
)
def test_download_has_a_short_name_for_get_head_and_resume(downloads, edition, filename):
    client, _, _, _, root, data = downloads
    catalog_path = root / "catalog.json"
    entries = json.loads(catalog_path.read_text())
    old_name = entries[0]["filename"]
    new_name = old_name.replace("-cpu-", "-" + edition + "-")
    if old_name != new_name:
        (root / old_name).rename(root / new_name)
    entries[0].update(id="desktop-" + edition, filename=new_name)
    catalog_path.write_text(json.dumps(entries))
    path = "/api/v1/downloads/desktop-" + edition
    for method, headers in [("GET", {}), ("HEAD", {}), ("GET", {"Range": "bytes=4-"})]:
        response = client.request(method, path, headers=headers)
        assert response.headers["content-disposition"] == f'attachment; filename="{filename}"'
        assert response.headers["etag"] == '"' + hashlib.sha256(data).hexdigest() + '"'
    assert client.get("/api/v1/downloads").json()["items"][0]["filename"] == new_name


def test_admin_gate_for_every_request(downloads):
    client, user, principal, session, _, _ = downloads
    user.platform_role = "org_user"
    for method, path in [
        ("GET", "/downloads"),
        ("GET", "/downloads/desktop-cpu"),
        ("HEAD", "/downloads/desktop-cpu"),
        ("GET", "/downloads/desktop-runtime"),
        ("HEAD", "/downloads/desktop-runtime"),
    ]:
        assert client.request(method, "/api/v1" + path).status_code == 403
    session.scalar.return_value = uuid4()
    assert client.get("/api/v1/downloads").status_code == 200
    user.is_active = False
    assert client.get("/api/v1/downloads").status_code == 403
    user.is_active = True
    principal = Principal()
    client.app.dependency_overrides[authentication] = lambda: principal
    assert client.get("/api/v1/downloads").status_code == 403
    del client.app.dependency_overrides[authentication]
    assert client.get("/api/v1/downloads").status_code == 401


@pytest.mark.parametrize("change", ["traversal", "size", "hash", "duplicate", "oversize", "debug", "edition"])
def test_corrupt_catalog_fails_closed(downloads, change):
    client, _, _, _, root, _ = downloads
    entries = json.loads((root / "catalog.json").read_text())
    if change == "traversal":
        entries[0]["filename"] = "../secret.zip"
    elif change == "debug":
        entries[0]["filename"] = entries[0]["filename"].replace("protected", "debug-source")
    elif change == "edition":
        entries[0]["id"] = "desktop-cuda"
    elif change == "size":
        entries[0]["size_bytes"] += 1
    elif change == "hash":
        entries[0]["sha256"] = "invalid"
    elif change == "duplicate":
        entries *= 2
    (root / "catalog.json").write_text(" " * 20000 if change == "oversize" else json.dumps(entries))
    response = client.get("/api/v1/downloads")
    assert response.status_code == 503
    assert "filename" not in response.text


def test_missing_catalog_and_unknown_release(downloads):
    client, _, _, _, root, _ = downloads
    assert client.get("/api/v1/downloads/unknown").status_code == 404
    (root / "catalog.json").unlink()
    assert catalog(root) == []
    assert client.get("/api/v1/downloads").json() == {"items": []}


def test_pinned_release_cannot_switch_bytes_during_resume(downloads):
    client, _, _, _, root, data = downloads
    digest = hashlib.sha256(data).hexdigest()
    url = "/api/v1/downloads/desktop-cpu?sha256=" + digest
    assert client.get(url, headers={"Range": "bytes=4-"}).content == data[4:]
    restarted = client.get(url, headers={"Range": "bytes=4-", "If-Range": '"old-etag"'})
    assert restarted.status_code == 200 and restarted.content == data
    entries = json.loads((root / "catalog.json").read_text())
    updated = b"PKnew release"
    entries[0].update(size_bytes=len(updated), sha256=hashlib.sha256(updated).hexdigest())
    (root / entries[0]["filename"]).write_bytes(updated)
    (root / "catalog.json").write_text(json.dumps(entries))
    assert client.get(url, headers={"Range": "bytes=4-"}).status_code == 409
    assert client.head(url).status_code == 409
    assert client.get("/api/v1/downloads/desktop-cpu?sha256=invalid").status_code == 422
    assert client.get("/api/v1/downloads/desktop-cpu").content == updated


def test_broken_manifest_link_is_unavailable_not_an_empty_catalog(downloads, monkeypatch):
    client, _, _, _, root, _ = downloads
    manifest = root / "catalog.json"
    manifest.unlink()
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == manifest or original(path))
    assert client.get("/api/v1/downloads").status_code == 503


def test_real_membership_lifecycle(platform, tmp_path):
    platform.settings.downloads_root = tmp_path
    admin, _ = platform.admin()
    org = platform.organization(admin)
    token, user = platform.user("downloads-admin")
    platform.sql(
        "INSERT INTO device_platform.organization_memberships "
        "(id,organization_id,user_id,role,invitation_status,is_active,joined_at) "
        "VALUES (%s,%s,%s,'org_admin','accepted',true,now())",
        (uuid4(), org["id"], user["id"]),
    )
    assert platform.call("GET", "/downloads", token) == {"items": []}
    for statement in [
        "UPDATE device_platform.organization_memberships SET is_active=false WHERE user_id=%s",
        "UPDATE device_platform.organization_memberships SET is_active=true,role='org_user' WHERE user_id=%s",
        "UPDATE device_platform.organization_memberships SET role='org_admin',is_active=false,invitation_status='revoked' WHERE user_id=%s",
    ]:
        platform.sql(statement, (user["id"],))
        platform.call("GET", "/downloads", token, expected=403)
    platform.sql(
        "UPDATE device_platform.organization_memberships SET is_active=true,invitation_status='accepted' WHERE user_id=%s",
        (user["id"],),
    )
    platform.sql(
        "UPDATE device_platform.organizations SET is_active=false,suspension_source='platform' WHERE id=%s",
        (org["id"],),
    )
    platform.call("GET", "/downloads", token, expected=403)
    assert platform.call("GET", "/downloads", admin) == {"items": []}
