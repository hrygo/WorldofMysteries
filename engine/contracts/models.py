"""Canonical Pydantic v2 mirrors of ``contracts/schemas/*.schema.json``.

JSON Schema files are the product-contract source of truth.  These models are a
strict Python projection: unknown fields are rejected, required fields remain
required, and enum/nullability rules match the schemas used by Golden 001.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, model_validator


def _json_integer(value: Any) -> Any:
    """JSON Schema integers include numerically integral JSON numbers (e.g. 1.0)."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


JsonInteger = Annotated[int, BeforeValidator(_json_integer)]
JsonNumber = StrictInt | StrictFloat


class SchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    _unique_fields: ClassVar[tuple[str, ...]] = ()
    _nonnullable_optional_fields: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null_for_nonnullable_optional_fields(cls, value: Any) -> Any:
        if isinstance(value, dict):
            for name in cls._nonnullable_optional_fields:
                if name in value and value[name] is None:
                    raise ValueError(f"{name} may be omitted but must not be null")
        return value

    @model_validator(mode="after")
    def unique_items_match_json_schema(self) -> "SchemaModel":
        for name in self._unique_fields:
            values = getattr(self, name, None)
            if values is not None and len(values) != len(set(values)):
                raise ValueError(f"{name} must contain unique items")
        return self


class ContractBase(SchemaModel):
    schema_version: Literal["1.0"]


class CharacterKind(StrEnum):
    CANONICAL = "canonical"
    ORIGINAL = "original"
    NPC = "npc"


class InputMode(StrEnum):
    VOICE = "voice"
    TEXT = "text"
    SUGGESTION = "suggestion"


