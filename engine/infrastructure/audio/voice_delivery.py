"""Post-COMMIT expression delivery: narrative publication and voice hand-off.

This module is the only place that turns a *committed* Domain outcome into
audible output.  It runs strictly after ``COMMIT`` (invariant 9): the order is

    COMMIT -> narrate -> publish NarrativeBlock -> seal SpeechUnit -> VoiceRenderRuntime

Nothing here can propose or change Domain state.  A failure at any stage leaves
the committed turn untouched and surfaces a code; it never rewrites history and
never falls back to canned prose.

The pipeline deliberately reuses the existing W-V05 sealing boundary rather than
re-deriving disclosure: ``SpeechUnitSealingService`` re-reads the durable
narrative through ``AudioDisclosureAuthorizer`` so the text that reaches the
provider is the text that was authorized.
"""
from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from application.speech_unit import (
    SealedSpeechUnit,
    SpeechUnitSealingError,
    SpeechUnitSealingService,
)
from contracts import NarrativeBlock, NarrativeSegment, TurnTransaction
from domain.voice_identity import VoiceBindingScope

from .voice_runtime import VoiceRenderRuntime, VoiceRenderRuntimeError

_NarrateFn = Callable[[str], Awaitable[str]]


class TurnDeliveryError(RuntimeError):
    """A committed turn could not be turned into published, sealed audio."""

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
    replayed: bool


@dataclass(frozen=True, slots=True)
class TurnDeliveryOutcome:
    """The committed facts a narrator is allowed to describe."""

    turn_id: str
    session_id: str
    story_revision: int
    state_delta_id: str
    scene_id: str | None
    protagonist_id: str
    player_action: str
    character_reply: str
    outcome_summary: str


class TurnDeliveryPipeline:
    """Narrate, publish, seal and hand one committed turn to the render runtime."""

    def __init__(
        self,
        *,
        narratives: object,
        sealing: SpeechUnitSealingService,
        voice: VoiceRenderRuntime,
        binding_scope: VoiceBindingScope,
        expected_binding_revision: int,
        execution_model_id: str,
        dictionary_revision: str,
        seal_arguments: dict[str, object],
        narrate: _NarrateFn | None = None,
    ) -> None:
        self._narratives = narratives
        self._sealing = sealing
        self._voice = voice
        self._binding_scope = binding_scope
        self._expected_binding_revision = expected_binding_revision
        self._execution_model_id = execution_model_id
        self._dictionary_revision = dictionary_revision
        self._seal_arguments = dict(seal_arguments)
        self._narrate = narrate

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

    async def deliver(self, outcome: TurnDeliveryOutcome) -> DeliveryReceipt:
        """Run the whole post-COMMIT chain for one committed turn."""
        if not isinstance(outcome, TurnDeliveryOutcome):
            raise TurnDeliveryError("invalid_delivery_outcome")

        if self._narrate is None:
            raise TurnDeliveryError("narrator_unavailable")

        try:
            text = await self._narrate(outcome.outcome_summary)
        except Exception:
            # Model, transport and timeout failures all collapse into one public
            # code; the committed turn is already durable and stays untouched.
            raise TurnDeliveryError("narrative_model_unavailable") from None
        if not isinstance(text, str) or not text.strip():
            raise TurnDeliveryError("narrative_model_invalid")

        block = NarrativeBlock(
            schema_version="1.0",
            id=_narrative_block_id(outcome.turn_id),
            story_session_id=outcome.session_id,
            source_story_revision=outcome.story_revision,
            scene_id=outcome.scene_id,
            segments=[
                NarrativeSegment(
                    type="character",
                    speaker_id=self._binding_scope.presentation_identity,
                    text=text.strip(),
                    speech_intent=outcome.character_reply or None,
                )
            ],
            source_state_delta_id=outcome.state_delta_id,
        )
        try:
            published = await self._narratives.publish(  # type: ignore[attr-defined]
                turn_id=outcome.turn_id, narrative=block
            )
        except Exception:
            raise TurnDeliveryError("narrative_publication_failed") from None

        turn: TurnTransaction = published.turn
        try:
            unit = await self._sealing.seal(
                turn_id=turn.id,
                expected_story_revision=outcome.story_revision,
                segment_index=0,
                binding_scope=self._binding_scope,
                expected_binding_revision=self._expected_binding_revision,
                execution_model_id=self._execution_model_id,
                dictionary_revision=self._dictionary_revision,
                **self._seal_arguments,  # type: ignore[arg-type]
            )
        except SpeechUnitSealingError as exc:
            raise TurnDeliveryError(exc.code) from None
        except Exception:
            raise TurnDeliveryError("speech_sealing_failed") from None

        try:
            self._voice.publish(unit)
        except VoiceRenderRuntimeError as exc:
            raise TurnDeliveryError(exc.code) from None
        return DeliveryReceipt(
            turn_id=turn.id,
            narrative_block_id=published.narrative.id,
            speech_unit_id=unit.unit_id,
            spoken_text=unit.spoken_text,
            render_recipe=unit.render_recipe(),
            replayed=bool(published.replayed),
        )


def _narrative_block_id(turn_id: str) -> str:
    return "nb_" + hashlib.sha256(f"wom-narrative/v1\0{turn_id}".encode()).hexdigest()[:32]


__all__ = [
    "DeliveryReceipt",
    "SealedSpeechUnit",
    "TurnDeliveryError",
    "TurnDeliveryOutcome",
    "TurnDeliveryPipeline",
]
