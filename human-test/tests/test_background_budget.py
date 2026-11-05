"""Exact local budgeting cache and scoped once-only background persistence."""

import asyncio
import json
import sqlite3
import time
from uuid import uuid4

import httpx
import pytest
from local_model_client.native import LocalModel
from test_session_sync import make_sync as make_sync
from test_session_sync import record, wait_for
from training_client import session_sync
from training_client.session_sync import SessionSync
from training_contracts.patient_turn import TurnError, fit_patient_prompt


@pytest.mark.asyncio
async def test_budget_cache_reuses_only_identical_prompts_and_expires():
    calls = []

    def server(request):
        calls.append(request.url.path)
        if request.url.path == "/props":
            return httpx.Response(200, json={"default_generation_settings": {"n_ctx": 2048}})
        if request.url.path == "/apply-template":
            return httpx.Response(200, json={"prompt": json.dumps(json.loads(request.content)["messages"])})
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1] * 100})
        raise AssertionError("unexpected request")

    async with httpx.AsyncClient(transport=httpx.MockTransport(server)) as client:
        first = LocalModel(8787, "fixture", "model", context_cap=2048, client=client)
        messages = [{"role": "system", "content": "Facts"}, {"role": "user", "content": "Hello"}]
        _, budget = await fit_patient_prompt(first, messages, 128, margin=128)
        assert budget["context_limit"] == 2048 and len(calls) == 3
        second = LocalModel(8787, "fixture", "model", context_cap=2048, client=client)
        _, budget = await fit_patient_prompt(second, messages, 128, margin=128)
        assert budget["method"] == "native_tokenizer_cached" and len(calls) == 3
        changed = [messages[0], {"role": "user", "content": "Different question"}]
        await fit_patient_prompt(second, changed, 128, margin=128)
        assert calls[-2:] == ["/apply-template", "/tokenize"] and len(calls) == 5
        second.budget_cache["expires"] = time.monotonic() - 1
        await fit_patient_prompt(second, changed, 128, margin=128)
        assert calls[-3:] == ["/props", "/apply-template", "/tokenize"]
        third = LocalModel(8787, "fixture", "other-model", context_cap=2048, client=client)
        assert third.budget_cache == {}


@pytest.mark.asyncio
async def test_model_error_invalidates_budget_cache_without_resubmission():
    async with httpx.AsyncClient() as client:
        model = LocalModel(8787, "fixture", "model", context_cap=2048, client=client)
        model.budget_cache["props"] = {"cached": True}
        with pytest.raises(TurnError) as failure:
            model.check(httpx.Response(422))
        assert failure.value.code == "llm_invalid_parameters"
        assert model.budget_cache == {}


@pytest.mark.asyncio
async def test_invalid_metadata_is_discarded_and_next_attempt_reads_fresh_props():
    props_calls = 0

    def server(request):
        nonlocal props_calls
        if request.url.path == "/props":
            props_calls += 1
            return httpx.Response(
                200, json={"default_generation_settings": {"n_ctx": "bad" if props_calls == 1 else 2048}}
            )
        if request.url.path == "/apply-template":
            return httpx.Response(200, json={"prompt": "fixture"})
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1] * 100})
        raise AssertionError("Generation must not be submitted by the fitter")

    async with httpx.AsyncClient(transport=httpx.MockTransport(server)) as client:
        model = LocalModel(8787, "fixture", "model", context_cap=2048, client=client)
        messages = [{"role": "system", "content": "Facts"}, {"role": "user", "content": "Hello"}]
        with pytest.raises(TurnError) as failure:
            await fit_patient_prompt(model, messages, 128)
        assert failure.value.code == "llm_context_limit_unavailable" and model.budget_cache == {}
        _, budget = await fit_patient_prompt(model, messages, 128)
        assert props_calls == 2 and budget["context_limit"] == 2048


def test_scoped_snapshot_saved_once_before_result_and_retained_on_restart(make_sync):
    sync, _ = make_sync()
    sync.busy(True)
    sid = str(uuid4())
    conversation = {
        "context": {"conversation_id": sid},
        "snapshot": {
            "system": "Clinical facts and approved background.",
            "session_background": [{"id": "food_drink", "detail": "Rice and vegetables."}],
        },
    }
    sync.activate(conversation)
    assert asyncio.run(sync.save_turn(sid, record()))
    path = sync.root / (sid + ".context")
    assert json.loads(path.read_bytes()) == conversation
    with sqlite3.connect(sync.root / "journal.sqlite") as db:
        assert (
            db.execute("SELECT context_size FROM sessions WHERE id=?", (sid,)).fetchone()[0]
            == path.stat().st_size
        )
    stamp = path.stat().st_mtime_ns
    sync.activate(conversation)
    wait_for(lambda: sync.queue.unfinished_tasks == 0)
    assert path.stat().st_mtime_ns == stamp
    asyncio.run(sync.close())
    assert json.loads(path.read_bytes()) == conversation
    with sqlite3.connect(sync.root / "journal.sqlite") as db:
        # An older journal has no accounting column yet.
        db.execute("ALTER TABLE sessions DROP COLUMN context_size")
    restarted = SessionSync(
        sync.settings, lambda *_: None, transport=httpx.MockTransport(lambda _: httpx.Response(503))
    )
    try:
        assert restarted.ready.wait(5) and restarted.disk_ok
        assert json.loads(path.read_bytes()) == conversation
        with sqlite3.connect(sync.root / "journal.sqlite") as db:
            assert (
                db.execute("SELECT context_size FROM sessions WHERE id=?", (sid,)).fetchone()[0]
                == path.stat().st_size
            )
    finally:
        asyncio.run(restarted.close())


