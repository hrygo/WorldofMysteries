"""Canonical StorySession / StoryState / TurnTransaction parity tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from contracts import StorySession, StoryState, TurnTransaction


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "contracts" / "schemas"


def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))


def _story_state() -> dict:
    return {
        "schema_version": "1.0",
        "story_session_id": "session_golden_001",
        "revision": 1,
        "turn": 1,
        "phase": "discovery",
        "scene": {
            "id": "consultation_room",
            "location_id": "loc_morris_clinic",
            "active_character_ids": ["char_evelyn_gray", "npc_doctor_morris"],
        },
        "world_time": "1349-06-12T21:45:00",
        "protagonist_goal": "find_missing_patient",
        "active_conflicts": ["morris_evasion"],
        "discovered_clue_ids": ["clue_doctor_pause"],
        "secret_states": {
            "secret_01": "hidden",
            "secret_02": "hidden",
            "secret_03": "hidden",
            "secret_04": "hidden",
        },
        "commitments": {"hard_ids": [], "soft_ids": ["morris_is_hiding_information"]},
        "local_state": {"doctor_suspicion": 0},
        "pressure": {"doctor_suspicion": 0},
        "last_state_delta_id": "delta_g001_t01",
    }


def _story_session() -> dict:
    return {
        "schema_version": "1.0",
        "id": "session_golden_001",
        "world_id": "world_001",
        "worldline_id": "wl_main",
        "protagonist_id": "char_evelyn_gray",
        "story_seed_id": "seed_golden_001",
        "base_revisions": {"world": 103, "character": 27, "story": 0},
        "story_state": _story_state(),
        "status": "active",
    }


def _turn_transaction() -> dict:
    return {
        "schema_version": "1.0",
        "id": "turn_g001_01",
        "session_id": "session_golden_001",
        "idempotency_key": "golden-001-turn-01",
        "status": "committed",
        "base_revisions": {"world": 103, "character": 27, "story": 0},
        "player_advice_id": "advice_g001_t01",
        "action_intent_id": "intent_g001_t01",
        "state_delta_id": "delta_g001_t01",
        "committed_story_revision": 1,
        "narrative_block_id": None,
    }


def _session_validator() -> Draft202012Validator:
    schema = copy.deepcopy(_schema("story_session"))
    schema["properties"]["story_state"] = _schema("story_state")
    return Draft202012Validator(schema)


@pytest.mark.parametrize(
    ("model", "validator", "factory"),
    [
        (StoryState, Draft202012Validator(_schema("story_state")), _story_state),
        (StorySession, _session_validator(), _story_session),
        (TurnTransaction, Draft202012Validator(_schema("turn_transaction")), _turn_transaction),
    ],
)
def test_schema_and_python_accept_same_story_contracts(model, validator, factory):
    data = factory()
    validator.validate(data)
    parsed = model.model_validate(data)
    wire = parsed.model_dump(mode="json", exclude_none=False)
    validator.validate(wire)


@pytest.mark.parametrize(
    ("model", "factory"),
    [
        (StoryState, _story_state),
        (StorySession, _story_session),
        (TurnTransaction, _turn_transaction),
    ],
)
def test_story_contracts_reject_unknown_fields(model, factory):
    data = factory()
    data["unexpected"] = True
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_story_state_rejects_duplicate_unique_arrays():
    data = _story_state()
    data["discovered_clue_ids"] = ["clue_doctor_pause", "clue_doctor_pause"]
    assert not Draft202012Validator(_schema("story_state")).is_valid(data)
    with pytest.raises(ValidationError, match="unique"):
        StoryState.model_validate(data)


@pytest.mark.parametrize("status", ["open", "paused", "done"])
def test_story_session_rejects_noncanonical_status(status):
    data = _story_session()
    data["status"] = status
    assert not _session_validator().is_valid(data)
    with pytest.raises(ValidationError):
        StorySession.model_validate(data)


def test_turn_transaction_rejects_noncanonical_status():
    data = _turn_transaction()
    data["status"] = "pending"
    assert not Draft202012Validator(_schema("turn_transaction")).is_valid(data)
    with pytest.raises(ValidationError):
        TurnTransaction.model_validate(data)


@pytest.mark.parametrize(
    ("model", "factory", "path"),
    [
        (StoryState, _story_state, ("revision",)),
        (StorySession, _story_session, ("base_revisions", "world")),
        (TurnTransaction, _turn_transaction, ("base_revisions", "story")),
    ],
)
def test_story_integer_semantics_accept_integral_json_number_and_reject_string(model, factory, path):
    data = factory()
    cursor = data
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = 1.0
    parsed = model.model_validate(data)
    out = parsed.model_dump(mode="json")
    actual = out
    for part in path:
        actual = actual[part]
    assert actual == 1

    data = factory()
    cursor = data
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = "1"
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_story_session_nested_state_must_reference_same_session():
    # The canonical schemas define shape, not cross-object equality. Keep that
    # semantic invariant explicit in the typed projection used by Application.
    data = _story_session()
    data["story_state"]["story_session_id"] = "other-session"
    session = StorySession.model_validate(data)
    assert session.story_state.story_session_id != session.id
