"""Pure StoryState reducer for committed Session facts.

This module owns no storage, AI, narrative, or I/O. It applies a canonical
StateDelta to the current StoryState after the Application layer has decided
that the delta is supported by the current vertical slice.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import math

from contracts import SecretState, StateDelta, StoryState


class StoryStateTransitionError(ValueError):
    """A StateDelta cannot be applied deterministically to the current StoryState."""


_SECRET_ORDER = {
    SecretState.HIDDEN: 0,
    SecretState.SUSPECTED: 1,
    SecretState.PARTIAL: 2,
    SecretState.REVEALED: 3,
}


def apply_story_delta(state: StoryState, delta: StateDelta) -> StoryState:
    story = delta.story_delta

    added = list(story.clue_ids_add or ())
    removed = set(story.clue_ids_remove or ())
    if set(added) & removed:
        raise StoryStateTransitionError("clue cannot be added and removed in one delta")

    clues = [item for item in (state.discovered_clue_ids or ()) if item not in removed]
    for clue_id in added:
        if clue_id not in clues:
            clues.append(clue_id)

    secrets = dict(state.secret_states)
    for secret_id, new_state in (story.secret_state_updates or {}).items():
        if secret_id not in secrets:
            raise StoryStateTransitionError("delta references an unknown story secret")
        if _SECRET_ORDER[new_state] < _SECRET_ORDER[secrets[secret_id]]:
            raise StoryStateTransitionError("story secret state cannot regress")
        secrets[secret_id] = new_state

    pressure = dict(state.pressure)
    for pressure_id, amount in (delta.pressure_delta or {}).items():
        if pressure_id not in pressure:
            raise StoryStateTransitionError("delta references an unknown story pressure")
        numeric = float(amount)
        if not math.isfinite(numeric):
            raise StoryStateTransitionError("pressure delta must be finite")
        pressure[pressure_id] = pressure[pressure_id] + amount

    if story.local_state_patches:
        raise StoryStateTransitionError(
            "local_state_patches are not supported by the first durable turn slice"
        )

    scene = state.scene
    if story.scene_id is not None:
        scene = scene.model_copy(update={"id": story.scene_id})

    world_time = state.world_time
    if story.world_time_delta_minutes is not None:
        if world_time is None:
            raise StoryStateTransitionError("world time delta requires current world time")
        try:
            current = datetime.fromisoformat(world_time)
        except ValueError as exc:
            raise StoryStateTransitionError("story world time is not ISO-8601") from exc
        world_time = (current + timedelta(minutes=float(story.world_time_delta_minutes))).isoformat()

    return state.model_copy(
        update={
            "revision": state.revision + 1,
            "turn": state.turn + 1,
            "scene": scene,
            "world_time": world_time,
            "discovered_clue_ids": clues,
            "secret_states": secrets,
            "pressure": pressure,
            "last_state_delta_id": delta.id,
        }
    )
