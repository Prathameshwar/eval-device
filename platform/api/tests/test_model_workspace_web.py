"""Opt-in browser -> Next -> API -> disposable PostgreSQL; no live provider calls."""

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


@pytest.mark.skipif(not os.getenv("PMS_MODELS_WEB_ORIGIN"), reason="Opt-in running Next.js model check")
def test_model_management_browser(platform):
    run_model_browser(platform, "browser-direct-models.mjs")


def run_model_browser(platform, script):
    h = platform
    h.settings.llm_enabled = True
    h.settings.external_calls_enabled = False
    h.settings.llm_allowed_base_urls = ["https://api.openai.com/v1", "https://api.anthropic.com/v1"]
    _, user, _ = local_account(h, browser=True)
    h.sql("UPDATE device_platform.users SET platform_role='platform_admin' WHERE id=%s", (user["id"],))
    tenant, _ = h.user("model-browser-tenant")
    org = h.organization(tenant, "Model browser tenant")["id"]
    device = h.device(tenant, org)
    h.sql(
        """UPDATE device_platform.devices SET capabilities=jsonb_build_object(
        'local_models_source','device_report_v1','local_models_received_at',now()::text,
        'local_models','{"llm":["qwen3-4b-local"],"speech":["large-v3"]}'::jsonb) WHERE id=%s""",
        (device["id"],),
    )
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(h.settings),
            host="127.0.0.1",
            port=8143,
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
            [shutil.which("node") or "node", "tests/" + script],
            cwd=root / "platform/ui/apps/web",
            capture_output=True,
            text=True,
            timeout=360,
            input=json.dumps(
                {
                    "origin": os.environ["PMS_MODELS_WEB_ORIGIN"],
                    "email": EMAIL,
                    "password": OLD,
                    "org": org,
                    "device": device["id"],
                    "device_name": device["name"],
                }
            ),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)
    finally:
        server.should_exit = True
        thread.join(15)
        assert not thread.is_alive()
