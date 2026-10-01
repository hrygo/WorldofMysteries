"""Trusted first-turn Story Session wire contract tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (ROOT / "contracts/protocol/story_session_control.schema.json").read_text(
        encoding="utf-8"
    )
)
FIXTURE = json.loads(
    (ROOT / "contracts/fixtures/ipc/story_session_control.json").read_text(
        encoding="utf-8"
    )
)


def _validator_for(shape: str) -> Draft202012Validator:
    return Draft202012Validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": f"#/$defs/{shape}",
            "$defs": SCHEMA["$defs"],
        }
    )


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["id"])
def test_story_session_control_fixture(case):
    assert _validator_for(case["shape"]).is_valid(case["value"]) is case["valid"]


def test_supported_advice_is_the_exact_server_frozen_text():
    assert FIXTURE["supported_advice"] == "先别问医生病人的事，我想看看他的反应。"
    entry = next(
        case["value"]
        for case in FIXTURE["cases"]
        if case["id"] == "entry_get_response_before_open_valid"
    )
    assert entry["supported_advice"] == [FIXTURE["supported_advice"]]


def test_public_view_is_an_allowlist_without_hidden_domain_state():
    view = SCHEMA["$defs"]["public_story_session_view"]
    assert view["additionalProperties"] is False
    assert set(view["properties"]) == {
        "schema_version",
        "scenario_id",
        "session_id",
        "mode",
        "status",
        "story_revision",
        "turn",
        "observed_store_revision",
        "world_time",
        "protagonist",
        "scene",
        "discovered_clues",
        "can_submit",
        "last_committed_turn_id",
    }
    forbidden = {
        "secret_states",
        "hidden_truth",
        "pressure",
        "local_state",
        "base_revisions",
        "story_state",
    }
    assert forbidden.isdisjoint(view["properties"])


def test_revision_boundaries_are_explicit():
    assert SCHEMA["$defs"]["revision"]["maximum"] == 2**63 - 1
    assert SCHEMA["$defs"]["expected_revision"]["maximum"] == 2**63 - 2
    assert SCHEMA["$defs"]["revision"]["minimum"] == 0
    assert SCHEMA["$defs"]["expected_revision"]["minimum"] == 0


def test_committed_receipt_requires_both_revision_tokens():
    validator = _validator_for("committed_receipt")
    valid = next(
        case["value"]["receipt"]
        for case in FIXTURE["cases"]
        if case["id"] == "advice_submit_response_valid"
    )
    validator.validate(valid)
    missing = dict(valid)
    missing.pop("committed_store_revision")
    assert not validator.is_valid(missing)


def test_unknown_response_fields_are_rejected():
    response = next(
        case["value"]
        for case in FIXTURE["cases"]
        if case["id"] == "advice_get_response_received_valid"
    )
    response = dict(response)
    response["debug_state"] = {"secret_states": {}}
    assert not _validator_for("advice_get_response").is_valid(response)


# --- turn_delivery: one entry per narrative segment -------------------------


def _recipe(segment_index: int, unit_id: str, *, voice_id: str = "voice_01") -> dict:
    return {
        "speech_unit_id": unit_id,
        "turn_id": "turn_01",
        "story_revision": 1,
        "narrative_block_id": "narrative_01",
        "segment_index": segment_index,
        "performance_plan_id": f"performance_{segment_index:02d}",
        "spoken_text": "别动那只表。",
        "voice_id": voice_id,
        "expected_voice_revision": "voice_revision_01",
        "expected_model_revision": None,
        "speed": 1.0,
        "language": "zh-CN",
        # The recipe pins what a human approved and the exact artifact they
        # heard. A delivery that omits these cannot be rendered under the same
        # evidence, so the contract must refuse to describe it.
        "evidence_id": "evidence_01",
        "evidence_digest": "a" * 64,
        "expected_model_artifact_revision": "model_artifact_01",
        "expected_model_catalog_revision": "qwen3-tts-20260929",
    }


def _delivery(*speech_units, state: str = "ready", reason: str | None = None):
    delivery = {"state": state}
    if state == "ready":
        delivery["narrative_block_id"] = "narrative_01"
    if reason is not None:
        delivery["reason"] = reason
    if speech_units:
        delivery["speech_units"] = list(speech_units)
    return delivery


def test_a_partially_voiced_turn_is_still_a_deliverable_turn():
    """The reason the batch exists, stated as a schema fact.

    Two speakers, one castable voice. Before this shape a turn could only say
    "ready" about a single segment or say nothing at all, so the segment that
    did have a voice was either played alone while the other silently vanished,
    or withheld entirely. Both outcomes lose information the player needs.
    """
    delivery = _delivery(
        {
            "segment_index": 1,
            "state": "ready",
            "speech_unit_id": "speech_unit_01",
            "spoken_text": "别动那只表。",
            "render_recipe": _recipe(1, "speech_unit_01"),
        },
        {
            "segment_index": 3,
            "state": "unavailable",
            "reason": "voice_binding_not_found",
        },
    )

    assert _validator_for("turn_delivery").is_valid(delivery)


def test_a_segment_that_is_ready_must_carry_its_own_recipe():
    delivery = _delivery(
        {
            "segment_index": 1,
            "state": "ready",
            "speech_unit_id": "speech_unit_01",
            "spoken_text": "别动那只表。",
        }
    )
    assert not _validator_for("turn_delivery").is_valid(delivery)


def test_a_missing_segment_voice_must_say_why():
    delivery = _delivery({"segment_index": 3, "state": "unavailable"})
    assert not _validator_for("turn_delivery").is_valid(delivery)


def test_a_segment_cannot_carry_a_voice_the_server_did_not_choose():
    """The recipe is sealed; a client naming a voice is a protocol violation."""
    delivery = _delivery(
        {
            "segment_index": 1,
            "state": "ready",
            "speech_unit_id": "speech_unit_01",
            "spoken_text": "别动那只表。",
            "render_recipe": _recipe(1, "speech_unit_01"),
            "voice_id": "voice_chosen_by_the_client",
        }
    )
    assert not _validator_for("turn_delivery").is_valid(delivery)


def test_a_recipe_carries_the_evidence_it_was_reviewed_against():
    """The contract has to allow the evidence the Engine already seals.

    Both ends emit these four fields, and ``additionalProperties: false`` meant
    the contract rejected the very payloads the App receives — a three-way
    disagreement in which the two implementations were right and only the
    document was wrong.
    """
    delivery = _delivery(
        {
            "segment_index": 1,
            "state": "ready",
            "speech_unit_id": "speech_unit_01",
            "spoken_text": "别动那只表。",
            "render_recipe": _recipe(1, "speech_unit_01"),
        }
    )
    assert _validator_for("turn_delivery").is_valid(delivery)

    # Declaring the fields must not turn the recipe into a free-for-all: an
    # unknown key is still a protocol violation, and a malformed digest is a
    # different claim rather than a variant of the same one.
    invented = copy.deepcopy(delivery)
    invented["speech_units"][0]["render_recipe"]["evidence_body"] = "the whole record"
    assert not _validator_for("turn_delivery").is_valid(invented)

    for bad_digest in ("", "not-a-digest", "A" * 64):
        malformed = copy.deepcopy(delivery)
        malformed["speech_units"][0]["render_recipe"]["evidence_digest"] = bad_digest
        assert not _validator_for("turn_delivery").is_valid(malformed), bad_digest


def test_the_single_segment_mirror_is_not_a_delivery_shape():
    """The mirror is gone from both ends, so the contract must stop offering it.

    The Engine seals batches and can only emit ``speech_units``; the App decodes
    batches and rejects any other key. A schema that still accepts the mirror is
    a contract that certifies payloads the only client will reject — a gap no
    runtime test can catch, because producer and consumer are both already
    correct and simply disagree with the document between them.
    """
    delivery = {
        "state": "ready",
        "narrative_block_id": "narrative_01",
        "speech_unit_id": "speech_unit_01",
        "spoken_text": "别动那只表。",
        "render_recipe": _recipe(1, "speech_unit_01"),
    }
    assert not _validator_for("turn_delivery").is_valid(delivery)


def test_a_ready_turn_must_carry_a_non_empty_batch():
    """``ready`` with an empty ``speech_units`` is the mirror's old failure mode.

    It used to be legal to say ``ready`` while naming a single voice at the top
    level. With the batch as the only view, an empty one means the same thing: a
    turn that claims to be audible and is not.
    """
    assert not _validator_for("turn_delivery").is_valid(
        {"state": "ready", "narrative_block_id": "narrative_01", "speech_units": []}
    )
