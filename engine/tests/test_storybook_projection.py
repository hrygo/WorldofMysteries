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
