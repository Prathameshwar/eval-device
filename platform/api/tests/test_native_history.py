"""Opt-in local Qwen + real HTTP API + disposable PostgreSQL/outbox recovery."""

import hashlib
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from test_local_turns import local as local
from training_contracts.privacy import private_directory

from pms_api.main import create_app

pytestmark = pytest.mark.skipif(
    os.getenv("HUMAN_TEST_NATIVE_LLM") != "1", reason="Opt-in resident local Qwen archive check"
)

CHILD = r"""
import asyncio, hashlib, json, sys, time
from pathlib import Path
from pydantic import SecretStr
from human_test.config import Settings
from training_client.controller import Controller

async def main():
    data = json.loads(Path(sys.argv[1]).read_text())
    phase = sys.argv[2]
    settings = Settings(_env_file=None, pms_url=data["url"], pms_token=data["token"],
        organization_id=data["org"], connection_id=data["route"]["llm"]["connection_id"],
        audio_token="fixture", local_llm_key=Path(data["key_path"]).read_text().strip(),
        history_enabled=True, history_dir=Path(data["outbox"]), language="en")
    statuses = []
    controller = Controller(settings, lambda kind, value: statuses.append(value)
                            if kind == "history_status" else None)
    controller.pms.use_models(data["route"])
    try:
        digest = None
        if phase != "recover":
            result = await controller.text_turn("Say hello briefly." if phase == "online" else "Say goodbye briefly.")
            digest = hashlib.sha256(result["answer"].encode()).hexdigest()
        deadline = time.monotonic() + 20
        desired = "saved_locally" if phase == "offline" else "saved_to_pms"
        while not any(item["status"] == desired for item in statuses):
            if time.monotonic() > deadline:
                raise RuntimeError("History acknowledgement timed out")
            await asyncio.sleep(.05)
        print(json.dumps({"answer_digest": digest, "pending": len(controller.recorder.pending()),
                          "inference_executed": controller._local_http is not None}))
    finally:
        await controller.close()
asyncio.run(main())
"""


def test_native_pair_saved_and_recovered_without_inference_replay(local, tmp_path):
    h, token, user, org, _, conn, route = local
    h.settings.local_history_enabled = True
    root = Path(__file__).resolve().parents[3]
    private = tmp_path / "native-history"
    private.mkdir()
    private_directory(private)
    script = private / "client.py"
    script.write_text(CHILD, encoding="utf-8")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    url = f"http://127.0.0.1:{port}"
    config = private / "config.json"
    config.write_text(
        json.dumps(
            {
                "url": url,
                "token": token,
                "org": org,
                "route": route,
                "key_path": str(root / "local-models/.state/api-key.txt"),
                "outbox": str(private / "outbox"),
            }
        )
    )
    private_directory(config)

    def start():
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(h.settings),
                host="127.0.0.1",
                port=port,
                loop="pms_api.cli:selector_loop_factory",
                log_config=None,
                access_log=False,
            )
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        until = time.monotonic() + 15
        while not server.started:
            assert thread.is_alive() and time.monotonic() < until, "HTTP API did not start"
            time.sleep(0.05)
        return server, thread

    def stop(server, thread):
        server.should_exit = True
        thread.join(10)
        assert not thread.is_alive(), "Owned API did not stop"

    def client(phase):
        checked = subprocess.run(
            [str(root / "human-test/.venv/Scripts/python.exe"), str(script), str(config), phase],
            capture_output=True,
            text=True,
            timeout=150,
        )
        assert checked.returncode == 0, (phase, checked.stderr[-1500:])
        return json.loads(checked.stdout)

    server, thread = start()
    try:
        first = client("online")
    finally:
        stop(server, thread)
    offline = client("offline")
    assert offline["pending"] == 1
    server, thread = start()
    try:
        recovered = client("recover")
        assert not recovered["inference_executed"]
    finally:
        stop(server, thread)
    base = f"/organizations/{org}/llm/local-conversation-turns"
    saved = h.call("GET", base, token)["items"]
    assert len(saved) == 2
    actual = {hashlib.sha256(row["response_text"].encode()).hexdigest() for row in saved}
    assert actual == {first["answer_digest"], offline["answer_digest"]}
    assert {row["input_text"] for row in saved} == {"Say hello briefly.", "Say goodbye briefly."}
    assert h.sql("SELECT count(*) FROM device_platform.llm_requests")[0][0] == 0
    assert h.sql("SELECT count(*) FROM device_platform.local_turns")[0][0] == 2
