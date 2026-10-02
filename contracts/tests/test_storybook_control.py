"""`story.storybook.get` wire contract tests (PRD §20.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_BASE = "https://worldofmysteries.io/schemas/protocol/"
CONTROL = json.loads(
    (ROOT / "contracts/protocol/storybook_control.schema.json").read_text(
        encoding="utf-8"
    )
)
BOOK = json.loads(
    (ROOT / "contracts/schemas/storybook.schema.json").read_text(encoding="utf-8")
)
FIXTURE = json.loads(
    (ROOT / "contracts/fixtures/ipc/storybook_control.json").read_text(encoding="utf-8")
)


def _registry() -> Registry:
    """Register under every URI the cross-file ``$ref`` may resolve to.

    ``storybook.schema.json`` carries a ``mysterious.world`` id while this
    protocol lives on ``worldofmysteries.io``, so the relative
    ``$ref: "storybook.schema.json"`` resolves against the protocol's own base
    and lands on a URI no schema claims. Registering only the declared ``$id``
    would hide that — the failure would look like "the ref is invalid" rather
    than "the response body was never validated as a whole".
    """
    resources = []
    for schema in (CONTROL, BOOK):
        resource = Resource.from_contents(schema)
        name = schema["$id"].rsplit("/", 1)[-1]
        resources.append((schema["$id"], resource))
        resources.append((f"{PROTOCOL_BASE}{name}", resource))
    return Registry().with_resources(resources)


def _validator_for(shape: str) -> Draft202012Validator:
    wrapper = {
        "$schema": CONTROL["$schema"],
        "$id": CONTROL["$id"],
        "$ref": f"#/$defs/{shape}",
        "$defs": CONTROL["$defs"],
    }
    return Draft202012Validator(wrapper, registry=_registry())


def test_both_schemas_are_valid_draft_2020_12():
    Draft202012Validator.check_schema(CONTROL)
    Draft202012Validator.check_schema(BOOK)


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["id"])
def test_storybook_control_fixture(case):
    assert _validator_for(case["shape"]).is_valid(case["value"]) is case["valid"]


def test_the_response_body_is_the_book_itself_with_no_wrapper():
    """The Engine returns the Story Book as the payload, not a box around it.

    This is the one modelling decision the two sides could most easily have
    disagreed on while both stayed internally consistent: an envelope carrying
    ``{"book": …}`` would satisfy every other test here and still fail on the
    wire. The Swift decoder reads the payload straight into ``StoryBookDTO``,
    so the contract has to say the same thing out loud.
    """
    assert CONTROL["$defs"]["storybook_get_response"]["$ref"] == "storybook.schema.json"

    book = next(
        case["value"]
        for case in FIXTURE["cases"]
        if case["id"] == "storybook_get_response_required_only"
    )
    assert "book" not in book and "storybook" not in book
    assert _validator_for("storybook_get_response").is_valid(book)


def test_the_request_declares_exactly_the_two_fields_the_app_sends():
    """Swift's ``StoryBookRequestDTO`` encodes exactly ``schema_version`` +
    ``session_id``, and the Engine's own hand-written validator demands exactly
    that same key set. A third field would be accepted by neither and is
    therefore declared by neither.
    """
    request = CONTROL["$defs"]["storybook_get_request"]

    assert request["required"] == ["schema_version", "session_id"]
    assert sorted(request["properties"]) == ["schema_version", "session_id"]
    assert request["additionalProperties"] is False


def test_every_rejected_case_says_what_it_refused():
    """An invalid fixture without a stated reason is a typo someone will keep.

    Each negative case exists because some real implementation once got it
    wrong; the id has to keep naming that mistake so the next reader can tell a
    genuine regression from a fixture that drifted.
    """
    rejected = {case["id"] for case in FIXTURE["cases"] if not case["valid"]}

    assert rejected == {
        "storybook_get_request_missing_session_id",
        "storybook_get_request_undeclared_key",
        "storybook_get_request_wrong_schema_version",
        "storybook_get_request_empty_session_id",
        "storybook_get_request_overlong_session_id",
        "storybook_get_response_refuses_a_canonical_proposition_id",
        "storybook_get_response_refuses_an_undeclared_section",
        "storybook_get_response_refuses_certainty_above_one",
        "storybook_get_response_refuses_a_relationship_that_moved_nothing",
    }
