"""Application boundary for committing one validated Story turn.

The service coordinates typed Domain state and a persistence port. It does not
import SQLite or concrete infrastructure. Narrative/BeatPlan/TTS remain strictly
post-COMMIT.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from contracts import (
    StateDelta,
    StorySession,
    StorySessionStatus,
    TurnStatus,
    TurnTransaction,
)
from domain.story_state_reducer import apply_story_delta


class StoryTurnValidationError(ValueError):
    """The candidate turn cannot cross the durable Session fact boundary."""


@dataclass(frozen=True, slots=True)
class StoryTurnCommitResult:
    store_revision: int
    session: StorySession
    turn: TurnTransaction
    delta: StateDelta
    replayed: bool


class StoryCommitPort(Protocol):
    async def commit_turn(
        self,
        session: StorySession,
        delta: StateDelta,
        turn: TurnTransaction,
        *,
        store_expected_revision: int,
        request_id: str,
        trace_id: str,
    ) -> StoryTurnCommitResult: ...


class StoryTurnCommitService:
    def __init__(self, port: StoryCommitPort):
        self._port = port

    @staticmethod
    def _validate(
        session: StorySession,
        delta: StateDelta,
        turn: TurnTransaction,
    ) -> None:
        if session.status != StorySessionStatus.ACTIVE:
            raise StoryTurnValidationError("only an active StorySession may commit a turn")
        if session.story_state.story_session_id != session.id:
            raise StoryTurnValidationError("StoryState belongs to another session")
        if turn.session_id != session.id or delta.turn_id != turn.id:
            raise StoryTurnValidationError("turn/session/delta identity mismatch")
        if turn.status != TurnStatus.VALIDATED:
            raise StoryTurnValidationError("turn must be validated before COMMIT")
        if turn.state_delta_id not in (None, delta.id):
            raise StoryTurnValidationError("TurnTransaction references another StateDelta")
        if (
            turn.base_revisions.world != session.base_revisions.world
            or turn.base_revisions.character != session.base_revisions.character
            or turn.base_revisions.story != session.story_state.revision
        ):
            raise StoryTurnValidationError("turn base revisions are stale")

        # The first durable vertical slice persists StoryState only. Refuse richer
        # overlays rather than silently dropping committed facts.
        if (
            delta.character_deltas
            or delta.relationship_deltas
            or delta.knowledge_candidates
            or delta.world_event_candidates
        ):
            raise StoryTurnValidationError(
                "this durable slice does not yet persist non-story session overlays"
            )

    async def commit_validated(
        self,
        session: StorySession,
        delta: StateDelta,
        turn: TurnTransaction,
        *,
        store_expected_revision: int,
        request_id: str,
        trace_id: str,
    ) -> StoryTurnCommitResult:
        self._validate(session, delta, turn)
        next_state = apply_story_delta(session.story_state, delta)
        committed_session = session.model_copy(update={"story_state": next_state})
        committed_turn = turn.model_copy(
            update={
                "status": TurnStatus.COMMITTED,
                "state_delta_id": delta.id,
                "committed_story_revision": next_state.revision,
            }
        )
        return await self._port.commit_turn(
            committed_session,
            delta,
            committed_turn,
            store_expected_revision=store_expected_revision,
            request_id=request_id,
            trace_id=trace_id,
        )
