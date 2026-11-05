"""Opt-in real browser tenant-association and lifecycle check."""

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


@pytest.mark.skipif(not os.getenv("PMS_DEVICE_WEB_ORIGIN"), reason="Opt-in running Next.js browser check")
def test_device_management_web(platform):
    h = platform
    h.settings.smtp_host = None
    _, owner, login = local_account(h, browser=True)
    source = h.organization(login["session_token"], "Source device tenant")["id"]
    target = h.organization(login["session_token"], "Destination device tenant")["id"]
    h.sql("UPDATE device_platform.users SET platform_role='platform_admin' WHERE id=%s", (owner["id"],))
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
            [shutil.which("node") or "node", "tests/browser-device-management.mjs"],
            cwd=root / "platform/ui/apps/web",
            capture_output=True,
            text=True,
            timeout=420,
            input=json.dumps(
                {
                    "origin": os.environ["PMS_DEVICE_WEB_ORIGIN"],
                    "api": "http://127.0.0.1:8137/api/v1",
                    "email": EMAIL,
                    "password": OLD,
                    "source": source,
                    "target": target,
                }
            ),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)
    finally:
        server.should_exit = True
        thread.join(15)
        assert not thread.is_alive(), "Browser API did not stop"
