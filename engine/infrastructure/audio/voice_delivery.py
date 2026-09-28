"""Post-COMMIT expression delivery: persisted character-segment voice hand-off.

This module turns one already-persisted character segment into audible output.
It runs strictly after ``COMMIT`` (invariant 9):

    COMMIT -> publish NarrativeBlock -> seal character SpeechUnit -> VoiceRenderRuntime

Nothing here can propose or change Domain state.  A failure at any stage leaves
the committed turn and NarrativeBlock untouched and surfaces a code. It never
generates, republishes, or rewrites narrative text.

The pipeline deliberately reuses the existing W-V05 sealing boundary rather than
re-deriving disclosure: ``SpeechUnitSealingService`` re-reads the durable
narrative through ``AudioDisclosureAuthorizer`` so the text that reaches the
provider is the text that was authorized.
"""
from __future__ import annotations

from dataclasses import dataclass

from application.speech_unit import (
    SealedSpeechUnit,
    SpeechUnitSealingError,
    SpeechUnitSealingService,
)
from contracts import NarrativeBlock
from domain.voice_identity import VoiceBindingScope

from .voice_runtime import VoiceRenderRuntime, VoiceRenderRuntimeError


class TurnDeliveryError(RuntimeError):
    """A persisted character segment could not be sealed or rendered."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    """What the caller may present after a successful delivery."""

    turn_id: str
    narrative_block_id: str
    speech_unit_id: str
    spoken_text: str
    # The exact recipe ``voice.render`` must echo; the media identity is the only
    # part the App supplies itself, and only after ``media.open`` mints it.
    render_recipe: dict[str, object]


@dataclass(frozen=True, slots=True)
class TurnDeliveryOutcome:
    """One persisted narrative segment selected for possible audio delivery."""

    turn_id: str
    session_id: str
    story_revision: int
    state_delta_id: str
    narrative: NarrativeBlock
    segment_index: int


class TurnDeliveryPipeline:
    """Seal and hand one persisted character segment to the render runtime."""

    def __init__(
        self,
        *,
        sealing: SpeechUnitSealingService,
        voice: VoiceRenderRuntime,
        binding_scope: VoiceBindingScope,
        expected_binding_revision: int,
        execution_model_id: str,
        dictionary_revision: str,
        seal_arguments: dict[str, object],
    ) -> None:
        self._sealing = sealing
        self._voice = voice
        self._binding_scope = binding_scope
        self._expected_binding_revision = expected_binding_revision
        self._execution_model_id = execution_model_id
        self._dictionary_revision = dictionary_revision
        self._seal_arguments = dict(seal_arguments)

    @property
    def binding_scope(self) -> VoiceBindingScope:
        return self._binding_scope

    def bind(self, scope: VoiceBindingScope, expected_binding_revision: int) -> None:
        """Attach the delivery pipeline to the scope proven for this session."""
        if not isinstance(scope, VoiceBindingScope):
            raise TurnDeliveryError("voice_binding_scope_invalid")
        if type(expected_binding_revision) is not int or expected_binding_revision < 1:
            raise TurnDeliveryError("voice_binding_revision_invalid")
        self._binding_scope = scope
        self._expected_binding_revision = expected_binding_revision

    async def deliver(
        self, outcome: TurnDeliveryOutcome
    ) -> DeliveryReceipt | None:
        """Render only the requested character segment.

        Narration and transition segments are text-only. Returning ``None`` for
        them keeps historical narration-only NarrativeBlocks safe to replay and
        prevents them from being sealed with a character voice.
        """
        if not isinstance(outcome, TurnDeliveryOutcome):
            raise TurnDeliveryError("invalid_delivery_outcome")
        block = outcome.narrative
        if not isinstance(block, NarrativeBlock):
            raise TurnDeliveryError("invalid_persisted_narrative")
        if (
            block.story_session_id != outcome.session_id
            or block.source_story_revision != outcome.story_revision
            or block.source_state_delta_id != outcome.state_delta_id
        ):
            raise TurnDeliveryError("persisted_narrative_binding_mismatch")
        if type(outcome.segment_index) is not int or outcome.segment_index < 0:
            raise TurnDeliveryError("invalid_segment_index")
        if outcome.segment_index >= len(block.segments):
            raise TurnDeliveryError("narrative_segment_out_of_bounds")
        segment = block.segments[outcome.segment_index]
        if segment.type != "character":
            return None

        try:
            unit = await self._sealing.seal(
                turn_id=outcome.turn_id,
                expected_story_revision=outcome.story_revision,
                segment_index=outcome.segment_index,
                binding_scope=self._binding_scope,
                expected_binding_revision=self._expected_binding_revision,
                execution_model_id=self._execution_model_id,
                dictionary_revision=self._dictionary_revision,
                **self._seal_arguments,  # type: ignore[arg-type]
            )
        except SpeechUnitSealingError as exc:
            raise TurnDeliveryError(exc.code) from None
        except Exception:  # noqa: BLE001 - never let post-COMMIT audio unwind the turn
            raise TurnDeliveryError("speech_sealing_failed") from None
        if unit.narrative_block_id != block.id:
            raise TurnDeliveryError("speech_unit_narrative_mismatch")

        try:
            self._voice.publish(unit)
        except VoiceRenderRuntimeError as exc:
            raise TurnDeliveryError(exc.code) from None
        return DeliveryReceipt(
            turn_id=outcome.turn_id,
            narrative_block_id=block.id,
            speech_unit_id=unit.unit_id,
            spoken_text=unit.spoken_text,
            render_recipe=unit.render_recipe(),
        )


__all__ = [
    "DeliveryReceipt",
    "SealedSpeechUnit",
    "TurnDeliveryError",
    "TurnDeliveryOutcome",
    "TurnDeliveryPipeline",
]
