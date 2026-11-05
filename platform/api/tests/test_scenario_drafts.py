"""Real PostgreSQL rules for authoring storage; no new API endpoints are exercised."""

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb
from sqlalchemy.engine import make_url
from training_contracts import fingerprint


class AuthorFixture(tuple):
    def __repr__(self):
        return "<synthetic author fixture; credentials redacted>"


@pytest.fixture
def author(platform):
    token, user = platform.user("scenario_author")
    org = platform.organization(token)["id"]
    return AuthorFixture((platform, token, user["id"], org))


def connect(p, purpose="api", **kwargs):
    url = getattr(p.settings, purpose + "_database_url" if purpose != "api" else "database_url")
    return psycopg.connect(
        make_url(url.get_secret_value()).set(drivername="postgresql").render_as_string(hide_password=False),
        **kwargs,
    )


def draft(c, org, user, code="case_a", document=None, source=None, request=None):
    document = (
        document
        if document is not None
        else {"version": 2, "code": code, "patient": {"name": "Fictional patient"}}
    )
    did = uuid4()
    c.execute(
        "INSERT INTO device_platform.training_scenario_drafts(id,organization_id,request_key,request_fingerprint,code,schema_version,document,source_scenario_id,created_by,updated_by) VALUES(%s,%s,%s,%s,%s,2,%s,%s,%s,%s)",
        (did, org, request or uuid4(), fingerprint(document), code, Jsonb(document), source, user, user),
    )
    return did


def publish(c, org, user, did, *, revision=1, version=1, request=None, document=None):
    value = c.execute(
        "SELECT code,document FROM device_platform.training_scenario_drafts WHERE id=%s", (did,)
    ).fetchone()
    code, data = value
    data = document if document is not None else data
    sid = uuid4()
    c.execute(
        "INSERT INTO device_platform.training_scenarios(id,organization_id,request_key,code,version,document,fingerprint,created_by,approved_by,approved_at,approval,source_draft_id,source_draft_revision) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp(),%s,%s,%s)",
        (
            sid,
            org,
            request or uuid4(),
            code,
            version,
            Jsonb(data),
            fingerprint(data),
            user,
            user,
            Jsonb(
                {
                    "educator_name": "Test only",
                    "statement": "Synthetic database fixture, not clinical approval.",
                }
            ),
            did,
            revision,
        ),
    )
    return sid


def test_draft_envelope_bounds_identity_and_concurrent_revision_contract(author):
    p, _, user, org = author
    with connect(p) as c:
        did = draft(c, org, user)
        first = c.execute(
            "SELECT revision,created_at,updated_at,request_fingerprint FROM device_platform.training_scenario_drafts WHERE id=%s",
            (did,),
        ).fetchone()
        assert first[0] == 1 and first[1] == first[2]
        for bad in (
            None,
            [],
            {},
            {"version": None, "code": "bad"},
            {"version": 99, "code": "bad"},
            {"version": 2, "code": "wrong"},
            {"version": 2, "code": "bad", "payload": "x" * 524288},
        ):
            with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
                draft(c, org, user, "bad", bad if bad is not None else {"code": "bad"})
        changed = c.execute(
            "UPDATE device_platform.training_scenario_drafts SET document=document || %s, revision=%s, updated_by=%s WHERE organization_id=%s AND id=%s AND revision=%s RETURNING revision,created_at,updated_at,request_fingerprint",
            (Jsonb({"title": "Edited"}), 1, user, org, did, 1),
        ).fetchone()
        assert (
            changed[0] == 2 and changed[1] == first[1] and changed[2] >= first[2] and changed[3] == first[3]
        )
        assert (
            c.execute(
                "UPDATE device_platform.training_scenario_drafts SET revision=1 WHERE id=%s AND revision=1 RETURNING id",
                (did,),
            ).fetchone()
            is None
        )
        with pytest.raises(psycopg.errors.SerializationFailure), c.transaction():
            c.execute("UPDATE device_platform.training_scenario_drafts SET revision=1 WHERE id=%s", (did,))
        with pytest.raises(psycopg.errors.SerializationFailure), c.transaction():
            c.execute(
                'UPDATE device_platform.training_scenario_drafts SET revision=NULL, document=document || \'{"title":"Unexpected overwrite"}\'::jsonb WHERE id=%s',
                (did,),
            )
        for field, value in (
            ("code", "renamed"),
            ("request_key", uuid4()),
            ("request_fingerprint", "a" * 64),
            ("id", uuid4()),
            ("organization_id", uuid4()),
            ("created_by", uuid4()),
        ):
            from psycopg import sql

            with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
                c.execute(
                    sql.SQL("UPDATE device_platform.training_scenario_drafts SET {}=%s WHERE id=%s").format(
                        sql.Identifier(field)
                    ),
                    (value, did),
                )
        c.execute(
            "UPDATE device_platform.training_scenario_drafts SET is_archived=true,revision=2 WHERE id=%s",
            (did,),
        )
        with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
            c.execute(
                'UPDATE device_platform.training_scenario_drafts SET document=document || \'{"title":"Archived edit"}\'::jsonb,revision=3 WHERE id=%s',
                (did,),
            )
        c.execute(
            "UPDATE device_platform.training_scenario_drafts SET is_archived=false,revision=3 WHERE id=%s",
            (did,),
        )
        assert c.execute(
            "SELECT revision FROM device_platform.training_scenario_drafts WHERE id=%s", (did,)
        ).fetchone() == (4,)


