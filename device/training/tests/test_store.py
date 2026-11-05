import asyncio
import json
import os
import threading
import time
from uuid import uuid4

import pytest
from training_contracts.privacy import StorageError

from device_training.store import Store


def document():
    return {"id": str(uuid4()), "expires_at": time.time() + 3600, "status": "completed", "video": []}


async def test_store_quota_expiration_and_single_writer(tmp_path):
    store = Store(tmp_path / "media", 10000)
    await store.ready()
    data = document()
    try:
        await store.call("save", data, {str(uuid4()) + "-patient.wav": b"test"})
        other = Store(tmp_path / "media", 10000)
        with pytest.raises(StorageError):
            await other.ready()
        with pytest.raises(StorageError):
            await store.call("save", data, {str(uuid4()) + "-patient.wav": bytes(10001)})
        data["expires_at"] = time.time() - 1
        await store.call("save", data)
        await store.call("cleanup")
        assert not (store.root / data["id"]).exists()
    finally:
        store.stop()
        await asyncio.to_thread(store.thread.join, 1)


async def test_store_rejects_unowned_and_hardlinked_data(tmp_path):
    root = tmp_path / "unowned"
    root.mkdir()
    (root / "keep.txt").write_text("keep")
    store = Store(root, 10000)
    with pytest.raises(StorageError):
        await store.ready()
    assert (root / "keep.txt").read_text() == "keep"
    store = Store(tmp_path / "owned", 100000)
    await store.ready()
    data = document()
    await store.call("save", data)
    os.link(store.root / data["id"] / "session.json", tmp_path / "second-link.json")
    with pytest.raises(StorageError):
        await store.call("read", data["id"])
    store.stop()
    await asyncio.to_thread(store.thread.join, 1)


async def test_store_bounded_queue_and_crash_remnant_recovery(tmp_path):
    store = Store(tmp_path / "owned", 100000)
    await store.ready()
    entered, release = threading.Event(), threading.Event()
    store.do_stall = lambda: (entered.set(), release.wait(2))
    first = asyncio.create_task(store.call("stall"))
    await asyncio.to_thread(entered.wait, 1)
    second = asyncio.create_task(store.call("cleanup"))
    third = asyncio.create_task(store.call("cleanup"))
    await asyncio.sleep(0.03)
    with pytest.raises(StorageError):
        await store.call("cleanup")
    release.set()
    await asyncio.gather(first, second, third)
    orphan = store.root / str(uuid4())
    orphan.mkdir()
    (orphan / "session.json.part").write_text("incomplete")
    await store.call("cleanup")
    assert not orphan.exists()
    store.stop()
    await asyncio.to_thread(store.thread.join, 1)


async def test_atomic_retry_after_uncertain_rename_does_not_duplicate(tmp_path, monkeypatch):
    import errno

    import device_training.store as module

    store = Store(tmp_path / "media", 100000)
    await store.ready()
    original = module.os.replace
    count = 0

    def replace(source, dest):
        nonlocal count
        count += 1
        original(source, dest)
        if count == 1:
            raise OSError(errno.EIO, "uncertain rename")

    monkeypatch.setattr(module.os, "replace", replace)
    data = document()
    await store.call("save", data)
    assert json.loads(await store.call("read", data["id"])) == data
    assert store.retry.retries == 1 and count == 1
    store.stop()
    await asyncio.to_thread(store.thread.join, 1)
