"""Fresh, disposable API for the first-run browser test; never use an application DSN."""

import asyncio
import json
import os
import secrets
import tempfile
from pathlib import Path

import uvicorn
from conftest import platform
from fastapi import Header, HTTPException
from pydantic import SecretStr

from pms_api.main import create_app

ARTIFACTS = Path(__file__).resolve().parents[3] / ".test_artifacts/initial-setup-20260926"


def main():
    if not os.environ.get("PMS_TEST_ADMIN_DSN"):
        raise RuntimeError("Use a dedicated disposable PMS_TEST_ADMIN_DSN")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pms-setup-browser-") as temporary:
        fixture = platform.__wrapped__(Path(temporary))
        harness = next(fixture)
        try:
            setup_key = secrets.token_urlsafe(48)
            control_key = secrets.token_urlsafe(32)
            harness.settings.initial_setup_key = SecretStr(setup_key)
            app = create_app(harness.settings)

            def authorize(value):
                if not secrets.compare_digest(value, control_key):
                    raise HTTPException(403)

            @app.get("/__test/summary", include_in_schema=False)
            def summary(x_test_key: str = Header(default="")):
                authorize(x_test_key)
                [(users, credentials, audits)] = harness.sql(
                    "SELECT (SELECT count(*) FROM device_platform.users),"
                    "(SELECT count(*) FROM device_platform.local_credentials WHERE password_hash LIKE %s),"
                    "(SELECT count(*) FROM device_platform.activity_events WHERE event_type='platform.initial_admin_created')",
                    ("$argon2id$%",),
                )
                return {"users": users, "hashed_credentials": credentials, "setup_audits": audits}

            @app.post("/__test/shutdown", include_in_schema=False)
            def shutdown(x_test_key: str = Header(default="")):
                authorize(x_test_key)
                server.should_exit = True
                return {"completed": True}

            server = uvicorn.Server(
                uvicorn.Config(app, host="127.0.0.1", port=8134, access_log=False, log_level="warning")
            )
            (ARTIFACTS / "browser-fixture.json").write_text(
                json.dumps(
                    {
                        "api": "http://127.0.0.1:8134",
                        "installationKey": setup_key,
                        "controlKey": control_key,
                    }
                ),
                encoding="utf-8",
            )
            print("Disposable setup API ready on port 8134.", flush=True)
            asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
        finally:
            fixture.close()
            (ARTIFACTS / "browser-fixture.json").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
