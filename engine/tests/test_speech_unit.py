"""W-V05 immutable SpeechUnit sealing integration tests."""
from __future__ import annotations

import pytest

from application.audio_disclosure import (
    AudioDisclosureAuthorizer,
    PronunciationRule,
    SemanticAnchor,
)
from application.performance_compiler import (
    DesiredPerformance,
    VoicePerformanceCapabilities,
)
from application.speech_unit import SpeechUnitSealingError, SpeechUnitSealingService
from contracts import BaseRevisions, NarrativeBlock, TurnStatus, TurnTransaction
from contracts.models import NarrativeSegment
from domain.voice_identity import (
    ProviderVoiceRevision,
    VoiceBinding,
    VoiceBindingScope,
    VoiceBindingStatus,
    VoiceIdentityAssurance,
    VoicePersonaRevision,
)


class MemoryDisclosurePort:
    def __init__(self, turn: TurnTransaction, block: NarrativeBlock):
        self.turn = turn
        self.block = block

    async def load_turn(self, turn_id: str) -> TurnTransaction:
        return self.turn

    async def load_narrative_block(self, narrative_block_id: str) -> NarrativeBlock:
        return self.block


class MemoryBindingPort:
    def __init__(self, binding: VoiceBinding | None):
        self.binding = binding

    async def load_scope(self, scope: VoiceBindingScope) -> VoiceBinding | None:
        return self.binding


def scope(*, identity: str = "klein-visible") -> VoiceBindingScope:
    return VoiceBindingScope(
        owner_id="player",
        world_id="world-1",
        worldline_id="line-1",
        presentation_identity=identity,
        phase="default",
        locale="zh-CN",
    )


def binding(
    *,
    assurance: VoiceIdentityAssurance = VoiceIdentityAssurance.CONTENT_ADDRESSED,
    status: VoiceBindingStatus = VoiceBindingStatus.ACTIVE,
) -> VoiceBinding:
    provider = ProviderVoiceRevision(
        provider_instance="speechrail-local",
        voice_id="klein-approved",
        assurance=assurance,
        voice_revision=(
            "voice-" + "a" * 40
            if assurance is VoiceIdentityAssurance.CONTENT_ADDRESSED
            else None
        ),
        model_catalog_revision="b" * 40,
    )
    return VoiceBinding(
        binding_id="binding-1",
        scope=scope(),
        persona=VoicePersonaRevision("voice-klein", "persona-r1"),
        provider=provider,
        binding_revision=2,
        status=status,
        reserved_at_world_revision=7,
    )


def turn() -> TurnTransaction:
    return TurnTransaction(
        schema_version="1.0",
        id="turn-1",
        session_id="session-1",
        idempotency_key="idem-1",
        status=TurnStatus.NARRATIVE_READY,
        base_revisions=BaseRevisions(world=3, character=4, story=6),
        state_delta_id="delta-1",
        committed_story_revision=7,
        narrative_block_id="narrative-1",
    )


def narrative(*, speaker_id: str | None = "klein-visible") -> NarrativeBlock:
    return NarrativeBlock(
        schema_version="1.0",
        id="narrative-1",
        story_session_id="session-1",
        source_story_revision=7,
        segments=[
            NarrativeSegment(
                type="character" if speaker_id is not None else "narration",
                speaker_id=speaker_id,
                text="克莱恩没有打开5kg重的门。",
                speech_intent="cautious",
            )
        ],
        source_state_delta_id="delta-1",
    )


def service(
    *,
    bound: VoiceBinding | None = None,
    speaker_id: str | None = "klein-visible",
) -> SpeechUnitSealingService:
    return SpeechUnitSealingService(
        disclosure=AudioDisclosureAuthorizer(
            MemoryDisclosurePort(turn(), narrative(speaker_id=speaker_id))
        ),
        bindings=MemoryBindingPort(bound if bound is not None else binding()),
    )


def pronunciation(display: str):
    number_start = display.index("5")
    unit_start = display.index("kg")
    anchors = (
        SemanticAnchor(
            anchor_id="number-5",
            category="number",
            semantic_key="number:5",
            start=number_start,
            end=number_start + 1,
            source_text="5",
            allowed_spoken_forms=frozenset({"五"}),
        ),
        SemanticAnchor(
            anchor_id="unit-kg",
            category="unit",
            semantic_key="unit:kg",
            start=unit_start,
            end=unit_start + 2,
            source_text="kg",
            allowed_spoken_forms=frozenset({"公斤"}),
        ),
    )
    rules = (
        PronunciationRule("rule-number", "number-5", "pron-v1", "五"),
        PronunciationRule("rule-unit", "unit-kg", "pron-v1", "公斤"),
    )
    return anchors, rules


