"""Resolving a speaker's voice: only a reviewed binding may be rendered."""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

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
    DIALOGUE_PHASE,
    NARRATION_PHASE,
    NARRATOR_IDENTITY,
    VoiceBindingResolutionError,
    binding_scope_for,
    resolve_voice_runtime,
    speaker_scope_for,
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


def _scope(
    presentation_identity: str = "klein", phase: str = DIALOGUE_PHASE
) -> VoiceBindingScope:
    """One speaker's scope.

    Named rather than derived, because that is the point of the change: the
    resolver no longer knows who is speaking, so a test that could not say
    would not be testing anything. The no-argument form is the migration seam
    and still resolves the protagonist; ``TestLegacyScopeFallback`` pins that
    it stops there.
    """
    if presentation_identity is None:
        return binding_scope_for(_session())
    return binding_scope_for(
        _session(), presentation_identity=presentation_identity, phase=phase
    )


def _segment(kind: str, speaker_id: str | None = None):
    return SimpleNamespace(type=kind, speaker_id=speaker_id)


class TestSpeakerScope:
    """Which identity a segment speaks under.

    Every one of these fails on the code this replaces, where the scope was
    read off the session and the protagonist was the only voice the system
    could name at all.
    """

    def test_narration_is_the_narrator_not_the_protagonist(self):
        scope = speaker_scope_for(_session(), _segment("narration"))

        assert scope is not None
        assert scope.presentation_identity == NARRATOR_IDENTITY
        assert scope.phase == NARRATION_PHASE

    def test_a_character_line_is_that_character(self):
        scope = speaker_scope_for(
            _session(), _segment("character", "ida-finch")
        )

        assert scope is not None
        assert scope.presentation_identity == "ida-finch"
        assert scope.phase == DIALOGUE_PHASE

    def test_one_identity_speaks_twice_under_two_scopes(self):
        """Narration and dialogue are different voices, not one voice reused.

        A catalog that casts somebody for both roles would otherwise have its
        dialogue binding silently answer a narration lookup, and the reader
        would hear the same mouth narrating and speaking all game.
        """
        session = _session()

        speaking = speaker_scope_for(session, _segment("character", "klein"))
        narrating = speaker_scope_for(session, _segment("narration"))

        assert speaking is not None and narrating is not None
        assert speaking != narrating

    def test_every_speaker_shares_one_world(self):
        """Different voices, one world — the scope still pins the session."""
        session = _session()

        narrator = speaker_scope_for(session, _segment("narration"))
        character = speaker_scope_for(
            session, _segment("character", "ida-finch")
        )

        assert narrator is not None and character is not None
        assert narrator.world_id == character.world_id
        assert narrator.worldline_id == character.worldline_id
        assert narrator.owner_id == character.owner_id

    @pytest.mark.parametrize(
        "segment",
        [
            _segment("transition"),
            _segment("character", None),
            _segment("character", "   "),
        ],
    )
    def test_a_segment_nobody_speaks_is_not_cast(self, segment):
        """A silent segment must not fail the turn, and must not be voiced.

        Returning None is what lets the caller seal the rest of the block; a
        line with no speaker is not a reason to refuse every other voice in
        the turn.
        """
        assert speaker_scope_for(_session(), segment) is None


class TestLegacyScopeFallback:
    """The migration seam, pinned so its removal is a deliberate act.

    ``binding_scope_for(session)`` with no speaker still resolves the
    protagonist, because call sites in ``story_runtime`` and
    ``post_commit_handlers`` have not been moved onto ``speaker_scope_for``
    yet. This is the reason the narrator and the cast are unreachable, so it
    is a temporary shape with a test: when the last caller moves, this class
    goes red and the fallback goes with it.
    """

    def test_no_speaker_still_resolves_the_protagonist(self):
        scope = binding_scope_for(_session())

        assert scope.presentation_identity == "klein"
        assert scope.phase == "narrative"

    def test_half_a_speaker_is_refused(self):
        """Naming an identity without a phase must not invent the other half."""
        with pytest.raises(VoiceBindingResolutionError) as caught:
            binding_scope_for(_session(), presentation_identity="ida-finch")

        assert caught.value.code == "voice_binding_scope_invalid"

    def test_a_named_speaker_never_falls_back(self):
        scope = _scope("ida-finch", DIALOGUE_PHASE)

        assert scope.presentation_identity == "ida-finch"


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
                scope=_scope(),
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
                scope=_scope(),
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
                scope=_scope(),
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
            scope=_scope(),
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
            scope=_scope(),
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
            scope=_scope(),
        )

    assert caught.value.code == "voice_not_configured"
    assert repository.scopes == []
