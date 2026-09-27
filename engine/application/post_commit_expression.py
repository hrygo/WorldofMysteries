"""Post-COMMIT BeatPlan and NarrativeBlock publication use case."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from contracts import BeatPlan, NarrativeBlock, TurnStatus


class ExpressionError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class BeatPlanPort(Protocol):
    async def publish(self, beat_plan: BeatPlan) -> None: ...


class NarrativePort(Protocol):
    async def publish(self, *, turn_id: str, narrative: NarrativeBlock): ...


@dataclass(frozen=True, slots=True)
class CommittedExpressionInput:
    session_id: str
    turn_id: str
    story_revision: int
    state_delta_id: str
    turn_status: TurnStatus


@dataclass(frozen=True, slots=True)
class PostCommitExpressionResult:
    beat_plan: BeatPlan
    narrative: NarrativeBlock
    replayed: bool


class PostCommitExpressionService:
    """Publish frozen expression only after authoritative Story COMMIT."""

    def __init__(
        self,
        *,
        templates,
        beats: BeatPlanPort | None,
        narratives: NarrativePort,
    ) -> None:
        self._templates = templates
        self._beats = beats
        self._narratives = narratives

    async def publish(
        self,
        *,
        turn_number: int,
        commit: CommittedExpressionInput,
    ) -> PostCommitExpressionResult:
        try:
            template = self._templates[turn_number]
        except (KeyError, TypeError):
            raise ExpressionError("unsupported_expression_turn") from None
        if commit.turn_status is not TurnStatus.COMMITTED:
            raise ExpressionError("expression_requires_committed_turn")
        if commit.story_revision != turn_number:
            raise ExpressionError("expression_story_revision_mismatch")
        if not commit.state_delta_id:
            raise ExpressionError("expression_missing_state_delta")

        beat = BeatPlan.model_validate(
            {
                **template.beat_plan.model_dump(
                    mode="json", exclude_none=True
                ),
                "story_session_id": commit.session_id,
                "source_story_revision": commit.story_revision,
            }
        )
        narrative = NarrativeBlock.model_validate(
            {
                **template.narrative_block.model_dump(
                    mode="json", exclude_none=True
                ),
                "story_session_id": commit.session_id,
                "source_story_revision": commit.story_revision,
                "source_state_delta_id": commit.state_delta_id,
            }
        )
        if self._beats is not None:
            await self._beats.publish(beat)
        published = await self._narratives.publish(
            turn_id=commit.turn_id,
            narrative=narrative,
        )
        result_turn = getattr(published, "turn", None)
        if result_turn is not None and result_turn.status not in {
            TurnStatus.NARRATIVE_READY,
            TurnStatus.AUDIO_READY,
            TurnStatus.DELIVERED,
        }:
            raise ExpressionError("narrative_publish_did_not_advance_turn")
        return PostCommitExpressionResult(
            beat_plan=beat,
            narrative=getattr(published, "narrative", narrative),
            replayed=bool(getattr(published, "replayed", False)),
        )
