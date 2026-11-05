"""The desktop monitor only observes externally owned services."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from startup import StopRequested
from supervisor import Supervisor


def test_unavailable_service_is_never_started_or_stopped():
    manager = Supervisor()
    manager.watch("Central API", lambda: False)
    for _ in range(2):
        manager.next_health = 0
        manager.monitor()
    manager.next_health = 0
    with pytest.raises(RuntimeError, match="owner application"):
        manager.monitor()
    assert not hasattr(manager, "ensure") and not hasattr(manager, "start_owned")


def test_readonly_monitor_recovers_and_can_be_cancelled():
    health = iter((False, True))
    state = []
    manager = Supervisor(state=lambda *value: state.append(value))
    manager.watch("Central API", lambda: next(health))
    manager.monitor()
    manager.next_health = 0
    manager.monitor()
    assert state == [("degraded", "Central API"), ("ready", None)]
    manager.cancelled = lambda: True
    with pytest.raises(StopRequested):
        manager.monitor()
