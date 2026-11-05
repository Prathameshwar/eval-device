"""Loopback-only browser fixture. Requires a dedicated disposable PMS_TEST_ADMIN_DSN.

Run from platform/api with: uv run python tests/browser_fixture.py
Never point the test DSN at an application or production PostgreSQL server.
"""

import asyncio
import os
import secrets
import tempfile
from pathlib import Path
from uuid import UUID

import uvicorn
from conftest import platform
from fastapi import Header, HTTPException
from sqlalchemy import select, text

from pms_api.database.models import AccountEmailOutbox
from pms_api.main import create_app
from pms_api.security.local_auth import decrypt_outbox_payload

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / ".test_artifacts/login-implementation-20260923"


def main():
    if not os.environ.get("PMS_TEST_ADMIN_DSN"):
        raise RuntimeError("Set PMS_TEST_ADMIN_DSN to a dedicated disposable server")
    os.environ["PMS_SMTP_HOST"] = ""
    os.environ["PMS_SMTP_SENDER"] = ""
    os.environ["PMS_EXTERNAL_CALLS_ENABLED"] = "false"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pms-browser-") as temporary:
        fixture = platform.__wrapped__(Path(temporary))
        harness = next(fixture)
        try:
            admin, _ = harness.admin("browser-fixture-owner")
            user = harness.call(
                "POST",
                "/platform/users",
                admin,
                expected=201,
                json={"email": "browser-login@example.com", "display_name": "Browser reviewer"},
            )["user"]
            harness.sql(
                "UPDATE device_platform.users SET platform_role='platform_admin' WHERE id=%s",
                (user["id"],),
            )
            app = create_app(harness.settings)
            control_key = secrets.token_urlsafe(32)

            def authorize(key):
                if not secrets.compare_digest(key or "", control_key):
                    raise HTTPException(403)

            @app.get("/__test/action/{purpose}", include_in_schema=False)
            async def action(purpose: str, x_test_key: str = Header(default="")):
                authorize(x_test_key)
                async with app.state.sessions() as session:
                    row = await session.scalar(
                        select(AccountEmailOutbox)
                        .where(
                            AccountEmailOutbox.user_id == UUID(user["id"]),
                            AccountEmailOutbox.purpose == purpose,
                        )
                        .order_by(AccountEmailOutbox.created_at.desc())
                    )
                    if row is None:
                        raise HTTPException(404)
                    return {"token": decrypt_outbox_payload(row, harness.settings)["token"]}

            @app.post("/__test/expire", include_in_schema=False)
            async def expire(x_test_key: str = Header(default="")):
                authorize(x_test_key)
                async with app.state.sessions() as session:
                    await session.execute(
                        text(
                            "UPDATE device_platform.local_sessions "
                            "SET created_at=now()-interval '2 days', "
                            "last_used_at=now()-interval '2 days', "
                            "expires_at=now()-interval '1 day' "
                            "WHERE user_id=:user_id AND revoked_at IS NULL"
                        ),
                        {"user_id": UUID(user["id"])},
                    )
                    await session.commit()
                return {"completed": True}

            @app.post("/__test/shutdown", include_in_schema=False)
            def shutdown(x_test_key: str = Header(default="")):
                authorize(x_test_key)
                server.should_exit = True
                return {"completed": True}

            server = uvicorn.Server(
                uvicorn.Config(
                    app,
                    host="127.0.0.1",
                    port=8133,
                    access_log=False,
                    log_level="warning",
                    loop="asyncio",
                )
            )
            import json

            (ARTIFACTS / "browser-fixture.json").write_text(
                json.dumps({"api": "http://127.0.0.1:8133", "controlKey": control_key}),
                encoding="utf-8",
            )
            print("Disposable browser API ready on loopback port 8133.", flush=True)
            asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
        finally:
            fixture.close()
            (ARTIFACTS / "browser-fixture.json").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
