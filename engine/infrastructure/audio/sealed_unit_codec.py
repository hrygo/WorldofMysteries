"""Versioned, typed persistence codec for Engine-owned sealed speech units."""
from __future__ import annotations

from dataclasses import fields
import hashlib
import hmac
import json
import math
import re

from application.audio_disclosure import SpokenSpanMapping
from application.performance_compiler import (
    DesiredPerformance,
    EffectiveBackendPerformance,
    EffectivePlaybackPerformance,
    EmphasisCue,
)
from application.speech_unit import SealedSpeechUnit


class SealedSpeechUnitCodecError(ValueError):
    """A durable sealed speech unit is malformed or fails an integrity check."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# v2 adds the evidence pins (evidence_id / evidence_digest) and the model
# artifact revision. The bump is deliberate: a v1 payload carries no evidence
# identity, so it must be re-sealed rather than silently accepted as if a human
# had approved it. v2 tolerates their absence only while sealing is being
# rolled out; the render boundary rejects an unpinned unit.
_FORMAT_VERSION = 2
_MAX_PAYLOAD_BYTES = 256 * 1024
_MAX_PRONUNCIATION_MAPPINGS = 128
_MAX_EMPHASIS_CUES = 64
_MAX_DIAGNOSTICS = 64
_VOLUMES = frozenset({"very_low", "low", "normal", "high"})
_SEMANTIC_CATEGORIES = frozenset(
    {"proper_name", "term", "number", "unit", "negation"}
)
_EMPHASIS_STRENGTHS = frozenset({"light", "medium", "strong"})
_CREDENTIAL_PATTERN = re.compile(
    r"(?i)(?:"
    r"\b(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|password)\s*[:=]\s*\S+"
    r"|\bbearer\s+[a-z0-9._~+/=-]{8,}"
    r"|\b(?:sk-[a-z0-9_-]{16,}|gsk_[a-z0-9_-]{16,}|AKIA[A-Z0-9]{16})\b"
    r"|\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@"
    r")"
)

_UNIT_STRING_LIMITS = {
    "unit_id": 128,
    "turn_id": 128,
    "story_session_id": 128,
    "narrative_block_id": 128,
    "presentation_identity": 256,
    "binding_id": 128,
    "logical_voice_id": 256,
    "persona_revision": 128,
    "provider_instance": 256,
    "voice_id": 256,
    "voice_revision": 256,
    "model_id": 256,
    "model_revision": 256,
    "evidence_id": 256,
    "evidence_digest": 256,
    "model_artifact_revision": 256,
    "language": 64,
    "performance_plan_id": 128,
    "display_text": 4096,
    "spoken_text": 4096,
    "pronunciation_revision": 128,
}

_MAPPING_KEYS = frozenset(
    {
        "anchor_id",
        "category",
        "semantic_key",
        "display_start",
        "display_end",
        "spoken_start",
        "spoken_end",
        "source_text",
        "spoken_text",
        "rule_id",
        "dictionary_revision",
    }
)
_DESIRED_KEYS = frozenset(
    {
        "emotion",
        "intensity",
        "pace_modifier",
        "energy_modifier",
        "volume",
        "pause_before_ms",
        "emphasis",
        "native_speed",
        "native_instructions",
        "native_seed",
    }
)
_BACKEND_KEYS = frozenset(
    {
        "speed",
        "instructions",
        "seed",
        "emotion",
        "intensity",
        "energy_modifier",
        "emphasis",
    }
)
_PLAYBACK_KEYS = frozenset({"volume", "pause_before_ms"})
_EMPHASIS_KEYS = frozenset({"text", "strength"})
_UNIT_KEYS = frozenset(_UNIT_STRING_LIMITS) | frozenset(
    {
        "story_revision",
        "segment_index",
        "binding_revision",
        "pronunciation_mappings",
        "desired",
        "backend",
        "playback",
        "unsupported",
        "degradation",
    }
)
# Carried by v2 payloads but tolerated as absent until every sealing path
# populates them. Present means validated; absent means "not yet pinned".
_OPTIONAL_UNIT_KEYS = frozenset({"evidence_id", "evidence_digest", "model_artifact_revision"})
_REQUIRED_UNIT_KEYS = _UNIT_KEYS - _OPTIONAL_UNIT_KEYS
# The codec never invents a field the dataclass does not have. Until sealing
# grows the evidence pins, a payload that carries them is refused rather than
# silently dropped on the way back into a unit.
_UNIT_FIELD_NAMES = frozenset(field.name for field in fields(SealedSpeechUnit))
_ENVELOPE_KEYS = frozenset({"format_version", "unit"})


def _fail(code: str) -> None:
    raise SealedSpeechUnitCodecError(code)


def _text(
    value: object,
    field: str,
    *,
    limit: int,
    allow_empty: bool = False,
) -> str:
    if (
        type(value) is not str
        or len(value) > limit
        or "\x00" in value
        or (not allow_empty and not value.strip())
    ):
        _fail(f"invalid_{field}_length_or_type")
    if _CREDENTIAL_PATTERN.search(value):
        _fail(f"credential_material_forbidden:{field}")
    return value


def _optional_text(value: object, field: str, *, limit: int) -> str | None:
    if value is None:
        return None
    return _text(value, field, limit=limit)


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail(f"invalid_{field}")
    return value


def _number(
    value: object,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if type(value) not in {int, float}:
        _fail(f"invalid_{field}")
    numeric = float(value)
    if (
        not math.isfinite(numeric)
        or (minimum is not None and numeric < minimum)
        or (maximum is not None and numeric > maximum)
    ):
        _fail(f"invalid_{field}")
    return numeric


def _object(
    value: object,
    field: str,
    *,
    keys: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> dict[str, object]:
    if type(value) is not dict:
        _fail(f"invalid_{field}_object")
    actual = frozenset(value)
    if actual - keys:
        _fail(f"unknown_{field}_field")
    if not keys - optional <= actual:
        _fail(f"missing_{field}_field")
    return value


def _sequence(value: object, field: str, *, maximum: int) -> list[object]:
    if type(value) is not list:
        _fail(f"invalid_{field}_list")
    if len(value) > maximum:
        _fail(f"{field}_limit_exceeded")
    return value


def _enum(value: object, field: str, choices: frozenset[str]) -> str:
    if type(value) is not str or value not in choices:
        _fail(f"invalid_{field}")
    return value


def _dump_emphasis(cues: object, field: str) -> list[dict[str, str]]:
    if type(cues) is not tuple:
        _fail(f"invalid_{field}_tuple")
    if len(cues) > _MAX_EMPHASIS_CUES:
        _fail(f"{field}_limit_exceeded")
    encoded: list[dict[str, str]] = []
    for cue in cues:
        if type(cue) is not EmphasisCue:
            _fail(f"invalid_{field}_item")
        encoded.append(
            {
                "text": _text(cue.text, f"{field}_text", limit=256),
                "strength": _enum(
                    cue.strength,
                    f"{field}_strength",
                    _EMPHASIS_STRENGTHS,
                ),
            }
        )
    return encoded


def _load_emphasis(value: object, field: str) -> tuple[EmphasisCue, ...]:
    entries = _sequence(value, field, maximum=_MAX_EMPHASIS_CUES)
    return tuple(
        EmphasisCue(
            text=_text(
                _object(item, f"{field}_item", keys=_EMPHASIS_KEYS)["text"],
                f"{field}_text",
                limit=256,
            ),
            strength=_enum(
                item["strength"],
                f"{field}_strength",
                _EMPHASIS_STRENGTHS,
            ),
        )
        for item in entries
    )


def _dump_desired(value: object) -> dict[str, object]:
    if type(value) is not DesiredPerformance:
        _fail("invalid_desired_performance_type")
    return {
        "emotion": _optional_text(value.emotion, "desired_emotion", limit=128),
        "intensity": _number(
            value.intensity,
            "desired_intensity",
            minimum=0.0,
            maximum=1.0,
        ),
        "pace_modifier": _number(
            value.pace_modifier,
            "desired_pace_modifier",
            minimum=-1.0,
            maximum=1.0,
        ),
        "energy_modifier": _number(
            value.energy_modifier,
            "desired_energy_modifier",
            minimum=-1.0,
            maximum=1.0,
        ),
        "volume": _enum(value.volume, "desired_volume", _VOLUMES),
        "pause_before_ms": _integer(value.pause_before_ms, "desired_pause_before_ms"),
        "emphasis": _dump_emphasis(value.emphasis, "desired_emphasis"),
        "native_speed": (
            None
            if value.native_speed is None
            else _number(
                value.native_speed,
                "desired_native_speed",
                minimum=0.25,
                maximum=4.0,
            )
        ),
        "native_instructions": _optional_text(
            value.native_instructions,
            "desired_native_instructions",
            limit=1024,
        ),
        "native_seed": (
            None
            if value.native_seed is None
            else _integer(value.native_seed, "desired_native_seed")
        ),
    }


def _load_desired(value: object) -> DesiredPerformance:
    data = _object(value, "desired_performance", keys=_DESIRED_KEYS)
    return DesiredPerformance(
        emotion=_optional_text(data["emotion"], "desired_emotion", limit=128),
        intensity=_number(
            data["intensity"],
            "desired_intensity",
            minimum=0.0,
            maximum=1.0,
        ),
        pace_modifier=_number(
            data["pace_modifier"],
            "desired_pace_modifier",
            minimum=-1.0,
            maximum=1.0,
        ),
        energy_modifier=_number(
            data["energy_modifier"],
            "desired_energy_modifier",
            minimum=-1.0,
            maximum=1.0,
        ),
        volume=_enum(data["volume"], "desired_volume", _VOLUMES),
        pause_before_ms=_integer(
            data["pause_before_ms"],
            "desired_pause_before_ms",
        ),
        emphasis=_load_emphasis(data["emphasis"], "desired_emphasis"),
        native_speed=(
            None
            if data["native_speed"] is None
            else _number(
                data["native_speed"],
                "desired_native_speed",
                minimum=0.25,
                maximum=4.0,
            )
        ),
        native_instructions=_optional_text(
            data["native_instructions"],
            "desired_native_instructions",
            limit=1024,
        ),
        native_seed=(
            None
            if data["native_seed"] is None
            else _integer(data["native_seed"], "desired_native_seed")
        ),
    )


def _dump_backend(value: object) -> dict[str, object]:
    if type(value) is not EffectiveBackendPerformance:
        _fail("invalid_backend_performance_type")
    return {
        "speed": _number(value.speed, "backend_speed", minimum=0.25, maximum=4.0),
        "instructions": _optional_text(
            value.instructions,
            "backend_instructions",
            limit=1024,
        ),
        "seed": None if value.seed is None else _integer(value.seed, "backend_seed"),
        "emotion": _optional_text(value.emotion, "backend_emotion", limit=128),
        "intensity": (
            None
            if value.intensity is None
            else _number(
                value.intensity,
                "backend_intensity",
                minimum=0.0,
                maximum=1.0,
            )
        ),
        "energy_modifier": (
            None
            if value.energy_modifier is None
            else _number(
                value.energy_modifier,
                "backend_energy_modifier",
                minimum=-1.0,
                maximum=1.0,
            )
        ),
        "emphasis": _dump_emphasis(value.emphasis, "backend_emphasis"),
    }


def _load_backend(value: object) -> EffectiveBackendPerformance:
    data = _object(value, "backend_performance", keys=_BACKEND_KEYS)
    return EffectiveBackendPerformance(
        speed=_number(data["speed"], "backend_speed", minimum=0.25, maximum=4.0),
        instructions=_optional_text(
            data["instructions"],
            "backend_instructions",
            limit=1024,
        ),
        seed=(None if data["seed"] is None else _integer(data["seed"], "backend_seed")),
        emotion=_optional_text(data["emotion"], "backend_emotion", limit=128),
        intensity=(
            None
            if data["intensity"] is None
            else _number(
                data["intensity"],
                "backend_intensity",
                minimum=0.0,
                maximum=1.0,
            )
        ),
        energy_modifier=(
            None
            if data["energy_modifier"] is None
            else _number(
                data["energy_modifier"],
                "backend_energy_modifier",
                minimum=-1.0,
                maximum=1.0,
            )
        ),
        emphasis=_load_emphasis(data["emphasis"], "backend_emphasis"),
    )


def _dump_mapping(
    mapping: object,
    *,
    display_text: str,
    spoken_text: str,
    pronunciation_revision: str,
) -> dict[str, object]:
    if type(mapping) is not SpokenSpanMapping:
        _fail("invalid_pronunciation_mapping_type")
    category = _enum(
        mapping.category,
        "pronunciation_mapping_category",
        _SEMANTIC_CATEGORIES,
    )
    semantic_key = _text(
        mapping.semantic_key,
        "pronunciation_mapping_semantic_key",
        limit=256,
    )
    display_start = _integer(mapping.display_start, "pronunciation_mapping_display_start")
    display_end = _integer(mapping.display_end, "pronunciation_mapping_display_end")
    spoken_start = _integer(mapping.spoken_start, "pronunciation_mapping_spoken_start")
    spoken_end = _integer(mapping.spoken_end, "pronunciation_mapping_spoken_end")
    source_text = _text(
        mapping.source_text,
        "pronunciation_mapping_source_text",
        limit=512,
    )
    mapped_spoken_text = _text(
        mapping.spoken_text,
        "pronunciation_mapping_spoken_text",
        limit=512,
    )
    anchor_id = _text(mapping.anchor_id, "pronunciation_mapping_anchor_id", limit=128)
    rule_id = _text(mapping.rule_id, "pronunciation_mapping_rule_id", limit=128)
    dictionary_revision = _text(
        mapping.dictionary_revision,
        "pronunciation_mapping_dictionary_revision",
        limit=128,
    )
    if (
        not semantic_key.startswith(f"{category}:")
        or display_end <= display_start
        or spoken_end <= spoken_start
        or display_end > len(display_text)
        or spoken_end > len(spoken_text)
        or display_text[display_start:display_end] != source_text
        or spoken_text[spoken_start:spoken_end] != mapped_spoken_text
        or dictionary_revision != pronunciation_revision
    ):
        _fail("invalid_pronunciation_mapping_span_or_revision")
    return {
        "anchor_id": anchor_id,
        "category": category,
        "semantic_key": semantic_key,
        "display_start": display_start,
        "display_end": display_end,
        "spoken_start": spoken_start,
        "spoken_end": spoken_end,
        "source_text": source_text,
        "spoken_text": mapped_spoken_text,
        "rule_id": rule_id,
        "dictionary_revision": dictionary_revision,
    }


def _load_mapping(
    value: object,
    *,
    display_text: str,
    spoken_text: str,
    pronunciation_revision: str,
) -> SpokenSpanMapping:
    data = _object(value, "pronunciation_mapping", keys=_MAPPING_KEYS)
    category = _enum(
        data["category"],
        "pronunciation_mapping_category",
        _SEMANTIC_CATEGORIES,
    )
    semantic_key = _text(
        data["semantic_key"],
        "pronunciation_mapping_semantic_key",
        limit=256,
    )
    display_start = _integer(data["display_start"], "pronunciation_mapping_display_start")
    display_end = _integer(data["display_end"], "pronunciation_mapping_display_end")
    spoken_start = _integer(data["spoken_start"], "pronunciation_mapping_spoken_start")
    spoken_end = _integer(data["spoken_end"], "pronunciation_mapping_spoken_end")
    source_text = _text(
        data["source_text"],
        "pronunciation_mapping_source_text",
        limit=512,
    )
    mapped_spoken_text = _text(
        data["spoken_text"],
        "pronunciation_mapping_spoken_text",
        limit=512,
    )
    dictionary_revision = _text(
        data["dictionary_revision"],
        "pronunciation_mapping_dictionary_revision",
        limit=128,
    )
    if (
        not semantic_key.startswith(f"{category}:")
        or display_end <= display_start
        or spoken_end <= spoken_start
        or display_end > len(display_text)
        or spoken_end > len(spoken_text)
        or display_text[display_start:display_end] != source_text
        or spoken_text[spoken_start:spoken_end] != mapped_spoken_text
        or dictionary_revision != pronunciation_revision
    ):
        _fail("invalid_pronunciation_mapping_span_or_revision")
    return SpokenSpanMapping(
        anchor_id=_text(
            data["anchor_id"],
            "pronunciation_mapping_anchor_id",
            limit=128,
        ),
        category=category,  # type: ignore[arg-type]
        semantic_key=semantic_key,
        display_start=display_start,
        display_end=display_end,
        spoken_start=spoken_start,
        spoken_end=spoken_end,
        source_text=source_text,
        spoken_text=mapped_spoken_text,
        rule_id=_text(data["rule_id"], "pronunciation_mapping_rule_id", limit=128),
        dictionary_revision=dictionary_revision,
    )


def _dump_strings(values: object, field: str) -> list[str]:
    if type(values) is not tuple:
        _fail(f"invalid_{field}_tuple")
    if len(values) > _MAX_DIAGNOSTICS:
        _fail(f"{field}_limit_exceeded")
    return [_text(value, field, limit=128) for value in values]


def _load_strings(value: object, field: str) -> tuple[str, ...]:
    return tuple(
        _text(entry, field, limit=128)
        for entry in _sequence(value, field, maximum=_MAX_DIAGNOSTICS)
    )


def _dump_unit(unit: SealedSpeechUnit) -> dict[str, object]:
    if type(unit) is not SealedSpeechUnit:
        _fail("invalid_sealed_speech_unit_type")
    values: dict[str, object] = {
        key: _text(getattr(unit, key), key, limit=limit)
        for key, limit in _UNIT_STRING_LIMITS.items()
        if key not in {"model_revision", "display_text", "spoken_text"}
        and key not in _OPTIONAL_UNIT_KEYS
    }
    # A unit sealed before the evidence pins existed simply has no attribute to
    # write; a unit that does have them is written in full, never truncated.
    for key in sorted(_OPTIONAL_UNIT_KEYS):
        value = getattr(unit, key, None)
        if value is not None:
            values[key] = _text(value, key, limit=_UNIT_STRING_LIMITS[key])
    values["model_revision"] = _optional_text(
        unit.model_revision,
        "model_revision",
        limit=_UNIT_STRING_LIMITS["model_revision"],
    )
    values["display_text"] = _text(
        unit.display_text,
        "display_text",
        limit=_UNIT_STRING_LIMITS["display_text"],
    )
    values["spoken_text"] = _text(
        unit.spoken_text,
        "spoken_text",
        limit=_UNIT_STRING_LIMITS["spoken_text"],
    )
    values["story_revision"] = _integer(unit.story_revision, "story_revision")
    values["segment_index"] = _integer(unit.segment_index, "segment_index")
    values["binding_revision"] = _integer(
        unit.binding_revision,
        "binding_revision",
        minimum=1,
    )
    if type(unit.pronunciation_mappings) is not tuple:
        _fail("invalid_pronunciation_mappings_tuple")
    if len(unit.pronunciation_mappings) > _MAX_PRONUNCIATION_MAPPINGS:
        _fail("pronunciation_mappings_limit_exceeded")
    values["pronunciation_mappings"] = [
        _dump_mapping(
            item,
            display_text=unit.display_text,
            spoken_text=unit.spoken_text,
            pronunciation_revision=unit.pronunciation_revision,
        )
        for item in unit.pronunciation_mappings
    ]
    anchor_ids = [
        item["anchor_id"]
        for item in values["pronunciation_mappings"]  # type: ignore[index]
    ]
    rule_ids = [
        item["rule_id"]
        for item in values["pronunciation_mappings"]  # type: ignore[index]
    ]
    if len(set(anchor_ids)) != len(anchor_ids) or len(set(rule_ids)) != len(rule_ids):
        _fail("duplicate_pronunciation_mapping_identity")
    values["desired"] = _dump_desired(unit.desired)
    values["backend"] = _dump_backend(unit.backend)
    if type(unit.playback) is not EffectivePlaybackPerformance:
        _fail("invalid_playback_performance_type")
    values["playback"] = {
        "volume": _enum(unit.playback.volume, "playback_volume", _VOLUMES),
        "pause_before_ms": _integer(
            unit.playback.pause_before_ms,
            "playback_pause_before_ms",
        ),
    }
    values["unsupported"] = _dump_strings(unit.unsupported, "unsupported")
    values["degradation"] = _dump_strings(unit.degradation, "degradation")
    if not _REQUIRED_UNIT_KEYS <= frozenset(values) <= _UNIT_KEYS:
        _fail("sealed_unit_codec_internal_field_mismatch")
    return values


def _load_unit(value: object) -> SealedSpeechUnit:
    data = _object(value, "sealed_unit", keys=_UNIT_KEYS, optional=_OPTIONAL_UNIT_KEYS)
    strings = {
        key: _text(data[key], key, limit=limit)
        for key, limit in _UNIT_STRING_LIMITS.items()
        if key not in {"model_revision", "display_text", "spoken_text"}
        and key not in _OPTIONAL_UNIT_KEYS
    }
    # Validate every pin that is present, then hand the dataclass only the ones
    # it actually declares. A v2 payload written before the dataclass grew the
    # fields still decodes; one written after must carry all three or fail.
    evidence_pins = {
        key: _text(data[key], key, limit=_UNIT_STRING_LIMITS[key])
        for key in sorted(_OPTIONAL_UNIT_KEYS)
        if key in data
    }
    if evidence_pins and frozenset(evidence_pins) != _OPTIONAL_UNIT_KEYS:
        _fail("incomplete_evidence_pins")
    if evidence_pins and not _OPTIONAL_UNIT_KEYS <= _UNIT_FIELD_NAMES:
        _fail("unsupported_evidence_pins")
    model_revision = _optional_text(
        data["model_revision"],
        "model_revision",
        limit=_UNIT_STRING_LIMITS["model_revision"],
    )
    display_text = _text(
        data["display_text"],
        "display_text",
        limit=_UNIT_STRING_LIMITS["display_text"],
    )
    spoken_text = _text(
        data["spoken_text"],
        "spoken_text",
        limit=_UNIT_STRING_LIMITS["spoken_text"],
    )
    pronunciation_revision = strings["pronunciation_revision"]
    mapping_values = _sequence(
        data["pronunciation_mappings"],
        "pronunciation_mappings",
        maximum=_MAX_PRONUNCIATION_MAPPINGS,
    )
    mappings = tuple(
        _load_mapping(
            item,
            display_text=display_text,
            spoken_text=spoken_text,
            pronunciation_revision=pronunciation_revision,
        )
        for item in mapping_values
    )
    if len({item.anchor_id for item in mappings}) != len(mappings) or len(
        {item.rule_id for item in mappings}
    ) != len(mappings):
        _fail("duplicate_pronunciation_mapping_identity")

    playback_data = _object(data["playback"], "playback_performance", keys=_PLAYBACK_KEYS)
    return SealedSpeechUnit(
        unit_id=strings["unit_id"],
        turn_id=strings["turn_id"],
        story_session_id=strings["story_session_id"],
        story_revision=_integer(data["story_revision"], "story_revision"),
        narrative_block_id=strings["narrative_block_id"],
        segment_index=_integer(data["segment_index"], "segment_index"),
        presentation_identity=strings["presentation_identity"],
        binding_id=strings["binding_id"],
        binding_revision=_integer(
            data["binding_revision"],
            "binding_revision",
            minimum=1,
        ),
        logical_voice_id=strings["logical_voice_id"],
        persona_revision=strings["persona_revision"],
        provider_instance=strings["provider_instance"],
        voice_id=strings["voice_id"],
        voice_revision=strings["voice_revision"],
        model_id=strings["model_id"],
        model_revision=model_revision,
        language=strings["language"],
        performance_plan_id=strings["performance_plan_id"],
        display_text=display_text,
        spoken_text=spoken_text,
        pronunciation_revision=pronunciation_revision,
        pronunciation_mappings=mappings,
        desired=_load_desired(data["desired"]),
        backend=_load_backend(data["backend"]),
        playback=EffectivePlaybackPerformance(
            volume=_enum(playback_data["volume"], "playback_volume", _VOLUMES),
            pause_before_ms=_integer(
                playback_data["pause_before_ms"],
                "playback_pause_before_ms",
            ),
        ),
        unsupported=_load_strings(data["unsupported"], "unsupported"),
        degradation=_load_strings(data["degradation"], "degradation"),
        **evidence_pins,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_object_key")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> object:
    _fail("invalid_json_constant")


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except TypeError, ValueError, UnicodeEncodeError:
        _fail("invalid_payload_value")


class SealedSpeechUnitCodec:
    """Serialize only the known SealedSpeechUnit and nested value types."""

    format_version = _FORMAT_VERSION

    def encode(self, unit: SealedSpeechUnit) -> tuple[str, str]:
        envelope = {
            "format_version": self.format_version,
            "unit": _dump_unit(unit),
        }
        payload_json = _canonical_json(envelope)
        try:
            encoded = payload_json.encode("utf-8")
        except UnicodeEncodeError:
            _fail("invalid_payload_unicode")
        if len(encoded) > _MAX_PAYLOAD_BYTES:
            _fail("payload_size_limit_exceeded")
        return payload_json, hashlib.sha256(encoded).hexdigest()

    def decode(
        self,
        payload_json: str,
        digest: str,
        *,
        expected_turn_id: str | None = None,
        expected_narrative_block_id: str | None = None,
        expected_unit_id: str | None = None,
        expected_binding_id: str | None = None,
    ) -> SealedSpeechUnit:
        if type(payload_json) is not str:
            _fail("payload_json_must_be_string")
        try:
            encoded = payload_json.encode("utf-8")
        except UnicodeEncodeError:
            _fail("invalid_payload_unicode")
        if len(encoded) > _MAX_PAYLOAD_BYTES:
            _fail("payload_size_limit_exceeded")
        if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            _fail("invalid_payload_digest")
        calculated_digest = hashlib.sha256(encoded).hexdigest()
        if not hmac.compare_digest(calculated_digest, digest):
            _fail("payload_digest_mismatch")

        try:
            envelope = json.loads(
                payload_json,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_json_constant,
            )
        except SealedSpeechUnitCodecError:
            raise
        except json.JSONDecodeError, TypeError, ValueError, RecursionError:
            _fail("invalid_payload_json")

        if _canonical_json(envelope) != payload_json:
            _fail("noncanonical_payload_json")
        envelope = _object(envelope, "payload", keys=_ENVELOPE_KEYS)
        version = envelope["format_version"]
        if type(version) is not int or version != self.format_version:
            _fail("unsupported_format_version")
        unit = _load_unit(envelope["unit"])
        _validate_expected_identity(unit, expected_turn_id, "turn_id")
        _validate_expected_identity(
            unit,
            expected_narrative_block_id,
            "narrative_block_id",
        )
        _validate_expected_identity(unit, expected_unit_id, "unit_id")
        _validate_expected_identity(unit, expected_binding_id, "binding_id")
        return unit


def _validate_expected_identity(
    unit: SealedSpeechUnit,
    expected: str | None,
    field: str,
) -> None:
    if expected is None:
        return
    expected_value = _text(expected, f"expected_{field}", limit=256)
    if getattr(unit, field) != expected_value:
        _fail(f"source_identity_mismatch:{field}")
