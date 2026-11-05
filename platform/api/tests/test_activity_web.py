"""Opt-in browser/API/database log checks on disposable PostgreSQL."""

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from test_activity_api import seed_event
from test_auth_sessions import EMAIL, OLD, local_account

from pms_api.main import create_app


@pytest.mark.skipif(not os.getenv("PMS_ACTIVITY_WEB_ORIGIN"), reason="Opt-in running Next.js browser check")
def test_activity_web(platform):
    h = platform
    h.settings.smtp_host = None
    _, owner, login = local_account(h, browser=True)
    org = h.organization(login["session_token"], "Logs browser tenant")["id"]
    other_org = h.organization(login["session_token"], "Other logs tenant")["id"]
    h.sql("UPDATE device_platform.users SET platform_role='platform_admin' WHERE id=%s", (owner["id"],))
    operation = seed_event(
        h,
        org,
        event_type="fixture.operational",
        severity="error",
        details={
            "status": "ready",
            "api_key": "private-browser-value",
            "transcript": "private-browser-conversation",
        },
    )
    audit = seed_event(
        h,
        org,
        category="audit",
        event_type="fixture.audit",
        severity="warning",
        details={
            "fields": ["is_active"],
            "reason": "https://private.invalid/file?sig=private-browser-signature",
        },
    )
    expired = seed_event(h, org, expired=True, event_type="fixture.expired")
    for index in range(28):
        seed_event(h, org, event_type=f"fixture.page.{index:02}")
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(h.settings),
            host="127.0.0.1",
            port=8137,
            loop="pms_api.cli:selector_loop_factory",
            access_log=False,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(0.05)
        root = Path(__file__).resolve().parents[3]
        result = subprocess.run(
            [shutil.which("node") or "node", "tests/browser-logs.mjs"],
            cwd=root / "platform/ui/apps/web",
            capture_output=True,
            text=True,
            timeout=420,
            input=json.dumps(
                {
                    "origin": os.environ["PMS_ACTIVITY_WEB_ORIGIN"],
                    "email": EMAIL,
                    "password": OLD,
                    "org": org,
                    "otherOrg": other_org,
                    "operation": operation,
                    "audit": audit,
                    "expired": expired,
                }
            ),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)
    finally:
        server.should_exit = True
        thread.join(15)
        assert not thread.is_alive(), "Browser API did not stop"
