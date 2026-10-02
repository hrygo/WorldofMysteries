"""Story Book reading-mode projection (PRD §20.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from application.storybook_projection import (
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
