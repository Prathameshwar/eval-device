import json
import time
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from training_client.history_outbox import Outbox
from training_contracts.privacy import StorageError


def record(**kw):
    return {
        "turn_key": str(uuid4()),
        "occurred_at": datetime.now(UTC).isoformat(),
        "outcome": "completed",
        "input_text": "Fictional question",
        "response_text": "Fictional answer",
        **kw,
    }


def test_restart_conflict_ack_and_expiry(tmp_path):
    item = record()
    box = Outbox(tmp_path / "private", "owner")
    box.put(item)
    box.close()
    box = Outbox(tmp_path / "private", "owner")
    assert box.snapshot()[0]["record"] == item
    box.put(item)
    with pytest.raises(StorageError):
        box.put({**item, "response_text": "changed"})
    box.acknowledge(item["turn_key"])
    assert box.snapshot() == []
    box.put(record())
    for value in box.records.values():
        value["expires_at"] = time.time() - 1
    assert box.expire() == 1
    box.close()


def test_capacity_and_corrupt_file_do_not_destroy_valid_record(tmp_path):
    box = Outbox(tmp_path / "private", "owner", max_records=2)
    item = record()
    box.put(item)
    bad = box.path / (str(uuid4()) + ".json")
    bad.write_text("{broken")
    box.close()
    box = Outbox(tmp_path / "private", "owner", max_records=2)
    assert box.bad_count == 1 and box.snapshot()[0]["record"] == item
    with pytest.raises(StorageError):
        box.put(record())
    box.close()


def test_private_record_never_contains_credentials_and_single_writer(tmp_path):
    box = Outbox(tmp_path / "private", "owner")
    item = record()
    box.put(item)
    data = json.loads((box.path / (item["turn_key"] + ".json")).read_text())
    assert set(data) == {"record", "metrics", "state", "expires_at"}
    with pytest.raises((OSError, StorageError)):
        Outbox(tmp_path / "private", "owner")
    box.close()


def test_structurally_invalid_record_is_quarantined_and_namespace_cannot_escape(tmp_path):
    box = Outbox(tmp_path / "private", "owner")
    good = record()
    box.put(good)
    key = str(uuid4())
    (box.path / (key + ".json")).write_text(
        json.dumps({"record": {"turn_key": key}, "state": "pending", "expires_at": time.time() + 60})
    )
    box.close()
    box = Outbox(tmp_path / "private", "owner")
    assert box.bad_count == 1 and len(box.snapshot()) == 1
    box.close()
    with pytest.raises(StorageError):
        Outbox(tmp_path / "private", "../outside")


def test_failed_ack_cleanup_stops_retries_but_recovers_safely(tmp_path, monkeypatch):
    from pathlib import Path

    box = Outbox(tmp_path / "private", "owner")
    item = record()
    box.put(item)
    original = Path.unlink

    def fail_owned_file(path, *args, **kwargs):
        if path == box.path / (item["turn_key"] + ".json"):
            raise PermissionError("Busy file")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_owned_file)
        with pytest.raises(PermissionError):
            box.acknowledge(item["turn_key"])
    assert box.snapshot()[0]["state"] == "acknowledged"
    box.close()
    restarted = Outbox(tmp_path / "private", "owner")
    assert restarted.snapshot()[0]["state"] == "pending"
    assert restarted.snapshot()[0]["record"] == item
    restarted.acknowledge(item["turn_key"])
    restarted.close()
