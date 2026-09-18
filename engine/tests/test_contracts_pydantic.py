"""Test suite for Contract Pydantic Models Validation (T-CON-002)."""

import json
from pathlib import Path
import pytest
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

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures" / "golden_001"


def test_character_pydantic_parsing():
    with open(FIXTURES_DIR / "character.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    char = Character.model_validate(data)
    assert char.id == "char_evelyn_gray"
    assert char.identity.display_name == "伊芙琳·格雷"
    assert char.identity.sequence == 9
    assert char.identity.pathway_id == "pathway.fool"
    assert char.revision == 27


def test_world_snapshot_pydantic_parsing():
    with open(FIXTURES_DIR / "world.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    world = WorldSnapshot.model_validate(data)
    assert world.world_id == "world_001"
    assert world.worldline_id == "wl_main"
    assert world.location is not None
    assert world.location.id == "loc_morris_clinic"
    assert world.revision == 103


def test_episode_pydantic_parsing():
    with open(FIXTURES_DIR / "expected_episode.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    ep = Episode.model_validate(data)
    assert ep.id == "ep_golden_001"
    assert ep.ending.type == "partial_truth"
    assert ep.secret_states["secret_04"] == "hidden"
    assert len(ep.discovered_clue_ids) == 5


def test_player_advice_pydantic_parsing():
    advice_files = list((FIXTURES_DIR / "turns").glob("*_advice.json"))
    assert len(advice_files) == 5

    for a_file in advice_files:
        with open(a_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        advice = PlayerAdvice.model_validate(data)
        assert advice.schema_version == "1.0"
        assert len(advice.raw_input) > 0


def test_character_knowledge_pydantic_parsing():
    k_files = list((FIXTURES_DIR / "knowledge").glob("*.json"))
    assert len(k_files) >= 4

    for k_file in k_files:
        with open(k_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        k = CharacterKnowledge.model_validate(data)
        assert k.schema_version == "1.0"
        assert k.character_id == "char_evelyn_gray"


def test_envelope_request_response_cycle():
    # Request
    req = EngineIPCEnvelope(
        kind="request",
        protocol_version="1.0",
        trace_id="trace_test_001",
        request_id="req_001",
        method="world.open",
        payload={"world_id": "world_001"},
    )
    req_json = req.model_dump_json()

    parsed_req = EngineIPCEnvelope.model_validate_json(req_json)
    assert parsed_req.kind == "request"
    assert parsed_req.method == "world.open"

    # Response
    resp = EngineIPCEnvelope(
        kind="response",
        protocol_version="1.0",
        trace_id="trace_test_001",
        request_id="req_001",
        status="ok",
        payload={"world_id": "world_001", "status": "opened"},
    )
    resp_json = resp.model_dump_json()
    parsed_resp = EngineIPCEnvelope.model_validate_json(resp_json)
    assert parsed_resp.status == "ok"
    assert parsed_resp.payload["status"] == "opened"


def test_strenum_contract_validation():
    from contracts import CharacterKind, EndingType, InputMode, KnowledgeStatus

    assert CharacterKind.ORIGINAL == "original"
    assert EndingType.PARTIAL_TRUTH == "partial_truth"
    assert InputMode.VOICE == "voice"
    assert KnowledgeStatus.CONFIRMED == "confirmed"

    # Verify that invalid enum value raises ValidationError
    with pytest.raises(Exception):
        from contracts import PlayerAdvice

        PlayerAdvice.model_validate(
            {
                "id": "adv_err",
                "raw_input": "test",
                "input_mode": "invalid_mode",
                "primary_intent": "test",
            }
        )


# Canonical Schema ↔ Pydantic parity.  These cases are deliberately small and
# inspect the actual source-of-truth Schemas rather than merely proving that a
# few hand-picked fixtures can be parsed.
from copy import deepcopy
from jsonschema import Draft202012Validator
from pydantic import ValidationError

SCHEMA_DIR = REPO_ROOT / "contracts" / "schemas"
RUNTIME_FIXTURE_DIR = REPO_ROOT / "docs" / "07_工程启动" / "golden_001_runtime"


def _schema(name: str):
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


STATE_DELTA_MINIMAL = {
    "schema_version": "1.0",
    "id": "delta_test",
    "turn_id": "turn_test",
    "outcome": "partial_success",
    "story_delta": {},
    "character_deltas": [],
    "world_event_candidates": [],
    "evidence_ids": [],
}

PARITY_CASES = [
    ("character", Character, lambda: _read(FIXTURES_DIR / "character.json")),
    ("world_snapshot", WorldSnapshot, lambda: _read(FIXTURES_DIR / "world.json")),
    ("player_advice", PlayerAdvice, lambda: _read(FIXTURES_DIR / "turns" / "01_advice.json")),
    ("action_intent", ActionIntent, lambda: _read(RUNTIME_FIXTURE_DIR / "mock" / "01_action_intent.json")),
    ("beat_plan", BeatPlan, lambda: _read(RUNTIME_FIXTURE_DIR / "mock" / "01_beat_plan.json")),
    ("narrative_block", NarrativeBlock, lambda: _read(RUNTIME_FIXTURE_DIR / "mock" / "01_narrative_block.json")),
    ("state_delta", StateDelta, lambda: deepcopy(STATE_DELTA_MINIMAL)),
    ("episode", Episode, lambda: _read(FIXTURES_DIR / "expected_episode.json")),
    ("character_knowledge", CharacterKnowledge, lambda: _read(FIXTURES_DIR / "knowledge" / "01_character_knowledge.json")),
]


@pytest.mark.parametrize("schema_name,model,sample_factory", PARITY_CASES, ids=lambda value: getattr(value, "__name__", str(value)))
def test_schema_and_pydantic_accept_same_canonical_sample(schema_name, model, sample_factory):
    sample = sample_factory()
    validator = Draft202012Validator(_schema(schema_name))
    validator.validate(sample)
    parsed = model.model_validate(sample)
    serialized = parsed.model_dump(mode="json", exclude_unset=True)
    validator.validate(serialized)


@pytest.mark.parametrize("schema_name,model,sample_factory", PARITY_CASES, ids=lambda value: getattr(value, "__name__", str(value)))
def test_schema_and_pydantic_both_reject_unknown_top_level_field(schema_name, model, sample_factory):
    sample = sample_factory()
    sample["__unknown_contract_field__"] = True
    assert not Draft202012Validator(_schema(schema_name)).is_valid(sample)
    with pytest.raises(ValidationError):
        model.model_validate(sample)


@pytest.mark.parametrize("schema_name,model,sample_factory", PARITY_CASES, ids=lambda value: getattr(value, "__name__", str(value)))
def test_schema_and_pydantic_both_reject_missing_required_field(schema_name, model, sample_factory):
    schema = _schema(schema_name)
    sample = sample_factory()
    # schema_version is required on every canonical contract and has no Pydantic default.
    sample.pop("schema_version")
    assert not Draft202012Validator(schema).is_valid(sample)
    with pytest.raises(ValidationError):
        model.model_validate(sample)


@pytest.mark.parametrize("schema_name,model,sample_factory", PARITY_CASES, ids=lambda value: getattr(value, "__name__", str(value)))
def test_schema_and_pydantic_both_reject_wrong_schema_version_type(schema_name, model, sample_factory):
    sample = sample_factory()
    sample["schema_version"] = 1
    assert not Draft202012Validator(_schema(schema_name)).is_valid(sample)
    with pytest.raises(ValidationError):
        model.model_validate(sample)


def test_action_intent_rejects_superseded_python_field_names():
    legacy = {
        "schema_version": "1.0",
        "id": "intent_old",
        "turn_id": "turn_old",
        "character_id": "char_x",
        "primary_intent": "observe",
        "concrete_actions": ["observe"],
        "adherence_to_advice": "full",
        "evidence_ids": [],
    }
    assert not Draft202012Validator(_schema("action_intent")).is_valid(legacy)
    with pytest.raises(ValidationError):
        ActionIntent.model_validate(legacy)


def test_state_delta_rejects_superseded_flat_shape():
    legacy = {
        "schema_version": "1.0",
        "id": "delta_old",
        "turn_id": "turn_old",
        "world_changes": {},
        "character_changes": {},
        "discovered_clues": [],
        "secret_state_updates": {},
    }
    assert not Draft202012Validator(_schema("state_delta")).is_valid(legacy)
    with pytest.raises(ValidationError):
        StateDelta.model_validate(legacy)


def test_schema_integer_semantics_accept_integral_json_number_without_string_coercion():
    sample = _read(FIXTURES_DIR / "world.json")
    sample["revision"] = 103.0
    schema = _schema("world_snapshot")
    assert Draft202012Validator(schema).is_valid(sample)
    assert WorldSnapshot.model_validate(sample).revision == 103
    sample["revision"] = "103"
    assert not Draft202012Validator(schema).is_valid(sample)
    with pytest.raises(ValidationError):
        WorldSnapshot.model_validate(sample)