def test_tenant_foreign_keys_publication_snapshot_and_history(author):
    p, token, user, org = author
    other = p.organization(token, name="Other tenant")["id"]
    with connect(p) as c:
        did = draft(c, org, user)
        sid = publish(c, org, user, did)
        for kwargs in (
            {"revision": 9, "version": 2},
            {"version": 2, "document": {"version": 2, "code": "case_a", "tampered": True}},
        ):
            with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
                publish(c, org, user, did, **kwargs)
        with pytest.raises(psycopg.errors.UniqueViolation), c.transaction():
            publish(c, org, user, did, version=2)
        with pytest.raises(psycopg.errors.ForeignKeyViolation), c.transaction():
            publish(c, other, user, did, version=2)
        with pytest.raises(psycopg.errors.ForeignKeyViolation), c.transaction():
            draft(c, other, user, "copied", source=sid)
        copied = draft(c, org, user, "copied", source=sid)
        assert copied != did
        with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
            c.execute(
                "UPDATE device_platform.training_scenarios SET source_draft_revision=99 WHERE id=%s", (sid,)
            )
        with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
            c.execute(
                "UPDATE device_platform.training_scenarios SET document=document || '{\"changed\":true}'::jsonb WHERE id=%s",
                (sid,),
            )
        c.execute(
            'UPDATE device_platform.training_scenario_drafts SET document=document || \'{"title":"Next revision"}\'::jsonb,revision=1 WHERE id=%s',
            (did,),
        )
        second = publish(c, org, user, did, revision=2, version=2)
        assert second != sid
        assert c.execute(
            "SELECT source_draft_revision, document ? 'title' FROM device_platform.training_scenarios WHERE id=%s",
            (sid,),
        ).fetchone() == (1, False)
        c.execute(
            "UPDATE device_platform.training_scenario_drafts SET is_archived=true,revision=2 WHERE id=%s",
            (did,),
        )
        with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
            publish(c, org, user, did, revision=3, version=3)


def test_publication_requires_approval_and_paired_provenance(author):
    p, _, user, org = author
    with connect(p) as c:
        did = draft(c, org, user)
        row = c.execute(
            "SELECT document FROM device_platform.training_scenario_drafts WHERE id=%s", (did,)
        ).fetchone()[0]
        for draft_id, rev in ((did, None), (None, 1), (did, 0), (did, 1)):
            with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
                c.execute(
                    "INSERT INTO device_platform.training_scenarios(id,organization_id,request_key,code,version,document,fingerprint,created_by,source_draft_id,source_draft_revision) VALUES(%s,%s,%s,'case_a',1,%s,%s,%s,%s,%s)",
                    (uuid4(), org, uuid4(), Jsonb(row), fingerprint(row), user, draft_id, rev),
                )


def test_draft_creation_keys_and_runtime_privileges(author):
    p, _, user, org = author
    key = uuid4()
    with connect(p) as c:
        did = draft(c, org, user, request=key)
        with pytest.raises(psycopg.errors.UniqueViolation), c.transaction():
            draft(c, org, user, code="another", request=key)
        with pytest.raises(psycopg.errors.UniqueViolation), c.transaction():
            draft(c, org, user)
        for query in (
            "DELETE FROM device_platform.training_scenario_drafts WHERE id=%s",
            "TRUNCATE device_platform.training_scenario_drafts",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege), c.transaction():
                c.execute(query, (did,) if "%s" in query else ())
    for purpose in ("worker", "retention"):
        with connect(p, purpose) as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute("SELECT document FROM device_platform.training_scenario_drafts")
    assert (
        p.sql(
            "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE n.nspname='device_platform' AND p.proname IN ('training_draft_guard','training_scenario_source_guard') AND a.grantee=0 AND a.privilege_type='EXECUTE'"
        )[0][0]
        == 0
    )


