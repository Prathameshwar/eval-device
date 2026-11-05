"""Only models and device assignment form the public management contract."""

from uuid import uuid4

import psycopg
import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from pms_api.core.config import Settings
from pms_api.main import create_app
from pms_api.modules.device_management import FleetDeviceCreate, FleetDevicePatch
from pms_api.modules.schemas import DevicePatch, OrganizationPatch


def test_removed_configuration_routes_and_inputs():
    paths = create_app(Settings(_env_file=None, token_pepper="p" * 40, media_signing_key="m" * 40)).openapi()[
        "paths"
    ]
    for path in paths:
        assert not any(
            segment in path.split("/")
            for segment in (
                "profiles",
                "connections",
                "model-profiles",
                "model-bindings",
                "model-options",
                "device-model-options",
            )
        )
    assert "/api/v1/platform/runtime-models" in paths
    assert "/api/v1/platform/devices/{device_id}/models" in paths
    for schema, values in (
        (
            FleetDeviceCreate,
            {"organization_id": uuid4(), "name": "Device", "device_type": "laptop", "profile_id": uuid4()},
        ),
        (FleetDevicePatch, {"expected_etag": "a" * 64, "profile_id": uuid4()}),
        (DevicePatch, {"profile_id": uuid4()}),
        (OrganizationPatch, {"default_profile_id": uuid4()}),
    ):
        with pytest.raises(ValidationError):
            schema(**values)


def test_admin_only_management_and_immutable_history(platform):
    from test_direct_models import local_model

    h = platform
    tenant, _ = h.user("model-owner")
    org = h.organization(tenant)["id"]
    admin, _ = h.admin("model-admin")
    device = h.device(tenant, org)
    credential = h.enroll(tenant, org, device["id"])
    model = h.call("POST", "/platform/runtime-models", admin, json=local_model(), expected=201)
    for token in (tenant, credential):
        h.call("GET", "/platform/runtime-models", token, expected=403)
        h.call("POST", "/platform/runtime-models", token, json=local_model(), expected=403)
        h.call("GET", f"/platform/devices/{device['id']}/models", token, expected=403)
        h.call(
            "PUT",
            f"/platform/runtime-models/{model['id']}",
            token,
            json={**local_model(), "expected_revision": 1},
            expected=403,
        )
        h.call("DELETE", f"/platform/runtime-models/{model['id']}?expected_revision=1", token, expected=403)
        h.call(
            "PUT",
            f"/platform/devices/{device['id']}/models",
            token,
            json={"mode": "local", "expected_version": 0},
            expected=403,
        )
    for path in (
        f"/organizations/{org}/profiles",
        f"/organizations/{org}/connections",
        f"/organizations/{org}/llm/connections",
        f"/organizations/{org}/model-profiles",
    ):
        h.call("POST", path, admin, json={}, expected=404)
    dsn = (
        make_url(h.settings.database_url.get_secret_value())
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
    with psycopg.connect(dsn) as c:
        for table in ("llm_connections", "provider_connections", "processing_profiles"):
            name = "device_platform." + table
            assert not c.execute(
                "SELECT has_table_privilege(current_user,%s,'INSERT') OR has_table_privilege(current_user,%s,'UPDATE')",
                (name, name),
            ).fetchone()[0]
    with pytest.raises(psycopg.errors.CheckViolation):
        h.sql(
            "INSERT INTO device_platform.processing_profiles(id,organization_id,name) VALUES(%s,%s,'Retired setup')",
            (uuid4(), org),
        )
