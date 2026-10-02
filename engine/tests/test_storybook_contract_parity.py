"""Engine <-> declared-contract reconciliation for ``story.storybook.get``.

SB-15 gave this call a declared contract. Two things were still free to drift
away from it without turning anything red:

* ``_validate_storybook_payload`` is a hand-written validator that happens to
  describe the same request the contract describes, and
* nothing proved the payload the handler hands back is the payload the
  contract's ``storybook_get_response`` accepts.

Self-consistency on both sides is precisely the condition under which SB-13
shipped: the App mirrored a stale key set, every unit test stayed green, and
the reading mode was unreachable in the built product. These tests reconcile the
Engine against the contract in both directions, so neither side can move alone.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from application.storybook_projection import StoryBookArtifacts
from application.storybook_service import FinalizedEpisode, StoryBookService
from contracts import Episode, NarrativeBlock
from contracts.models import NarrativeSegment
from infrastructure.story_runtime import (
    _StoryBookRejected,
    _storybook_handler,
    _validate_storybook_payload,
)

ROOT = Path(__file__).resolve().parent.parent.parent
PROTOCOL_BASE = "https://worldofmysteries.io/schemas/protocol/"
CONTROL = json.loads(
    (ROOT / "contracts/protocol/storybook_control.schema.json").read_text(
        encoding="utf-8"
    )
)
BOOK_SCHEMA = json.loads(
    (ROOT / "contracts/schemas/storybook.schema.json").read_text(encoding="utf-8")
)
FIXTURE = json.loads(
    (ROOT / "contracts/fixtures/ipc/storybook_control.json").read_text(encoding="utf-8")
)


def _contract(shape: str) -> Draft202012Validator:
    """Validate against the declared control surface, cross-file ``$ref`` included.

    ``storybook.schema.json`` declares a ``mysterious.world`` id while the
    protocol lives on ``worldofmysteries.io``, so the relative ``$ref`` resolves
    against the protocol's own base. Registering both spellings is what makes
    the response body get validated as a whole instead of silently skipped.
    """
    resources = []
    for schema in (CONTROL, BOOK_SCHEMA):
        resource = Resource.from_contents(schema)
        name = schema["$id"].rsplit("/", 1)[-1]
        resources.append((schema["$id"], resource))
        resources.append((f"{PROTOCOL_BASE}{name}", resource))
    return Draft202012Validator(
        {
            "$schema": CONTROL["$schema"],
            "$id": CONTROL["$id"],
            "$ref": f"#/$defs/{shape}",
            "$defs": CONTROL["$defs"],
        },
        registry=Registry().with_resources(resources),
    )


REQUEST = _contract("storybook_get_request")
RESPONSE = _contract("storybook_get_response")


def _engine_accepts(payload: object) -> bool:
    try:
        _validate_storybook_payload(payload)  # type: ignore[arg-type]
    except _StoryBookRejected:
        return False
    return True


REQUEST_CASES = [
    case for case in FIXTURE["cases"] if case["shape"] == "storybook_get_request"
]


# ---- request side: the Engine agrees with the contract, case by case ----


@pytest.mark.parametrize("case", REQUEST_CASES, ids=lambda case: case["id"])
def test_the_engine_agrees_with_the_contract_on_every_declared_request(case):
    assert _engine_accepts(case["value"]) is case["valid"], (
        "the Engine's hand-written validator and the declared contract disagree; "
 "whichever side moved, the request shape changed on only one of them"
    )


def test_the_reconciliation_covered_both_verdicts():
    """A one-sided case list reconciles nothing.

    If every declared request were valid, the assertion above would still pass
    with an Engine that accepts anything — the exact inverse of the bug this
    file exists to catch.
    """
    verdicts = {case["valid"] for case in REQUEST_CASES}
    assert verdicts == {True, False}


# Malformed payloads the Engine's own suite already refuses but the shared
# fixture never names. They are checked against the contract as well, so the
# two implementations cannot each quietly grow a private rule.
UNDECLARED_ENGINE_CASES = [
    pytest.param("", False, id="blank_session_id"),
    pytest.param(" ", False, id="whitespace_session_id"),
    pytest.param("bad\x00id", False, id="nul_in_session_id"),
    pytest.param(5, False, id="session_id_is_not_a_string"),
    pytest.param(None, False, id="session_id_is_null"),
    pytest.param(["s"], False, id="session_id_is_a_list"),
    pytest.param("s", True, id="well_formed"),
]


@pytest.mark.parametrize("session_id,valid", UNDECLARED_ENGINE_CASES)
def test_the_contract_says_the_same_thing_about_session_ids(session_id, valid):
    payload = {"schema_version": "1.0", "session_id": session_id}
    assert REQUEST.is_valid(payload) is valid
    assert _engine_accepts(payload) is valid


def test_the_declared_request_is_exactly_the_key_set_the_engine_demands():
    """Catch a field added to one side only, before it reaches the wire."""
    declared = CONTROL["$defs"]["storybook_get_request"]

    assert sorted(declared["properties"]) == sorted(declared["required"]) == [
        "schema_version",
        "session_id",
    ]
    assert declared["additionalProperties"] is False

    # Both sides must refuse a key the contract never declared. If one side
    # grows a private field, the other refuses it and this turns red.
    for field in ("chapter_id", "cursor", "locale", "world_id"):
        candidate = {"schema_version": "1.0", "session_id": "s", field: "x"}
        assert REQUEST.is_valid(candidate) is False, field
        assert _engine_accepts(candidate) is False, field


# ---- response side: the Engine serves what the contract describes -------


def _bootstrap(names: dict[str, str], propositions: dict[str, str]):
    return SimpleNamespace(
        presentation=SimpleNamespace(
            character_display_names=names,
            proposition_display_names=propositions,
        )
    )


def _block() -> NarrativeBlock:
    return NarrativeBlock(
        schema_version="1.0",
        id="b1",
        story_session_id="session-1",
        source_story_revision=1,
        scene_id="consultation_room",
        segments=[
            NarrativeSegment(type="narration", text="雨落在诊所的窗外。"),
            NarrativeSegment(
                type="character",
                speaker_id="char_morris",
                text="你还没有回答我的问题。",
            ),
        ],
    )


def _episode() -> Episode:
    return Episode.model_validate(
        {
            "schema_version": "1.0",
            "id": "episode_session-1",
            "world_id": "world-1",
            "worldline_id": "worldline-1",
            "protagonist_ids": ["char_evelyn"],
            "title": "哈维诊所的停顿",
            "start_world_time": "1349-06-12T21:40:00",
            "end_world_time": "1349-06-12T21:52:00",
            "ending": {"type": "partial_truth", "main_problem": "乔纳森·维尔去向不明"},
            "secret_states": {"fact.patient_disappeared": "partial"},
            "unresolved_threads": ["乔纳森·维尔是否还活着"],
            "narrative_block_ids": ["b1"],
        }
    )


def _artifacts() -> StoryBookArtifacts:
    return StoryBookArtifacts(
        character_events=(
            {
                "id": "ce_1",
                "change": {
                    "character_id": "char_morris",
                    "patches": [{"path": "/p0", "operation": "set"}],
                    "evidence_ids": [],
                },
            },
        ),
        relationship_events=(
            {
                "id": "re_1",
                "change": {
                    "from_character_id": "char_evelyn",
                    "to_character_id": "char_morris",
                    "dimension_deltas": {"trust": 0.3, "fear": 0.2},
                    "evidence_ids": [],
                },
            },
        ),
        knowledge_changes=(
            {
                "schema_version": "1.0",
                "id": "know_1",
                "character_id": "char_evelyn",
                "worldline_id": "worldline-1",
                "proposition_id": "fact.patient_disappeared",
                "certainty": 1,
                "source": {"type": "document", "ref": "src_1"},
                "acquired_world_time": "1349-06-12T20:30:00",
                "status": "confirmed",
                "revision": 1,
            },
        ),
        world_events=(
            {
                "schema_version": "1.0",
                "id": "we_1",
                "world_id": "world-1",
                "worldline_id": "worldline-1",
                "world_time": "1349-06-12T21:20:00",
                "event_type": "patient_discovered_missing",
                "actors": ["char_evelyn"],
                "targets": ["char_morris"],
                "payload": {"internal": "not for readers"},
                "visibility": {"public": False},
                "persistence": "world",
                "importance": "local",
                "canon_relation": "gap",
                "provenance": {"source_type": "generated"},
                "revision": 1,
            },
        ),
    )


def _service() -> StoryBookService:
    bootstrap = _bootstrap(
        {"char_morris": "莫里斯医生", "char_evelyn": "爱伦·格雷"},
        {"fact.patient_disappeared": "病人失踪了"},
    )
    episode = _episode()
    artifacts = _artifacts()
    block = _block()

    class _Boot:
        async def load(self, session_id):
            return bootstrap

    class _Epi:
        async def load_finalized_episode(self, session_id):
            return FinalizedEpisode(episode=episode, artifacts=artifacts)

    class _Nar:
        async def load_narrative_block(self, block_id):
            return block if block_id == "b1" else None

    return StoryBookService(
        bootstraps=_Boot(), episodes=_Epi(), narratives=_Nar()
    )


@pytest.mark.asyncio
async def test_the_book_the_engine_serves_is_the_book_the_contract_describes():
    payload, code, retryable = await _storybook_handler(_service())(
        {}, {"schema_version": "1.0", "session_id": "session-1"}
    )

    assert (code, retryable) == (None, False)
    RESPONSE.validate(payload)


@pytest.mark.asyncio
async def test_the_served_book_carries_every_section_the_contract_allows():
    """All four additive sections populated, not the empty-shell shape.

    Validating only the required-fields book would leave the four sections the
    contract added in SB-09..SB-12 unchecked on the real IPC path.
    """
    payload, _, _ = await _storybook_handler(_service())(
        {}, {"schema_version": "1.0", "session_id": "session-1"}
    )

    for section in (
        "discovered_secrets",
        "key_characters",
        "relationship_changes",
        "world_impacts",
    ):
        assert payload[section], f"{section} is empty on the served book"
    RESPONSE.validate(payload)


@pytest.mark.asyncio
async def test_no_canonical_id_escapes_through_the_ipc_handler():
    """Invariant 6 at the wire: the App must never receive what it may not know.

    The projection fails closed per section; this checks the boundary the App
    actually reads, where a future adapter could reintroduce the id. The
    protagonist is exempt: ``protagonist_ids`` names the player, who is the
    addressee rather than a party the secret is being kept from.
    """
    payload, _, _ = await _storybook_handler(_service())(
        {}, {"schema_version": "1.0", "session_id": "session-1"}
    )
    wire = json.dumps(payload, ensure_ascii=False)

    for canonical in ("char_morris", "fact.patient_disappeared"):
        assert canonical not in wire
