"""Resolving a session's voice: only a reviewed binding may be rendered."""
from __future__ import annotations

from dataclasses import replace

import pytest

from application.performance_compiler import VoicePerformanceCapabilities
from contracts import (
    BaseRevisions,
    SecretState,
    StoryPhase,
    StorySession,
    StorySessionStatus,
    StoryState,
)
from contracts.models import StoryCommitments, StoryScene
from domain.voice_identity import (
    ProviderVoiceRevision,
    VoiceBinding,
    VoiceBindingScope,
    VoiceEvidenceReference,
    VoiceIdentityAssurance,
    VoicePersonaRevision,
)
from infrastructure import voice_binding_resolver as resolver_module
from infrastructure.audio.capabilities import (
    AudioCapabilityObservation,
    VoiceCapabilityObservation,
)
from infrastructure.audio.config import AudioProviderConfig
from infrastructure.voice_binding_resolver import (
    VoiceBindingResolutionError,
    binding_scope_for,
    resolve_voice_runtime,
)

VOICE_ID = "klein-approved"
VOICE_REVISION = "voice-" + "a" * 40
MODEL_CATALOG_REVISION = "b" * 40


def _session() -> StorySession:
    return StorySession(
        schema_version="1.0",
        id="session_voice_resolver",
        world_id="world_test",
        worldline_id="wl_test",
        protagonist_id="klein",
        story_seed_id="seed_voice_resolver_test_only",
        base_revisions=BaseRevisions(world=0, character=0, story=0),
        story_state=StoryState(
            schema_version="1.0",
            story_session_id="session_voice_resolver",
            revision=3,
            turn=3,
            phase=StoryPhase.INVESTIGATION,
            scene=StoryScene(id="scene_test"),
            world_time="1349-06-12T21:40:00",
            active_conflicts=[],
            discovered_clue_ids=[],
            secret_states={"secret_test": SecretState.HIDDEN},
            commitments=StoryCommitments(hard_ids=[], soft_ids=[]),
            local_state={},
            pressure={},
        ),
        status=StorySessionStatus.ACTIVE,
    )


def _scope() -> VoiceBindingScope:
    return binding_scope_for(_session())


def _provider(voice_revision: str = VOICE_REVISION) -> ProviderVoiceRevision:
    return ProviderVoiceRevision(
        provider_instance="speechrail-local",
        voice_id=VOICE_ID,
        assurance=VoiceIdentityAssurance.CONTENT_ADDRESSED,
        voice_revision=voice_revision,
        model_catalog_revision=MODEL_CATALOG_REVISION,
        revoked=False,
    )


def _evidence() -> VoiceEvidenceReference:
    return VoiceEvidenceReference(
        evidence_id="ev_klein_1",
        evidence_digest="d" * 64,
        model_artifact_revision="qwen3-tts-2026-09-29",
    )


def _reviewed_binding() -> VoiceBinding:
    """A binding that a human listened to and approved, and that went live."""
    reserved = VoiceBinding.reserve(
        binding_id="vb_klein",
        scope=_scope(),
        persona=VoicePersonaRevision("voice-klein", "persona-r1"),
        provider=_provider(),
        world_revision=3,
    )
    return replace(reserved, evidence=_evidence()).activate(
        expected_binding_revision=reserved.binding_revision
    )


def _unreviewed_binding() -> VoiceBinding:
    """A reservation nobody listened to: persisted, but never made live."""
    return VoiceBinding.reserve(
        binding_id="vb_klein",
        scope=_scope(),
        persona=VoicePersonaRevision("voice-klein", "persona-r1"),
        provider=_provider(),
        world_revision=3,
    )


def _observation(voice: VoiceCapabilityObservation) -> AudioCapabilityObservation:
    return AudioCapabilityObservation(
        provider_name="speechrail",
        status="ready",
        assurance="verified",
        voices=(voice,),
    )


def _provider_voice(**overrides) -> VoiceCapabilityObservation:
    values = {
        "voice_id": VOICE_ID,
        "available": True,
        "voice_revision": VOICE_REVISION,
        "voice_identity_assurance": VoiceIdentityAssurance.CONTENT_ADDRESSED.value,
        "realtime_speech": True,
        "model_source": "qwen3-tts",
        "model_catalog_revision": MODEL_CATALOG_REVISION,
    }
    values.update(overrides)
    return VoiceCapabilityObservation(**values)


