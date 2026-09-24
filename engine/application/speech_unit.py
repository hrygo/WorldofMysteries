"""W-V05 immutable SpeechUnit sealing.

This application boundary is the bridge between post-COMMIT narrative authorization
and W-V03 render execution. It freezes the exact narrative segment, active binding
revision, spoken-text mapping and effective performance before any provider call.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Protocol

from domain.voice_identity import (
    VoiceBinding,
    VoiceBindingScope,
    VoiceBindingStatus,
)

from .audio_disclosure import (
    AudioDisclosureAuthorizer,
    PronunciationRule,
    SemanticAnchor,
    SpokenSpanMapping,
    SpokenTextCompiler,
)
from .performance_compiler import (
    CompiledPerformance,
    DesiredPerformance,
    EffectiveBackendPerformance,
    EffectivePlaybackPerformance,
    PerformanceCompiler,
    VoicePerformanceCapabilities,
)


class SpeechUnitSealingError(RuntimeError):
    """A narrative segment cannot be frozen into an executable speech unit."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class VoiceBindingReadPort(Protocol):
    async def load_scope(self, scope: VoiceBindingScope) -> VoiceBinding | None: ...


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _desired_payload(desired: DesiredPerformance) -> dict[str, object]:
    return {
        "emotion": desired.emotion,
        "intensity": float(desired.intensity),
        "pace_modifier": float(desired.pace_modifier),
        "energy_modifier": float(desired.energy_modifier),
        "volume": desired.volume,
        "pause_before_ms": desired.pause_before_ms,
        "emphasis": [
            {"text": cue.text, "strength": cue.strength}
            for cue in desired.emphasis
        ],
        "native_speed": (
            None if desired.native_speed is None else float(desired.native_speed)
        ),
        "native_instructions": desired.native_instructions,
        "native_seed": desired.native_seed,
    }


def _performance_payload(compiled: CompiledPerformance) -> dict[str, object]:
    return {
        "desired": _desired_payload(compiled.desired),
        "backend": compiled.backend.provider_fields(),
        "playback": {
            "volume": compiled.playback.volume,
            "pause_before_ms": compiled.playback.pause_before_ms,
        },
        "unsupported": list(compiled.unsupported),
        "degradation": list(compiled.degradation),
    }


@dataclass(frozen=True, slots=True)
class SealedSpeechUnit:
    unit_id: str
    turn_id: str
    story_session_id: str
    story_revision: int
    narrative_block_id: str
    segment_index: int
    presentation_identity: str
    binding_id: str
    binding_revision: int
    logical_voice_id: str
    persona_revision: str
    provider_instance: str
    voice_id: str
    voice_revision: str
    model_id: str
    model_revision: str | None
    language: str
    performance_plan_id: str
    display_text: str
    spoken_text: str
    pronunciation_revision: str
    pronunciation_mappings: tuple[SpokenSpanMapping, ...]
    desired: DesiredPerformance
    backend: EffectiveBackendPerformance
    playback: EffectivePlaybackPerformance
    unsupported: tuple[str, ...]
    degradation: tuple[str, ...]

    @property
    def sealed(self) -> bool:
        return True

    def render_recipe(self) -> dict[str, object]:
        """Execution-safe fields before media stream identity is attached."""
        fields = self.backend.provider_fields()
        if set(fields) != {"speed"}:
            raise SpeechUnitSealingError("sealed_unit_has_unrepresentable_backend_fields")
        return {
            "speech_unit_id": self.unit_id,
            "turn_id": self.turn_id,
            "story_revision": self.story_revision,
            "narrative_block_id": self.narrative_block_id,
            "segment_index": self.segment_index,
            "performance_plan_id": self.performance_plan_id,
            "spoken_text": self.spoken_text,
            "voice_id": self.voice_id,
            "expected_voice_revision": self.voice_revision,
            "expected_model_revision": self.model_revision,
            "speed": float(fields["speed"]),
            "language": self.language,
        }


