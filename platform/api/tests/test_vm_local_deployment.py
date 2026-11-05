import base64
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pms_api.core.common import AppError
from pms_api.core.config import Settings
from pms_api.integrations.storage import LocalStorage
from pms_api.modules import auth


def vm_settings(**changes):
    values = {
        "environment": "production",
        "vm_local_mode": True,
        "public_base_url": "https://eval.centralindia.cloudapp.azure.com",
        "local_auth_enabled": True,
        "local_token_signing_key": "l" * 40,
        "token_pepper": "p" * 40,
        "media_signing_key": "m" * 40,
        "active_credential_key": "v1",
        "credential_keys": {"v1": base64.b64encode(b"k" * 32).decode()},
        "storage_backend": "local",
        "storage_root": Path("/var/lib/pms-media"),
        "oidc_issuer": "",
        "oidc_audience": "",
        "smtp_host": "",
        "smtp_sender": "",
    }
    values.update(changes)
    return Settings(_env_file=None, **values)


def test_vm_local_mode_requires_explicit_private_configuration():
    assert vm_settings().vm_local_mode
    for change in (
        {"vm_local_mode": False},
        {"environment": "staging"},
        {"storage_root": Path("/tmp/media")},
        {"storage_backend": "azure"},
        {"oidc_issuer": "https://issuer.example", "oidc_audience": "audience"},
        {"smtp_host": "smtp.example", "smtp_sender": "sender@example.com"},
        {"local_auth_enabled": False},
    ):
        with pytest.raises(ValidationError):
            vm_settings(**change)


@pytest.mark.asyncio
async def test_vm_local_mode_fails_closed_for_email_actions():
    settings = vm_settings()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))
    with pytest.raises(AppError) as denied:
        auth.email_available(request)
    assert denied.value.status == 503


@pytest.mark.asyncio
async def test_vm_local_media_quota_is_shared_and_overwrite_safe(monkeypatch, tmp_path):
    if sys.platform == "win32":
        monkeypatch.setitem(
            sys.modules,
            "fcntl",
            SimpleNamespace(flock=lambda *_: None, LOCK_EX=1, LOCK_UN=8),
        )
    storage = LocalStorage(
        SimpleNamespace(storage_root=tmp_path, vm_local_mode=True, vm_local_storage_limit_bytes=5)
    )
    await storage.write("a", b"1234")
    with pytest.raises(AppError) as full:
        await storage.write("b", b"56")
    assert full.value.status == 507
    assert not (tmp_path / "b").exists()
    await storage.write("a", b"12")
    await storage.write("b", b"345")
    assert (tmp_path / "a").read_bytes() == b"12"
    await storage.delete("a")
    await storage.write("c", b"67")
    assert (tmp_path / "c").read_bytes() == b"67"
