"""Real PostgreSQL regressions for local accounts and browser sessions."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from sqlalchemy import select

from pms_api.database.models import AccountEmailOutbox
from pms_api.modules import auth
from pms_api.security.local_auth import decrypt_outbox_payload

OLD = "a long original test password"
NEW = "a different long test password"
EMAIL = "local-session@example.com"


def action_token(p, user_id, purpose):
    async def read():
        async with p.client.app.state.sessions() as session:
            row = await session.scalar(
                select(AccountEmailOutbox)
                .where(AccountEmailOutbox.user_id == UUID(user_id), AccountEmailOutbox.purpose == purpose)
                .order_by(AccountEmailOutbox.created_at.desc())
            )
            assert row is not None
            return decrypt_outbox_payload(row, p.settings)["token"]

    return p.client.portal.call(read)


def local_account(p, browser=False, remember=False):
    admin, _ = p.admin("session-owner")
    user = p.call(
        "POST",
        "/platform/users",
        admin,
        expected=201,
        json={
            "email": EMAIL,
            "display_name": "Session user",
        },
    )["user"]
    token = action_token(p, user["id"], "setup")
    p.call("POST", "/auth/password/setup", json={"token": token, "password": OLD})
    body = {"email": EMAIL, "password": OLD}
    if browser:
        body["remember"] = remember
    result = p.call("POST", "/auth/browser/login" if browser else "/auth/login", json=body)
    return admin, user, result


def test_browser_cookie_credential_is_opaque_bounded_and_revocable(platform):
    p = platform
    _, user, login = local_account(p, browser=True)
    token = login["session_token"]
    assert token.startswith("web_") and login["expires_in"] == p.settings.local_browser_session_hours * 3600
    assert "access_token" not in login and "refresh_token" not in login
    assert p.sql(
        "SELECT EXTRACT(EPOCH FROM (expires_at-created_at))::int "
        "FROM device_platform.local_sessions WHERE user_id=%s ORDER BY created_at DESC LIMIT 1",
        (user["id"],),
    ) == [(login["expires_in"],)]
    assert p.sql(
        "SELECT browser_token_hash=%s FROM device_platform.local_sessions WHERE user_id=%s",
        (token, user["id"]),
    ) == [(False,)]
    context = p.call("GET", "/auth/context", token)
    assert context["user"]["password_management"] is True and context["contexts"] == []
    p.call("GET", "/platform/users", token, expected=403)
    p.call("GET", "/me", "web_" + "x" * 43, expected=401)
    response = p.client.post("/api/v1/auth/logout", headers=p.headers(token))
    assert response.status_code == 204
    p.call("GET", "/me", token, expected=401)
    p.settings.local_browser_session_hours = 2
    remembered = p.call(
        "POST", "/auth/browser/login", json={"email": EMAIL, "password": OLD, "remember": True}
    )
    assert remembered["expires_in"] == 2 * 3600
    assert p.sql(
        "SELECT EXTRACT(EPOCH FROM (expires_at-created_at))::int "
        "FROM device_platform.local_sessions WHERE user_id=%s ORDER BY created_at DESC LIMIT 1",
        (user["id"],),
    ) == [(2 * 3600,)]


def test_parallel_browser_requests_do_not_rotate_or_revoke_session(platform):
    p = platform
    _, _, login = local_account(p, browser=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: p.client.get("/api/v1/auth/context", headers=p.headers(login["session_token"])),
                range(8),
            )
        )
    assert all(result.status_code == 200 for result in results)
    p.call("GET", "/me", login["session_token"])


def test_rehash_cannot_restore_password_replaced_while_login_was_verifying(platform, monkeypatch):
    p = platform
    _, _, login = local_account(p)
    started, resume = threading.Event(), threading.Event()
    original_hash = auth.hash_password

    async def paused_hash(value):
        if value == OLD:
            started.set()
            assert await asyncio.to_thread(resume.wait, 15)
        return await original_hash(value)

    monkeypatch.setattr(auth, "password_needs_rehash", lambda _: True)
    monkeypatch.setattr(auth, "hash_password", paused_hash)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(p.client.post, "/api/v1/auth/login", json={"email": EMAIL, "password": OLD})
        try:
            assert started.wait(10)
            p.call(
                "POST",
                "/auth/password/change",
                login["access_token"],
                json={"current_password": OLD, "new_password": NEW},
            )
        finally:
            resume.set()
        assert pending.result(timeout=15).status_code == 401
    monkeypatch.setattr(auth, "password_needs_rehash", lambda _: False)
    p.call("POST", "/auth/login", expected=401, json={"email": EMAIL, "password": OLD})
    changed = p.call("POST", "/auth/login", json={"email": EMAIL, "password": NEW})
    p.call("GET", "/me", changed["access_token"])


def test_email_change_reauthorizes_an_inflight_revoked_session(platform, monkeypatch):
    p = platform
    _, _, login = local_account(p)
    started, resume = threading.Event(), threading.Event()
    original = auth.locked_actor
    calls = 0

    async def pause_first(session, actor):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            assert await asyncio.to_thread(resume.wait, 15)
        return await original(session, actor)

    monkeypatch.setattr(auth, "locked_actor", pause_first)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            p.client.post,
            "/api/v1/auth/email/change",
            headers=p.headers(login["access_token"]),
            json={"email": "changed@example.com", "current_password": OLD},
        )
        try:
            assert started.wait(10)
            p.call(
                "POST",
                "/auth/password/change",
                login["access_token"],
                json={"current_password": OLD, "new_password": NEW},
            )
        finally:
            resume.set()
        assert pending.result(timeout=15).status_code == 401
    assert p.sql(
        "SELECT count(*) FROM device_platform.account_action_tokens WHERE purpose='email_change'"
    ) == [(0,)]


def test_password_change_invalidates_already_issued_email_confirmation(platform):
    p = platform
    _, user, login = local_account(p)
    access = login["access_token"]
    p.call(
        "POST",
        "/auth/email/change",
        access,
        expected=202,
        json={"email": "changed@example.com", "current_password": OLD},
    )
    token = action_token(p, user["id"], "email_change")
    p.call("POST", "/auth/password/change", access, json={"current_password": OLD, "new_password": NEW})
    p.call("POST", "/auth/email/confirm", expected=422, json={"token": token})
    p.call("POST", "/auth/login", json={"email": EMAIL, "password": NEW})


def test_email_confirmation_changes_identifier_and_revokes_both_session_types(platform):
    p = platform
    _, user, bearer = local_account(p)
    browser = p.call("POST", "/auth/browser/login", json={"email": EMAIL, "password": OLD})
    p.call(
        "POST",
        "/auth/email/change",
        browser["session_token"],
        expected=202,
        json={"email": "changed@example.com", "current_password": OLD},
    )
    token = action_token(p, user["id"], "email_change")
    p.call("POST", "/auth/email/confirm", json={"token": token})
    p.call("POST", "/auth/email/confirm", expected=422, json={"token": token})
    p.call("GET", "/me", bearer["access_token"], expected=401)
    p.call("GET", "/me", browser["session_token"], expected=401)
    p.call("POST", "/auth/login", expected=401, json={"email": EMAIL, "password": OLD})
    p.call("POST", "/auth/login", json={"email": "changed@example.com", "password": OLD})


def test_reset_purpose_expiry_reuse_and_session_invalidation(platform):
    p = platform
    _, user, login = local_account(p, browser=True)
    p.call("POST", "/auth/password/forgot", expected=202, json={"email": EMAIL})
    token = action_token(p, user["id"], "password_reset")
    p.call("POST", "/auth/password/setup", expected=422, json={"token": token, "password": NEW})
    p.call("POST", "/auth/password/reset", json={"token": token, "password": NEW})
    p.call("POST", "/auth/password/reset", expected=422, json={"token": token, "password": OLD})
    p.call("GET", "/me", login["session_token"], expected=401)
    p.call("POST", "/auth/login", expected=401, json={"email": EMAIL, "password": OLD})
    p.call("POST", "/auth/login", json={"email": EMAIL, "password": NEW})
    p.call("POST", "/auth/password/forgot", expected=202, json={"email": EMAIL})
    expired = action_token(p, user["id"], "password_reset")
    p.sql(
        "UPDATE device_platform.account_action_tokens SET created_at=now()-interval '2 days', expires_at=now()-interval '1 day' WHERE purpose='password_reset'"
    )
    p.call("POST", "/auth/password/reset", expected=422, json={"token": expired, "password": OLD})


def test_refresh_rotates_and_replay_revokes_family(platform):
    p = platform
    _, _, login = local_account(p)
    rotated = p.call("POST", "/auth/refresh", json={"refresh_token": login["refresh_token"]})
    p.call("GET", "/me", rotated["access_token"])
    p.call("GET", "/me", login["access_token"], expected=401)
    replay = p.call("POST", "/auth/refresh", expected=401, json={"refresh_token": login["refresh_token"]})
    assert replay["error"]["code"] == "refresh_reuse"
    p.call("GET", "/me", rotated["access_token"], expected=401)


def test_simultaneous_refresh_detects_replay(platform):
    p = platform
    _, _, login = local_account(p)
    barrier = threading.Barrier(2)

    def refresh():
        barrier.wait(timeout=10)
        return p.client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(refresh) for _ in range(2)]
        results = [item.result(timeout=15) for item in pending]
    assert sorted(item.status_code for item in results) == [200, 401]
    winner = next(item.json() for item in results if item.status_code == 200)
    p.call("GET", "/me", winner["access_token"], expected=401)


def test_deactivation_and_expiry_never_revive_browser_session(platform):
    p = platform
    admin, user, login = local_account(p, browser=True)
    p.call("PATCH", f"/platform/users/{user['id']}", admin, json={"is_active": False})
    p.call("GET", "/me", login["session_token"], expected=401)
    p.call("POST", "/auth/browser/login", expected=401, json={"email": EMAIL, "password": OLD})
    p.call("PATCH", f"/platform/users/{user['id']}", admin, json={"is_active": True})
    p.call("GET", "/me", login["session_token"], expected=401)
    fresh = p.call("POST", "/auth/browser/login", json={"email": EMAIL, "password": OLD})
    p.sql(
        "UPDATE device_platform.local_sessions SET created_at=now()-interval '1 day', last_used_at=now()-interval '1 day', expires_at=now()-interval '1 second' WHERE user_id=%s",
        (user["id"],),
    )
    p.call("GET", "/me", fresh["session_token"], expected=401)
    p.settings.local_auth_enabled = False
    p.call("POST", "/auth/browser/login", expected=503, json={"email": EMAIL, "password": OLD})


def test_contexts_exclude_inactive_memberships_and_do_not_union_platform_grants(platform):
    p = platform
    admin, user, login = local_account(p, browser=True)
    organization = p.organization(admin)
    p.sql(
        "INSERT INTO device_platform.organization_memberships(id, organization_id, user_id, role, is_active, invitation_status, joined_at) VALUES(gen_random_uuid(),%s,%s,'org_read_only',true,'accepted',now())",
        (organization["id"], user["id"]),
    )
    context = p.call("GET", "/auth/context", login["session_token"])
    assert len(context["contexts"]) == 1
    assert context["contexts"][0]["role"] == "org_read_only"
    assert all(not permission.startswith("platform.") for permission in context["contexts"][0]["permissions"])
    p.call("GET", "/platform/users", login["session_token"], expected=403)
    p.sql(
        "UPDATE device_platform.organization_memberships SET is_active=false WHERE user_id=%s", (user["id"],)
    )
    assert p.call("GET", "/auth/context", login["session_token"])["contexts"] == []


def test_invalid_credentials_are_generic_rate_limited_and_redacted(platform):
    p = platform
    for attempt in range(11):
        response = p.client.post(
            "/api/v1/auth/browser/login", json={"email": "missing@example.com", "password": OLD}
        )
        assert response.status_code == (401 if attempt < 10 else 429)
        assert OLD not in response.text
    invalid = p.client.post("/api/v1/auth/login", json={"email": "invalid", "password": OLD})
    assert invalid.status_code == 422 and OLD not in invalid.text