async def seal_once(
    *,
    svc: SpeechUnitSealingService | None = None,
    expected_binding_revision: int = 2,
    desired: DesiredPerformance | None = None,
    capabilities: VoicePerformanceCapabilities | None = None,
):
    display = "克莱恩没有打开5kg重的门。"
    anchors, rules = pronunciation(display)
    return await (svc or service()).seal(
        turn_id="turn-1",
        expected_story_revision=7,
        segment_index=0,
        binding_scope=scope(),
        expected_binding_revision=expected_binding_revision,
        dictionary_revision="pron-v1",
        semantic_anchors=anchors,
        pronunciation_rules=rules,
        desired_performance=desired
        or DesiredPerformance(
            native_instructions="whisper dramatically",
            volume="low",
            pause_before_ms=120,
        ),
        performance_capabilities=capabilities
        or VoicePerformanceCapabilities(
            variant="base_clone",
            native_instructions=True,
            native_speed=True,
        ),
    )


async def test_seal_freezes_authorized_text_binding_and_neutral_base_clone():
    unit = await seal_once()

    assert unit.sealed
    assert unit.turn_id == "turn-1"
    assert unit.narrative_block_id == "narrative-1"
    assert unit.presentation_identity == "klein-visible"
    assert unit.binding_id == "binding-1"
    assert unit.binding_revision == 2
    assert unit.spoken_text == "克莱恩没有打开五公斤重的门。"
    assert unit.voice_revision == "voice-" + "a" * 40
    assert unit.model_revision == "b" * 40
    assert unit.desired.native_instructions == "whisper dramatically"
    assert unit.backend.provider_fields() == {"speed": 1.0}
    assert unit.playback.volume == "low"
    assert unit.playback.pause_before_ms == 120
    assert "native_instructions" in unit.unsupported
    assert unit.render_recipe()["expected_voice_revision"] == unit.voice_revision
    assert set(unit.render_recipe()) == {
        "speech_unit_id",
        "turn_id",
        "story_revision",
        "narrative_block_id",
        "segment_index",
        "performance_plan_id",
        "spoken_text",
        "voice_id",
        "expected_voice_revision",
        "expected_model_revision",
        "speed",
        "language",
    }


async def test_sealing_is_deterministic_for_identical_authorized_inputs():
    first = await seal_once()
    second = await seal_once()

    assert first.unit_id == second.unit_id
    assert first.performance_plan_id == second.performance_plan_id
    assert first == second


async def test_seal_rejects_stale_binding_revision_and_wrong_presentation_identity():
    with pytest.raises(SpeechUnitSealingError, match="voice_binding_revision_mismatch"):
        await seal_once(expected_binding_revision=1)

    display = "克莱恩没有打开5kg重的门。"
    anchors, rules = pronunciation(display)
    with pytest.raises(
        SpeechUnitSealingError, match="binding_presentation_identity_mismatch"
    ):
        await service().seal(
            turn_id="turn-1",
            expected_story_revision=7,
            segment_index=0,
            binding_scope=scope(identity="other-visible"),
            expected_binding_revision=2,
            dictionary_revision="pron-v1",
            semantic_anchors=anchors,
            pronunciation_rules=rules,
            desired_performance=DesiredPerformance(),
            performance_capabilities=VoicePerformanceCapabilities(
                variant="base_clone"
            ),
        )


async def test_seal_requires_active_content_addressed_binding():
    legacy = binding(assurance=VoiceIdentityAssurance.LEGACY)
    with pytest.raises(
        SpeechUnitSealingError, match="voice_revision_is_not_content_addressed"
    ):
        await seal_once(svc=service(bound=legacy))

    reserved = binding(status=VoiceBindingStatus.RESERVED)
    with pytest.raises(SpeechUnitSealingError, match="voice_binding_not_renderable"):
        await seal_once(svc=service(bound=reserved))


async def test_seal_rejects_speakerless_narration_until_narrator_policy_exists():
    with pytest.raises(
        SpeechUnitSealingError, match="speakerless_segment_requires_narrator_policy"
    ):
        await seal_once(svc=service(speaker_id=None))


async def test_seal_does_not_silently_drop_native_fields_missing_from_wv03_control():
    with pytest.raises(
        SpeechUnitSealingError,
        match="effective_backend_not_representable_by_render_control",
    ):
        await seal_once(
            desired=DesiredPerformance(native_instructions="speak softly"),
            capabilities=VoicePerformanceCapabilities(
                variant="custom_voice",
                native_instructions=True,
            ),
        )


async def test_performance_plan_identity_preserves_desired_intent_even_when_effective_is_same():
    first = await seal_once(
        desired=DesiredPerformance(native_instructions="whisper dramatically"),
        capabilities=VoicePerformanceCapabilities(variant="base_clone"),
    )
    second = await seal_once(
        desired=DesiredPerformance(native_instructions="speak solemnly"),
        capabilities=VoicePerformanceCapabilities(variant="base_clone"),
    )

    assert first.backend == second.backend
    assert first.degradation == second.degradation
    assert first.performance_plan_id != second.performance_plan_id
    assert first.unit_id != second.unit_id
