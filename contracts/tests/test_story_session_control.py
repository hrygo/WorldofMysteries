"""Trusted first-turn Story Session wire contract tests."""

from __future__ import annotations

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
