import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy.engine import make_url

from pms_api.core.config import Settings
from pms_api.main import create_app

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
# Desktop parity fixtures import the shared client without making it an API
# production dependency. Native hardware remains lazy and is mocked by tests.
sys.path.insert(0, str(ROOT.parents[1] / "shared/training-client/src"))


@pytest.fixture
def platform(tmp_path):
    dsn = os.environ.get("PMS_TEST_ADMIN_DSN")
    if not dsn:
        pytest.skip("Set PMS_TEST_ADMIN_DSN for disposable PostgreSQL integration tests")
    url = make_url(dsn)
    name = "pms_test_" + uuid4().hex[:16]
    roles = [name + "_" + purpose for purpose in ("api", "worker", "retention")]
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        for role in roles:
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
    owner = url.set(database=name).render_as_string(hide_password=False)
    api_url = url.set(drivername="postgresql+psycopg", database=name, username=roles[0]).render_as_string(
        hide_password=False
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk["kid"] = "local-test"
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps({"keys": [jwk]}))
    values = dict(
        environment="test",
        migration_database_url=url.set(drivername="postgresql+psycopg", database=name).render_as_string(
            hide_password=False
        ),
        database_url=api_url,
        worker_database_url=url.set(
            drivername="postgresql+psycopg", database=name, username=roles[1]
        ).render_as_string(hide_password=False),
        retention_database_url=url.set(
            drivername="postgresql+psycopg", database=name, username=roles[2]
        ).render_as_string(hide_password=False),
        oidc_issuer="https://issuer.test",
        oidc_audience="pms-test",
        oidc_jwks_file=jwks,
        token_pepper="p" * 40,
        media_signing_key="m" * 40,
        local_auth_enabled=True,
        local_token_signing_key="l" * 40,
        active_credential_key="test-v1",
        credential_keys={"test-v1": base64.b64encode(b"k" * 32).decode()},
        storage_root=tmp_path / "media",
    )
    env = {
        **os.environ,
        # Explicitly isolate migrations from the developer's configured owner URL in .env.
        "PMS_MIGRATION_DATABASE_URL": values["migration_database_url"],
        "PMS_DATABASE_URL": url.set(drivername="postgresql+psycopg", database=name).render_as_string(
            hide_password=False
        ),
        "PMS_TOKEN_PEPPER": "p" * 40,
        "PMS_MEDIA_SIGNING_KEY": "m" * 40,
    }
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), "upgrade", "head"],
            env=env,
            check=True,
            capture_output=True,
        )
        psql = shutil.which(os.environ.get("PMS_TEST_PSQL", "psql"))
        if not psql and sys.platform == "win32":
            candidate = Path("C:/Program Files/PostgreSQL/17/bin/psql.exe")
            psql = str(candidate) if candidate.is_file() else None
        if not psql:
            pytest.fail("Install the PostgreSQL client or set PMS_TEST_PSQL to exercise deployment grants")
        grant_env = {**env, "PGPASSWORD": url.password or ""}
        subprocess.run(
            [
                psql,
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                url.host or "127.0.0.1",
                "-p",
                str(url.port or 5432),
                "-U",
                url.username or "postgres",
                "-d",
                name,
                "-v",
                f"db_name={name}",
                "-v",
                f"api_role={roles[0]}",
                "-v",
                f"worker_role={roles[1]}",
                "-v",
                f"maintenance_role={roles[2]}",
                "-f",
                str(ROOT / "deploy/grant-runtime-access.sql"),
            ],
            env=grant_env,
            check=True,
            capture_output=True,
        )
        settings = Settings(_env_file=None, **values)
        app = create_app(settings)
        with TestClient(app) as client:
            yield Harness(client, settings, owner, key)
    finally:
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
            for role in roles:
                connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


