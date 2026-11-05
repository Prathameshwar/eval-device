from human_test.config import Settings


def test_new_laptop_reports_history_by_default_and_can_explicitly_opt_out(monkeypatch):
    monkeypatch.delenv("HUMAN_HISTORY_ENABLED", raising=False)
    assert Settings(_env_file=None).history_enabled
    monkeypatch.setenv("HUMAN_HISTORY_ENABLED", "false")
    assert not Settings(_env_file=None).history_enabled
