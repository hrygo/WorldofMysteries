"""W-V09 pending-turn control arbitration (voice-first design §5.3).

A pure MediaStop / Pause / Replay / Volume never reaches this module: those are
local presentation controls handled by ``turn_input.InputCommandRouter``.
Only an explicit user cancellation of a pending turn -- or a replacement
decision confirmed by the final interpretation -- may arbitrate against a
concurrent COMMIT.

Cancel and COMMIT are serialized by the one Domain writer. The winning order is
reported as a typed outcome instead of an exception, because "COMMIT wins" is a
normal, non-recoverable race result: the caller stops expression and a new
advice creates a new turn. An exception would invite the caller to retry, and a
retry must never re-open or re-commit an already committed turn.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class TurnControlError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TurnCancellationOutcome(StrEnum):
    """Closed arbitration vocabulary shared by Application and storage."""

    CANCELLED_BEFORE_COMMIT = "cancelled_before_commit"
    ALREADY_COMMITTED = "already_committed"
    STALE_REVISION = "stale_revision"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class TurnCancellationResult:
    outcome: TurnCancellationOutcome
    turn_id: str
    input_turn_id: str | None
    session_id: str | None
    committed_world_revision: int | None
    replayed: bool = False


class PendingTurnControlPort(Protocol):
    async def cancel_pending(
        self,
        turn_id: str,
        *,
        expected_revision: int,
        request_id: str,
        trace_id: str,
    ) -> TurnCancellationResult:
        """Arbitrate cancel vs COMMIT atomically under the single Domain writer.

        ``expected_revision`` is the world revision the caller observed when it
        decided to cancel. A pending turn received against another revision is
        refused (``stale_revision``) instead of being cancelled, so a late or
        misrouted cancellation cannot discard a turn the caller never saw.
        """
        ...


def _text(value: str, field: str, *, limit: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or "\x00" in value
    ):
        raise TurnControlError(f"invalid_{field}")
    return value.strip()


def _natural(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TurnControlError(f"invalid_{field}")
    return value


class TurnControlService:
    """Fail-closed boundary around one pending-turn cancellation."""

    def __init__(self, *, turns: PendingTurnControlPort) -> None:
        self._turns = turns

    async def cancel_pending(
        self,
        turn_id: str,
        *,
        expected_revision: int,
        request_id: str,
        trace_id: str,
    ) -> TurnCancellationResult:
        _text(turn_id, "turn_id")
        _natural(expected_revision, "expected_revision")
        _text(request_id, "request_id")
        _text(trace_id, "trace_id")

        result = await self._turns.cancel_pending(
            turn_id,
            expected_revision=expected_revision,
            request_id=request_id,
            trace_id=trace_id,
        )
        self._require_consistent(turn_id, result)
        return result

    @staticmethod
    def _require_consistent(
        turn_id: str,
        result: TurnCancellationResult,
    ) -> None:
        """Refuse a port answer that contradicts the arbitration contract.

        The cancellation path must never manufacture or report a world result.
        Only the COMMIT-wins branch may carry a committed revision, and it must
        carry one: an "already committed" answer without a revision cannot be
        recovered from by the caller.
        """
        if not isinstance(result, TurnCancellationResult):
            raise TurnControlError("invalid_turn_cancellation_result")
        if result.turn_id != turn_id:
            raise TurnControlError("turn_cancellation_identity_mismatch")
        outcome = result.outcome
        if not isinstance(outcome, TurnCancellationOutcome):
            raise TurnControlError("invalid_turn_cancellation_outcome")
        revision = result.committed_world_revision
        if revision is not None:
            _natural(revision, "committed_world_revision")
        if outcome is TurnCancellationOutcome.ALREADY_COMMITTED:
            if revision is None:
                raise TurnControlError("committed_outcome_missing_store_revision")
            if result.input_turn_id is None or result.session_id is None:
                raise TurnControlError("committed_outcome_missing_turn_identity")
            return
        if revision is not None:
            raise TurnControlError("cancellation_reports_world_revision")
        if outcome is TurnCancellationOutcome.NOT_FOUND:
            if result.input_turn_id is not None or result.session_id is not None:
                raise TurnControlError("not_found_reports_turn_identity")
            return
        if result.input_turn_id is None or result.session_id is None:
            raise TurnControlError("cancellation_missing_turn_identity")
