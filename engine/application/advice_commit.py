"""W-V09 deterministic resolution and COMMIT orchestration.

This Application service is the narrow bridge between an already durable
PlayerAdvice/ActionIntent proposal and the existing StoryCommit transaction.
It owns no narrative output and runs strictly before COMMIT-time expression.
Lost-ACK retries recover the committed turn instead of invoking the model again.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

from contracts import (
    ActionIntent,
    PlayerAdvice,
    StateDelta,
    StorySession,
    StorySessionStatus,
    TurnStatus,
    TurnTransaction,
)
from domain.resolution_policy import ResolutionPolicy
from domain.resolver import OutcomeResolverProtocol

from .advice_action import (
    AdviceActionError,
    AdviceActionIntentService,
    DurableAdviceReadPort,
)
from .advice_interpretation import FrozenTurnInput
from .story_turn_commit import (
    StoryCommitPort,
    StoryTurnCommitResult,
    StoryTurnCommitService,
)
from .turn_input import TurnInputStatus


class AdviceCommitError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _text(value: str, field: str, *, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
        raise AdviceCommitError(f"invalid_{field}")
    return value.strip()


def _natural(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AdviceCommitError(f"invalid_{field}")
    return value


def _state_delta_id(turn_id: str) -> str:
    digest = hashlib.sha256(f"wom-state-delta/v1\0{turn_id}".encode()).hexdigest()
    return f"delta_{digest[:32]}"


class StoryTurnCommitPort(StoryCommitPort, Protocol):
    async def load_session(self, session_id: str) -> StorySession: ...

    async def load_turn(self, turn_id: str) -> TurnTransaction: ...

    async def load_delta(self, delta_id: str) -> StateDelta: ...


class AdviceCommitService:
    """Resolve one durable advice proposal and commit it through StoryCommit."""

    def __init__(
        self,
        *,
        durable: DurableAdviceReadPort,
        proposal: AdviceActionIntentService,
        story: StoryTurnCommitPort,
        resolver: OutcomeResolverProtocol,
    ) -> None:
        self._durable = durable
        self._proposal = proposal
        self._story = story
        self._resolver = resolver

    async def commit(
        self,
        input_turn_id: str,
        *,
        policy: ResolutionPolicy,
        store_expected_revision: int,
        request_id: str,
        trace_id: str,
    ) -> StoryTurnCommitResult:
        _text(input_turn_id, "input_turn_id")
        if not isinstance(policy, ResolutionPolicy):
            raise AdviceCommitError("invalid_resolution_policy")
        _natural(store_expected_revision, "store_expected_revision")
        _text(request_id, "request_id")
        _text(trace_id, "trace_id")

        frozen = await self._durable.load_input(input_turn_id)
        if frozen is None:
            raise AdviceCommitError("input_turn_not_found")
        if frozen.status is TurnInputStatus.COMMITTED:
            return await self._recover_committed(frozen)
        if frozen.status is TurnInputStatus.CANCELLED:
            raise AdviceCommitError("input_turn_cancelled")
        if frozen.status is not TurnInputStatus.RECEIVED:
            raise AdviceCommitError("input_turn_not_committable")

        try:
            proposal = await self._proposal.propose(input_turn_id)
        except AdviceActionError as exc:
            raise AdviceCommitError(exc.code) from None

        session = await self._story.load_session(frozen.session_id)
        self._validate_session(frozen, session)
        self._validate_action_intent(frozen, proposal.action_intent, proposal.advice)

        delta = self._resolver.resolve(
            proposal.action_intent,
            policy,
            delta_id=_state_delta_id(frozen.turn_id),
        )
        if not isinstance(delta, StateDelta) or delta.turn_id != frozen.turn_id:
            raise AdviceCommitError("resolver_identity_mismatch")

        turn = TurnTransaction.model_validate(
            {
                "schema_version": "1.0",
                "id": frozen.turn_id,
                "session_id": frozen.session_id,
                "idempotency_key": frozen.idempotency_key,
                "status": TurnStatus.VALIDATED.value,
                "base_revisions": frozen.base_revisions.model_dump(mode="json"),
                "player_advice_id": proposal.advice.id,
                "action_intent_id": proposal.action_intent.id,
                "state_delta_id": delta.id,
                "committed_story_revision": None,
                "narrative_block_id": None,
            }
        )
        return await StoryTurnCommitService(self._story).commit_validated(
            session,
            delta,
            turn,
            store_expected_revision=store_expected_revision,
            request_id=request_id,
            trace_id=trace_id,
        )

    async def _recover_committed(self, frozen: FrozenTurnInput) -> StoryTurnCommitResult:
        if frozen.committed_world_revision is None:
            raise AdviceCommitError("committed_turn_missing_store_revision")
        turn = await self._story.load_turn(frozen.turn_id)
        if (
            not isinstance(turn, TurnTransaction)
            or turn.session_id != frozen.session_id
            or turn.idempotency_key != frozen.idempotency_key
            or turn.status is not TurnStatus.COMMITTED
            or turn.base_revisions != frozen.base_revisions
            or turn.state_delta_id is None
            or turn.committed_story_revision is None
        ):
            raise AdviceCommitError("committed_turn_identity_mismatch")
        delta = await self._story.load_delta(turn.state_delta_id)
        if (
            not isinstance(delta, StateDelta)
            or delta.id != turn.state_delta_id
            or delta.turn_id != frozen.turn_id
        ):
            raise AdviceCommitError("committed_delta_identity_mismatch")
        session = await self._story.load_session(frozen.session_id)
        if not isinstance(session, StorySession) or session.id != frozen.session_id:
            raise AdviceCommitError("story_session_identity_mismatch")
        return StoryTurnCommitResult(
            store_revision=frozen.committed_world_revision,
            session=session,
            turn=turn,
            delta=delta,
            replayed=True,
        )

    @staticmethod
    def _validate_session(frozen: FrozenTurnInput, session: StorySession) -> None:
        if not isinstance(session, StorySession) or session.id != frozen.session_id:
            raise AdviceCommitError("story_session_identity_mismatch")
        if session.status is not StorySessionStatus.ACTIVE:
            raise AdviceCommitError("story_session_not_active")
        if (
            session.base_revisions.world != frozen.base_revisions.world
            or session.base_revisions.character != frozen.base_revisions.character
        ):
            raise AdviceCommitError("story_session_base_revision_mismatch")
        if session.story_state.revision != frozen.base_revisions.story:
            raise AdviceCommitError("input_turn_stale")

    @staticmethod
    def _validate_action_intent(
        frozen: FrozenTurnInput,
        action_intent: ActionIntent,
        advice: PlayerAdvice,
    ) -> None:
        if (
            not isinstance(action_intent, ActionIntent)
            or action_intent.turn_id != frozen.turn_id
            or not action_intent.id
            or not action_intent.character_id
            or advice.id not in action_intent.evidence_ids
        ):
            raise AdviceCommitError("action_intent_identity_mismatch")
