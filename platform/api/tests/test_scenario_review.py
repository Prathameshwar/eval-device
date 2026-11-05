"""Regressions from the scenario API's first review."""

import base64
import json
from uuid import uuid4

import pytest
from scenario_samples import example as legacy_example
from test_scenario_library import library as library
from test_scenario_library import member, publication
from training_contracts import canonical, fingerprint
from training_contracts.clinical_cases import simplify_case
from training_contracts.scenarios import normalize_draft

from pms_api.core.common import AppError
from pms_api.modules.scenarios import paged, require_runtime


def example(code="sample_cough"):
    return simplify_case(legacy_example(code))


def create(value):
    h, token, _, _, base = value
    body = {
        "request_key": str(uuid4()),
        "code": "sample_cough",
        "document": example(),
        "specialty_id": h.test_specialty_id,
    }
    return h.call("POST", base + "/scenario-drafts", token, expected=201, json=body)["draft"], body


def publish(value, row):
    h, token, _, _, base = value
    path = base + f"/scenario-drafts/{row['id']}"
    row = h.call("POST", path + "/submit", token, json={"expected_revision": row["revision"]})
    for language in ("en", "hi"):
        row = h.call(
            "POST",
            path + f"/localizations/{language}/review",
            h.reviewer_token,
            json={"expected_revision": row["revision"], "approval": publication()["approval"]},
        )
    body = publication(row["revision"])
    result = h.call("POST", path + "/publish", h.reviewer_token, expected=201, json=body)
    return result["scenario"], body


@pytest.mark.parametrize("identifier", [123, [], {}])
async def test_malformed_cursor_identifier_is_a_client_error(identifier):
    scope = {"org": "synthetic"}
    cursor = base64.urlsafe_b64encode(
        canonical(
            {
                "scope": fingerprint(scope),
                "created_at": "2026-09-18T12:00:00+00:00",
                "id": identifier,
            }
        ).encode()
    ).decode()
    with pytest.raises(AppError) as raised:
        await paged(None, None, None, 1, cursor, scope)
    assert raised.value.status == 422 and raised.value.code == "invalid_cursor"


def test_postgres_incompatible_text_rejected_before_storage():
    document = example()
    normalize_draft(document)
    document["presentation"]["chief_complaint"] = {"en": "Synthetic\u0000text"}
    with pytest.raises(ValueError):
        normalize_draft(document)


def test_validation_does_not_echo_unknown_field_names(library):
    h, token, _, _, base = library
    row, _ = create(library)
    path = base + f"/scenario-drafts/{row['id']}"
    document = example()
    document["sensitive-content-used-as-a-key"] = "synthetic"
    result = h.call("PUT", path, token, expected=422, json={"expected_revision": 1, "document": document})
    assert "sensitive-content-used-as-a-key" not in json.dumps(result)
    document = example()
    document["fact_disclosure"] = {"sensitive-content-used-as-a-key": "on_question"}
    result = h.call("PUT", path, token, expected=422, json={"expected_revision": 1, "document": document})
    assert "sensitive-content-used-as-a-key" not in json.dumps(result)


def test_approval_rejects_null_text_as_input_error(library):
    h, token, _, _, base = library
    row, _ = create(library)
    body = publication()
    body["approval"]["statement"] = "Synthetic review with a null character: \u0000"
    h.call("POST", base + f"/scenario-drafts/{row['id']}/publish", h.reviewer_token, expected=422, json=body)


def test_keys_bind_author_and_publisher_and_draft_identity(library):
    h, token, _, org, base = library
    row, creation = create(library)
    path = base + f"/scenario-drafts/{row['id']}"
    other_author, other_user = member(h, token, org, "second_author", "org_admin")
    h.grant_capability(token, org, other_user["id"], "org.clinical.author")
    h.call("POST", base + "/scenario-drafts", other_author, expected=409, json=creation)
    case, body = publish(library, row)
    assert case["id"]
    h.call("POST", path + "/publish", other_author, expected=403, json=body)
    saved = h.call("GET", path, token)
    for document, status in (({"version": 1, "code": row["code"]}, 422), (example("wrong_code"), 409)):
        h.call(
            "PUT",
            path,
            token,
            expected=status,
            json={"expected_revision": saved["revision"], "document": document},
        )
    assert h.call("GET", path, token) == saved


def test_noop_save_by_second_author_preserves_content_attribution(library):
    h, token, author_id, org, base = library
    row, _ = create(library)
    other_author, other_user = member(h, token, org, "noop_author", "org_admin")
    h.grant_capability(token, org, other_user["id"], "org.clinical.author")
    saved = h.call(
        "PUT",
        base + f"/scenario-drafts/{row['id']}",
        other_author,
        json={"expected_revision": row["revision"], "document": row["document"]},
    )
    assert saved["revision"] == row["revision"] + 1
    content_author, last_editor = h.sql(
        "SELECT content_updated_by,updated_by FROM device_platform.training_scenario_drafts WHERE id=%s",
        (row["id"],),
    )[0]
    assert str(content_author) == author_id
    assert str(last_editor) == other_user["id"]


@pytest.mark.parametrize("version", [1, 2, 3, 99])
def test_legacy_and_future_runtime_versions_fail_closed(version):
    with pytest.raises(AppError) as raised:
        require_runtime({**example(), "version": version})
    assert raised.value.status == 409
    assert raised.value.code == "scenario_runtime_unsupported"


def test_retired_create_cannot_bypass_publication_and_reader_privacy(library):
    h, token, _, org, base = library
    row, _ = create(library)
    case, body = publish(library, row)
    h.call(
        "POST",
        base + "/scenarios",
        token,
        expected=405,
        json={"request_key": body["request_key"], "scenario": case["document"]},
    )
    reader, _ = member(h, token, org, "scenario_reader", "org_user")
    summaries = h.call("GET", base + "/scenarios", reader)["items"]
    assert case["id"] in {item["id"] for item in summaries}
    assert all("code" not in item and "document" not in item for item in summaries)
    summary = h.call("GET", base + f"/scenarios/{case['id']}", reader)
    assert "document" not in summary and "code" not in summary and "approval" not in summary
    assert h.call("GET", base + "/scenarios?q=sample_cough", reader)["items"] == []
