import asyncio
import base64
import json
import threading
import time
from uuid import uuid4

import httpx
import pytest
from test_history_outbox import record
from training_client.conversation_history import HistoryRecorder, merge_history

from human_test.config import Settings


def settings(tmp_path):
    claims = base64.urlsafe_b64encode(json.dumps({"iss": "fixture", "sub": "operator"}).encode()).decode()
    return Settings(
        _env_file=None,
        history_enabled=True,
        history_dir=tmp_path / "history",
        pms_token="header." + claims + ".signature",
        organization_id=uuid4(),
        connection_id=uuid4(),
        audio_token="fixture",
    )


async def until(predicate, seconds=5):
    end = time.monotonic() + seconds
    while not predicate():
        if time.monotonic() > end:
            pytest.fail("Background operation did not complete")
        await asyncio.sleep(0.02)


async def test_unavailable_upload_does_not_hold_disk_or_enqueue(tmp_path):
    entered, release = threading.Event(), threading.Event()
    value = settings(tmp_path)

    def handler(request):
        entered.set()
        release.wait(2)
        return httpx.Response(503)

    statuses = []
    worker = HistoryRecorder(value, lambda k, v: statuses.append(v), transport=httpx.MockTransport(handler))
    try:
        one, two = record(), record()
        assert worker.enqueue(one)
        await until(entered.is_set)
        started = time.perf_counter()
        assert worker.enqueue(two)
        assert time.perf_counter() - started < 0.05
        await until(lambda: len(worker.pending()) == 2)
        assert all(row["save_status"] == "saved_locally" for row in worker.pending())
    finally:
        release.set()
        await worker.close()
    restarted = HistoryRecorder(
        value, lambda *args: None, transport=httpx.MockTransport(lambda r: httpx.Response(503))
    )
    try:
        await until(lambda: len(restarted.pending()) == 2)
    finally:
        await restarted.close()


async def test_lost_ack_retries_same_record_and_removes_only_after_success(tmp_path):
    value = settings(tmp_path)
    calls, accepted = [], set()

    def handler(request):
        if request.url.path.endswith("/identity"):
            return httpx.Response(
                200,
                json={
                    "issuer": "fixture",
                    "subject": "operator",
                    "organization_id": str(value.organization_id),
                },
            )
        body = json.loads(request.content)
        calls.append(body)
        accepted.add(body["turn_key"])
        if len(calls) == 1:
            raise httpx.ReadError("Lost response")
        return httpx.Response(200, json={"turn_key": body["turn_key"]})

    statuses = []
    worker = HistoryRecorder(value, lambda k, v: statuses.append(v), transport=httpx.MockTransport(handler))
    try:
        item = record()
        worker.enqueue(item)
        await until(lambda: any(s["status"] == "saved_to_pms" for s in statuses))
        assert len(calls) == 2 and calls[0] == calls[1] and len(accepted) == 1
        assert worker.pending() == []
    finally:
        await worker.close()


async def test_identity_mismatch_never_uploads_text(tmp_path):
    calls = []
    value = settings(tmp_path)

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={"issuer": "fixture", "subject": "different", "organization_id": str(value.organization_id)},
        )

    worker = HistoryRecorder(value, lambda *args: None, transport=httpx.MockTransport(handler))
    try:
        worker.enqueue(record())
        await until(lambda: calls)
        assert all(path.endswith("/identity") for path in calls)
        assert len(worker.pending()) == 1
    finally:
        await worker.close()


async def test_device_history_uses_verified_device_identity(tmp_path):
    from pydantic import SecretStr

    value = settings(tmp_path)
    value.device_id = uuid4()
    value.pms_token = SecretStr("dev_fixture")
    calls = []

    def handler(request):
        if request.url.path.endswith("/identity"):
            return httpx.Response(
                200,
                json={
                    "issuer": "urn:pms:device",
                    "subject": str(value.device_id),
                    "organization_id": str(value.organization_id),
                    "department_id": None,
                },
            )
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"turn_key": calls[-1]["turn_key"]})

    worker = HistoryRecorder(value, lambda *args: None, transport=httpx.MockTransport(handler))
    try:
        assert worker.identity == ("urn:pms:device", str(value.device_id))
        item = record()
        worker.enqueue(item)
        await until(lambda: bool(calls) and not worker.pending())
        assert calls == [item]
    finally:
        await worker.close()


async def test_queue_pressure_is_bounded_and_visible(tmp_path):
    from training_client.history_outbox import Outbox

    gate = threading.Event()
    value = settings(tmp_path)
    value.history_queue_records = 1

    def factory(*a, **kw):
        gate.wait(2)
        return Outbox(*a, **kw)

    statuses = []
    worker = HistoryRecorder(
        value,
        lambda k, v: statuses.append(v),
        transport=httpx.MockTransport(lambda r: httpx.Response(503)),
        outbox_factory=factory,
    )
    try:
        assert worker.enqueue(record())
        assert not worker.enqueue(record())
        assert statuses[-1]["status"] == "not_saved"
    finally:
        gate.set()
        await worker.close()


def test_merge_preserves_exact_pairs_and_server_ack_wins():
    item = record()
    pending = {**item, "save_status": "saved_locally"}
    remote = {**item, "save_status": "saved_to_pms"}
    assert merge_history([remote], [pending]) == [remote]
    assert merge_history([], [record(outcome="cancelled", response_text=None)]) == []


