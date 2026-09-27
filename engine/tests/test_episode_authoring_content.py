"""Authored Episode input is valid, agrees with the golden oracle, and leaves
evidence-bound fields empty so production settlement binds them from the real
committed turns (never from the test oracle)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "golden_001"
SCHEMAS = ROOT / "contracts" / "schemas"

# Fields the settlement binds from committed evidence at finalization time.
EVIDENCE_BOUND = (
    "secret_states",
    "discovered_clue_ids",
    "character_event_ids",
    "relationship_event_ids",
    "knowledge_change_ids",
    "memory_ids",
    "world_event_ids",
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(_read(SCHEMAS / schema_name))


@pytest.mark.parametrize(
    ("fixture", "schema"),
    [("episode.json", "episode.schema.json"),
     ("episode_memory.json", "character_memory.schema.json")],
)
def test_authored_episode_input_matches_contract(fixture: str, schema: str) -> None:
    errors = sorted(_validator(schema).iter_errors(_read(FIXTURES / fixture)),
                    key=lambda e: list(e.path))
    assert not errors, f"{fixture} violates {schema}: {errors}"


def test_authored_episode_agrees_with_the_golden_oracle() -> None:
    authored = _read(FIXTURES / "episode.json")
    oracle = _read(FIXTURES / "expected_episode.json")
    # The authored narrative is the single source of truth shared by the
    # production settlement input and the T1 acceptance oracle.
    for field in (
        "world_id", "worldline_id", "story_seed_id", "protagonist_ids",
        "title", "start_world_time", "ending", "unresolved_threads",
    ):
        assert authored[field] == oracle[field], field
    assert authored["ending"]["type"] == "partial_truth"
    assert set(authored["unresolved_threads"]) == {
        "jonathan_current_location", "occult_group_identity"}


def test_evidence_bound_fields_are_empty_in_the_authored_input() -> None:
    authored = _read(FIXTURES / "episode.json")
    for field in EVIDENCE_BOUND:
        value = authored[field]
        assert value in ({}, []), f"{field} must stay empty for settlement binding"
    memory = _read(FIXTURES / "episode_memory.json")
    assert memory["source_ids"] == []
