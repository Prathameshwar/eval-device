from copy import deepcopy

import pytest
from pydantic import ValidationError
from scenario_samples import example
from training_contracts import Scenario, canonical, fingerprint
from training_contracts.scenarios import normalize_draft, patient_preview, validate_publication

from pms_api.modules.scenario_schemas import DraftCreate, DraftPublish, DraftSave


def test_incomplete_and_bilingual_published_contracts():
    incomplete = normalize_draft({"version": 2, "code": "partial"})
    assert validate_publication(incomplete)
    for kind in ("cough", "kidney"):
        value = normalize_draft(example(kind=kind))
        assert not validate_publication(value)
        preview = patient_preview(value)
        assert "35" in preview["topics"][0]["answer"]["hi"]
        assert "मेरा" in preview["greeting"]["hi"]
        assert all(
            secret not in canonical(preview)
            for secret in ("Hidden teaching", "Private assessment", "rubric", "specialty")
        )
        assert fingerprint(value) == fingerprint(normalize_draft(value))
    value = example()
    del value["dialogue"]["greeting"]["hi"]
    assert normalize_draft(value)
    assert any(i.path == ["dialogue", "greeting", "hi"] for i in validate_publication(value))


@pytest.mark.parametrize(
    "field,value",
    [
        ("patient", {"age_years": True}),
        ("patient", {"age_years": -1}),
        ("patient", {"height_cm": "170"}),
        ("vitals", {"temperature_c": float("nan")}),
        ("vitals", {"heart_rate_bpm": True}),
        ("vitals", {"spo2_percent": 101}),
        ("vitals", {"temperature_f": 98.6}),
        ("history", {"allergies": {"knowledge": "none", "entries": [{"en": "test"}]}}),
    ],
)
def test_rejects_malformed_supplied_fields(field, value):
    with pytest.raises(ValidationError):
        normalize_draft({"version": 2, "code": "case", field: value})


@pytest.mark.parametrize(
    "reference",
    [
        "{instructor.diagnosis}",
        "{patient.__dict__}",
        "{patient.name!r}",
        "{patient.age_years:04d}",
        "{patient[name]}",
        "{missing}",
        "{",
    ],
)
def test_no_arbitrary_template_references(reference):
    value = example()
    value["dialogue"]["greeting"]["en"] = reference
    with pytest.raises(ValidationError):
        normalize_draft(value)


def test_reference_disclosure_and_missing_values():
    value = example()
    value["dialogue"]["greeting"]["en"] = "I am {patient.age_years}."
    with pytest.raises(ValidationError):
        normalize_draft(value)
    value = example()
    value["fact_disclosure"]["patient.age_years"] = "never"
    with pytest.raises(ValidationError):
        normalize_draft(value)
    value = example()
    del value["patient"]["age_years"]
    assert normalize_draft(value)
    assert validate_publication(value)
    assert patient_preview(value)["topics"][0]["answer"]["en"] is None


def test_duplicate_identifiers_document_budget_and_abnormal_vitals():
    value = example()
    value["dialogue"]["topics"] *= 2
    with pytest.raises(ValidationError):
        normalize_draft(value)
    value = example()
    value["vitals"]["heart_rate_bpm"] = 200
    assert not validate_publication(normalize_draft(value))
    value["dialogue"]["topics"] = [
        {"id": f"topic_{i}", "answer": {"en": "ह" * 600, "hi": "ह" * 600}} for i in range(32)
    ]
    with pytest.raises(ValidationError):
        normalize_draft(value)


@pytest.mark.parametrize("revision", [None, True, False, 0, -1, "1", 1.0])
def test_revision_is_strict_positive_integer(revision):
    with pytest.raises(ValidationError):
        DraftSave.model_validate({"expected_revision": revision, "document": example()})


def test_request_identity_and_unknown_fields():
    from uuid import uuid4

    with pytest.raises(ValidationError):
        DraftCreate.model_validate(
            {
                "request_key": str(uuid4()),
                "code": "copy",
                "source_scenario_id": str(uuid4()),
                "schema_version": 2,
            }
        )
    with pytest.raises(ValidationError):
        DraftCreate.model_validate({"request_key": str(uuid4()), "code": "wrong", "document": example()})
    with pytest.raises(ValidationError):
        DraftPublish.model_validate(
            {
                "request_key": str(uuid4()),
                "expected_revision": 1,
                "created_by": str(uuid4()),
                "approval": {"educator_name": "Test", "statement": "A synthetic testing statement."},
            }
        )


def test_version_one_roundtrip_unchanged():
    import json
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[3]
        / "device/training/src/device_training/scenarios/cough_interview_dev.json"
    )
    original = Scenario.model_validate(json.loads(path.read_text(encoding="utf-8"))).model_dump(mode="json")
    before = deepcopy(original)
    assert normalize_draft(original) == before
    assert not validate_publication(original)
    assert fingerprint(normalize_draft(original)) == fingerprint(before)
    assert "rubric" not in patient_preview(original)