class AdherenceType(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    REINTERPRET = "reinterpret"
    REJECT = "reject"


class EndingType(StrEnum):
    PARTIAL_TRUTH = "partial_truth"
    COMPLETE_TRUTH = "complete_truth"
    FATAL_DISTORTION = "fatal_distortion"
    CONTAINMENT_FAILURE = "containment_failure"


class SecretState(StrEnum):
    HIDDEN = "hidden"
    SUSPECTED = "suspected"
    PARTIAL = "partial"
    REVEALED = "revealed"


class KnowledgeStatus(StrEnum):
    CONFIRMED = "confirmed"
    PROBABLE = "probable"
    UNCERTAIN = "uncertain"
    CONTRADICTED = "contradicted"
    REVOKED = "revoked"


class KnowledgeSourceType(StrEnum):
    OBSERVATION = "observation"
    CONVERSATION = "conversation"
    DOCUMENT = "document"
    INVESTIGATION = "investigation"
    ABILITY = "ability"
    ORGANIZATION = "organization"
    CANON_EVENT = "canon_event"
    INFERENCE = "inference"
    MEMORY_RECALL = "memory_recall"


# Character -----------------------------------------------------------------
class CharacterIdentity(SchemaModel):
    display_name: str = Field(min_length=1)
    age: JsonInteger | None = Field(default=None, ge=0)
    occupation: str | None = None
    pathway_id: str | None = None
    sequence: JsonInteger | None = Field(default=None, ge=0, le=9)


class SpeechStyle(SchemaModel):
    tone: str | None = None
    verbosity: str | None = None
    formality: str | None = None
    humor: str | None = None
    metaphor: str | None = None


class CharacterCore(SchemaModel):
    _unique_fields = ("decision_style", "hard_boundaries")
    _nonnullable_optional_fields = ("speech_style",)

    traits: dict[str, str]
    decision_style: list[str]
    values: dict[str, str]
    hard_boundaries: list[str]
    speech_style: SpeechStyle | None = None


class CharacterGoals(SchemaModel):
    long: str | None = None
    medium: str | None = None
    immediate: str | None = None


class CharacterEmotion(SchemaModel):
    _unique_fields = ("secondary", "cause_ids")
    _nonnullable_optional_fields = ("intensity", "secondary", "cause_ids")

    primary: str | None = None
    intensity: JsonNumber | None = Field(default=None, ge=0, le=1)
    secondary: list[str] | None = None
    cause_ids: list[str] | None = None


class CharacterCondition(SchemaModel):
    injury: str | None = None
    fatigue: JsonNumber | None = Field(default=None, ge=0, le=1)
    spirituality: JsonNumber | None = None
    corruption: JsonNumber | None = Field(default=None, ge=0, le=1)


class CharacterState(SchemaModel):
    location_id: str | None
    goals: CharacterGoals
    emotion: CharacterEmotion | None = None
    condition: CharacterCondition | None = None


class Character(ContractBase):
    id: str = Field(min_length=1)
    kind: CharacterKind
    identity: CharacterIdentity
    canon_anchor: dict[str, Any] | None = None
    core: CharacterCore
    state: CharacterState
    revision: JsonInteger = Field(ge=0)


# World Snapshot -------------------------------------------------------------
class WorldLocation(SchemaModel):
    _unique_fields = ("rooms", "discovered_rooms")
    _nonnullable_optional_fields = ("rooms", "discovered_rooms")

    id: str = Field(min_length=1)
    display_name: str | None = None
    city: str | None = None
    district: str | None = None
    open: StrictBool | None = None
    closes_at: str | None = None
    rooms: list[str] | None = None
    discovered_rooms: list[str] | None = None


class WorldSnapshot(ContractBase):
    world_id: str
    worldline_id: str
    world_time: str
    revision: JsonInteger = Field(ge=0)
    location: WorldLocation
    weather: str | None = None


# Player Advice --------------------------------------------------------------
class PlayerAdvice(ContractBase):
    _unique_fields = ("secondary_intents", "proposed_actions")
    _nonnullable_optional_fields = ("secondary_intents",)

    id: str
    turn_id: str
    raw_input: str = Field(min_length=1)
    input_mode: InputMode
    primary_intent: str
    secondary_intents: list[str] | None = None
    proposed_actions: list[str]
    risk_preference: str | None = None
    confidence: JsonNumber = Field(ge=0, le=1)


# Action Intent --------------------------------------------------------------
class IntentAction(SchemaModel):
    _unique_fields = ("target_ids",)
    _nonnullable_optional_fields = ("target_ids", "parameters")

    type: str = Field(min_length=1)
    purpose: str | None = None
    target_ids: list[str] | None = None
    parameters: dict[str, Any] | None = None


class ExpectedCost(SchemaModel):
    resource: str
    amount: JsonNumber
    unit: str | None = None


class PerceivedRisk(SchemaModel):
    risk: str
    level: JsonNumber = Field(ge=0, le=1)


class ActionIntent(ContractBase):
    _unique_fields = ("evidence_ids",)
    _nonnullable_optional_fields = ("expected_costs", "perceived_risks")

    id: str
    turn_id: str
    character_id: str
    intent: str
    adherence: AdherenceType
    actions: list[IntentAction] = Field(min_length=1)
    reason_summary: str | None = None
    speech_intent: str | None = None
    evidence_ids: list[str]
    expected_costs: list[ExpectedCost] | None = None
    perceived_risks: list[PerceivedRisk] | None


# Beat Plan ------------------------------------------------------------------
class WorldEventOpportunity(SchemaModel):
    _unique_fields = ("actor_ids", "target_ids")
    _nonnullable_optional_fields = ("actor_ids", "target_ids")

    event_type: str = Field(min_length=1)
    actor_ids: list[str] | None = None
    target_ids: list[str] | None = None
    purpose: str | None = None


class NPCIntent(SchemaModel):
    character_id: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    purpose: str | None = None


class BeatPlan(ContractBase):
    _unique_fields = ("reveal_ids", "constraints")
    _nonnullable_optional_fields = ("world_event_opportunities", "reveal_ids", "npc_intents", "constraints")

    id: str
    story_session_id: str
    source_story_revision: JsonInteger = Field(ge=0)
    beat_type: str
    dramatic_goal: str
    world_event_opportunities: list[WorldEventOpportunity] | None = None
    reveal_ids: list[str] | None = None
    npc_intents: list[NPCIntent] | None = None
    tension_delta: str | JsonNumber | None = None
    constraints: list[str] | None = None
    intervention_required: StrictBool


# Narrative Block ------------------------------------------------------------
class NarrativeSegment(SchemaModel):
    type: Literal["narration", "character", "transition"]
    speaker_id: str | None = None
    text: str
    speech_intent: str | None = None


class AmbientCue(SchemaModel):
    _nonnullable_optional_fields = ("action",)
    cue: str = Field(min_length=1)
    action: Literal["start", "continue", "duck", "stop"] | None = None
    level: JsonNumber | None = Field(default=None, ge=0, le=1)


class SFXCue(SchemaModel):
    cue: str = Field(min_length=1)
    at_ms: JsonInteger | None = Field(default=None, ge=0)


class NarrativeBlock(ContractBase):
    _nonnullable_optional_fields = ("ambient_cues", "sfx_cues")

    id: str
    story_session_id: str
    source_story_revision: JsonInteger = Field(ge=0)
    scene_id: str | None = None
    segments: list[NarrativeSegment]
    ambient_cues: list[AmbientCue] | None = None
    sfx_cues: list[SFXCue] | None = None
    source_state_delta_id: str | None = None


# State Delta -----------------------------------------------------------------
class StatePatch(SchemaModel):
    path: str = Field(min_length=1)
    operation: Literal["set", "remove", "increment"]
    value: Any | None = None


class CharacterPatch(SchemaModel):
    path: str = Field(min_length=1)
    operation: Literal["set", "remove", "increment", "add_to_set", "remove_from_set"]
    value: Any | None = None


class StoryDelta(SchemaModel):
    _unique_fields = ("clue_ids_add", "clue_ids_remove")
    _nonnullable_optional_fields = ("clue_ids_add", "clue_ids_remove", "secret_state_updates", "local_state_patches")

    scene_id: str | None = None
    world_time_delta_minutes: JsonNumber | None = None
    clue_ids_add: list[str] | None
    clue_ids_remove: list[str] | None = None
    secret_state_updates: dict[str, SecretState] | None = None
    local_state_patches: list[StatePatch] | None = None


class CharacterDelta(SchemaModel):
    _unique_fields = ("evidence_ids",)
    character_id: str = Field(min_length=1)
    patches: list[CharacterPatch]
    evidence_ids: list[str]


class RelationshipDimensions(SchemaModel):
    _nonnullable_optional_fields = ("trust", "affection", "respect", "fear", "dependency", "hostility")
    trust: JsonNumber | None = None
    affection: JsonNumber | None = None
    respect: JsonNumber | None = None
    fear: JsonNumber | None = None
    dependency: JsonNumber | None = None
    hostility: JsonNumber | None = None


class RelationshipDelta(SchemaModel):
    _unique_fields = ("evidence_ids",)
    from_character_id: str = Field(min_length=1)
    to_character_id: str = Field(min_length=1)
    dimension_deltas: RelationshipDimensions
    evidence_ids: list[str]


class KnowledgeCandidate(SchemaModel):
    character_id: str = Field(min_length=1)
    proposition_id: str = Field(min_length=1)
    certainty: JsonNumber = Field(ge=0, le=1)
    source_ref: str = Field(min_length=1)
    status: KnowledgeStatus


class WorldEventVisibility(SchemaModel):
    _unique_fields = ("known_by", "possibly_known_by")
    _nonnullable_optional_fields = ("known_by", "possibly_known_by")
    public: StrictBool
    known_by: list[str] | None = None
    possibly_known_by: list[str] | None


class WorldEventCandidate(SchemaModel):
    _unique_fields = ("actors", "targets")
    event_type: str = Field(min_length=1)
    actors: list[str]
    targets: list[str]
    payload: dict[str, Any]
    visibility: WorldEventVisibility


class StateDelta(ContractBase):
    _unique_fields = ("evidence_ids",)
    _nonnullable_optional_fields = ("relationship_deltas", "knowledge_candidates", "pressure_delta")

    id: str
    turn_id: str
    outcome: Literal[
        "clean_success", "success_with_cost", "partial_success", "complication",
        "failure", "catastrophic_failure"
    ]
    story_delta: StoryDelta
    character_deltas: list[CharacterDelta]
    relationship_deltas: list[RelationshipDelta] | None = None
    knowledge_candidates: list[KnowledgeCandidate] | None = None
    pressure_delta: dict[str, JsonNumber] | None = None
    world_event_candidates: list[WorldEventCandidate]
    evidence_ids: list[str]


# Episode -----------------------------------------------------------------
class EpisodeEnding(SchemaModel):
    type: str
    main_problem: str | None = None


class Episode(ContractBase):
    _unique_fields = (
        "protagonist_ids", "narrative_block_ids", "discovered_clue_ids", "unresolved_threads",
        "character_event_ids", "relationship_event_ids", "knowledge_change_ids", "memory_ids", "world_event_ids",
    )
    _nonnullable_optional_fields = (
        "narrative_block_ids", "discovered_clue_ids", "worldline_divergence", "character_event_ids",
        "relationship_event_ids", "knowledge_change_ids", "memory_ids", "world_event_ids",
    )

    id: str
    world_id: str
    worldline_id: str
    story_seed_id: str | None = None
    protagonist_ids: list[str]
    title: str
    start_world_time: str | None
    end_world_time: str | None = None
    ending: EpisodeEnding
    secret_states: dict[str, SecretState]
    narrative_block_ids: list[str] | None = None
    discovered_clue_ids: list[str] | None = None
    unresolved_threads: list[str]
    worldline_divergence: StrictBool | None = None
    character_event_ids: list[str] | None = None
    relationship_event_ids: list[str] | None = None
    knowledge_change_ids: list[str] | None = None
    memory_ids: list[str] | None = None
    world_event_ids: list[str] | None = None


# Character Knowledge ---------------------------------------------------------
class KnowledgeSource(SchemaModel):
    type: KnowledgeSourceType
    ref: str
    reliability: JsonNumber | None = Field(default=None, ge=0, le=1)


class CharacterKnowledge(ContractBase):
    id: str
    character_id: str
    worldline_id: str
    proposition_id: str
    certainty: JsonNumber = Field(ge=0, le=1)
    source: KnowledgeSource
    acquired_world_time: str | None = None
    status: KnowledgeStatus
    revision: JsonInteger = Field(ge=0)
