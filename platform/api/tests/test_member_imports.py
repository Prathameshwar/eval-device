"""Workbook validation and tenant import behavior through real runtime grants."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from uuid import uuid4
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook, load_workbook

from pms_api.core.common import AppError
from pms_api.database.session import engine_for, sessions_for
from pms_api.modules.invitation_delivery import deliver_once
from pms_api.modules.member_workbooks import MAX_BYTES, MIME, parse_workbook, template_bytes, workbook_bytes


def book(rows):
    return workbook_bytes({"Members": [("Full name", "Email"), *rows]})


def setup(h):
    admin, _ = h.admin()
    org = h.organization(admin)["id"]
    return admin, org, f"/organizations/{org}/member-imports"


def validate(h, token, path, rows, role="org_user", auth="local", expected=201, **params):
    return upload(h, token, path, book(rows), role, auth, expected, params)


def upload(h, token, path, data, role="org_user", auth="local", expected=201, params=None):
    response = h.client.post(
        "/api/v1" + path + "/validate",
        content=data,
        params={"role": role, "auth_method": auth, **(params or {})},
        headers={**h.headers(token), "Content-Type": MIME},
    )
    assert response.status_code == expected, response.text
    return response.json()


def test_template_plain_text_and_round_trip():
    template = load_workbook(BytesIO(template_bytes("org_trainee", "local")))
    assert template.sheetnames == ["Members", "Instructions"]
    assert [c.value for c in template["Members"][1]] == ["Full name", "Email", "Password (optional)"]
    external = load_workbook(BytesIO(template_bytes("org_user", "oidc")))
    assert "Leave Password blank for external sign-in" in external["Instructions"]["B6"].value
    data = book([("=not a formula", "person@example.com")])
    cells = load_workbook(BytesIO(data))["Members"]
    assert cells["A2"].data_type == "s"
    assert parse_workbook(data)[0]["full_name"] == "=not a formula"


@pytest.mark.parametrize(
    "data,code",
    [
        (b"", "import_file_size"),
        (b"x" * (MAX_BYTES + 1), "import_file_size"),
        (b"not excel", "import_invalid_workbook"),
        (book([]), "import_empty"),
        (workbook_bytes({"Other": [["Full name", "Email"]]}), "import_sheet"),
        (workbook_bytes({"Members": [["Email", "Full name"], ["a@example.com", "A"]]}), "import_headers"),
        (book([(str(i), f"p{i}@example.com") for i in range(201)]), "import_row_limit"),
    ],
    ids=lambda value: "workbook" if isinstance(value, bytes) else value,
)
def test_reject_invalid_workbook(data, code):
    with pytest.raises(AppError) as result:
        parse_workbook(data)
    assert result.value.code == code


def test_import_upload_limit_is_enforced_before_workbook_parsing(platform):
    h = platform
    token, _, path = setup(h)
    response = h.client.post(
        "/api/v1" + path + "/validate",
        content=b"x" * (MAX_BYTES + 1),
        params={"role": "org_user", "auth_method": "local"},
        headers={**h.headers(token), "Content-Type": MIME},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
    assert h.sql("SELECT count(*) FROM device_platform.member_imports") == [(0,)]


def test_formula_and_numeric_cells_are_row_errors():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Members"
    sheet.append(["Full name", "Email"])
    sheet.append(["=1+1", "one@example.com"])
    sheet.append([123, "two@example.com"])
    sheet.append(["", ""])
    sheet.append(["Valid", "valid@example.com"])
    target = BytesIO()
    workbook.save(target)
    rows = parse_workbook(target.getvalue())
    assert [r["status"] for r in rows] == ["invalid", "invalid", "ready"]
    assert "No saved value for Full name" in rows[0]["message"]
    assert "as text" in rows[1]["message"]
    assert rows[-1]["row_number"] == 5


@pytest.mark.parametrize(
    "member,payload",
    [
        ("xl/worksheets/sheet1.xml", b'<!DOCTYPE x [<!ENTITY boom "unsafe">]><x>&boom;</x>'),
        ("xl/worksheets/sheet1.xml", b'<worksheet><sheetData><row r="999999"/></sheetData></worksheet>'),
        (
            "xl/worksheets/sheet1.xml",
            b'<worksheet><sheetData><row r="2"><c r="ZZZ2"/></row></sheetData></worksheet>',
        ),
        (
            "xl/worksheets/sheet1.xml",
            b'<worksheet><sheetData><row r="2"><c r="A999999"/></row></sheetData></worksheet>',
        ),
        ("xl/sharedStrings.xml", b"x" * (4 * 1024 * 1024 + 1)),
        (
            "xl/_rels/workbook.xml.rels",
            b'<Relationships><Relationship TargetMode="External" Target="https://example.com"/></Relationships>',
        ),
    ],
    ids=lambda value: "payload" if isinstance(value, bytes) else value,
)
def test_hostile_workbooks_are_rejected(member, payload):
    source = ZipFile(BytesIO(book([("A", "a@example.com")])))
    target = BytesIO()
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for name in source.namelist():
            if name != member:
                archive.writestr(name, source.read(name))
        archive.writestr(member, payload)
    with pytest.raises(AppError):
        parse_workbook(target.getvalue())


def cached_formula_workbook(cached_values=None, cell_types=None):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Members"
    sheet.append(["Full name", "Email", "Password (optional)"])
    sheet.append(['="Saved Person"', '="saved@example.com"', '="saved-password-123"'])
    target = BytesIO()
    workbook.save(target)
    result = BytesIO()
    with ZipFile(BytesIO(target.getvalue())) as source, ZipFile(result, "w", ZIP_DEFLATED) as archive:
        for name in source.namelist():
            data = source.read(name)
            if name == "xl/worksheets/sheet1.xml":
                root = ElementTree.fromstring(data)
                namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
                for cell in root.iter(namespace + "c"):
                    if cell.find(namespace + "f") is not None:
                        cell.set("t", (cell_types or {}).get(cell.get("r"), "str"))
                        values = {
                            "A2": "Saved Person",
                            "B2": "saved@example.com",
                            "C2": "saved-password-123",
                        } | (cached_values or {})
                        cell.find(namespace + "v").text = values[cell.get("r")]
                data = ElementTree.tostring(root)
            archive.writestr(name, data)
    return result.getvalue()


def test_formulas_import_saved_values_without_evaluation():
    row = parse_workbook(cached_formula_workbook())[0]
    assert row["status"] == "ready"
    assert row["full_name"] == "Saved Person"
    assert row["email"] == "saved@example.com"
    assert row["password"] == "saved-password-123"


def test_saved_empty_optional_password_is_accepted():
    row = parse_workbook(cached_formula_workbook({"C2": ""}))[0]
    assert row["status"] == "ready" and row["password"] == ""


def test_cached_excel_errors_are_identified_instead_of_imported():
    row = parse_workbook(cached_formula_workbook({"A2": "#REF!"}, {"A2": "e"}))[0]
    assert row["status"] == "invalid"
    assert row["message"] == "Fix the Excel error in Full name and save the workbook."


def test_hyperlinks_and_unused_workbook_features_do_not_block_import(monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail("Workbook parsing must never fetch external links")

    monkeypatch.setattr("socket.create_connection", no_network)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Members"
    sheet.append(["Full name", "Email"])
    sheet.append(["Linked Person", "linked@example.com"])
    sheet["B2"].hyperlink = "mailto:linked@example.com"
    sheet["A2"].hyperlink = "https://example.com/person"
    workbook.create_sheet("Notes")["A1"] = "=1+1"
    target = BytesIO()
    workbook.save(target)
    result = BytesIO()
    with ZipFile(BytesIO(target.getvalue())) as source, ZipFile(result, "w", ZIP_DEFLATED) as archive:
        for name in source.namelist():
            archive.writestr(name, source.read(name))
        archive.writestr("xl/vbaProject.bin", b"ignored macro content")
        archive.writestr("xl/embeddings/oleObject1.bin", b"ignored embedded content")
        archive.writestr("xl/activeX/activeX1.bin", b"ignored object")
        archive.writestr("xl/externalLinks/externalLink1.xml", b"<externalLink/>")
    rows = parse_workbook(result.getvalue())
    assert len(rows) == 1
    assert rows[0]["status"] == "ready"
    assert rows[0]["email"] == "linked@example.com"


def test_missing_formula_results_identify_cells_instead_of_skipping_row():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Members"
    sheet.append(["Full name", "Email", "Password (optional)"])
    sheet.append(['="Name"', '="person@example.com"', '="password-12345"'])
    target = BytesIO()
    workbook.save(target)
    row = parse_workbook(target.getvalue())[0]
    assert row["row_number"] == 2 and row["status"] == "invalid"
    assert "Full name, Email, Password (optional)" in row["message"]
    assert "Recalculate and save" in row["message"]


def test_saved_formula_values_validate_and_import_end_to_end(platform):
    h = platform
    token, _, path = setup(h)
    batch = upload(h, token, path, cached_formula_workbook())
    assert batch["counts"]["ready"] == 1
    result = h.call("POST", path + "/" + batch["id"] + "/commit", token)
    assert result["counts"]["succeeded"] == 1
    assert result["rows"][0]["email"] == "saved@example.com"
    assert result["rows"][0]["password"] == "saved-password-123"


def test_validation_partial_import_reports_and_idempotency(platform):
    h = platform
    token, org, path = setup(h)
    batch = validate(
        h,
        token,
        path,
        [
            ("Valid", "valid@example.com"),
            ("Invalid", "bad"),
            ("Duplicate", "VALID@example.com"),
            ("", "missing@example.com"),
            ("Second", "second@example.com"),
        ],
        role="org_trainee",
    )
    assert batch["counts"] == {"total": 5, "ready": 2, "failed": 3, "succeeded": 0}
    assert h.sql("SELECT count(*) FROM device_platform.users WHERE auth_method='local'")[0][0] == 0
    assert not batch["email_configured"]
    url = path + "/" + batch["id"]
    result = h.call("POST", url + "/commit", token)
    assert result["counts"] == {"total": 5, "ready": 0, "failed": 3, "succeeded": 2}
    assert result["status"] == "completed"
    assert h.call("POST", url + "/commit", token) == result
    assert h.call("GET", url, token) == result
    assert h.call("GET", path, token)["items"][0]["counts"] == result["counts"]
    assert h.sql(
        "SELECT role,invitation_status,is_active FROM device_platform.organization_memberships WHERE invited_email IS NOT NULL"
    ) == [("org_trainee", "pending", False), ("org_trainee", "pending", False)]
    assert h.sql("SELECT count(*) FROM device_platform.account_email_outbox")[0][0] == 0
    assert h.sql("SELECT count(*) FROM device_platform.invitation_email_outbox")[0][0] == 2
    assert not any(
        secret in json.dumps(result) for secret in ("inv_", "act_", "encrypted_payload", "token_hash")
    )
    response = h.client.get("/api/v1" + url + "/report", headers=h.headers(token))
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    report = load_workbook(BytesIO(response.content))
    assert report["Errors"].max_row == 4
    assert report["Members"].max_row == 4
    assert [r["email"] for r in parse_workbook(response.content)] == [
        "bad",
        "valid@example.com",
        "missing@example.com",
    ]
    events = h.sql(
        "SELECT details::text FROM device_platform.activity_events WHERE entity_id=%s", (batch["id"],)
    )
    assert len(events) >= 2 and all("@example.com" not in e[0] for e in events)


def test_scopes_roles_departments_and_lifecycle(platform):
    h = platform
    token, org, path = setup(h)
    stranger, _ = h.admin("outsider")
    for suffix in ("", "/template?role=org_user&auth_method=local"):
        h.call("GET", path + suffix, stranger, expected=404)
    batch = validate(h, token, path, [("Person", "person@example.com")])
    other_org = h.organization(stranger, "Other tenant")["id"]
    other = f"/organizations/{other_org}/member-imports/{batch['id']}"
    for suffix in ("", "/report"):
        h.call("GET", other + suffix, stranger, expected=404)
    h.call("POST", other + "/commit", stranger, expected=404)
    validate(h, token, path, [("Escalate", "escalate@example.com")], role="platform_admin", expected=422)
    foreign_dept = h.call(
        "POST", f"/organizations/{other_org}/departments", stranger, expected=201, json={"name": "Foreign"}
    )["id"]
    validate(h, token, path, [("Person", "p@example.com")], department_id=foreign_dept, expected=422)
    own_dept = h.call("POST", f"/organizations/{org}/departments", token, expected=201, json={"name": "Own"})[
        "id"
    ]
    validate(
        h, token, path, [("Admin", "a@example.com")], role="org_admin", department_id=own_dept, expected=422
    )
    low, user = h.user("reader")
    h.sql(
        """INSERT INTO device_platform.organization_memberships(id,organization_id,user_id,role,invitation_status,is_active,joined_at)
             VALUES(%s,%s,%s,'org_read_only','accepted',true,now())""",
        (uuid4(), org, user["id"]),
    )
    h.call("GET", path, low, expected=403)
    h.call("POST", path + "/" + batch["id"] + "/commit", low, expected=403)
    validate(h, low, path, [("Fail", "f@example.com")], expected=403)
    h.call("PATCH", f"/platform/organizations/{org}", token, json={"is_active": False})
    h.call("POST", path + "/" + batch["id"] + "/commit", token, expected=409)
    assert h.call("GET", path + "/" + batch["id"], token)["status"] == "validated"


def test_revalidation_no_orphan_accounts_and_capacity(platform):
    h = platform
    token, org, path = setup(h)
    batch = validate(h, token, path, [("First", "first@example.com"), ("Second", "second@example.com")])
    h.call(
        "POST",
        f"/organizations/{org}/invitations",
        token,
        expected=201,
        json={"email": "first@example.com", "role": "org_user", "auth_method": "oidc"},
    )
    result = h.call("POST", path + "/" + batch["id"] + "/commit", token)
    assert result["counts"]["failed"] == 1 and result["counts"]["succeeded"] == 1
    assert h.sql("SELECT count(*) FROM device_platform.users WHERE email='first@example.com'")[0][0] == 0
    # Simulate a lower remaining quota after validation while preserving existing usage.
    batch = validate(h, token, path, [("Third", "third@example.com"), ("Fourth", "fourth@example.com")])
    h.sql("UPDATE device_platform.subscription_plans SET max_users=4 WHERE code='standard'")
    result = h.call("POST", path + "/" + batch["id"] + "/commit", token)
    assert result["counts"]["succeeded"] == 1 and result["rows"][1]["code"] == "subscription_user_limit"
    assert h.sql("SELECT count(*) FROM device_platform.users WHERE email='fourth@example.com'")[0][0] == 0
    failed = validate(h, token, path, [("Fifth", "fifth@example.com")])
    assert failed["rows"][0]["code"] == "subscription_user_limit"
    h.call("POST", path + "/" + failed["id"] + "/commit", token, expected=409)


def test_concurrent_commit_and_cross_batch_duplicates(platform):
    h = platform
    token, _, path = setup(h)
    first = validate(h, token, path, [("First", "first@example.com")])
    second = validate(h, token, path, [("First", "first@example.com")])

    def commit(batch):
        return h.call("POST", path + "/" + batch["id"] + "/commit", token)

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(commit, [first, first, second]))
    assert results[0] == results[1]
    assert sorted(r["counts"]["succeeded"] for r in (results[0], results[2])) == [0, 1]
    assert h.sql("SELECT count(*) FROM device_platform.local_credentials")[0][0] == 1
    assert h.sql("SELECT count(*) FROM device_platform.invitation_email_outbox")[0][0] == 1


def test_department_change_expiry_and_existing_identity(platform):
    h = platform
    token, org, path = setup(h)
    dept = h.call(
        "POST", f"/organizations/{org}/departments", token, expected=201, json={"name": "Training"}
    )["id"]
    batch = validate(h, token, path, [("Person", "person@example.com")], department_id=dept)
    h.call("PATCH", f"/organizations/{org}/departments/{dept}", token, json={"is_active": False})
    result = h.call("POST", path + "/" + batch["id"] + "/commit", token)
    assert result["counts"]["failed"] == 1
    assert h.sql("SELECT count(*) FROM device_platform.local_credentials")[0][0] == 0
    batch = validate(h, token, path, [("Expired", "expired@example.com")])
    h.sql(
        "UPDATE device_platform.member_imports SET created_at=now()-interval '2 days',validated_until=now()-interval '1 day',expires_at=now()+interval '20 days' WHERE id=%s",
        (batch["id"],),
    )
    h.call("POST", path + "/" + batch["id"] + "/commit", token, expected=409)
    account = h.call(
        "POST",
        "/platform/users",
        token,
        expected=201,
        json={"display_name": "Original", "email": "existing@example.com"},
    )["user"]
    batch = validate(h, token, path, [("Do not overwrite", "existing@example.com")], role="org_read_only")
    assert h.call("POST", path + "/" + batch["id"] + "/commit", token)["counts"]["succeeded"] == 1
    assert h.call("GET", "/platform/users/" + account["id"], token)["display_name"] == "Original"


def test_encrypted_delivery_manual_retry_and_cleanup(platform, monkeypatch):
    h = platform
    token, _, path = setup(h)
    batch = validate(h, token, path, [("One", "one@example.com"), ("Two", "two@example.com")], auth="oidc")
    result = h.call("POST", path + "/" + batch["id"] + "/commit", token)
    sent = []

    async def sender(settings, recipient, raw):
        assert raw.startswith("inv_")
        sent.append(recipient)
        return recipient == "one@example.com"

    monkeypatch.setattr("pms_api.modules.invitation_delivery.send_invitation", sender)
    settings = h.settings.model_copy(update={"smtp_host": "mock.invalid", "smtp_sender": "test@example.com"})

    async def cycle():
        engine = engine_for(settings)
        try:
            return await deliver_once(sessions_for(engine), settings)
        finally:
            await engine.dispose()

    assert asyncio.run(cycle()) == 2
    assert asyncio.run(cycle()) == 0
    assert len(sent) == 2
    statuses = h.call("GET", path + "/" + batch["id"], token)["rows"]
    assert {r["email_status"] for r in statuses} == {"sent", "failed"}
    raw = h.sql("SELECT encrypted_payload FROM device_platform.invitation_email_outbox")
    assert all(b"inv_" not in bytes(row[0]) for row in raw)
    # An interrupted send must be marked uncertain, never automatically retried.
    h.sql(
        "UPDATE device_platform.invitation_email_outbox SET status='sending',lease_expires_at=now()-interval '1 second' WHERE membership_id=%s",
        (result["rows"][1]["membership_id"],),
    )
    assert asyncio.run(cycle()) == 0 and len(sent) == 2
    assert h.call("GET", path + "/" + batch["id"], token)["rows"][1]["email_status"] == "unknown"
    h.sql(
        "UPDATE device_platform.member_imports SET created_at=now()-interval '31 days',validated_until=now()-interval '30 days',expires_at=now()-interval '1 day' WHERE id=%s",
        (batch["id"],),
    )
    asyncio.run(cycle())
    h.call("GET", path + "/" + batch["id"], token, expected=404)


def test_failed_row_rolls_back_account_setup_and_audits(platform, monkeypatch):
    h = platform
    token, _, path = setup(h)
    batch = validate(
        h, token, path, [("Rollback", "rollback@example.com"), ("Success", "success@example.com")]
    )
    from pms_api.modules import member_imports

    original = member_imports.queue_invitation

    def fail_first(session, settings, member, raw):
        if member.invited_email == "rollback@example.com":
            raise AppError(409, "delivery_unavailable", "Invitation could not be prepared")
        return original(session, settings, member, raw)

    monkeypatch.setattr(member_imports, "queue_invitation", fail_first)
    result = h.call("POST", path + "/" + batch["id"] + "/commit", token)
    assert result["counts"]["succeeded"] == 1 and result["counts"]["failed"] == 1
    assert h.sql("SELECT count(*) FROM device_platform.users WHERE email='rollback@example.com'")[0][0] == 0
    assert h.sql("SELECT count(*) FROM device_platform.account_email_outbox")[0][0] == 0
    assert (
        h.sql(
            "SELECT count(*) FROM device_platform.activity_events WHERE event_type='membership.local_user_created'"
        )[0][0]
        == 1
    )


def test_import_passwords_are_generated_or_supplied_and_recoverable_from_history(platform):
    h = platform
    token, org, path = setup(h)
    supplied = "supplied-only-test-password-2026"
    workbook = workbook_bytes(
        {
            "Members": [
                ("Full name", "Email", "Password (optional)"),
                ("Supplied", "supplied@example.com", supplied),
                ("Generated", "generated@example.com", ""),
            ]
        }
    )
    batch = upload(h, token, path, workbook)
    assert supplied not in json.dumps(batch)
    assert batch["rows"][0]["has_password"] and not batch["rows"][1]["has_password"]
    raw = h.sql(
        "SELECT rows::text,passwords_encrypted FROM device_platform.member_imports WHERE id=%s",
        (batch["id"],),
    )[0]
    assert supplied not in raw[0] and supplied.encode() not in bytes(raw[1])
    result = h.call("POST", path + "/" + batch["id"] + "/commit", token)
    assert result["password_count"] == 2
    passwords = {row["email"]: row["password"] for row in result["rows"]}
    assert passwords["supplied@example.com"] == supplied
    assert len(passwords["generated@example.com"]) >= 24
    assert h.call("GET", path, token)["items"][0]["password_count"] == 2
    assert h.call("GET", path + "/" + batch["id"], token)["rows"] == result["rows"]
    response = h.client.get(
        "/api/v1" + path + "/" + batch["id"] + "/report?passwords_only=true",
        headers=h.headers(token),
    )
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    downloaded = load_workbook(BytesIO(response.content))["Passwords"]
    assert [cell.value for cell in downloaded[2]] == ["Supplied", "supplied@example.com", supplied]
    for email, password in passwords.items():
        assert (
            h.call("POST", "/auth/login", json={"email": email, "password": password})["user"]["email"]
            == email
        )
    assert h.sql("SELECT count(*) FROM device_platform.account_email_outbox") == [(0,)]
    events = h.sql(
        "SELECT event_type FROM device_platform.activity_events WHERE entity_id=%s", (batch["id"],)
    )
    assert ("membership.import.passwords_viewed",) in events
    assert ("membership.import.passwords_downloaded",) in events
    invalid = upload(
        h,
        token,
        path,
        workbook_bytes(
            {
                "Members": [
                    ("Full name", "Email", "Password (optional)"),
                    ("Existing", "supplied@example.com", "do-not-change-existing-password"),
                ]
            }
        ),
    )
    assert invalid["rows"][0]["code"] == "existing_account_password"
    oidc = upload(
        h,
        token,
        path,
        workbook_bytes(
            {
                "Members": [
                    ("Full name", "Email", "Password (optional)"),
                    ("Supplied", "oidc-supplied@example.com", supplied),
                    ("Blank", "oidc-blank@example.com", ""),
                ]
            }
        ),
        auth="oidc",
    )
    assert oidc["rows"][0]["code"] == "password_auth_method"
    assert oidc["rows"][1]["status"] == "ready"
    outsider, _ = h.admin("password-history-outsider")
    for suffix in ("", "/report?passwords_only=true"):
        h.call("GET", path + "/" + batch["id"] + suffix, outsider, expected=404)
    h.sql(
        "UPDATE device_platform.member_imports SET created_at=now()-interval '31 days', "
        "validated_until=now()-interval '30 days', expires_at=now()-interval '1 day' WHERE id=%s",
        (batch["id"],),
    )
    for suffix in ("", "/report?passwords_only=true"):
        h.call("GET", path + "/" + batch["id"] + suffix, token, expected=404)


def test_concurrent_batches_cannot_overbook_one_remaining_seat(platform):
    h = platform
    token, _, path = setup(h)
    h.sql("UPDATE device_platform.subscription_plans SET max_users=2 WHERE code='standard'")
    batches = [validate(h, token, path, [(name, name + "@example.com")]) for name in ["one", "two"]]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda b: h.call("POST", path + "/" + b["id"] + "/commit", token), batches))
    assert sorted(r["counts"]["succeeded"] for r in results) == [0, 1]
    assert h.sql("SELECT count(*) FROM device_platform.local_credentials")[0][0] == 1


def test_local_auth_changed_after_validation_and_runtime_grants(platform):
    h = platform
    token, _, path = setup(h)
    batch = validate(h, token, path, [("New", "new@example.com")])
    h.settings.local_auth_enabled = False
    h.call("POST", path + "/" + batch["id"] + "/commit", token, expected=409)
    assert h.sql("SELECT count(*) FROM device_platform.local_credentials")[0][0] == 0
    from sqlalchemy.engine import make_url

    for dsn in [h.settings.worker_database_url, h.settings.retention_database_url]:
        role = make_url(dsn.get_secret_value()).username
        for table in ["member_imports", "invitation_email_outbox"]:
            assert h.sql(
                "SELECT has_table_privilege(%s,%s,'SELECT')", (role, "device_platform." + table)
            ) == [(False,)]


def test_delivery_skips_inactive_departments_and_corrupt_payloads(platform, monkeypatch):
    h = platform
    token, org, path = setup(h)
    dept = h.call(
        "POST", f"/organizations/{org}/departments", token, expected=201, json={"name": "Training"}
    )["id"]
    batch = validate(h, token, path, [("Scoped", "scoped@example.com")], auth="oidc", department_id=dept)
    h.call("POST", path + "/" + batch["id"] + "/commit", token)
    h.call("PATCH", f"/organizations/{org}/departments/{dept}", token, json={"is_active": False})
    batch2 = validate(
        h, token, path, [("Corrupt", "corrupt@example.com"), ("Good", "good@example.com")], auth="oidc"
    )
    imported = h.call("POST", path + "/" + batch2["id"] + "/commit", token)
    h.sql(
        "UPDATE device_platform.invitation_email_outbox SET encrypted_payload=%s WHERE membership_id=%s",
        (b"0" * 40, imported["rows"][0]["membership_id"]),
    )
    sent = []

    async def sender(settings, recipient, raw):
        sent.append(recipient)
        return True

    monkeypatch.setattr("pms_api.modules.invitation_delivery.send_invitation", sender)
    settings = h.settings.model_copy(update={"smtp_host": "mock.invalid", "smtp_sender": "test@example.com"})

    async def cycle():
        engine = engine_for(settings)
        try:
            return await deliver_once(sessions_for(engine), settings)
        finally:
            await engine.dispose()

    assert asyncio.run(cycle()) == 1
    assert sent == ["good@example.com"]
    assert h.call("GET", path + "/" + batch["id"], token)["rows"][0]["email_status"] == "cancelled"
    assert h.call("GET", path + "/" + batch2["id"], token)["rows"][0]["email_status"] == "failed"


def test_maximum_200_person_local_import(platform):
    import time

    h = platform
    token, _ = h.admin()
    org = h.organization(token, plan="advanced")["id"]
    path = f"/organizations/{org}/member-imports"
    started = time.monotonic()
    batch = validate(h, token, path, [(f"Person {i}", f"person{i}@example.com") for i in range(200)])
    validated = time.monotonic()
    assert batch["counts"]["ready"] == 200
    result = h.call("POST", path + "/" + batch["id"] + "/commit", token)
    finished = time.monotonic()
    assert result["counts"] == {"total": 200, "ready": 0, "succeeded": 200, "failed": 0}
    assert h.sql("SELECT count(*) FROM device_platform.local_credentials")[0][0] == 200
    assert h.sql("SELECT count(*) FROM device_platform.invitation_email_outbox")[0][0] == 200
    print(
        f"200-person import: validation={validated - started:.2f}s, commit={finished - validated:.2f}s (local database; SMTP disabled)"
    )
