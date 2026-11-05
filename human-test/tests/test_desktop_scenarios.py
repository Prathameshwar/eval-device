"""Desktop setup selects published scenarios without the removed web page."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from test_flow import settings
from training_client.pms_client import PMSClient

from human_test.app import Window


class Field:
    def __init__(self, value=""):
        self.value = value
        self.options = {}

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def configure(self, **options):
        self.options.update(options)


def window():
    value = Window.__new__(Window)
    value.settings = SimpleNamespace(language_choices=["en", "hi"], language="en")
    value.running = False
    value.session_queue = SimpleNamespace(next=None, assigned=lambda: False, blocks_setup=lambda: False)
    for name in (
        "category",
        "patient_profile",
        "case_choice",
        "patient_name",
        "patient_info",
        "case_summary",
        "setup_note",
        "state",
        "category_box",
        "patient_box",
        "case_box",
        "lang_box",
        "save_button",
    ):
        setattr(value, name, Field())
    value.language = Field("English")
    value.vitals = {"temperature_c": Field()}
    return value


def test_new_user_selects_default_and_can_change_scenario_and_language_without_web(monkeypatch):
    monkeypatch.setattr("human_test.app.LANGUAGES", {"English": "en", "Hindi": "hi"})
    value = window()
    options = {
        "categories": [],
        "patients": [],
        "cases": [],
        "scenarios": [
            {
                "id": "first",
                "title": "Same title",
                "version": 1,
                "languages": ["en"],
                "vitals": {"temperature_c": 36.8},
            },
            {
                "id": "second",
                "title": "Same title",
                "version": 2,
                "languages": ["hi"],
                "vitals": {"temperature_c": 37.2},
            },
        ],
        "default": {"scenario_id": "second", "language": "hi"},
    }
    value.apply_catalog(options, None)
    assert value.loaded_case["id"] == "second"
    assert value.vitals["temperature_c"].get() == "37.2"
    assert len(value.case_box.options["values"]) == 2
    assert value.lang_box.options["values"] == [value.language.get()]
    assert value.save_button.options["state"] == "normal"
    value.case_choice.set(next(iter(value.cases)))
    value.load_case()
    assert value.loaded_case["id"] == "first"
    assert value.language.get() == "English"
    assert value.vitals["temperature_c"].get() == "36.8"
    assert value.saved is None  # Loading/default selection does not create a private record.


def test_no_supported_scenarios_does_not_restore_an_unavailable_saved_case():
    value = window()
    value.apply_catalog(
        {"categories": [], "patients": [], "cases": [], "scenarios": []},
        {"scenario_id": "retired", "revision": 7},
    )
    assert value.loaded_case is None
    assert value.save_button.options["state"] == "disabled"
    assert "No published" in value.state.get()
    assert value.saved["revision"] == 7  # Retain concurrency token for a later replacement.


async def test_options_use_the_authenticated_tenant_practice_endpoint(monkeypatch):
    client = PMSClient(settings())

    async def request(method, path, **kwargs):
        assert method == "GET" and path == client.practice_base + "/scenario-options"
        return {"items": [], "default": None, "selection": None}

    monkeypatch.setattr(client, "json", request)
    try:
        assert (await client.scenario_options())["selection"] is None
    finally:
        await client.close()


def test_scenario_without_vitals_loads_for_manual_entry():
    value = window()
    value.apply_catalog(
        {
            "scenarios": [
                {"id": "empty", "title": "History only", "version": 1, "languages": ["en"], "vitals": None}
            ]
        },
        None,
    )
    assert value.loaded_case["id"] == "empty"
    assert value.vitals["temperature_c"].get() == ""
    assert value.save_button.options["state"] == "normal"


@pytest.mark.parametrize(
    "field,reading",
    [
        ("pulse_bpm", ""),
        ("pain_0_10", "11"),
        ("spo2_percent", "101"),
        ("temperature_c", "nan"),
        ("systolic_mmhg", "40"),
    ],
)
def test_invalid_observations_never_reach_the_api(field, reading):
    value = window()
    readings = {
        "temperature_c": "37",
        "heart_rate_bpm": "80",
        "pulse_bpm": "80",
        "systolic_mmhg": "120",
        "diastolic_mmhg": "80",
        "respirations_per_minute": "16",
        "spo2_percent": "98",
        "pain_0_10": "2",
    }
    readings[field] = reading
    value.vitals = {key: Field(text) for key, text in readings.items()}
    value.loaded_case = {"id": "selected"}
    value.submit = Mock()
    value.save_setup()
    value.submit.assert_not_called()
    assert "all eight" in value.state.get()


async def test_eight_observations_save_using_current_scenario_contract():
    from test_speech import WindowSpeaker
    from training_client.runtime import Runtime

    value = window()
    value.vitals = {
        key: Field(str(number))
        for key, number in {
            "temperature_c": 37,
            "heart_rate_bpm": 80,
            "pulse_bpm": 81,
            "systolic_mmhg": 120,
            "diastolic_mmhg": 80,
            "respirations_per_minute": 16,
            "spo2_percent": 98,
            "pain_0_10": 2,
        }.items()
    }
    value.loaded_case, value.saved, value.scenario_selected = {"id": "published"}, {"revision": 4}, True
    selected = {"id": "saved", "revision": 5}
    save = AsyncMock(return_value=selected)
    value.controller = SimpleNamespace(
        pms=SimpleNamespace(save_scenario_selection=save), use_selection=Mock()
    )
    value.emit = Mock()
    value.runtime = Runtime(settings(), value.emit, controller=value.controller, speaker=WindowSpeaker())
    pending = []
    value.submit = lambda action, *_: pending.append(action)
    value.save_setup()
    await pending[0]
    payload = save.call_args.args[0]
    assert payload["scenario_id"] == "published" and payload["expected_revision"] == 4
    assert payload["vitals"]["pulse_bpm"] == 81 and len(payload["vitals"]) == 8
