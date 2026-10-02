"""Resolve an already-reviewed VoiceBinding against a live provider voice.

W-V03 refuses to render without an immutable provider pin, and SpeechRail only
publishes a content-addressed ``voice_revision`` for reference-conditioned
voices.  System voices report ``voice_revision = null`` and legacy assurance, so
they can never satisfy the sealed-render contract no matter how they are
configured here.

This resolver therefore never hardcodes a revision, and it never chooses a
voice.  It resolves the binding a human already reviewed for this presentation
identity, then reads one ``effective_capabilities_v1`` generation, selects the
voice an operator named, and requires all four pins to be present:

* ``voice_revision``          -- content-addressed voice identity
* ``voice_identity_assurance`` -- must be ``content_addressed``
* ``model.source_model``       -- the execution model the receipt will report
* ``model.catalog_revision``   -- the model catalogue generation

Anything missing fails closed.  A binding is supplied once per scope and reused
afterwards, so a provider catalogue change never silently rewrites a live
binding.

Supplying a binding is somebody else's decision (see
``application.voice_casting``).  Reserving one here would mean putting a voice
in front of a player that no human had listened to, so a scope without a
reviewed binding is refused rather than filled in.  The refusal is reported as
``voice_binding_not_reviewed`` — the truthful reason, and the one the delivery
surfaces show the player.

The scope names a *speaker*, and the caller supplies it. Deriving it here from
the session would make the protagonist the only voice the system can address:
the narrator and every cast character could be published, reviewed and bound,
and nothing here would ever look any of them up. ``speaker_scope_for`` is the
one place that decides which identity a narrative segment speaks under, so
that rule is written down once instead of at each call site.
"""
from __future__ import annotations

from dataclasses import dataclass

from application.performance_compiler import (
    DesiredPerformance,
    VoicePerformanceCapabilities,
)
from contracts import StorySession
from domain.voice_identity import (
    VoiceBindingScope,
    VoiceIdentityAssurance,
)

from .audio.capabilities import (
    AudioCapabilityObservation,
    VoiceCapabilityObservation,
    probe_audio_capabilities,
)
from .audio.config import AudioProviderConfig
from .voice_binding_repository import SQLiteVoiceBindingRepository

_BINDING_LOCALE = "zh-CN"

#: The identity narration speaks under. A published narrative block carries
#: its narration with no ``speaker_id`` at all, so the narrator inherits
#: nobody's voice and has to be named — and it is named by the same slug the
#: casting catalog publishes, because a binding looked up under any other
#: spelling would be a binding no cast ever wrote.
NARRATOR_IDENTITY = "narrator"

#: Phases are part of the scope, so one identity cast for dialogue and the
#: same identity cast for narration are two different voices. That is the
#: point of a per-speaker scope: "who" and "in what role" both decide which
#: reviewed voice applies.
NARRATION_PHASE = "narration"
DIALOGUE_PHASE = "dialogue"


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


def binding_scope_for(
    session: StorySession,
    *,
    presentation_identity: str,
    phase: str,
) -> VoiceBindingScope:
    """Derive the stable presentation scope of one speaker in one session.

    Naming the speaker is the point: an earlier version read the protagonist
    off the session, which made the protagonist the only addressable voice in
    the entire system. A narrator and four cast characters could all be
    published, reviewed and bound, and no code path would ever look any of
    them up.

    Both halves of the speaker are named because both decide the voice: the
    same identity cast for narration and for dialogue is two bindings, and a
    scope carrying only the identity would let one silently stand in for the
    other. Neither has a default. This function used to read the protagonist
    off the session when the caller named nobody, which is precisely what
    made the narrator and the cast unreachable; the fallback existed only
    until the last delivery site moved onto ``speaker_scope_for``, and it is
    gone now.
    """
    if not isinstance(session, StorySession):
        raise VoiceBindingResolutionError("voice_binding_scope_invalid")
    if not isinstance(presentation_identity, str) or not presentation_identity.strip():
        raise VoiceBindingResolutionError("voice_binding_scope_invalid")
    if not isinstance(phase, str) or not phase.strip():
        raise VoiceBindingResolutionError("voice_binding_scope_invalid")
    return VoiceBindingScope(
        owner_id=session.protagonist_id,
        world_id=session.world_id,
        worldline_id=session.worldline_id,
        presentation_identity=presentation_identity,
        phase=phase,
        locale=_BINDING_LOCALE,
    )


def speaker_scope_for(
    session: StorySession, segment: object
) -> VoiceBindingScope | None:
    """The scope ``segment`` speaks under, or ``None`` when it is not voiced.

    A turn's audio is decided per segment rather than per turn: the narration
    and the protagonist's line are two voices, and a cast character's line is
    a third. Returning ``None`` for a segment nobody speaks — a transition, or
    a character line with no speaker — is what lets the caller seal the rest
    of the block instead of refusing the whole turn over one silent segment.
    """
    kind = getattr(segment, "type", None)
    if kind == "narration":
        return binding_scope_for(
            session,
            presentation_identity=NARRATOR_IDENTITY,
            phase=NARRATION_PHASE,
        )
    speaker_id = getattr(segment, "speaker_id", None)
    if kind == "character" and isinstance(speaker_id, str) and speaker_id.strip():
        return binding_scope_for(
            session,
            presentation_identity=speaker_id,
            phase=DIALOGUE_PHASE,
        )
    return None


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
    scope: VoiceBindingScope,
    fetch_json=None,
) -> ResolvedVoiceRuntime:
    """Resolve one speaker to its reviewed, verified voice.

    The scope is passed in rather than derived, because the speaker is the
    caller's to know: the delivery stage knows which segment it is sealing,
    and a resolver that re-derived "the protagonist" here would quietly throw
    that knowledge away. It is required for the same reason — a resolver
    willing to pick a speaker would pick the protagonist every time, and the
    narrator and the cast would stay unreachable however many were cast.
    """
    if not isinstance(voice_id, str) or not voice_id.strip():
        raise VoiceBindingResolutionError("voice_not_configured")
    if not isinstance(scope, VoiceBindingScope):
        raise VoiceBindingResolutionError("voice_binding_scope_invalid")

    # The scope is checked before the provider is probed.  With no reviewed
    # binding there is nothing for a provider generation to be verified
    # against, and a provider error would name a problem that is not the one
    # actually stopping this session from being voiced.
    existing = await repository.load_scope(scope)
    if existing is None:
        raise VoiceBindingResolutionError("voice_binding_not_reviewed")

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

    if (
        existing.provider.voice_id != voice.voice_id
        or existing.provider.voice_revision != voice.voice_revision
    ):
        # A live binding is immutable presentation state.  Re-binding it would
        # change the voice a player already heard, so fail closed instead.
        raise VoiceBindingResolutionError("voice_binding_conflicts_with_provider")
    if not existing.permits_new_render:
        # The binding exists but carries no review a human stood behind, so it
        # never went live.  That is a missing review, not a provider conflict.
        raise VoiceBindingResolutionError("voice_binding_not_reviewed")

    return ResolvedVoiceRuntime(
        scope=scope,
        binding=existing,
        provider_instance=config.provider_name,
        execution_model_id=voice.model_source or "",
        model_catalog_revision=voice.model_catalog_revision or "",
        capabilities=_capabilities(voice),
        performance=DesiredPerformance(),
    )


__all__ = [
    "DIALOGUE_PHASE",
    "NARRATION_PHASE",
    "NARRATOR_IDENTITY",
    "ResolvedVoiceRuntime",
    "VoiceBindingResolutionError",
    "binding_scope_for",
    "speaker_scope_for",
    "resolve_voice_runtime",
]
