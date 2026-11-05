"""Opt-in tenant popup browser test against a disposable PostgreSQL fixture."""

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from test_auth_sessions import EMAIL, OLD, local_account

from pms_api.main import create_app


@pytest.mark.skipif(
    not os.getenv("PMS_ASSOCIATIONS_WEB_ORIGIN"), reason="Opt-in running Next.js browser check"
)
def test_tenant_associations_browser(platform):
    p = platform
    _, owner, login = local_account(p, browser=True)
    token = login["session_token"]
    org = p.organization(token, "Popup tenant")
    source = p.organization(token, "Source popup tenant")
    p.sql("UPDATE device_platform.users SET platform_role='platform_admin' WHERE id=%s", (owner["id"],))
    _, candidate = p.user("popup-candidate")
    p.call(
        "POST",
        f"/platform/organizations/{source['id']}/members",
        token,
        expected=201,
        json={"user_id": candidate["id"], "role": "org_trainee"},
    )
    own_device = p.device(token, org["id"], name="Popup own device")
    source_device = p.device(token, source["id"], name="Popup source device")
    p.enroll(token, source["id"], source_device["id"])
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(p.settings),
            host="127.0.0.1",
            port=8139,
            loop="pms_api.cli:selector_loop_factory",
            access_log=False,
            log_level="warning",
            timeout_graceful_shutdown=5,
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
            [shutil.which("node") or "node", "tests/browser-tenant-associations.mjs"],
            cwd=root / "platform/ui/apps/web",
            capture_output=True,
            text=True,
            timeout=300,
            input=json.dumps(
                {
                    "origin": os.environ["PMS_ASSOCIATIONS_WEB_ORIGIN"],
                    "api": "http://127.0.0.1:8139/api/v1",
                    "email": EMAIL,
                    "password": OLD,
                    "tenant": org,
                    "source": source,
                    "candidate": candidate,
                    "device": own_device,
                    "sourceDevice": source_device,
                }
            ),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)
    finally:
        server.should_exit = True
        thread.join(15)
        assert not thread.is_alive(), "Review API did not stop"
