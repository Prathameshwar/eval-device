import secrets

from pms_api.core.config import Settings


def test_history_reporting_defaults_on_and_explicit_opt_out_is_respected(monkeypatch):
    monkeypatch.delenv("PMS_LOCAL_HISTORY_ENABLED", raising=False)
    values = {"token_pepper": secrets.token_urlsafe(32), "media_signing_key": secrets.token_urlsafe(32)}
    assert Settings(_env_file=None, **values).local_history_enabled
    monkeypatch.setenv("PMS_LOCAL_HISTORY_ENABLED", "false")
    assert not Settings(_env_file=None, **values).local_history_enabled