class Harness:
    def __init__(self, client, settings, dsn, key):
        self.client = client
        self.settings = settings
        self.dsn = dsn
        self.key = key

    def token(self, subject, **overrides):
        claims = {
            "iss": "https://issuer.test",
            "aud": "pms-test",
            "sub": subject,
            "email": subject + "@example.com",
            "email_verified": True,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            **overrides,
        }
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "local-test"})

    def headers(self, token):
        return {"Authorization": "Bearer " + token}

    def call(self, method, path, token=None, expected=200, **kwargs):
        response = self.client.request(
            method, "/api/v1" + path, headers=self.headers(token) if token else {}, **kwargs
        )
        assert response.status_code == expected, (method, path, response.status_code, response.text)
        return response.json()

    def user(self, subject):
        token = self.token(subject)
        user = self.call("POST", "/identity/sync", token)
        return token, user

    def sql(self, statement, params=()):
        with psycopg.connect(self.dsn) as connection:
            cursor = connection.execute(statement, params)
            return cursor.fetchall() if cursor.description else None

    def admin(self, subject="admin"):
        token, user = self.user(subject)
        self.sql("UPDATE device_platform.users SET platform_role='platform_admin' WHERE id=%s", (user["id"],))
        return token, user

    def organization(self, token, name="Test organization", plan="standard"):
        plans = self.call("GET", "/subscription-plans", token)["items"]
        plan_id = next(row["id"] for row in plans if row["code"] == plan)
        return self.call(
            "POST",
            "/organizations",
            token,
            expected=201,
            json={"name": name, "subscription_plan_id": plan_id},
        )

    def grant_capability(self, admin_token, organization_id, user_id, capability):
        membership_id = self.sql(
            "SELECT id FROM device_platform.organization_memberships "
            "WHERE organization_id=%s AND user_id=%s AND invitation_status='accepted'",
            (organization_id, user_id),
        )[0][0]
        return self.call(
            "POST",
            f"/organizations/{organization_id}/members/{membership_id}/capabilities",
            admin_token,
            json={"capability": capability},
        )

    def device(self, token, org, **values):
        if not hasattr(self, "_fleet_token"):
            self._fleet_token, _ = self.admin("fleet-device-fixture")
        registration = {
            "device_unique_id": values.pop("device_unique_id", str(uuid4())),
            "organization_id": org,
            "name": values.pop("name", "Laptop"),
            "device_type": values.pop("device_type", "laptop"),
            "is_active": values.pop("is_active", True),
        }
        for field in ("preferred_language", "profile_id"):
            if field in values:
                registration[field] = values.pop(field)
        created = self.call(
            "POST",
            "/platform/devices",
            self._fleet_token,
            expected=201,
            json=registration,
        )
        if values:
            self.call(
                "PATCH",
                f"/organizations/{org}/devices/{created['id']}",
                token,
                json={"expected_etag": created["management_etag"], **values},
            )
        return self.call("GET", f"/organizations/{org}/devices/{created['id']}", token)

    def enroll(self, token, org, device):
        invite = self.call("POST", f"/organizations/{org}/devices/{device}/enrollment", token)
        return self.call(
            "POST",
            "/device/enroll",
            json={
                "token": invite["enrollment_token"],
                "capabilities": {
                    "engines": ["audio_activity", "opencv_motion", "espeak_ng", "device_player"]
                },
            },
        )["credential"]

    def profile(self, token, org, section="audio_input", operation="audio.activity", engine="audio_activity"):
        operator, _ = self.admin("profile-operator-" + uuid4().hex[:12])
        value = self.call(
            "POST",
            f"/organizations/{org}/profiles",
            operator,
            expected=201,
            json={
                "name": "Local profile",
                "draft_settings": {
                    section: {
                        "enabled": True,
                        "operation": operation,
                        "execution_mode": "local",
                        "engine": engine,
                    }
                },
            },
        )
        revision = self.call(
            "POST", f"/organizations/{org}/profiles/{value['id']}/publish", operator, json={}
        )
        self.call("PATCH", f"/organizations/{org}", token, json={"default_profile_id": value["id"]})
        return value, revision