async def test_controller_records_delivered_answer_and_freezes_configuration(monkeypatch, tmp_path):
    from test_local_execution import QUESTION, SPOKEN, conversation_transport, model_server, route, selection
    from training_client.controller import Controller

    captured = []

    class Recorder:
        def __init__(self, *args):
            pass

        def enqueue(self, value, metrics):
            captured.append((value, metrics))
            return True

        async def close(self):
            pass

    monkeypatch.setattr("training_client.controller.HistoryRecorder", Recorder)
    c = Controller(settings(tmp_path), lambda *args: None)
    from pydantic import SecretStr

    c.settings.local_models_key = SecretStr("laptop-model-key")
    c.pms.use_models(route())
    c.use_selection(selection())
    await c.pms.http.aclose()
    c.pms.http = httpx.AsyncClient(
        base_url="http://pms.invalid",
        transport=conversation_transport(c, lambda request: httpx.Response(200, json={"status": "saved"})),
    )
    c._local_http = httpx.AsyncClient(transport=httpx.MockTransport(model_server([])))
    try:
        result = await c.text_turn(QUESTION)
        assert result["answer"] == SPOKEN
        event, metrics = captured[0]
        assert event["input_text"] == QUESTION and event["response_text"] == SPOKEN
        assert event["turn_key"] == metrics["turn_key"]
        assert event["input_source"] == "text" and event["audio_mode"] == "none"
        original = event["connection_id"]
        c.use_models(route())
        assert event["connection_id"] == original
        assert c.conversation_id != event["conversation_id"]
    finally:
        await c.close()


@pytest.mark.parametrize("cancelled", [False, True])
async def test_failure_has_no_invented_answer(monkeypatch, tmp_path, cancelled):
    from test_local_execution import route
    from training_client.controller import Controller

    saved = []

    class Recorder:
        def __init__(self, *args):
            pass

        def enqueue(self, record, metrics):
            saved.append(record)
            return True

        async def close(self):
            pass

    monkeypatch.setattr("training_client.controller.HistoryRecorder", Recorder)
    c = Controller(settings(tmp_path), lambda *args: None)
    c.pms.use_models(route())

    async def fail(*args):
        if cancelled:
            raise asyncio.CancelledError()
        raise RuntimeError("not recorded")

    c.local_answer = fail
    try:
        with pytest.raises(asyncio.CancelledError if cancelled else RuntimeError):
            await c.text_turn("Fictional question")
        assert saved[0]["outcome"] == ("cancelled" if cancelled else "failed")
        assert saved[0]["response_text"] is None
    finally:
        await c.close()


async def test_malformed_ack_is_retried_without_killing_uploader(tmp_path):
    value = settings(tmp_path)
    bodies, statuses = [], []

    def handler(request):
        if request.url.path.endswith("/identity"):
            return httpx.Response(
                200,
                json={
                    "issuer": "fixture",
                    "subject": "operator",
                    "organization_id": str(value.organization_id),
                },
            )
        body = json.loads(request.content)
        bodies.append(body)
        return httpx.Response(200, json=[] if len(bodies) == 1 else {"turn_key": body["turn_key"]})

    worker = HistoryRecorder(value, lambda k, v: statuses.append(v), transport=httpx.MockTransport(handler))
    try:
        worker.enqueue(record())
        await until(lambda: any(s["status"] == "saved_to_pms" for s in statuses))
        assert bodies[0] == bodies[1]
    finally:
        await worker.close()


async def test_status_callback_failure_does_not_fail_enqueue(tmp_path):
    def unavailable_ui(*args):
        raise RuntimeError("UI backlog")

    worker = HistoryRecorder(
        settings(tmp_path), unavailable_ui, transport=httpx.MockTransport(lambda r: httpx.Response(503))
    )
    try:
        assert worker.enqueue(record())
        await until(lambda: len(worker.pending()) == 1)
    finally:
        await worker.close()


async def test_slow_ack_cleanup_does_not_repeat_network_upload(tmp_path):
    from training_client.history_outbox import Outbox

    entered, release = threading.Event(), threading.Event()
    calls, statuses = [], []
    value = settings(tmp_path)

    class SlowCleanup(Outbox):
        def acknowledge(self, key):
            entered.set()
            release.wait(3)
            super().acknowledge(key)

    def handler(request):
        if request.url.path.endswith("/identity"):
            return httpx.Response(
                200,
                json={
                    "issuer": "fixture",
                    "subject": "operator",
                    "organization_id": str(value.organization_id),
                },
            )
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json={"turn_key": body["turn_key"]})

    worker = HistoryRecorder(
        value,
        lambda k, v: statuses.append(v),
        transport=httpx.MockTransport(handler),
        outbox_factory=SlowCleanup,
    )
    try:
        worker.enqueue(record())
        await until(entered.is_set)
        await asyncio.sleep(0.5)
        assert len(calls) == 1
        release.set()
        await until(lambda: any(item["status"] == "saved_to_pms" for item in statuses))
        assert len(calls) == 1 and worker.pending() == []
    finally:
        release.set()
        await worker.close()
