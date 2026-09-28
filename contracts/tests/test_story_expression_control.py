"""story.expression.get read-only narrative query wire contract tests (AO-01).

The query exists so a missing voice service can never cost the player the text.
It therefore carries disclosed, player-visible segments only: no internal
NarrativeBlock shape, no hidden identity, no authorization inventory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "contracts/protocol/story_expression_control.schema.json"
FIXTURE = json.loads(
    (ROOT / "contracts/fixtures/ipc/story_expression_control.json").read_text(
        encoding="utf-8"
    )
)
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validator_for(shape: str) -> Draft202012Validator:
    return Draft202012Validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": f"#/$defs/{shape}",
            "$defs": SCHEMA["$defs"],
        }
    )


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["id"])
def test_story_expression_control_fixture(case):
    assert _validator_for(case["shape"]).is_valid(case["value"]) is case["valid"]


def test_every_referenced_shape_exists():
    for case in FIXTURE["cases"]:
        assert case["shape"] in SCHEMA["$defs"], case["shape"]


def test_response_is_a_closed_allowlist_without_internal_narrative_shape():
    response = SCHEMA["$defs"]["expression_get_response"]
    assert response["additionalProperties"] is False
    assert set(response["properties"]) == {
        "schema_version",
        "session_id",
        "turn_id",
        "narrative_state",
        "segments",
        "reason",
    }
    # The wire must never re-export the persisted NarrativeBlock verbatim.
    forbidden = {
        "narrative_block",
        "narrative_block_id",
        "source_story_revision",
        "ambient_cues",
        "sfx_cues",
        "source_state_delta_id",
        "speech_unit",
        "authorized",
        "capabilities",
    }
    assert forbidden.isdisjoint(response["properties"])


def test_segment_is_a_closed_allowlist_without_hidden_identity():
    segment = SCHEMA["$defs"]["expression_segment"]
    assert segment["additionalProperties"] is False
    assert set(segment["properties"]) == {"type", "speaker_display_name", "text"}
    # Internal speaker ids stay server-side; only a display name crosses the wire.
    assert "speaker_id" not in segment["properties"]


def test_segment_text_is_bounded_like_the_disclosure_boundary():
    text = SCHEMA["$defs"]["segment_text"]
    assert text["minLength"] == 1
    assert text["maxLength"] == 4096


def test_narrative_state_is_exactly_pending_ready_unavailable():
    assert SCHEMA["$defs"]["narrative_state"]["enum"] == [
        "pending",
        "ready",
        "unavailable",
    ]


def test_request_carries_no_expression_or_generation_switch():
    request = SCHEMA["$defs"]["expression_get_request"]
    assert request["additionalProperties"] is False
    assert set(request["properties"]) == {"schema_version", "session_id", "turn_id"}
