"""Opt-in real browser/API/PostgreSQL check. No external email or cloud calls."""

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from test_auth_sessions import EMAIL, OLD, action_token, local_account

from pms_api.main import create_app


@pytest.mark.skipif(not os.getenv("PMS_PEOPLE_WEB_ORIGIN"), reason="Opt-in running Next.js browser check")
def test_people_web_crud(platform):
    h = platform
    h.settings.smtp_host = None
    admin, owner, login = local_account(h, browser=True)
    org = h.organization(login["session_token"], "People browser tenant")["id"]
    h.sql("UPDATE device_platform.users SET platform_role='platform_admin' WHERE id=%s", (owner["id"],))
    recipient_email = "browser-recipient@example.com"
    recipient = h.call(
        "POST",
        "/platform/users",
        admin,
        expected=201,
        json={"email": recipient_email, "display_name": "Browser recipient"},
    )["user"]
    h.call(
        "POST",
        "/auth/password/setup",
        json={"token": action_token(h, recipient["id"], "setup"), "password": OLD},
    )
    department = h.call(
        "POST",
        f"/organizations/{org}/departments",
        login["session_token"],
        expected=201,
        json={"name": "Training"},
    )
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
            assert thread.is_alive() and time.monotonic() < deadline, "Browser API failed to start"
            time.sleep(0.05)
        root = Path(__file__).resolve().parents[3]
        result = subprocess.run(
            [shutil.which("node") or "node", "tests/browser-people.mjs"],
            cwd=root / "platform/ui/apps/web",
            capture_output=True,
            text=True,
            timeout=420,
            input=json.dumps(
                {
                    "origin": os.environ["PMS_PEOPLE_WEB_ORIGIN"],
                    "api": "http://127.0.0.1:8137/api/v1",
                    "email": EMAIL,
                    "password": OLD,
                    "recipient": recipient_email,
                    "org": org,
                    "department": department["id"],
                }
            ),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert (
            h.sql(
                "SELECT count(*) FROM device_platform.account_email_outbox WHERE recipient='browser-created@example.com'"
            )[0][0]
            >= 1
        )
        print(result.stdout)
    finally:
        server.should_exit = True
        thread.join(15)
        assert not thread.is_alive(), "Browser API did not stop"
