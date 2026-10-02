"""Story Book reading-mode projection (PRD §20.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from application.storybook_projection import (
    StoryBookArtifacts,
    StoryBookProjectionError,
    project_story_book,
)
from contracts import Episode, NarrativeBlock, SecretState
from contracts.models import NarrativeSegment

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "contracts"
    / "schemas"
    / "storybook.schema.json"
)


def _block(block_id: str, *, scene_id: str | None = "consultation_room") -> NarrativeBlock:
    return NarrativeBlock(
        schema_version="1.0",
        id=block_id,
        story_session_id="session-1",
        source_story_revision=1,
        scene_id=scene_id,
        segments=[
            NarrativeSegment(type="narration", text="雨落在诊所的窗外。"),
            NarrativeSegment(
                type="character",
                speaker_id="char_morris",
                text="你还没有回答我的问题。",
            ),
        ],
    )


def _episode(*, block_ids: list[str] | None) -> Episode:
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
            "ending": {"type": "partial_truth", "main_problem": " Jonathan 去向不明"},
            "secret_states": {"secret_01": SecretState.PARTIAL},
            "unresolved_threads": ["Jonathan 是否还活着"],
            **({"narrative_block_ids": block_ids} if block_ids is not None else {}),
        }
    )


def test_projection_assembles_chapters_in_committed_order_and_matches_contract():
    blocks = {"b2": _block("b2"), "b1": _block("b1")}
    episode = _episode(block_ids=["b1", "b2"])
    names = {"char_morris": "莫里斯医生"}

    book = project_story_book(
        episode=episode,
        narrative_blocks=blocks,
        character_display_names=names,
    )

    # Chapter order follows the Episode's own references, not dict order.
    assert [c["block_id"] for c in book["chapters"]] == ["b1", "b2"]
    assert book["title"] == "哈维诊所的停顿"
    assert book["ending"] == {
        "type": "partial_truth",
        "main_problem": " Jonathan 去向不明",
    }
    assert book["unresolved_threads"] == ["Jonathan 是否还活着"]

    # The projection output must satisfy the SB-01 contract.
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(book)


def test_the_protagonist_is_projected_as_a_public_label():
    """PRD §20 的「主角」要的是名字，不是 canonical id。"""
    blocks = {"b1": _block("b1")}
    episode = _episode(block_ids=["b1"])

    book = project_story_book(
        episode=episode,
        narrative_blocks=blocks,
        character_display_names={"char_evelyn": "伊芙琳·格雷"},
    )

    assert book["protagonist_labels"] == ["伊芙琳·格雷"]


def test_an_unnamed_protagonist_keeps_its_slot_as_null():
    """解析不出时给 null：既不回落成 canonical id，也不把主角悄悄丢掉。

    丢弃会让「两个主角其中一个叫不出名字」读成「只有一个主角」；回落成 id 则
    直接违反 publicLabel「canonical id 永远不得出现在这里」。
    """
    blocks = {"b1": _block("b1")}
    episode = _episode(block_ids=["b1"])

    book = project_story_book(
        episode=episode,
        narrative_blocks=blocks,
        character_display_names={"char_morris": "莫里斯医生"},
    )

    assert book["protagonist_ids"] == ["char_evelyn"]
    assert book["protagonist_labels"] == [None]
    assert "char_evelyn" not in json.dumps(
        book["protagonist_labels"], ensure_ascii=False
    )


def test_protagonist_labels_stay_positionally_aligned():
    """下标即对应关系——错位会把名字安到错误角色身上。"""
    blocks = {"b1": _block("b1")}
    base = json.loads(_episode(block_ids=["b1"]).model_dump_json(exclude_none=True))
    episode = Episode.model_validate(
        {**base, "protagonist_ids": ["char_evelyn", "char_morris", "char_audrey"]}
    )

    book = project_story_book(
        episode=episode,
        narrative_blocks=blocks,
        character_display_names={"char_morris": "莫里斯医生"},
    )

    assert book["protagonist_labels"] == [None, "莫里斯医生", None]
    assert len(book["protagonist_labels"]) == len(book["protagonist_ids"])


def test_speaker_is_resolved_to_public_label_not_canonical_id():
    blocks = {"b1": _block("b1")}
    book = project_story_book(
        episode=_episode(block_ids=["b1"]),
        narrative_blocks=blocks,
        character_display_names={"char_morris": "莫里斯医生"},
    )
    segments = book["chapters"][0]["segments"]
    assert segments[0]["speaker"] is None  # narration never carries a speaker
    assert segments[1]["speaker"] == "莫里斯医生"  # public label, not the id


def test_speaker_fails_closed_when_no_public_label_exists():
    """A speaker with no public label renders null; the canonical id must not leak."""
    blocks = {"b1": _block("b1")}
    book = project_story_book(
        episode=_episode(block_ids=["b1"]),
        narrative_blocks=blocks,
        character_display_names={},  # fail-closed: no public labels at all
    )
    speaker = book["chapters"][0]["segments"][1]["speaker"]
    assert speaker is None
    assert "char_morris" not in json.dumps(book)


def test_chapterless_episode_is_rejected_rather_than_producing_an_empty_book():
    with pytest.raises(StoryBookProjectionError) as exc:
        project_story_book(
            episode=_episode(block_ids=None),
            narrative_blocks={},
            character_display_names={},
        )
    assert exc.value.code == "storybook_has_no_chapters"


def test_missing_referenced_chapter_is_rejected():
    with pytest.raises(StoryBookProjectionError) as exc:
        project_story_book(
            episode=_episode(block_ids=["b1", "ghost"]),
            narrative_blocks={"b1": _block("b1")},
            character_display_names={},
        )
    assert exc.value.code == "storybook_chapter_missing"


# ---- PRD §20 additive sections -----------------------------------------


def _artifacts(**overrides) -> StoryBookArtifacts:
    base = {
        "character_events": (),
        "relationship_events": (),
        "knowledge_changes": (),
        "world_events": (),
    }
    base.update(overrides)
    return StoryBookArtifacts(**base)


def _character_event(character_id: str, patches: int) -> dict:
    return {
        "id": f"ce_{character_id}",
        "change": {
            "character_id": character_id,
            "patches": [
                {"path": f"/p{i}", "operation": "set"} for i in range(patches)
            ],
            "evidence_ids": [],
        },
    }


def _relationship_event(source: str, target: str, **dimensions) -> dict:
    return {
        "id": "re_1",
        "change": {
            "from_character_id": source,
            "to_character_id": target,
            "dimension_deltas": dimensions,
            "evidence_ids": [],
        },
    }


def _knowledge(character_id: str, proposition_id: str, **overrides) -> dict:
    item = {
        "schema_version": "1.0",
        "id": f"know_{proposition_id}",
        "character_id": character_id,
        "worldline_id": "wl-1",
        "proposition_id": proposition_id,
        "certainty": 0.9,
        "source": {"type": "document", "ref": "src_1"},
        "acquired_world_time": "1349-06-12T20:30:00",
        "status": "confirmed",
        "revision": 1,
    }
    item.update(overrides)
    return item


def _world_event(event_type: str, **overrides) -> dict:
    item = {
        "schema_version": "1.0",
        "id": f"we_{event_type}",
        "world_id": "world-1",
        "worldline_id": "worldline-1",
        "world_time": "1349-06-12T21:52:00",
        "event_type": event_type,
        "actors": [],
        "targets": [],
        "payload": {"internal": "not for readers"},
        "visibility": {"public": False},
        "persistence": "world",
        "importance": "local",
        "canon_relation": "gap",
        "provenance": {"source_type": "generated"},
        "revision": 1,
    }
    item.update(overrides)
    return item


NAMES = {"char_morris": "莫里斯医生", "char_jonathan": "Jonathan"}
PROPOSITIONS = {"fact.patient_disappeared": "病人失踪了"}


def _book(artifacts=None, propositions=None, names=None):
    return project_story_book(
        episode=_episode(block_ids=["b1"]),
        narrative_blocks={"b1": _block("b1")},
        character_display_names=NAMES if names is None else names,
        proposition_display_names=PROPOSITIONS if propositions is None else propositions,
        artifacts=artifacts,
    )


def _assert_matches_contract(book):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(book)


def test_a_book_without_artifacts_keeps_the_sb01_shape_and_gains_four_empty_sections():
    book = _book()

    for section in (
        "discovered_secrets",
        "key_characters",
        "relationship_changes",
        "world_impacts",
    ):
        assert book[section] == []
    _assert_matches_contract(book)


def test_additive_sections_project_and_match_the_contract():
    book = _book(
        artifacts=_artifacts(
            character_events=(_character_event("char_morris", 2),),
            relationship_events=(
                _relationship_event("char_jonathan", "char_morris", trust=0.3, affection=None),
            ),
            knowledge_changes=(_knowledge("char_evelyn", "fact.patient_disappeared"),),
            world_events=(
                _world_event("patient_left", actors=["char_morris"], targets=["loc_clinic"]),
            ),
        )
    )

    assert book["key_characters"] == [{"label": "莫里斯医生", "change_count": 2}]
    # Only the axis that actually moved is projected.
    assert book["relationship_changes"] == [
        {"from": "Jonathan", "to": "莫里斯医生", "dimensions": {"trust": 0.3}}
    ]
    assert book["discovered_secrets"] == [
        {
            "proposition": "病人失踪了",
            "holder": None,
            "certainty": 0.9,
            "status": "confirmed",
            "acquired_world_time": "1349-06-12T20:30:00",
        }
    ]
    assert book["world_impacts"] == [
        {
            "event_type": "patient_left",
            "world_time": "1349-06-12T21:52:00",
            "importance": "local",
            "persistence": "world",
            "actors": ["莫里斯医生"],
            "targets": [],
        }
    ]
    _assert_matches_contract(book)


def test_an_unnamed_proposition_is_dropped_and_its_id_never_reaches_the_book():
    book = _book(
        artifacts=_artifacts(
            knowledge_changes=(
                _knowledge("char_evelyn", "fact.patient_disappeared"),
                _knowledge("char_evelyn", "fact.unwritten"),
            )
        ),
        propositions={"fact.patient_disappeared": "病人失踪了"},
    )

    assert [s["proposition"] for s in book["discovered_secrets"]] == ["病人失踪了"]
    assert "fact.unwritten" not in json.dumps(book, ensure_ascii=False)


def test_characters_without_a_public_label_never_reach_the_additive_sections():
    """The point of the allowlist: no name, no row — never the canonical id."""
    book = _book(
        artifacts=_artifacts(
            character_events=(_character_event("char_hidden", 5),),
            relationship_events=(
                _relationship_event("char_hidden", "char_also_hidden", trust=0.9),
            ),
            world_events=(_world_event("e", actors=["char_hidden"]),),
        )
    )

    assert book["key_characters"] == []
    assert book["relationship_changes"] == []
    assert book["world_impacts"][0]["actors"] == []
    assert "char_hidden" not in json.dumps(book, ensure_ascii=False)
    assert "char_also_hidden" not in json.dumps(book, ensure_ascii=False)


def test_a_one_sided_relationship_survives_but_an_anonymous_pair_does_not():
    """One unnamed endpoint still leaves a readable fact; two leave nothing."""
    book = _book(
        artifacts=_artifacts(
            relationship_events=(
                _relationship_event("char_morris", "char_hidden", fear=0.4),
                _relationship_event("char_hidden", "char_also_hidden", fear=0.4),
            )
        )
    )

    assert book["relationship_changes"] == [
        {"from": "莫里斯医生", "to": None, "dimensions": {"fear": 0.4}}
    ]


def test_a_relationship_with_no_moved_dimension_is_not_a_change():
    book = _book(
        artifacts=_artifacts(
            relationship_events=(
                _relationship_event("char_morris", "char_jonathan"),
                _relationship_event(
                    "char_morris", "char_jonathan", trust=None, affection=None
                ),
            )
        )
    )

    assert book["relationship_changes"] == []


def test_world_impacts_lead_with_the_most_far_reaching_importance():
    book = _book(
        artifacts=_artifacts(
            world_events=(
                _world_event("a", importance="personal"),
                _world_event("b", importance="world"),
                _world_event("c", importance="local"),
            )
        )
    )

    assert [e["event_type"] for e in book["world_impacts"]] == ["b", "c", "a"]


def test_the_free_form_world_event_payload_is_not_projected():
    book = _book(artifacts=_artifacts(world_events=(_world_event("e"),)))

    assert "payload" not in book["world_impacts"][0]
    assert "not for readers" not in json.dumps(book, ensure_ascii=False)


@pytest.mark.parametrize(
    "artifacts",
    [
        _artifacts(character_events=({"change": None}, {}, {"no": "change"})),
        _artifacts(
            character_events=({"change": {"character_id": "x", "patches": "many"}},)
        ),
        _artifacts(relationship_events=({"change": {"dimension_deltas": "trust"}},)),
        _artifacts(relationship_events=({"change": {"dimension_deltas": {"luck": 1}}},)),
        _artifacts(knowledge_changes=({"proposition_id": "fact.x"}, "not-a-mapping")),
        _artifacts(knowledge_changes=({"proposition_id": "fact.x", "certainty": "high"},)),
        _artifacts(
            knowledge_changes=(
                {"proposition_id": "fact.x", "certainty": True, "status": "confirmed"},
            )
        ),
        _artifacts(world_events=({"event_type": ""},)),
        _artifacts(world_events=({"event_type": "e", "importance": "cosmic"},)),
        _artifacts(world_events=({"event_type": "e", "persistence": "forever"},)),
    ],
)
def test_malformed_artifacts_are_skipped_rather_than_crashing_the_book(artifacts):
    """A reading view loses a line, not the book."""
    book = _book(artifacts=artifacts, propositions={"fact.x": "某件事"})

    assert book["chapters"][0]["block_id"] == "b1"
    assert book["key_characters"] == []
    assert book["relationship_changes"] == []
    assert book["discovered_secrets"] == []
    assert book["world_impacts"] == []


def test_the_sections_are_ordered_totally_not_by_storage_order():
    """Two reads of one Episode must not disagree about the order of a page."""
    events = (
        _character_event("char_morris", 1),
        _character_event("char_jonathan", 4),
        _character_event("char_morris", 1),
    )
    forward = _book(artifacts=_artifacts(character_events=events))
    backward = _book(artifacts=_artifacts(character_events=tuple(reversed(events))))

    assert forward == backward
    assert forward["key_characters"][0] == {"label": "Jonathan", "change_count": 4}


def test_character_change_counts_accumulate_across_turns():
    book = _book(
        artifacts=_artifacts(
            character_events=(
                _character_event("char_morris", 1),
                _character_event("char_morris", 2),
            )
        )
    )

    assert book["key_characters"] == [{"label": "莫里斯医生", "change_count": 3}]


# ---------------------------------------------------------------------------
# The shipped bundle, not a hand-written fixture.
#
# Every test above builds its artifacts inline, which is right for pinning the
# projection's rules and wrong for pinning whether those rules have anything to
# work on. Those are different questions, and only the second one caught the
# fact that 已发现秘密 shipped dead: the projection was correct, the allowlist
# it reads was simply absent from the bundle the product actually launches
# with. A green suite said nothing about it for three slices.
#
# So these read the real builder. If a presentation table stops being emitted,
# the product loses a section of the book and this file goes red.
# ---------------------------------------------------------------------------


def _shipped_payload() -> dict:
    import sys

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "scripts"))
    try:
        import build_story_content as builder
    finally:
        sys.path.pop(0)
    return builder.build_payload()


def _shipped_book(payload: dict, artifacts=None) -> dict:
    presentation = payload["presentation"]
    return project_story_book(
        episode=_episode(block_ids=["b1"]),
        narrative_blocks={"b1": _block("b1")},
        character_display_names=presentation.get("character_display_names", {}),
        proposition_display_names=presentation.get("proposition_display_names", {}),
        artifacts=artifacts
        or StoryBookArtifacts(knowledge_changes=tuple(payload["knowledge"])),
    )


def _golden_turn_artifacts(payload: dict) -> StoryBookArtifacts:
    """Artifacts shaped like the ones the shipped five turns actually commit.

    Counts come from the acceptance oracle
    (``docs/04_Golden_Scenarios/golden_001/expected_episode.json``):
    **zero** character events, one relationship event, three knowledge
    changes, one world event. The zero is the load-bearing part — it is why
    关键人物 stays empty no matter what the roster says.
    """
    return StoryBookArtifacts(
        knowledge_changes=tuple(payload["knowledge"]),
        relationship_events=(
            _relationship_event("char_evelyn_gray", "npc_doctor_morris", trust=0.3),
        ),
        world_events=(
            _world_event("occult_evidence", actors=["npc_doctor_morris"]),
        ),
    )


def test_the_shipped_bundle_carries_the_names_the_book_reads():
    """An empty allowlist is legal; an empty one in the shipped bundle is a bug.

    ``ScenarioPresentation`` defaults every table to ``{}`` so that bundles
    written before a table existed keep validating. That default is the right
    compatibility choice and a poor product state: it means a builder that
    forgets to pass a table produces a bundle that validates, ships, and
    silently empties a section of the reading mode.
    """
    presentation = _shipped_payload()["presentation"]

    assert presentation["clue_display_names"], "线索公开名表不应为空"
    assert presentation["proposition_display_names"], (
        "命题公开名表不应为空——没有它，Story Book 的「已发现秘密」整段为空"
    )


def test_the_shipped_bundle_projects_readable_secrets():
    """End to end: real builder, real knowledge, real projection."""
    payload = _shipped_payload()
    table = payload["presentation"]["proposition_display_names"]

    book = _shipped_book(payload)

    secrets = book["discovered_secrets"]
    assert secrets, "出货固件的真实 knowledge 投影不出任何秘密"
    # Every row is a public label drawn from the allowlist, never a bare id.
    assert {row["proposition"] for row in secrets} <= set(table.values())
    serialized = json.dumps(book, ensure_ascii=False)
    assert not [key for key in table if key in serialized], "canonical id 泄漏进了书里"
    _assert_matches_contract(book)


def test_reading_the_book_twice_gives_the_same_page():
    """The shipped path is as order-stable as the fixture path."""
    payload = _shipped_payload()

    assert _shipped_book(payload) == _shipped_book(payload)


def test_the_shipped_roster_and_the_two_sections_it_feeds_stay_in_step():
    """关键人物 and 关系变化 are a function of the shipped roster — nothing else.

    A prior author left ``character_display_names`` out on purpose, reasoning
    that shipping it would push the supporting cast into voice casting and
    speaker binding, and installed this test as a tripwire: shipping the roster
    was supposed to turn it red so whoever did it had to say so out loud.

    SB-19 got the shape of this wrong and asserted the roster fills *both*
    sections. It fills one. Each section is a function of its own input, and
    only two of the four read the roster at all:

    =========================  ==============================  ==========
    section                    fed by                          roster?
    =========================  ==============================  ==========
    已发现秘密                  knowledge + proposition names   no
    对世界造成的影响             world events                    no*
    重要关系变化                relationship events             yes
    关键人物                   character events                yes
    =========================  ==============================  ==========

    (*) ``world_impacts`` projects ``event_type`` / ``importance`` regardless
    of names; the roster only decides whether ``actors`` / ``targets`` carry
    labels instead of being dropped.

    关键人物 is empty for a reason the roster cannot fix: the shipped five
    turns commit **zero** character events. That is the oracle's
    ``character_event_ids: []``, not a missing allowlist — and conflating the
    two would send the next person looking for a roster that is already
    shipped.
    """
    presentation = _shipped_payload()["presentation"]
    roster = presentation.get("character_display_names") or {}
    payload = _shipped_payload()
    book = _shipped_book(payload, _golden_turn_artifacts(payload))

    assert book["discovered_secrets"], "秘密段由命题表驱动，与角色名册无关"
    assert book["world_impacts"], "世界影响的事件类型不依赖角色名册"

    if roster:
        assert book["relationship_changes"], "名册已出货，关系变化段不该为空"
        # 主角不在公开名册里 —— 她是玩家自己，App 本来就知道她是谁。
        assert book["relationship_changes"][0]["from"] is None
        assert book["relationship_changes"][0]["to"] in roster.values()
    else:
        assert book["relationship_changes"] == []

    assert book["key_characters"] == [], (
        "出货五轮不产生任何角色状态变更（oracle character_event_ids == []），"
        "关键人物段为空与角色名册无关"
    )


def test_key_characters_is_driven_by_character_events_not_by_the_roster():
    """证明上一条断言里的「空」另有原因，而不是名册没出货。

    同一份名册，同一段投影，只要喂进一条角色事件，关键人物段就立刻有内容。
    于是关键人物段的空只能归因于零角色事件。
    """
    payload = _shipped_payload()
    payload["presentation"]["character_display_names"] = {
        "npc_doctor_morris": "莫里斯医生",
    }

    without = _shipped_book(
        payload,
        StoryBookArtifacts(
            relationship_events=(
                _relationship_event("char_evelyn_gray", "npc_doctor_morris"),
            )
        ),
    )
    with_event = _shipped_book(
        payload,
        StoryBookArtifacts(
            character_events=(_character_event("npc_doctor_morris", 2),),
            relationship_events=(
                _relationship_event("char_evelyn_gray", "npc_doctor_morris"),
            ),
        ),
    )

    assert without["key_characters"] == []
    assert with_event["key_characters"] == [
        {"label": "莫里斯医生", "change_count": 2}
    ]


# ---------------------------------------------------------------------------
# The cross-language wire fixture.
#
# `macos-app/WorldOfMysteriesTests/Fixtures/storybook_wire.json` is what the App
# decodes. SB-13 generated it from the real projection after finding the App
# could not open a book at all, and the whole class of that bug -- a fixture
# quietly disagreeing with its producer -- is only closed once something
# notices the two drifting apart again. This is that something.

WIRE_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "macos-app"
    / "WorldOfMysteriesTests"
    / "Fixtures"
    / "storybook_wire.json"
)


def _wire_fixture_book() -> dict:
    """Rebuild, from the live projection, the payload the fixture was cut from."""
    import sys

    from application.story_initialization import GOLDEN_CHARACTER_DISPLAY_NAMES

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "scripts"))
    try:
        import build_story_content as builder
    finally:
        sys.path.pop(0)
    payload = builder.build_payload()

    block = NarrativeBlock(
        schema_version="1.0",
        id="block-1",
        story_session_id="session-1",
        source_story_revision=1,
        scene_id="consultation_room",
        segments=[
            NarrativeSegment(type="narration", text="雨落在诊所的窗外。"),
            NarrativeSegment(
                type="character",
                speaker_id="npc_doctor_morris",
                text="你还没有回答我的问题。",
            ),
        ],
    )
    episode = Episode.model_validate(
        {
            "schema_version": "1.0",
            "id": "episode-001",
            "world_id": "world-tingen",
            "worldline_id": "wl-1349-main",
            "protagonist_ids": ["char_evelyn_gray"],
            "title": "哈维诊所的停顿",
            "start_world_time": "1349-06-12T21:40:00",
            "end_world_time": "1349-06-12T21:52:00",
            "ending": {
                "type": "partial_truth",
                "main_problem": "乔纳森·维尔去向不明",
            },
            "secret_states": {"secret_01": SecretState.PARTIAL},
            "unresolved_threads": ["乔纳森·维尔是否还活着"],
            "narrative_block_ids": ["block-1"],
        }
    )
    artifacts = StoryBookArtifacts(
        character_events=(
            {
                "id": "ce_1",
                "change": {
                    "character_id": "npc_doctor_morris",
                    "patches": [
                        {"path": "/manner", "operation": "set"},
                        {"path": "/suspicion", "operation": "set"},
                    ],
                },
            },
        ),
        relationship_events=(
            {
                "id": "re_1",
                "change": {
                    "from_character_id": "char_evelyn_gray",
                    "to_character_id": "npc_doctor_morris",
                    # `affection` is null on purpose: the projection must omit
                    # an axis that did not move rather than assert all six, and
                    # the App asserts it reads only the two that did.
                    "dimension_deltas": {"trust": 0.3, "fear": 0.2, "affection": None},
                },
            },
        ),
        knowledge_changes=tuple(payload["knowledge"]),
        world_events=(
            {
                "event_type": "patient_discovered_missing",
                "world_time": "1349-06-12T21:20:00",
                "importance": "local",
                "persistence": "world",
                "actors": ["char_evelyn_gray"],
                "targets": ["npc_doctor_morris"],
                # Model-authored free-form data. The projection drops it, and
                # the App asserts this string never reaches the page.
                "payload": {"note": "model-authored field, deliberately dropped"},
            },
        ),
    )
    return project_story_book(
        episode=episode,
        narrative_blocks={"block-1": block},
        character_display_names=dict(GOLDEN_CHARACTER_DISPLAY_NAMES),
        proposition_display_names=payload["presentation"]["proposition_display_names"],
        artifacts=artifacts,
    )


def test_the_committed_wire_fixture_is_what_the_projection_produces():
    """The App is checked against its producer, not against a memory of it.

    SB-13 found the App shipping a Story Book it could not open: the decoder
    mirrored the contract strictly, the projection had always emitted four keys
    the decoder did not allow, and every Swift fixture happened to omit them.
    Swapping those fixtures for generated output closes the *shape* half of that
    gap. This closes the other half -- without it the new fixture is just
    another committed snapshot that rots the first time the projection moves.

    Regenerate deliberately, never as a side effect of a failing run:
    `WOM_REGEN_STORYBOOK_FIXTURE=1 pytest tests/test_storybook_projection.py`
    """
    import os

    produced = (
        json.dumps(_wire_fixture_book(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )

    if os.getenv("WOM_REGEN_STORYBOOK_FIXTURE") == "1":
        WIRE_FIXTURE.write_text(produced, encoding="utf-8")

    assert WIRE_FIXTURE.exists(), f"缺少线缆夹具：{WIRE_FIXTURE}"
    assert WIRE_FIXTURE.read_text(encoding="utf-8") == produced, (
        "storybook_wire.json 与真实投影不一致——App 正在对照一份过期的生产者快照。"
        "确认这是有意的内容变更后，用 WOM_REGEN_STORYBOOK_FIXTURE=1 重新生成，"
        "并把这次变更登记为一次产品内容变更（参照 golden_policy 对内容摘要的纪律）。"
    )


def test_the_wire_fixture_carries_all_four_sections():
    """A fixture with an empty section cannot prove the App reads that section.

    This is the assertion whose absence let 已发现秘密 ship empty for three
    slices: the section existed in the contract, in the projection and in the
    DTO, and none of them had anything to show.
    """
    book = json.loads(WIRE_FIXTURE.read_text(encoding="utf-8"))

    for section in (
        "discovered_secrets",
        "key_characters",
        "relationship_changes",
        "world_impacts",
    ):
        assert book[section], f"线缆夹具的 {section} 段为空"
