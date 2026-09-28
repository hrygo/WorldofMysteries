"""Read-only player projection of an already-persisted narrative."""
from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts import NarrativeBlock, TurnTransaction

from .audio_disclosure import AudioDisclosureAuthorizer, AudioDisclosureError


def _public_text(value: object, *, field: str, limit: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or "\x00" in value
        or len(value) > limit
    ):
        raise StoryExpressionError(f"invalid_{field}")
    return value.strip()


class StoryExpressionError(RuntimeError):
    """A persisted narrative cannot be projected safely for the player."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class StoryExpressionSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["narration", "character"]
    speaker_display_name: str | None = Field(
        default=None, min_length=1, max_length=256
    )
    text: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def narration_has_no_speaker(self) -> StoryExpressionSegment:
        if self.type == "narration" and self.speaker_display_name is not None:
            raise ValueError("narration_cannot_have_speaker")
        if not self.text.strip() or "\x00" in self.text:
            raise ValueError("invalid_segment_text")
        if (
            self.speaker_display_name is not None
            and (
                not self.speaker_display_name.strip()
                or "\x00" in self.speaker_display_name
            )
        ):
            raise ValueError("invalid_speaker_display_name")
        return self


class StoryExpressionResponse(BaseModel):
    """Strict application DTO matching ``expression_get_response``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    session_id: str = Field(min_length=1, max_length=256)
    turn_id: str = Field(min_length=1, max_length=256)
    narrative_state: Literal["pending", "ready", "unavailable"]
    segments: list[StoryExpressionSegment] = Field(max_length=256)
    reason: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def state_matches_projection(self) -> StoryExpressionResponse:
        if self.narrative_state == "ready":
            if not self.segments or self.reason is not None:
                raise ValueError("invalid_ready_expression_projection")
        elif self.narrative_state == "pending":
            if self.segments or self.reason is not None:
                raise ValueError("invalid_pending_expression_projection")
        elif not self.reason or self.segments:
            raise ValueError("invalid_unavailable_expression_projection")
        if (
            not self.session_id.strip()
            or "\x00" in self.session_id
            or not self.turn_id.strip()
            or "\x00" in self.turn_id
            or (self.reason is not None and "\x00" in self.reason)
        ):
            raise ValueError("invalid_expression_identity")
        return self


class StoryExpressionReadPort(Protocol):
    async def load_turn(self, turn_id: str) -> TurnTransaction: ...

    async def load_narrative_block(
        self, narrative_block_id: str
    ) -> NarrativeBlock: ...


class NarrativePublicIdentityReadPort(Protocol):
    """Resolve a speaker only to a name already approved for player display.

    Returning ``None`` omits the name. Implementations must never return an
    internal ID or a hidden identity as a fallback.
    """

    async def display_name(
        self, *, session_id: str, speaker_id: str
    ) -> str | None: ...


class StoryExpressionQueryService:
    """Project durable, authorized narrative text without creating side effects.

    The service only reads a committed turn and calls the existing disclosure
    authorizer for each segment. It never compiles text, seals speech, or calls a
    model/audio provider. Without a persisted block, state remains ``pending``
    unless the caller supplies an explicit stable current capability reason.
    """

    def __init__(
        self,
        *,
        reads: StoryExpressionReadPort,
        disclosure: AudioDisclosureAuthorizer,
        identities: NarrativePublicIdentityReadPort,
        capability_unavailable_reason: str | None = None,
    ) -> None:
        self._reads = reads
        self._disclosure = disclosure
        self._identities = identities
        if capability_unavailable_reason is not None:
            code = _public_text(
                capability_unavailable_reason,
                field="capability_reason",
                limit=128,
            )
            if not code.isascii() or not all(
                char.islower() or char.isdigit() or char == "_"
                for char in code
            ):
                raise StoryExpressionError("invalid_capability_reason")
            self._capability_unavailable_reason = code
        else:
            self._capability_unavailable_reason = None

    async def get(
        self, *, session_id: str, turn_id: str
    ) -> StoryExpressionResponse:
        session = _public_text(session_id, field="session_id", limit=256)
        requested_turn = _public_text(turn_id, field="turn_id", limit=256)
        turn = await self._reads.load_turn(requested_turn)
        if not isinstance(turn, TurnTransaction) or turn.id != requested_turn:
            raise StoryExpressionError("turn_identity_mismatch")
        if turn.session_id != session:
            raise StoryExpressionError("turn_session_mismatch")

        if turn.narrative_block_id is None:
            if self._capability_unavailable_reason is not None:
                return StoryExpressionResponse(
                    session_id=session,
                    turn_id=requested_turn,
                    narrative_state="unavailable",
                    reason=self._capability_unavailable_reason,
                    segments=[],
                )
            return StoryExpressionResponse(
                session_id=session,
                turn_id=requested_turn,
                narrative_state="pending",
                segments=[],
            )

        if turn.committed_story_revision is None:
            raise StoryExpressionError("turn_has_no_committed_story_revision")
        block = await self._reads.load_narrative_block(turn.narrative_block_id)
        if not isinstance(block, NarrativeBlock):
            raise StoryExpressionError("invalid_persisted_narrative")
        if (
            block.id != turn.narrative_block_id
            or block.story_session_id != session
            or block.source_story_revision != turn.committed_story_revision
            or block.source_state_delta_id != turn.state_delta_id
        ):
            raise StoryExpressionError("persisted_narrative_binding_mismatch")
        if not block.segments:
            raise StoryExpressionError("persisted_narrative_has_no_segments")
        if len(block.segments) > 256:
            raise StoryExpressionError("narrative_segment_limit_exceeded")

        projected: list[StoryExpressionSegment] = []
        try:
            for segment_index in range(len(block.segments)):
                authorized = await self._disclosure.authorize(
                    turn_id=requested_turn,
                    expected_story_revision=turn.committed_story_revision,
                    segment_index=segment_index,
                )
                if authorized.segment_type == "narration":
                    if authorized.speaker_id is not None:
                        raise StoryExpressionError(
                            "narration_segment_has_speaker"
                        )
                    projected.append(
                        StoryExpressionSegment(
                            type="narration",
                            text=authorized.display_text,
                        )
                    )
                elif authorized.segment_type == "character":
                    display_name = None
                    if authorized.speaker_id is not None:
                        display_name = await self._identities.display_name(
                            session_id=session,
                            speaker_id=authorized.speaker_id,
                        )
                    if display_name is not None:
                        display_name = _public_text(
                            display_name,
                            field="speaker_display_name",
                            limit=256,
                        )
                    projected.append(
                        StoryExpressionSegment(
                            type="character",
                            speaker_display_name=display_name,
                            text=authorized.display_text,
                        )
                    )
                else:
                    raise StoryExpressionError(
                        "unsupported_persisted_narrative_segment"
                    )
        except AudioDisclosureError as exc:
            raise StoryExpressionError(exc.code) from None

        if not projected:
            raise StoryExpressionError("narrative_projection_is_empty")
        return StoryExpressionResponse(
            session_id=session,
            turn_id=requested_turn,
            narrative_state="ready",
            segments=projected,
        )


__all__ = [
    "NarrativePublicIdentityReadPort",
    "StoryExpressionError",
    "StoryExpressionQueryService",
    "StoryExpressionReadPort",
    "StoryExpressionResponse",
    "StoryExpressionSegment",
]
