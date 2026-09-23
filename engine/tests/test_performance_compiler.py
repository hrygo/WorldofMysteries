"""W-V05 performance compiler safety and lowering tests."""
from __future__ import annotations

import pytest

from application.performance_compiler import (
    DesiredPerformance,
    EmphasisCue,
    PerformanceCompiler,
    PerformanceCompilerError,
    VoicePerformanceCapabilities,
)


def test_base_clone_never_sends_instructions_seed_or_non_neutral_speed():
    desired = DesiredPerformance(
        pace_modifier=0.5,
        volume="low",
        pause_before_ms=320,
        native_speed=1.25,
        native_instructions="speak with dramatic menace",
        native_seed=42,
    )
    # Stale/overstated capability metadata must not weaken Base clone rules.
    caps = VoicePerformanceCapabilities(
        variant="base_clone",
        native_speed=True,
        native_instructions=True,
        native_seed=True,
    )

    compiled = PerformanceCompiler().compile(desired, caps)

    assert compiled.backend.provider_fields() == {"speed": 1.0}
    assert compiled.playback.volume == "low"
    assert compiled.playback.pause_before_ms == 320
    assert set(compiled.unsupported) == {
        "native_speed",
        "native_instructions",
        "native_seed",
        "pace_modifier",
    }


def test_pause_and_volume_are_playback_only_and_never_provider_fields():
    compiled = PerformanceCompiler().compile(
        DesiredPerformance(volume="very_low", pause_before_ms=900),
        VoicePerformanceCapabilities(variant="custom_voice"),
    )

    assert compiled.playback.volume == "very_low"
    assert compiled.playback.pause_before_ms == 900
    assert compiled.backend.provider_fields() == {"speed": 1.0}
    assert "volume" not in compiled.backend.provider_fields()
    assert "pause_before_ms" not in compiled.backend.provider_fields()


def test_only_explicit_native_capabilities_can_reach_backend():
    desired = DesiredPerformance(
        emotion="whispered",
        intensity=0.7,
        energy_modifier=-0.4,
        emphasis=(EmphasisCue("克莱恩", "strong"),),
        native_speed=0.9,
        native_instructions="keep names crisp",
        native_seed=7,
    )
    caps = VoicePerformanceCapabilities(
        variant="custom_voice",
        native_speed=True,
        native_emotion=True,
        native_emphasis=True,
        # instructions, seed, intensity and energy are intentionally unsupported.
    )

    compiled = PerformanceCompiler().compile(desired, caps)
    fields = compiled.backend.provider_fields()

    assert fields["speed"] == 0.9
    assert fields["emotion"] == "whispered"
    assert fields["emphasis"] == ({"text": "克莱恩", "strength": "strong"},)
    assert "instructions" not in fields
    assert "seed" not in fields
    assert "intensity" not in fields
    assert "energy_modifier" not in fields
    assert set(compiled.unsupported) == {
        "native_instructions",
        "native_seed",
        "intensity",
        "energy_modifier",
    }


def test_semantic_pace_is_not_guessed_into_native_speed():
    compiled = PerformanceCompiler().compile(
        DesiredPerformance(pace_modifier=1.0),
        VoicePerformanceCapabilities(variant="voice_design", native_speed=True),
    )

    assert compiled.backend.speed == 1.0
    assert compiled.unsupported == ("pace_modifier",)
    assert compiled.degradation == ("pace_modifier_not_lowered_to_native_speed",)


def test_neutral_desired_performance_has_no_false_degradation():
    compiled = PerformanceCompiler().compile(
        DesiredPerformance(),
        VoicePerformanceCapabilities(variant="base_clone"),
    )

    assert compiled.backend.provider_fields() == {"speed": 1.0}
    assert compiled.unsupported == ()
    assert compiled.degradation == ()


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"intensity": 1.1}, "invalid_intensity"),
        ({"pace_modifier": float("nan")}, "invalid_pace_modifier"),
        ({"energy_modifier": -1.1}, "invalid_energy_modifier"),
        ({"pause_before_ms": -1}, "invalid_pause_before_ms"),
        ({"native_speed": 5.0}, "invalid_native_speed"),
        ({"native_instructions": "   "}, "invalid_native_instructions"),
        ({"native_seed": -1}, "invalid_native_seed"),
    ],
)
def test_invalid_desired_performance_fails_closed(kwargs, code):
    with pytest.raises(PerformanceCompilerError, match=code):
        DesiredPerformance(**kwargs)


def test_compilation_is_deterministic_for_same_inputs():
    desired = DesiredPerformance(
        emotion="calm",
        intensity=0.4,
        volume="high",
        pause_before_ms=80,
        native_speed=1.1,
    )
    caps = VoicePerformanceCapabilities(
        variant="custom_voice",
        native_speed=True,
        native_emotion=True,
        native_intensity=True,
    )

    first = PerformanceCompiler().compile(desired, caps)
    second = PerformanceCompiler().compile(desired, caps)

    assert first == second
