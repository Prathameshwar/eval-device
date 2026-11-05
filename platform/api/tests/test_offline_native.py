"""Opt-in real local ASR -> desktop controller -> resident Qwen integration.

PMS uses its real authenticated API and isolated PostgreSQL fixture through an in-process
transport, and it stays authoritative for the case, the language and the model selection.
The published model is local, so the desktop app executes the turn against the loopback Qwen
and PMS is never on its data path: it only receives the turn's metadata afterwards.
"""

import asyncio
import json
import os
from pathlib import Path

import httpx
import pytest
from test_patient_practice import setup


@pytest.mark.skipif(
    os.getenv("PMS_TEST_NATIVE_AUDIO") != "1" or os.getenv("PMS_TEST_NATIVE_LLM") != "1",
    reason="Opt-in resident local audio and Qwen integration",
)
def test_native_desktop_audio_patient_roundtrip(platform, monkeypatch):
    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "human-test/src"))
    from human_test.config import Settings
    from training_client.capture import wav_frames
    from training_client.controller import Controller

    p = platform
    p.settings.llm_enabled = True
    assert not p.settings.external_calls_enabled
    token, _ = p.user("offline-patient")
    org = p.organization(token)["id"]
    platform_admin, _ = p.admin("offline-model-admin")
    key = Path(os.environ["PMS_TEST_LLM_KEY_FILE"]).read_text().strip()
    connection = p.call(
        "POST",
        f"/organizations/{org}/llm/connections",
        platform_admin,
        expected=201,
        json={"name": "Native offline Qwen", "api_key": key},
    )
    route = p.call(
        "POST",
        f"/organizations/{org}/model-profiles",
        token,
        json={"llm_connection_id": connection["id"], "local_audio_model": "large-v3"},
    )
    _, _, selected = setup(p, token, org, language="en")
    audio = json.loads(Path(os.environ["PMS_TEST_AUDIO_STATE_FILE"]).read_text())
    observations = []

    async def exercise():
        settings = Settings(
            _env_file=None,
            pms_token=token,
            organization_id=org,
            connection_id=connection["id"],
            # The local model's key comes from the stack launcher, never from PMS.
            local_llm_key=key,
            use_pms_models=True,
            processing_profile_id=route["profile_id"],
            audio_url=f"ws://127.0.0.1:{audio['port']}/v1/audio/stream",
            audio_token=audio["token"],
            audio_model=audio["model"],
            audio_device=audio["device"],
            language="en",
            speaker_output=False,
        )
        events = []
        controller = Controller(settings, lambda *event: events.append(event))
        await controller.pms.http.aclose()

        async def dispatch(request):
            # This adapter changes only the transport, not the PMS response.
            response = await asyncio.to_thread(
                p.client.request,
                request.method,
                request.url.raw_path.decode(),
                headers=dict(request.headers),
                content=request.content,
            )
            return httpx.Response(response.status_code, headers=response.headers, content=response.content)

        controller.pms.http = httpx.AsyncClient(
            base_url=settings.pms_url,
            transport=httpx.MockTransport(dispatch),
            headers={"Authorization": "Bearer " + token},
        )
        try:
            controller.use_models(route)
            controller.use_selection(selected)
            assert controller.runs_locally()
            await controller.preflight()
            for streaming in (False, True):
                settings.streaming = streaming
                controller.reset()
                result = await controller.turn(wav_frames(Path(os.environ["PMS_TEST_AUDIO_WAV"])))
                assert result and result["transcript"].lower().rstrip("?.") == "when did the chest pain start"
                assert result["answer"] and controller.history[-1]["content"] == result["answer"]
                # Nothing was submitted to PMS, so there is no request to recover.
                assert controller.pms.last_request is None
                recorded = await controller.pms.json("GET", controller.pms.base + "/local-turns")
                turn = recorded["items"][0]
                assert "duration" in turn["topics"]
                assert turn["answer_source"] in {"patient_voice", "scripted_case"}
                assert result["answer"] not in json.dumps(recorded)
                observations.append({"streaming": streaming, **result})
            assert any(kind == "speak" for kind, value in events)
            # Both turns ran here: PMS holds their metadata and no provider request at all.
            assert len((await controller.pms.json("GET", controller.pms.base + "/local-turns"))["items"]) == 2
            assert p.sql("SELECT count(*) FROM device_platform.llm_requests")[0][0] == 0
        finally:
            await controller.close()

    asyncio.run(exercise())
    if destination := os.getenv("PMS_TEST_OFFLINE_EVIDENCE"):
        Path(destination).write_text(json.dumps(observations, ensure_ascii=False, indent=2), encoding="utf-8")
