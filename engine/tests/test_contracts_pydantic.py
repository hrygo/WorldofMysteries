"""Schema/Pydantic parity for canonical product-domain contracts."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from contracts.models import VoiceRenderAccepted, VoiceRenderControlRequest
from contracts import (
    ActionIntent,
    BeatPlan,
    Character,
    CharacterKnowledge,
    EngineIPCEnvelope,
    Episode,
    NarrativeBlock,
    PlayerAdvice,
    StateDelta,
    WorldSnapshot,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "contracts" / "schemas"
FIXTURES = ROOT / "fixtures" / "golden_001"
RUNTIME = ROOT / "docs" / "07_工程启动" / "golden_001_runtime"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema(name: str) -> dict:
    return _read(SCHEMAS / f"{name}.schema.json")


def _state_delta_sample() -> dict:
    return {
        "schema_version": "1.0",
        "id": "delta_contract_probe",
        "turn_id": "turn_contract_probe",
        "outcome": "partial_success",
        "story_delta": {},
        "character_deltas": [],
        "world_event_candidates": [],
        "evidence_ids": [],
    }


CASES = [
    ("character", Character, lambda: _read(FIXTURES / "character.json")),
    ("world_snapshot", WorldSnapshot, lambda: _read(FIXTURES / "world.json")),
    ("player_advice", PlayerAdvice, lambda: _read(FIXTURES / "turns" / "01_advice.json")),
    ("action_intent", ActionIntent, lambda: _read(RUNTIME / "mock" / "01_action_intent.json")),
    ("beat_plan", BeatPlan, lambda: _read(RUNTIME / "mock" / "01_beat_plan.json")),
    ("narrative_block", NarrativeBlock, lambda: _read(RUNTIME / "mock" / "01_narrative_block.json")),
    ("state_delta", StateDelta, _state_delta_sample),
    ("episode", Episode, lambda: _read(FIXTURES / "expected_episode.json")),
    ("character_knowledge", CharacterKnowledge, lambda: _read(FIXTURES / "knowledge" / "01_character_knowledge.json")),
]


@pytest.mark.parametrize("schema_name,model,load", CASES, ids=[item[0] for item in CASES])
def test_schema_and_pydantic_accept_same_canonical_examples(schema_name, model, load):
    data = load()
    validator = Draft202012Validator(_schema(schema_name))
    validator.validate(data)
    parsed = model.model_validate(data)
    wire = parsed.model_dump(mode="json", exclude_none=True)
    validator.validate(wire)


@pytest.mark.parametrize("index", range(1, 6))
def test_all_golden_advice_action_beats_and_narrative_match_schema_and_python(index):
    suffix = f"{index:02d}"
    cases = [
        ("player_advice", PlayerAdvice, FIXTURES / "turns" / f"{suffix}_advice.json"),
        ("action_intent", ActionIntent, RUNTIME / "mock" / f"{suffix}_action_intent.json"),
        ("beat_plan", BeatPlan, RUNTIME / "mock" / f"{suffix}_beat_plan.json"),
        ("narrative_block", NarrativeBlock, RUNTIME / "mock" / f"{suffix}_narrative_block.json"),
    ]
    for schema_name, model, path in cases:
        data = _read(path)
        Draft202012Validator(_schema(schema_name)).validate(data)
        parsed = model.model_validate(data)
        Draft202012Validator(_schema(schema_name)).validate(
            parsed.model_dump(mode="json", exclude_none=True)
        )


@pytest.mark.parametrize("path", sorted((FIXTURES / "knowledge").glob("*.json")))
def test_all_golden_knowledge_matches_schema_and_python(path):
    data = _read(path)
    validator = Draft202012Validator(_schema("character_knowledge"))
    validator.validate(data)
    validator.validate(CharacterKnowledge.model_validate(data).model_dump(mode="json", exclude_none=True))


@pytest.mark.parametrize("schema_name,model,load", CASES, ids=[item[0] for item in CASES])
def test_unknown_fields_are_rejected_by_schema_and_pydantic(schema_name, model, load):
    data = load()
    data["__unknown_contract_field__"] = True
    assert not Draft202012Validator(_schema(schema_name)).is_valid(data)
    with pytest.raises(ValidationError):
        model.model_validate(data)


@pytest.mark.parametrize("schema_name,model,load", CASES, ids=[item[0] for item in CASES])
def test_missing_required_field_is_rejected_by_schema_and_pydantic(schema_name, model, load):
    data = load()
    required = _schema(schema_name)["required"]
    victim = next(name for name in required if name != "schema_version")
    data.pop(victim)
    assert not Draft202012Validator(_schema(schema_name)).is_valid(data)
    with pytest.raises(ValidationError):
        model.model_validate(data)


@pytest.mark.parametrize(
    "schema_name,model,data",
    [
        ("player_advice", PlayerAdvice, {
            "schema_version": "1.0", "id": "a", "turn_id": "t", "raw_input": "x",
            "input_mode": "invalid", "primary_intent": "observe", "proposed_actions": [], "confidence": 1,
        }),
        ("action_intent", ActionIntent, {
            "schema_version": "1.0", "id": "i", "turn_id": "t", "character_id": "c",
            "intent": "observe", "adherence": "obey", "actions": [{"type": "wait"}], "evidence_ids": [],
        }),
        ("state_delta", StateDelta, {
            **_state_delta_sample(), "outcome": "lucky_success",
        }),
    ],
)
def test_invalid_enums_are_rejected_by_schema_and_pydantic(schema_name, model, data):
    assert not Draft202012Validator(_schema(schema_name)).is_valid(data)
    with pytest.raises(ValidationError):
        model.model_validate(data)


@pytest.mark.parametrize(
    "model,data",
    [
        (PlayerAdvice, {
            "schema_version": "1.0", "id": "a", "turn_id": "t", "raw_input": "x", "input_mode": "text",
            "primary_intent": "observe", "proposed_actions": [], "confidence": "1.0",
        }),
        (WorldSnapshot, {
            "schema_version": "1.0", "world_id": "w", "worldline_id": "wl", "world_time": "now",
            "revision": "1", "location": {"id": "loc"},
        }),
    ],
)
def test_wrong_scalar_types_are_not_coerced(model, data):
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_legacy_action_intent_shape_is_rejected():
    legacy = {
        "schema_version": "1.0",
        "id": "intent_old",
        "turn_id": "turn_old",
        "character_id": "char_old",
        "primary_intent": "observe",
        "concrete_actions": ["wait"],
        "adherence_to_advice": "full",
    }
    assert not Draft202012Validator(_schema("action_intent")).is_valid(legacy)
    with pytest.raises(ValidationError):
        ActionIntent.model_validate(legacy)


def test_suggestion_is_a_valid_player_advice_input_mode():
    data = _read(FIXTURES / "turns" / "01_advice.json")
    data["input_mode"] = "suggestion"
    Draft202012Validator(_schema("player_advice")).validate(data)
    assert PlayerAdvice.model_validate(data).input_mode.value == "suggestion"


def test_json_schema_integral_number_semantics_are_preserved():
    data = _read(FIXTURES / "world.json")
    data["revision"] = 103.0
    Draft202012Validator(_schema("world_snapshot")).validate(data)
    assert WorldSnapshot.model_validate(data).revision == 103


def test_duplicate_unique_items_are_rejected():
    data = _read(FIXTURES / "turns" / "01_advice.json")
    data["proposed_actions"] = ["observe_morris", "observe_morris"]
    assert not Draft202012Validator(_schema("player_advice")).is_valid(data)
    with pytest.raises(ValidationError):
        PlayerAdvice.model_validate(data)


def test_envelope_request_response_cycle_remains_unchanged():
    req = EngineIPCEnvelope(
        kind="request", protocol_version="1.0", trace_id="trace_test_001",
        request_id="req_001", method="world.open", payload={"world_id": "world_001"},
    )
    parsed = EngineIPCEnvelope.model_validate_json(req.model_dump_json())
    assert parsed.method == "world.open"


def test_voice_render_control_schema_and_python_parity():
    schema = _read(ROOT / "contracts" / "protocol" / "voice_render_control.schema.json")
    fixture = _read(ROOT / "contracts" / "fixtures" / "ipc" / "voice_render_control.json")
    validator = Draft202012Validator(schema)

    for key, model in (
        ("request", VoiceRenderControlRequest),
        ("accepted", VoiceRenderAccepted),
    ):
        payload = fixture[key]
        validator.validate(payload)
        parsed = model.model_validate(payload)
        validator.validate(parsed.model_dump(mode="json", exclude_none=True))


def test_voice_render_control_rejects_unsealed_or_unpinned_shapes():
    schema = _read(ROOT / "contracts" / "protocol" / "voice_render_control.schema.json")
    fixture = _read(ROOT / "contracts" / "fixtures" / "ipc" / "voice_render_control.json")
    request = copy.deepcopy(fixture["request"])
    request.pop("story_revision")
    assert not Draft202012Validator(schema).is_valid(request)
    with pytest.raises(ValidationError):
        VoiceRenderControlRequest.model_validate(request)

    request = copy.deepcopy(fixture["request"])
    request["expected_model_revision"] = "not-a-revision"
    assert not Draft202012Validator(schema).is_valid(request)
    with pytest.raises(ValidationError):
        VoiceRenderControlRequest.model_validate(request)

    request = copy.deepcopy(fixture["request"])
    request["__unknown"] = True
    assert not Draft202012Validator(schema).is_valid(request)
    with pytest.raises(ValidationError):
        VoiceRenderControlRequest.model_validate(request)
