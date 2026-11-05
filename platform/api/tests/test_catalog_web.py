"""Opt-in real Next/API/PostgreSQL management journeys; all provider calls stay mocked."""

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
from test_patient_practice import setup

from pms_api.main import create_app


@pytest.mark.skipif(not os.getenv("PMS_CATALOG_WEB_ORIGIN"), reason="Opt-in running Next.js browser check")
def test_catalog_web(platform):
    h = platform
    h.settings.smtp_host = None
    _, _, login = local_account(h, browser=True)
    token = login["session_token"]
    org = h.organization(token, "Content browser tenant")["id"]
    _, selection, _ = setup(h, token, org)
    case = h.call("GET", f"/organizations/{org}/patient-practice/cases/{selection['template_id']}", token)
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
        deadline = time.monotonic() + 20
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline
            time.sleep(0.05)
        root = Path(__file__).resolve().parents[3]
        result = subprocess.run(
            [shutil.which("node") or "node", "tests/browser-catalog.mjs"],
            cwd=root / "platform/ui/apps/web",
            capture_output=True,
            text=True,
            timeout=480,
            input=json.dumps(
                {
                    "origin": os.environ["PMS_CATALOG_WEB_ORIGIN"],
                    "email": EMAIL,
                    "password": OLD,
                    "org": org,
                    "case": case,
                }
            ),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)
        assert (
            h.sql(
                "SELECT count(*) FROM device_platform.organization_clinical_specialties WHERE organization_id=%s AND code='browser_category'",
                (org,),
            )[0][0]
            == 1
        )
        assert (
            h.sql(
                "SELECT count(*) FROM device_platform.organization_patient_profiles WHERE organization_id=%s AND code='browser_patient'",
                (org,),
            )[0][0]
            == 1
        )
        assert (
            h.sql(
                "SELECT count(*) FROM device_platform.patient_practice_selections WHERE organization_id=%s",
                (org,),
            )[0][0]
            == 1
        )
        assert h.sql(
            "SELECT count(*) FROM device_platform.organization_case_templates WHERE organization_id=%s AND code='browser_case'",
            (org,),
        ) == [(1,)]
        assert h.sql(
            "SELECT count(*) FROM device_platform.training_scenario_drafts "
            "WHERE organization_id=%s AND code='browser_training_case' AND source_case_id=%s",
            (org, selection["template_id"]),
        ) == [(1,)]
    finally:
        server.should_exit = True
        thread.join(20)
        assert not thread.is_alive(), "Browser API did not stop"
