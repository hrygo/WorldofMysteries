"""Tests for the pure StoryState reducer, focused on scene roster membership.

``apply_story_delta`` had no dedicated coverage — it reached production only
through ``story_turn_commit``. That is how the scene roster survived as a
persisted world fact that nothing could ever change: the field was seeded at
session open and every delta since has left it alone, with nothing to say so.
"""
from __future__ import annotations

import pytest

from contracts import StateDelta, StoryState
from domain.story_state_reducer import (
    StoryStateTransitionError,
    apply_story_delta,
)


def _state(roster: list[str] | None = None) -> StoryState:
    scene: dict = {"id": "consultation_room", "location_id": "loc_morris_clinic"}
    if roster is not None:
        scene["active_character_ids"] = roster
    return StoryState.model_validate(
        {
            "schema_version": "1.0",
            "story_session_id": "session_roster",
            "revision": 1,
            "turn": 1,
            "phase": "discovery",
            "scene": scene,
            "world_time": "1349-06-12T21:45:00",
            "protagonist_goal": "find_missing_patient",
            "active_conflicts": ["morris_evasion"],
            "discovered_clue_ids": [],
            "secret_states": {"secret_01": "hidden"},
            "commitments": {"hard_ids": [], "soft_ids": []},
            "local_state": {},
            "pressure": {},
            "last_state_delta_id": "delta_roster_01",
        }
    )


def _delta(
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    delta_id: str = "delta_roster_02",
) -> StateDelta:
    story_delta: dict = {}
    if add is not None:
        story_delta["active_character_ids_add"] = add
    if remove is not None:
        story_delta["active_character_ids_remove"] = remove
    return StateDelta.model_validate(
        {
            "schema_version": "1.0",
            "id": delta_id,
            "turn_id": "turn_roster",
            "outcome": "clean_success",
            "story_delta": story_delta,
            "character_deltas": [
                {
                    "character_id": "npc_doctor_morris",
                    "patches": [],
                    "evidence_ids": [],
                }
            ],
            "world_event_candidates": [],
            "evidence_ids": [],
        }
    )


def test_a_character_entering_the_scene_extends_the_roster():
    result = apply_story_delta(
        _state(["char_evelyn_gray"]),
        _delta(add=["npc_doctor_morris"]),
    )

    assert result.scene.active_character_ids == [
        "char_evelyn_gray",
        "npc_doctor_morris",
    ]


def test_a_character_leaving_the_scene_narrows_the_roster():
    result = apply_story_delta(
        _state(["char_evelyn_gray", "npc_doctor_morris"]),
        _delta(remove=["npc_doctor_morris"]),
    )

    assert result.scene.active_character_ids == ["char_evelyn_gray"]


def test_one_delta_cannot_add_and_remove_the_same_character():
    with pytest.raises(StoryStateTransitionError):
        apply_story_delta(
            _state(["char_evelyn_gray"]),
            _delta(add=["npc_doctor_morris"], remove=["npc_doctor_morris"]),
        )


def test_re_adding_a_character_already_present_does_not_duplicate_them():
    """Re-adding is how a delta that moves a character out and back reads.

    The roster is hashed into NarrativeBlock identity, so a duplicate would
    not merely be untidy: the same committed history would publish under two
    different block ids depending on how many turns it took.
    """
    result = apply_story_delta(
        _state(["char_evelyn_gray", "npc_doctor_morris"]),
        _delta(add=["npc_doctor_morris"]),
    )

    assert result.scene.active_character_ids == [
        "char_evelyn_gray",
        "npc_doctor_morris",
    ]


def test_removing_someone_absent_is_vacuous_rather_than_an_error():
    result = apply_story_delta(
        _state(["char_evelyn_gray"]),
        _delta(remove=["npc_never_arrived"]),
    )

    assert result.scene.active_character_ids == ["char_evelyn_gray"]


def test_a_removal_alone_does_not_declare_a_roster_the_world_never_stated():
    """``None`` and ``[]`` are different claims and must not merge.

    ``None`` means the world has never said who is here; an empty list is the
    assertion that the scene is empty. A delta removing someone who was never
    declared asserts only that one person is absent, which says nothing about
    the rest — so it must not manufacture an empty roster.
    """
    result = apply_story_delta(
        _state(None),
        _delta(remove=["npc_never_arrived"]),
    )

    assert result.scene.active_character_ids is None


def test_an_entry_materializes_a_roster_the_world_had_not_stated():
    """The converse: an entry *is* a statement that someone is here."""
    result = apply_story_delta(
        _state(None),
        _delta(add=["npc_doctor_morris"]),
    )

    assert result.scene.active_character_ids == ["npc_doctor_morris"]


def test_roster_order_is_the_committed_order_and_not_an_iteration_order():
    declared = ["npc_dunn", "npc_teresa", "npc_omar", "npc_peter"]
    result = apply_story_delta(
        _state(["char_evelyn_gray"]),
        _delta(add=declared),
    )

    assert result.scene.active_character_ids == ["char_evelyn_gray", *declared]


def test_the_roster_is_a_function_of_the_committed_deltas():
    """Same history, same roster — twice over, and in a different order of
    application."""
    forward = apply_story_delta(
        apply_story_delta(
            _state(["char_evelyn_gray"]),
            _delta(add=["npc_dunn", "npc_teresa"], delta_id="d1"),
        ),
        _delta(remove=["npc_dunn"], delta_id="d2"),
    )
    replay = apply_story_delta(
        apply_story_delta(
            _state(["char_evelyn_gray"]),
            _delta(add=["npc_dunn", "npc_teresa"], delta_id="d1"),
        ),
        _delta(remove=["npc_dunn"], delta_id="d2"),
    )

    assert forward.scene.active_character_ids == replay.scene.active_character_ids


def test_a_delta_that_says_nothing_about_the_roster_leaves_it_alone():
    result = apply_story_delta(
        _state(["char_evelyn_gray", "npc_doctor_morris"]),
        _delta(),
    )

    assert result.scene.active_character_ids == [
        "char_evelyn_gray",
        "npc_doctor_morris",
    ]
