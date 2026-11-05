import importlib.util
from pathlib import Path


def test_installed_qualification_requires_ready_idle_service():
    path = Path(__file__).parents[1] / "deployment" / "qualify.py"
    spec = importlib.util.spec_from_file_location("pi_test_qualify", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    status = {
        "ready": True,
        "state": "idle",
        "active": False,
        "camera_active": False,
        "video_processing": False,
        "finishing": False,
        "job": None,
    }
    assert module.installed_idle(status)
    for change in ({"ready": False}, {"state": "unavailable"}, {"video_processing": True}):
        assert not module.installed_idle({**status, **change})
