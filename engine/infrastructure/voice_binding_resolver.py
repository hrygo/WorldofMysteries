"""Resolve a provider voice into a durable, content-addressed VoiceBinding.

W-V03 refuses to render without an immutable provider pin, and SpeechRail only
publishes a content-addressed ``voice_revision`` for reference-conditioned
voices.  System voices report ``voice_revision = null`` and legacy assurance, so
they can never satisfy the sealed-render contract no matter how they are
configured here.

This resolver therefore never hardcodes a revision.  It reads one
``effective_capabilities_v1`` generation, selects the voice an operator named,
and requires all four pins to be present:

* ``voice_revision``          -- content-addressed voice identity
* ``voice_identity_assurance`` -- must be ``content_addressed``
* ``model.source_model``       -- the execution model the receipt will report
* ``model.catalog_revision``   -- the model catalogue generation

Anything missing fails closed.  A binding is reserved once per scope and reused
afterwards, so a provider catalogue change never silently rewrites a live
binding.
"""
from __future__ import annotations

from dataclasses import dataclass

from application.performance_compiler import (
    DesiredPerformance,
    VoicePerformanceCapabilities,
)
from contracts import StorySession
from domain.voice_identity import (
    ProviderVoiceRevision,
    VoiceBinding,
    VoiceBindingScope,
    VoiceIdentityAssurance,
    VoicePersonaRevision,
)

from .audio.capabilities import (
    AudioCapabilityObservation,
    VoiceCapabilityObservation,
    probe_audio_capabilities,
)
from .audio.config import AudioProviderConfig
from .voice_binding_repository import SQLiteVoiceBindingRepository

_BINDING_PHASE = "narrative"
_BINDING_LOCALE = "zh-CN"


class VoiceBindingResolutionError(RuntimeError):
    """No content-addressed provider voice could be bound for this session."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ResolvedVoiceRuntime:
    """Everything the render runtime needs, already proven against the provider."""

    scope: VoiceBindingScope
    binding: VoiceBinding
    provider_instance: str
    execution_model_id: str
    model_catalog_revision: str
    capabilities: VoicePerformanceCapabilities
    performance: DesiredPerformance


def binding_scope_for(session: StorySession) -> VoiceBindingScope:
    """Derive the stable presentation scope of one session's protagonist."""
    if not isinstance(session, StorySession):
        raise VoiceBindingResolutionError("voice_binding_scope_invalid")
    return VoiceBindingScope(
        owner_id=session.protagonist_id,
        world_id=session.world_id,
        worldline_id=session.worldline_id,
        presentation_identity=session.protagonist_id,
        phase=_BINDING_PHASE,
        locale=_BINDING_LOCALE,
    )


def _select(observation: AudioCapabilityObservation, voice_id: str) -> VoiceCapabilityObservation:
    if observation.status != "ready":
        raise VoiceBindingResolutionError("voice_provider_not_ready")
    for voice in observation.voices:
        if voice.voice_id == voice_id:
            return voice
    raise VoiceBindingResolutionError("voice_not_in_provider_catalog")


def _capabilities(voice: VoiceCapabilityObservation) -> VoicePerformanceCapabilities:
    # Realtime 4.0.0 exposes native speed on every streaming variant this build
    # can seal.  Instruction/seed/emphasis are not represented by the render
    # control contract, so they stay off and the compiler records no degradation
    # it cannot express.
    variant = "base_clone" if voice.voice_id.startswith("voice_clone") else "custom_voice"
    return VoicePerformanceCapabilities(variant=variant, native_speed=True)


async def resolve_voice_runtime(
    *,
    repository: SQLiteVoiceBindingRepository,
    session: StorySession,
    config: AudioProviderConfig,
    voice_id: str,
    fetch_json=None,
) -> ResolvedVoiceRuntime:
    """Bind one session's protagonist to a verified provider voice."""
    if not isinstance(voice_id, str) or not voice_id.strip():
        raise VoiceBindingResolutionError("voice_not_configured")
    observation = await probe_audio_capabilities(config, fetch_json=fetch_json)
    voice = _select(observation, voice_id.strip())

    if voice.available is not True:
        raise VoiceBindingResolutionError("voice_provider_unavailable")
    if voice.realtime_speech is False:
        raise VoiceBindingResolutionError("voice_realtime_unsupported")
    if voice.revoked:
        raise VoiceBindingResolutionError("voice_revoked")
    if voice.voice_identity_assurance != VoiceIdentityAssurance.CONTENT_ADDRESSED.value:
        raise VoiceBindingResolutionError("voice_revision_is_not_content_addressed")
    if not voice.voice_revision or not voice.model_catalog_revision or not voice.model_source:
        raise VoiceBindingResolutionError("voice_revision_is_not_content_addressed")

    scope = binding_scope_for(session)
    existing = await repository.load_scope(scope)
    if existing is not None:
        if (
            existing.provider.voice_id != voice.voice_id
            or existing.provider.voice_revision != voice.voice_revision
            or not existing.permits_new_render
        ):
            # A live binding is immutable presentation state.  Re-binding it would
            # change the voice a player already heard, so fail closed instead.
            raise VoiceBindingResolutionError("voice_binding_conflicts_with_provider")
        binding = existing
    else:
        reserved = VoiceBinding.reserve(
            binding_id=_binding_id(scope),
            scope=scope,
            persona=VoicePersonaRevision(
                logical_voice_id=voice.voice_id,
                revision=f"persona-{voice.voice_revision}",
            ),
            provider=ProviderVoiceRevision(
                provider_instance=config.provider_name,
                voice_id=voice.voice_id,
                assurance=VoiceIdentityAssurance.CONTENT_ADDRESSED,
                voice_revision=voice.voice_revision,
                model_catalog_revision=voice.model_catalog_revision,
                revoked=False,
            ),
            world_revision=session.story_state.revision,
        )
        binding = await repository.reserve(reserved)
        binding = await repository.activate(
            binding.binding_id, expected_binding_revision=binding.binding_revision
        )

    return ResolvedVoiceRuntime(
        scope=scope,
        binding=binding,
        provider_instance=config.provider_name,
        execution_model_id=voice.model_source or "",
        model_catalog_revision=voice.model_catalog_revision or "",
        capabilities=_capabilities(voice),
        performance=DesiredPerformance(),
    )


def _binding_id(scope: VoiceBindingScope) -> str:
    import hashlib

    seed = "\x00".join(
        (
            scope.owner_id,
            scope.world_id,
            scope.worldline_id,
            scope.presentation_identity,
            scope.phase,
            scope.locale,
        )
    )
    return "vb_" + hashlib.sha256(f"wom-voice-binding/v1\x00{seed}".encode()).hexdigest()[:32]


__all__ = [
    "ResolvedVoiceRuntime",
    "VoiceBindingResolutionError",
    "binding_scope_for",
    "resolve_voice_runtime",
]