def test_snapshot_quota_includes_retained_context_and_can_retry_after_capacity_change(make_sync):
    sync, _ = make_sync(session_sync_max_bytes=1048576)
    sync.busy(True)
    for _ in range(8):
        sid = str(uuid4())
        sync.activate({"context": {"conversation_id": sid}, "snapshot": {"system": "x" * 120000}})
        wait_for(lambda: sync.queue.unfinished_tasks == 0)
        assert (sync.root / (sid + ".context")).exists()
    with sqlite3.connect(sync.root / "journal.sqlite") as db:
        # Retained evidence still consumes space after server acknowledgement.
        db.execute("UPDATE sessions SET acknowledged=1")
    sid = str(uuid4())
    conversation = {"context": {"conversation_id": sid}, "snapshot": {"system": "x" * 120000}}
    sync.activate(conversation)
    wait_for(lambda: sync.queue.unfinished_tasks == 0)
    assert sid in sync.failed and sync.current is None
    assert not (sync.root / (sid + ".context")).exists()
    assert len(list(sync.root.glob("*.context"))) == 8
    sync.settings.session_sync_max_bytes = 2097152
    sync.activate(conversation)
    wait_for(lambda: sync.queue.unfinished_tasks == 0)
    assert (sync.root / (sid + ".context")).exists()


def test_fast_snapshot_failure_cannot_be_overwritten_by_activation(make_sync, monkeypatch):
    sync, _ = make_sync()
    sync.busy(True)
    sid = str(uuid4())
    submit = sync.submit

    def immediate_failure(*args):
        accepted = submit(*args)
        wait_for(lambda: sid in sync.failed)
        return accepted

    monkeypatch.setattr(sync, "submit", immediate_failure)
    sync.activate({"context": {"conversation_id": sid}, "snapshot": {"system": "x" * 131073}})
    assert sync.current is None


def test_failed_snapshot_replacement_reserves_partial_space_and_retry_reuses_it(make_sync, monkeypatch):
    sync, _ = make_sync()
    sync.busy(True)
    sync.settings.session_sync_max_bytes = 150000
    sid = str(uuid4())
    conversation = {"context": {"conversation_id": sid}, "snapshot": {"system": "x" * 120000}}
    replace = session_sync.durable_replace

    def fail_replace(*args):
        raise OSError("injected replacement failure")

    monkeypatch.setattr(session_sync, "durable_replace", fail_replace)
    sync.activate(conversation)
    wait_for(lambda: sync.queue.unfinished_tasks == 0)
    partial = sync.root / (sid + ".context.part")
    assert partial.exists() and sync.current is None
    with sqlite3.connect(sync.root / "journal.sqlite") as db:
        assert (
            db.execute("SELECT context_size FROM sessions WHERE id=?", (sid,)).fetchone()[0]
            == partial.stat().st_size
        )
    monkeypatch.setattr(session_sync, "durable_replace", replace)
    sync.activate(conversation)
    wait_for(lambda: sync.queue.unfinished_tasks == 0)
    assert not partial.exists()
    assert json.loads((sync.root / (sid + ".context")).read_bytes()) == conversation


def test_camera_recovery_includes_snapshot_quota_without_deleting_original(make_sync):
    sync, _ = make_sync(session_sync_max_bytes=1048576)
    sync.busy(True)
    for _ in range(8):
        sid = str(uuid4())
        sync.activate({"context": {"conversation_id": sid}, "snapshot": {"system": "x" * 120000}})
        wait_for(lambda: sync.queue.unfinished_tasks == 0)
    sync.stop.set()
    sync.disk.join(3)
    sync.upload.join(3)
    camera = sync.settings.video_recording_dir / "2026/10/06/session"
    camera.mkdir(parents=True)
    original = camera / "video-0001.mkv"
    original.write_bytes(bytes(100000))
    (camera / "session.json").write_text(
        json.dumps({"archive_id": sid, "archive_namespace": sync.root.name, "segments": [original.name]}),
        encoding="utf-8",
    )
    restarted = SessionSync(
        sync.settings, lambda *_: None, transport=httpx.MockTransport(lambda _: httpx.Response(503))
    )
    try:
        assert restarted.ready.wait(5) and restarted.disk_ok
        with sqlite3.connect(sync.root / "journal.sqlite") as db:
            assert db.execute("SELECT count(*) FROM items WHERE kind='video'").fetchone()[0] == 0
        assert original.stat().st_size == 100000
    finally:
        asyncio.run(restarted.close())


def test_activation_can_retry_rejected_queue_and_preserves_immutable_snapshot(make_sync, monkeypatch):
    sync, _ = make_sync()
    sync.busy(True)
    sid = str(uuid4())
    conversation = {"context": {"conversation_id": sid}, "snapshot": {"system": "Fixed background."}}
    original = sync.submit
    monkeypatch.setattr(sync, "submit", lambda *args: False)
    sync.activate(conversation)
    assert sync.current is None
    monkeypatch.setattr(sync, "submit", original)
    sync.activate(conversation)
    path = sync.root / (sid + ".context")
    wait_for(lambda: path.exists())
    assert json.loads(path.read_bytes()) == conversation
    sync.current = None
    sync.activate({**conversation, "status": "active", "sequence": 2})
    wait_for(lambda: sync.queue.unfinished_tasks == 0)
    assert json.loads(path.read_bytes()) == conversation
    sync.current = None
    sync.activate({**conversation, "snapshot": {"system": "Different background."}})
    wait_for(lambda: sid in sync.failed)
    assert json.loads(path.read_bytes()) == conversation