class _Repository:
    """Only the one verb the resolver is allowed to use."""

    def __init__(self, binding: VoiceBinding | None):
        self.binding = binding
        self.scopes = []

    async def load_scope(self, scope: VoiceBindingScope) -> VoiceBinding | None:
        self.scopes.append(scope)
        return self.binding


@pytest.fixture
def probes(monkeypatch):
    """Record provider probes so a test can assert the provider was left alone."""
    calls = []

    async def _probe(config, *, fetch_json=None, cached=None):
        calls.append(config)
        return _observation(_provider_voice())

    monkeypatch.setattr(resolver_module, "probe_audio_capabilities", _probe)
    return calls


@pytest.mark.asyncio
async def test_a_scope_with_no_binding_reports_the_missing_review(probes):
    """Nothing has been supplied for this identity yet.

    This is the state every new world starts in, so the resolver has to name it
    plainly instead of picking a voice nobody has heard.
    """
    repository = _Repository(None)

    with pytest.raises(VoiceBindingResolutionError) as caught:
        await resolve_voice_runtime(
            repository=repository,
            session=_session(),
            config=AudioProviderConfig(),
            voice_id=VOICE_ID,
        )

    assert caught.value.code == "voice_binding_not_reviewed"
    # The scope is what decided this, so there was no reason to reach the
    # provider at all.
    assert probes == []
    assert repository.scopes == [_scope()]


@pytest.mark.asyncio
async def test_a_reservation_nobody_listened_to_does_not_render(probes):
    repository = _Repository(_unreviewed_binding())

    with pytest.raises(VoiceBindingResolutionError) as caught:
        await resolve_voice_runtime(
            repository=repository,
            session=_session(),
            config=AudioProviderConfig(),
            voice_id=VOICE_ID,
        )

    assert caught.value.code == "voice_binding_not_reviewed"


@pytest.mark.asyncio
async def test_a_reviewed_binding_resolves_against_the_live_provider(probes):
    repository = _Repository(_reviewed_binding())

    resolved = await resolve_voice_runtime(
        repository=repository,
        session=_session(),
        config=AudioProviderConfig(),
        voice_id=VOICE_ID,
    )

    assert resolved.binding == _reviewed_binding()
    assert resolved.scope == _scope()
    assert resolved.provider_instance == "speechrail"
    assert resolved.execution_model_id == "qwen3-tts"
    assert resolved.model_catalog_revision == MODEL_CATALOG_REVISION
    assert resolved.capabilities == VoicePerformanceCapabilities(
        variant="custom_voice", native_speed=True
    )
    assert len(probes) == 1


@pytest.mark.asyncio
async def test_a_provider_serving_a_different_voice_conflicts(monkeypatch):
    """The player approved one voice; the provider now serves another."""

    async def _probe(config, *, fetch_json=None, cached=None):
        return _observation(_provider_voice(voice_revision="voice-" + "d" * 40))

    monkeypatch.setattr(resolver_module, "probe_audio_capabilities", _probe)

    with pytest.raises(VoiceBindingResolutionError) as caught:
        await resolve_voice_runtime(
            repository=_Repository(_reviewed_binding()),
            session=_session(),
            config=AudioProviderConfig(),
            voice_id=VOICE_ID,
        )

    assert caught.value.code == "voice_binding_conflicts_with_provider"


@pytest.mark.asyncio
async def test_a_voice_the_provider_cannot_pin_still_fails_closed(monkeypatch):
    async def _probe(config, *, fetch_json=None, cached=None):
        return _observation(_provider_voice(voice_revision=None))

    monkeypatch.setattr(resolver_module, "probe_audio_capabilities", _probe)

    with pytest.raises(VoiceBindingResolutionError) as caught:
        await resolve_voice_runtime(
            repository=_Repository(_reviewed_binding()),
            session=_session(),
            config=AudioProviderConfig(),
            voice_id=VOICE_ID,
        )

    assert caught.value.code == "voice_revision_is_not_content_addressed"


@pytest.mark.asyncio
async def test_an_unnamed_voice_is_refused_before_anything_is_looked_up(probes):
    repository = _Repository(_reviewed_binding())

    with pytest.raises(VoiceBindingResolutionError) as caught:
        await resolve_voice_runtime(
            repository=repository,
            session=_session(),
            config=AudioProviderConfig(),
            voice_id="  ",
        )

    assert caught.value.code == "voice_not_configured"
    assert repository.scopes == []
