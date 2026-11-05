import os
from types import SimpleNamespace

import pytest

from pms_api.integrations import storage as module
from pms_api.integrations.storage import LocalStorage


async def test_chunk_is_flushed_before_publication_and_publication_failure_is_recoverable(
    monkeypatch, tmp_path
):
    storage = LocalStorage(SimpleNamespace(storage_root=tmp_path, vm_local_mode=False))
    await storage.write("archive/chunk", b"previous")
    real_flush = os.fsync
    flushed = []

    def flush(descriptor):
        flushed.append(descriptor)
        real_flush(descriptor)

    def fail_publish(source, destination):
        assert flushed
        assert source.read_bytes() == b"new recording"
        raise OSError("simulated publication failure")

    monkeypatch.setattr(module.os, "fsync", flush)
    real_publish = module.durable_replace
    monkeypatch.setattr(module, "durable_replace", fail_publish)
    with pytest.raises(OSError, match="publication"):
        await storage.write("archive/chunk", b"new recording")
    assert await storage.read("archive/chunk", 100) == b"previous"
    assert not list(tmp_path.rglob("*.part"))
    monkeypatch.setattr(module, "durable_replace", real_publish)
    await storage.write("archive/chunk", b"new recording")
    assert await storage.read("archive/chunk", 100) == b"new recording"


async def test_failed_flush_does_not_publish_or_acknowledge_chunk(monkeypatch, tmp_path):
    storage = LocalStorage(SimpleNamespace(storage_root=tmp_path, vm_local_mode=False))

    def failed_flush(*_):
        raise OSError("disk flush failed")

    monkeypatch.setattr(module.os, "fsync", failed_flush)
    with pytest.raises(OSError, match="flush failed"):
        await storage.write("recording", b"synthetic recording")
    assert not (tmp_path / "recording").exists()
