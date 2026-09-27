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
from domain.domain_candidate_validator import validate_state_delta_overlays
from domain.story_state_reducer import apply_story_delta


class StoryTurnValidationError(ValueError):
    """The candidate turn cannot cross the durable Session fact boundary."""


@dataclass(frozen=True, slots=True)
class DomainValidationContext:
    """Authorized facts a single turn may use for cross-domain candidates."""

    known_character_ids: tuple[str, ...]
    authorized_evidence_ids: frozenset[str]
    hidden_fact_literals: tuple[str, ...] = ()

    def with_runtime_identities(self, *identities: str) -> DomainValidationContext:
        return DomainValidationContext(
            known_character_ids=self.known_character_ids,
            authorized_evidence_ids=self.authorized_evidence_ids
            | frozenset(identities),
            hidden_fact_literals=self.hidden_fact_literals,
        )


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
    def __init__(
        self,
        port: StoryCommitPort,
        *,
        domain_context: DomainValidationContext | None = None,
    ):
        self._port = port
        self._domain_context = domain_context

    def _validate(
        self,
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

        if (
            delta.character_deltas
            or delta.relationship_deltas
            or delta.knowledge_candidates
            or delta.world_event_candidates
        ):
            if self._domain_context is None:
                raise StoryTurnValidationError(
                    "cross-domain overlays require an authorized validation context"
                )
            context = self._domain_context
            validate_state_delta_overlays(
                delta,
                known_character_ids=context.known_character_ids,
                authorized_evidence_ids=context.authorized_evidence_ids,
                hidden_fact_literals=context.hidden_fact_literals,
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
