"""W-V09 cancel-vs-COMMIT arbitration contract tests (proposal boundary)."""
from __future__ import annotations

import pytest

from application.turn_control import (
    TurnCancellationOutcome,
    TurnCancellationResult,
    TurnControlError,
    TurnControlService,
)
from application.turn_input import (
    ControlIntent,
    ControlIntentKind,
    InputCommandRouter,
    RoutedControlIntent,
)

TURN_ID = "turn.001"


def _result(
    outcome: TurnCancellationOutcome,
    *,
    turn_id: str = TURN_ID,
    input_turn_id: str | None = "input.turn.001",
    session_id: str | None = "session.001",
    committed_world_revision: int | None = None,
    replayed: bool = False,
) -> TurnCancellationResult:
    return TurnCancellationResult(
        outcome=outcome,
        turn_id=turn_id,
        input_turn_id=input_turn_id,
        session_id=session_id,
        committed_world_revision=committed_world_revision,
        replayed=replayed,
    )


class _RecordingTurns:
    def __init__(self, result: TurnCancellationResult) -> None:
        self.result = result
        self.calls: list[tuple[str, int, str, str]] = []

    async def cancel_pending(
        self,
        turn_id: str,
        *,
        expected_revision: int,
        request_id: str,
        trace_id: str,
    ) -> TurnCancellationResult:
        self.calls.append((turn_id, expected_revision, request_id, trace_id))
        return self.result


class _RecordingControls:
    def __init__(self) -> None:
        self.intents: list[ControlIntent] = []

    async def execute(self, intent: ControlIntent) -> None:
        self.intents.append(intent)


class _UnreachableStory:
    async def receive(self, value):  # pragma: no cover - must never run
        raise AssertionError("presentation control reached the story intake")


async def _cancel(turns, *, expected_revision: int = 103):
    return await TurnControlService(turns=turns).cancel_pending(
        TURN_ID,
        expected_revision=expected_revision,
        request_id="request.001",
        trace_id="trace.001",
    )


@pytest.mark.asyncio
async def test_cancel_wins_before_commit_releases_pending_work_without_world_revision():
    turns = _RecordingTurns(_result(TurnCancellationOutcome.CANCELLED_BEFORE_COMMIT))

    result = await _cancel(turns)

    assert result.outcome is TurnCancellationOutcome.CANCELLED_BEFORE_COMMIT
    assert result.committed_world_revision is None
    assert result.replayed is False
    assert turns.calls == [(TURN_ID, 103, "request.001", "trace.001")]


@pytest.mark.asyncio
async def test_commit_wins_over_cancel_and_reports_committed_proposal_revision():
    """COMMIT 先赢是正常竞态结果：返回已提交修订号，而不是异常。"""
    turns = _RecordingTurns(
        _result(
            TurnCancellationOutcome.ALREADY_COMMITTED,
            committed_world_revision=104,
        )
    )

    result = await _cancel(turns)

    assert result.outcome is TurnCancellationOutcome.ALREADY_COMMITTED
    assert result.committed_world_revision == 104
    assert result.input_turn_id == "input.turn.001"
    assert result.session_id == "session.001"


@pytest.mark.asyncio
async def test_repeated_cancel_is_idempotent_and_never_releases_twice():
    turns = _RecordingTurns(
        _result(TurnCancellationOutcome.CANCELLED_BEFORE_COMMIT, replayed=True)
    )

    result = await _cancel(turns)

    assert result.outcome is TurnCancellationOutcome.CANCELLED_BEFORE_COMMIT
    assert result.replayed is True
    assert result.committed_world_revision is None


@pytest.mark.asyncio
async def test_unknown_turn_reports_not_found_and_stays_inert():
    turns = _RecordingTurns(
        _result(
            TurnCancellationOutcome.NOT_FOUND,
            input_turn_id=None,
            session_id=None,
        )
    )

    result = await _cancel(turns)

    assert result.outcome is TurnCancellationOutcome.NOT_FOUND
    assert result.input_turn_id is None
    assert result.committed_world_revision is None


@pytest.mark.asyncio
async def test_stale_expected_revision_refuses_to_cancel_an_unseen_turn():
    turns = _RecordingTurns(_result(TurnCancellationOutcome.STALE_REVISION))

    result = await _cancel(turns, expected_revision=7)

    assert result.outcome is TurnCancellationOutcome.STALE_REVISION
    assert result.committed_world_revision is None
    assert turns.calls[0][1] == 7


@pytest.mark.asyncio
async def test_committed_outcome_without_store_revision_fails_closed():
    turns = _RecordingTurns(_result(TurnCancellationOutcome.ALREADY_COMMITTED))

    with pytest.raises(TurnControlError, match="committed_outcome_missing_store_revision"):
        await _cancel(turns)


@pytest.mark.asyncio
async def test_cancellation_reporting_a_world_revision_fails_closed():
    turns = _RecordingTurns(
        _result(
            TurnCancellationOutcome.CANCELLED_BEFORE_COMMIT,
            committed_world_revision=3,
        )
    )

    with pytest.raises(TurnControlError, match="cancellation_reports_world_revision"):
        await _cancel(turns)


@pytest.mark.asyncio
async def test_foreign_turn_identity_fails_closed():
    turns = _RecordingTurns(
        _result(
            TurnCancellationOutcome.CANCELLED_BEFORE_COMMIT,
            turn_id="turn.other",
        )
    )

    with pytest.raises(TurnControlError, match="turn_cancellation_identity_mismatch"):
        await _cancel(turns)


@pytest.mark.asyncio
async def test_not_found_claiming_turn_identity_fails_closed():
    turns = _RecordingTurns(_result(TurnCancellationOutcome.NOT_FOUND))

    with pytest.raises(TurnControlError, match="not_found_reports_turn_identity"):
        await _cancel(turns)


@pytest.mark.asyncio
@pytest.mark.parametrize("expected_revision", [-1, True, 1.5, "103"])
async def test_invalid_expected_revision_never_reaches_the_port(expected_revision):
    turns = _RecordingTurns(_result(TurnCancellationOutcome.CANCELLED_BEFORE_COMMIT))

    with pytest.raises(TurnControlError, match="invalid_expected_revision"):
        await TurnControlService(turns=turns).cancel_pending(
            TURN_ID,
            expected_revision=expected_revision,
            request_id="request.001",
            trace_id="trace.001",
        )
    assert turns.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [ControlIntentKind.STOP, ControlIntentKind.CONTINUE],
)
async def test_media_control_never_reaches_the_pending_proposal_cancel_port(kind):
    """纯媒体控制不是取消授权：不得触碰 pending turn 提案端口。"""
    turns = _RecordingTurns(_result(TurnCancellationOutcome.CANCELLED_BEFORE_COMMIT))
    controls = _RecordingControls()
    router = InputCommandRouter(story=_UnreachableStory(), controls=controls)

    routed = await router.route(ControlIntent(kind))

    assert isinstance(routed, RoutedControlIntent)
    assert [intent.kind for intent in controls.intents] == [kind]
    assert turns.calls == []


@pytest.mark.asyncio
async def test_volume_control_never_reaches_the_pending_proposal_cancel_port():
    turns = _RecordingTurns(_result(TurnCancellationOutcome.CANCELLED_BEFORE_COMMIT))
    controls = _RecordingControls()
    router = InputCommandRouter(story=_UnreachableStory(), controls=controls)

    routed = await router.route(ControlIntent(ControlIntentKind.SET_VOLUME, volume=0.2))

    assert isinstance(routed, RoutedControlIntent)
    assert controls.intents[0].volume == 0.2
    assert turns.calls == []