class SpeechUnitSealingService:
    """Seal one authorized character segment for later TTS execution."""

    def __init__(
        self,
        *,
        disclosure: AudioDisclosureAuthorizer,
        bindings: VoiceBindingReadPort,
        spoken_text: SpokenTextCompiler | None = None,
        performance: PerformanceCompiler | None = None,
    ) -> None:
        self._disclosure = disclosure
        self._bindings = bindings
        self._spoken_text = spoken_text or SpokenTextCompiler()
        self._performance = performance or PerformanceCompiler()

    async def seal(
        self,
        *,
        turn_id: str,
        expected_story_revision: int,
        segment_index: int,
        binding_scope: VoiceBindingScope,
        expected_binding_revision: int,
        execution_model_id: str,
        dictionary_revision: str,
        semantic_anchors: tuple[SemanticAnchor, ...],
        pronunciation_rules: tuple[PronunciationRule, ...],
        desired_performance: DesiredPerformance,
        performance_capabilities: VoicePerformanceCapabilities,
    ) -> SealedSpeechUnit:
        if type(expected_binding_revision) is not int or expected_binding_revision < 1:
            raise SpeechUnitSealingError("invalid_expected_binding_revision")
        if (
            not isinstance(execution_model_id, str)
            or not execution_model_id.strip()
            or len(execution_model_id) > 256
            or "\x00" in execution_model_id
        ):
            raise SpeechUnitSealingError("invalid_execution_model_id")

        authorized = await self._disclosure.authorize(
            turn_id=turn_id,
            expected_story_revision=expected_story_revision,
            segment_index=segment_index,
        )

        # Narration has no speaker identity in NarrativeBlock v1. Until an explicit
        # narrator presentation policy exists, never let a caller choose one here.
        if authorized.speaker_id is None:
            raise SpeechUnitSealingError("speakerless_segment_requires_narrator_policy")
        if authorized.speaker_id != binding_scope.presentation_identity:
            raise SpeechUnitSealingError("binding_presentation_identity_mismatch")

        binding = await self._bindings.load_scope(binding_scope)
        if binding is None:
            raise SpeechUnitSealingError("voice_binding_not_found")
        if binding.scope != binding_scope:
            raise SpeechUnitSealingError("voice_binding_scope_mismatch")
        if (
            binding.status is not VoiceBindingStatus.ACTIVE
            or not binding.permits_new_render
        ):
            raise SpeechUnitSealingError("voice_binding_not_renderable")
        if binding.binding_revision != expected_binding_revision:
            raise SpeechUnitSealingError("voice_binding_revision_mismatch")

        voice_revision = binding.provider.conditional_pin
        if voice_revision is None:
            # W-V03 sealed render requires an exact immutable provider voice pin.
            raise SpeechUnitSealingError("voice_revision_is_not_content_addressed")

        spoken = self._spoken_text.compile(
            display_text=authorized.display_text,
            dictionary_revision=dictionary_revision,
            semantic_anchors=semantic_anchors,
            pronunciation_rules=pronunciation_rules,
        )
        compiled = self._performance.compile(
            desired_performance,
            performance_capabilities,
        )

        # Current W-V03 wire can carry native speed only. Do not silently drop a
        # supported instruction/emotion/emphasis field produced by W-V05.
        provider_fields = compiled.backend.provider_fields()
        if set(provider_fields) != {"speed"}:
            raise SpeechUnitSealingError(
                "effective_backend_not_representable_by_render_control"
            )

        performance_payload = _performance_payload(compiled)
        performance_plan_id = "perf_" + _digest(performance_payload)[:24]
        identity_payload: dict[str, object] = {
            "turn_id": authorized.turn_id,
            "story_session_id": authorized.story_session_id,
            "story_revision": authorized.story_revision,
            "narrative_block_id": authorized.narrative_block_id,
            "segment_index": authorized.segment_index,
            "presentation_identity": binding.scope.presentation_identity,
            "binding_id": binding.binding_id,
            "binding_revision": binding.binding_revision,
            "logical_voice_id": binding.persona.logical_voice_id,
            "persona_revision": binding.persona.revision,
            "provider_instance": binding.provider.provider_instance,
            "voice_id": binding.provider.voice_id,
            "voice_revision": voice_revision,
            "model_id": execution_model_id,
            "model_revision": binding.provider.model_catalog_revision,
            "language": binding.scope.locale,
            "performance_plan_id": performance_plan_id,
            "display_text": spoken.display_text,
            "spoken_text": spoken.spoken_text,
            "pronunciation_revision": spoken.dictionary_revision,
            "pronunciation_mappings": [
                {
                    "anchor_id": item.anchor_id,
                    "semantic_key": item.semantic_key,
                    "display_start": item.display_start,
                    "display_end": item.display_end,
                    "spoken_start": item.spoken_start,
                    "spoken_end": item.spoken_end,
                    "rule_id": item.rule_id,
                }
                for item in spoken.mappings
            ],
            "effective_performance": performance_payload,
        }
        unit_id = "speech_" + _digest(identity_payload)[:32]

        return SealedSpeechUnit(
            unit_id=unit_id,
            turn_id=authorized.turn_id,
            story_session_id=authorized.story_session_id,
            story_revision=authorized.story_revision,
            narrative_block_id=authorized.narrative_block_id,
            segment_index=authorized.segment_index,
            presentation_identity=binding.scope.presentation_identity,
            binding_id=binding.binding_id,
            binding_revision=binding.binding_revision,
            logical_voice_id=binding.persona.logical_voice_id,
            persona_revision=binding.persona.revision,
            provider_instance=binding.provider.provider_instance,
            voice_id=binding.provider.voice_id,
            voice_revision=voice_revision,
            model_id=execution_model_id,
            model_revision=binding.provider.model_catalog_revision,
            language=binding.scope.locale,
            performance_plan_id=performance_plan_id,
            display_text=spoken.display_text,
            spoken_text=spoken.spoken_text,
            pronunciation_revision=spoken.dictionary_revision,
            pronunciation_mappings=spoken.mappings,
            desired=compiled.desired,
            backend=compiled.backend,
            playback=compiled.playback,
            unsupported=compiled.unsupported,
            degradation=compiled.degradation,
        )
