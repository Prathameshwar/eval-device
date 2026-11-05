"""Role navigation and tenant boundaries through a real, disposable API and web UI."""

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


@pytest.mark.skipif(
    not os.getenv("PMS_TENANT_ROLES_WEB_ORIGIN"), reason="Opt-in running Next.js browser check"
)
def test_tenant_roles_browser(platform):
    p = platform
    _, owner, login = local_account(p, browser=True)
    token = login["session_token"]
    org = p.organization(token, "Role review tenant")
    p.sql("UPDATE device_platform.users SET platform_role='platform_admin' WHERE id=%s", (owner["id"],))
    p.grant_capability(token, org["id"], owner["id"], "org.training.instruct")
    device = p.device(token, org["id"], name="Role review device")
    p.enroll(token, org["id"], device["id"])
    other = p.organization(token, "Separate tenant")
    accounts = [{"role": "org_admin", "email": EMAIL, "password": OLD}]
    base = f"/organizations/{org['id']}"
    for role in ("org_user", "org_read_only", "org_trainee"):
        email = role + "@example.com"
        user = p.call(
            "POST",
            "/platform/users",
            token,
            expected=201,
            json={"email": email, "display_name": role},
        )["user"]
        p.call(
            "POST",
            "/auth/password/setup",
            json={
                "token": action_token(p, user["id"], "setup"),
                "password": OLD,
            },
        )
        member_token = p.call("POST", "/auth/browser/login", json={"email": email, "password": OLD})[
            "session_token"
        ]
        invitation = p.call(
            "POST",
            base + "/invitations",
            token,
            expected=201,
            json={"email": email, "auth_method": "local", "role": role},
        )
        p.call("POST", "/invitations/accept", member_token, json={"token": invitation["invitation_token"]})
        summary = p.call("GET", base + "/devices/" + device["id"], member_token)
        assert summary["summary_only"] == (role == "org_trainee")
        p.call("GET", base + "/members", member_token, expected=403)
        p.call("GET", f"/organizations/{other['id']}/devices", member_token, expected=404)
        p.call("GET", "/platform/users", member_token, expected=403)
        if role == "org_trainee":
            p.call("GET", base + "/devices/" + device["id"] + "/configuration", member_token, expected=403)
        accounts.append({"role": role, "email": email, "password": OLD})

    server = uvicorn.Server(
        uvicorn.Config(
            create_app(p.settings),
            host="127.0.0.1",
            port=8146,
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
            [shutil.which("node") or "node", "tests/browser-tenant-roles.mjs"],
            cwd=root / "platform/ui/apps/web",
            capture_output=True,
            text=True,
            timeout=360,
            input=json.dumps(
                {
                    "origin": os.environ["PMS_TENANT_ROLES_WEB_ORIGIN"],
                    "tenant": org,
                    "device": device,
                    "accounts": accounts,
                }
            ),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)
    finally:
        server.should_exit = True
        thread.join(15)
        assert not thread.is_alive(), "Role review API did not stop"