def test_two_editors_cannot_overwrite_the_same_revision(author):
    p, _, user, org = author
    with connect(p) as c:
        did = draft(c, org, user)
    barrier = Barrier(2)

    def edit(label):
        with connect(p) as c:
            barrier.wait(timeout=10)
            return c.execute(
                "UPDATE device_platform.training_scenario_drafts SET document=document || %s, revision=1 WHERE organization_id=%s AND id=%s AND revision=1 RETURNING revision",
                (Jsonb({"title": label}), org, did),
            ).fetchone()

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(edit, ("A", "B")))
    assert sum(r is not None for r in replies) == 1
    assert p.sql("SELECT revision FROM device_platform.training_scenario_drafts WHERE id=%s", (did,)) == [
        (2,)
    ]


def wait_for_lock(p, pid):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        rows = p.sql("SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s", (pid,))
        if rows == [("Lock",)]:
            return
        time.sleep(0.02)
    pytest.fail("Expected the second transaction to wait for the organization lock")


def test_draft_quota_serializes_concurrent_inserts(author):
    p, _, user, org = author
    with connect(p) as c:
        for number in range(99):
            draft(c, org, user, f"case_{number}")
    with connect(p) as first, connect(p) as second:
        draft(first, org, user, "last_allowed")
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(draft, second, org, user, "over_quota")
            wait_for_lock(p, second.info.backend_pid)
            first.commit()
            with pytest.raises(psycopg.errors.CheckViolation) as rejected:
                pending.result(timeout=10)
            assert rejected.value.diag.constraint_name == "training_draft_capacity"
            second.rollback()
    assert p.sql(
        "SELECT count(*) FROM device_platform.training_scenario_drafts WHERE organization_id=%s", (org,)
    ) == [(100,)]


def test_draft_creation_rejects_stale_snapshot_isolation(author):
    p, _, user, org = author
    for isolation in ("REPEATABLE READ", "SERIALIZABLE"):
        with connect(p) as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL " + isolation)
            with pytest.raises(psycopg.errors.InvalidTransactionState):
                draft(c, org, user)


def test_concurrent_publication_is_once_per_draft_revision(author):
    p, _, user, org = author
    with connect(p) as c:
        did = draft(c, org, user)
    with connect(p) as first, connect(p) as second:
        publish(first, org, user, did)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(publish, second, org, user, did, version=2)
            wait_for_lock(p, second.info.backend_pid)
            first.commit()
            with pytest.raises(psycopg.errors.UniqueViolation):
                pending.result(timeout=10)
            second.rollback()
    assert p.sql(
        "SELECT count(*) FROM device_platform.training_scenarios WHERE source_draft_id=%s", (did,)
    ) == [(1,)]


def test_atomic_rollback_keeps_draft_publication_and_audit_together(author):
    p, _, user, org = author
    with connect(p) as c:
        did = draft(c, org, user)
    event = uuid4()
    with connect(p) as c:
        sid = publish(c, org, user, did)
        c.execute(
            "INSERT INTO device_platform.activity_events(id,organization_id,actor_type,actor_user_id,category,event_type,entity_type,entity_id,severity,occurred_at,details,expires_at) VALUES(%s,%s,'user',%s,'audit','training.scenario.published','training_scenario',%s,'info',clock_timestamp(),%s,clock_timestamp()+interval '1 day')",
            (event, org, user, sid, Jsonb({"draft_revision": 1})),
        )
        c.rollback()
    assert p.sql("SELECT id FROM device_platform.training_scenarios WHERE id=%s", (sid,)) == []
    assert p.sql("SELECT id FROM device_platform.activity_events WHERE id=%s", (event,)) == []
    assert p.sql("SELECT revision FROM device_platform.training_scenario_drafts WHERE id=%s", (did,)) == [
        (1,)
    ]


def test_read_only_deployment_verifier(author):
    import os
    import shutil
    import subprocess

    p, _, _, _ = author
    url = make_url(p.dsn)
    args = [
        shutil.which("psql") or "C:/Program Files/PostgreSQL/17/bin/psql.exe",
        "-X",
        "-h",
        url.host,
        "-p",
        str(url.port),
        "-U",
        url.username,
        "-d",
        url.database,
        "-f",
        str(Path(__file__).resolve().parents[1] / "deploy/verify-scenario-library.sql"),
    ]
    result = subprocess.run(
        args, env={**os.environ, "PGPASSWORD": url.password or ""}, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "scenario authoring storage verified" in result.stdout
    p.sql("ALTER TABLE device_platform.training_scenario_drafts DROP CONSTRAINT training_draft_document")
    broken = subprocess.run(
        args, env={**os.environ, "PGPASSWORD": url.password or ""}, capture_output=True, text=True
    )
    assert broken.returncode != 0, "Verifier accepted a missing draft envelope constraint"
