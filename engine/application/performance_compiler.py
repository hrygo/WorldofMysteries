"""W-V05 desired-to-effective performance lowering.

The compiler separates expressive intent from provider execution. It never
invent a backend mapping for a semantic control that has no approved native
capability. Timeline/mixer controls remain local presentation operations.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal


Volume = Literal["very_low", "low", "normal", "high"]
VoiceVariant = Literal["base_clone", "custom_voice", "voice_design"]
EmphasisStrength = Literal["light", "medium", "strong"]


class PerformanceCompilerError(ValueError):
    """Desired performance or capability metadata is invalid."""


@dataclass(frozen=True, slots=True)
class EmphasisCue:
    text: str
    strength: EmphasisStrength

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip() or len(self.text) > 256:
            raise PerformanceCompilerError("invalid_emphasis_text")
        if self.strength not in {"light", "medium", "strong"}:
            raise PerformanceCompilerError("invalid_emphasis_strength")


@dataclass(frozen=True, slots=True)
class DesiredPerformance:
    emotion: str | None = None
    intensity: float = 0.0
    pace_modifier: float = 0.0
    energy_modifier: float = 0.0
    volume: Volume = "normal"
    pause_before_ms: int = 0
    emphasis: tuple[EmphasisCue, ...] = ()
    native_speed: float | None = None
    native_instructions: str | None = None
    native_seed: int | None = None

    def __post_init__(self) -> None:
        for name, value, low, high in (
            ("intensity", self.intensity, 0.0, 1.0),
            ("pace_modifier", self.pace_modifier, -1.0, 1.0),
            ("energy_modifier", self.energy_modifier, -1.0, 1.0),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PerformanceCompilerError(f"invalid_{name}")
            numeric = float(value)
            if not math.isfinite(numeric) or not low <= numeric <= high:
                raise PerformanceCompilerError(f"invalid_{name}")

        if self.volume not in {"very_low", "low", "normal", "high"}:
            raise PerformanceCompilerError("invalid_volume")
        if type(self.pause_before_ms) is not int or self.pause_before_ms < 0:
            raise PerformanceCompilerError("invalid_pause_before_ms")
        if self.emotion is not None and (
            not isinstance(self.emotion, str)
            or not self.emotion.strip()
            or len(self.emotion) > 128
        ):
            raise PerformanceCompilerError("invalid_emotion")
        if self.native_speed is not None:
            if (
                isinstance(self.native_speed, bool)
                or not isinstance(self.native_speed, (int, float))
                or not math.isfinite(float(self.native_speed))
                or not 0.25 <= float(self.native_speed) <= 4.0
            ):
                raise PerformanceCompilerError("invalid_native_speed")
        if self.native_instructions is not None and (
            not isinstance(self.native_instructions, str)
            or not self.native_instructions.strip()
            or len(self.native_instructions) > 1024
        ):
            raise PerformanceCompilerError("invalid_native_instructions")
        if self.native_seed is not None and (
            type(self.native_seed) is not int or self.native_seed < 0
        ):
            raise PerformanceCompilerError("invalid_native_seed")


@dataclass(frozen=True, slots=True)
class VoicePerformanceCapabilities:
    variant: VoiceVariant
    native_speed: bool = False
    native_instructions: bool = False
    native_seed: bool = False
    native_emotion: bool = False
    native_intensity: bool = False
    native_energy: bool = False
    native_emphasis: bool = False

    def __post_init__(self) -> None:
        if self.variant not in {"base_clone", "custom_voice", "voice_design"}:
            raise PerformanceCompilerError("invalid_voice_variant")
        for field in (
            "native_speed",
            "native_instructions",
            "native_seed",
            "native_emotion",
            "native_intensity",
            "native_energy",
            "native_emphasis",
        ):
            if type(getattr(self, field)) is not bool:
                raise PerformanceCompilerError(f"invalid_capability_{field}")


@dataclass(frozen=True, slots=True)
class EffectiveBackendPerformance:
    speed: float
    instructions: str | None = None
    seed: int | None = None
    emotion: str | None = None
    intensity: float | None = None
    energy_modifier: float | None = None
    emphasis: tuple[EmphasisCue, ...] = ()

    def provider_fields(self) -> dict[str, object]:
        """Return only fields explicitly approved for provider execution."""
        values: dict[str, object] = {"speed": self.speed}
        if self.instructions is not None:
            values["instructions"] = self.instructions
        if self.seed is not None:
            values["seed"] = self.seed
        if self.emotion is not None:
            values["emotion"] = self.emotion
        if self.intensity is not None:
            values["intensity"] = self.intensity
        if self.energy_modifier is not None:
            values["energy_modifier"] = self.energy_modifier
        if self.emphasis:
            values["emphasis"] = tuple(
                {"text": cue.text, "strength": cue.strength} for cue in self.emphasis
            )
        return values


@dataclass(frozen=True, slots=True)
class EffectivePlaybackPerformance:
    volume: Volume
    pause_before_ms: int


@dataclass(frozen=True, slots=True)
class CompiledPerformance:
    desired: DesiredPerformance
    backend: EffectiveBackendPerformance
    playback: EffectivePlaybackPerformance
    unsupported: tuple[str, ...]
    degradation: tuple[str, ...]


class PerformanceCompiler:
    """Fail-closed lowering from semantic intent to effective execution."""

    def compile(
        self,
        desired: DesiredPerformance,
        capabilities: VoicePerformanceCapabilities,
    ) -> CompiledPerformance:
        unsupported: list[str] = []
        degradation: list[str] = []

        speed = 1.0
        instructions: str | None = None
        seed: int | None = None
        emotion: str | None = None
        intensity: float | None = None
        energy: float | None = None
        emphasis: tuple[EmphasisCue, ...] = ()

        # Base clone is a hard provider invariant: no caller speed,
        # instructions, or seed even if stale capability metadata says otherwise.
        if capabilities.variant == "base_clone":
            if desired.native_speed is not None and float(desired.native_speed) != 1.0:
                unsupported.append("native_speed")
                degradation.append("native_speed_to_base_clone_1_0")
            if desired.native_instructions is not None:
                unsupported.append("native_instructions")
                degradation.append("instructions_to_neutral_voice")
            if desired.native_seed is not None:
                unsupported.append("native_seed")
                degradation.append("seed_omitted_for_base_clone")
        else:
            if desired.native_speed is not None:
                if capabilities.native_speed:
                    speed = float(desired.native_speed)
                else:
                    unsupported.append("native_speed")
                    degradation.append("native_speed_to_1_0")
            if desired.native_instructions is not None:
                if capabilities.native_instructions:
                    instructions = desired.native_instructions.strip()
                else:
                    unsupported.append("native_instructions")
                    degradation.append("instructions_to_neutral_voice")
            if desired.native_seed is not None:
                if capabilities.native_seed:
                    seed = desired.native_seed
                else:
                    unsupported.append("native_seed")
                    degradation.append("seed_omitted")

        # pace_modifier is semantic. There is deliberately no guessed conversion
        # to native speed without a separate approved translation contract.
        if desired.pace_modifier != 0:
            unsupported.append("pace_modifier")
            degradation.append("pace_modifier_not_lowered_to_native_speed")

        if desired.emotion is not None:
            if capabilities.native_emotion:
                emotion = desired.emotion.strip()
            else:
                unsupported.append("emotion")
                degradation.append("emotion_to_neutral_voice")

        if desired.intensity != 0:
            if capabilities.native_intensity:
                intensity = float(desired.intensity)
            else:
                unsupported.append("intensity")
                degradation.append("intensity_not_native")

        if desired.energy_modifier != 0:
            if capabilities.native_energy:
                energy = float(desired.energy_modifier)
            else:
                unsupported.append("energy_modifier")
                degradation.append("energy_not_native")

        if desired.emphasis:
            if capabilities.native_emphasis:
                emphasis = desired.emphasis
            else:
                unsupported.append("emphasis")
                degradation.append("emphasis_not_native")

        return CompiledPerformance(
            desired=desired,
            backend=EffectiveBackendPerformance(
                speed=speed,
                instructions=instructions,
                seed=seed,
                emotion=emotion,
                intensity=intensity,
                energy_modifier=energy,
                emphasis=emphasis,
            ),
            playback=EffectivePlaybackPerformance(
                volume=desired.volume,
                pause_before_ms=desired.pause_before_ms,
            ),
            unsupported=tuple(unsupported),
            degradation=tuple(degradation),
        )
