"""Core Domain and Story Contract Models (Pydantic v2).

All models are strictly aligned with contracts/schemas/*.schema.json.
"""

from enum import StrEnum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------
# Enumerations
# ---------------------------------------------------------
class CharacterKind(StrEnum):
    CANONICAL = "canonical"
    ORIGINAL = "original"
    NPC = "npc"


class InputMode(StrEnum):
    TEXT = "text"
    VOICE = "voice"


class AdherenceType(StrEnum):
    FULL = "full"
    REINTERPRET = "reinterpret"
    REFUSE = "refuse"
    PARTIAL = "partial"


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


# ---------------------------------------------------------
# Common & Base
# ---------------------------------------------------------
class ContractBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    schema_version: str = "1.0"


# ---------------------------------------------------------
# Character Models (contracts/schemas/character.schema.json)
# ---------------------------------------------------------
class CharacterIdentity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    display_name: str = Field(min_length=1)
    age: Optional[int] = None
    occupation: Optional[str] = None
    pathway_id: Optional[str] = None
    sequence: Optional[int] = Field(default=None, ge=0, le=9)


class CharacterCore(BaseModel):
    model_config = ConfigDict(extra="ignore")
    traits: dict[str, str] = Field(default_factory=dict)
    decision_style: list[str] = Field(default_factory=list)
    values: dict[str, str] = Field(default_factory=dict)
    hard_boundaries: list[str] = Field(default_factory=list)
    speech_style: Optional[dict[str, Any]] = None


class CharacterGoals(BaseModel):
    model_config = ConfigDict(extra="ignore")
    long: Optional[str] = None
    medium: Optional[str] = None
    immediate: Optional[str] = None


class CharacterEmotion(BaseModel):
    model_config = ConfigDict(extra="ignore")
    primary: Optional[str] = None
    intensity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    secondary: list[str] = Field(default_factory=list)
    cause_ids: list[str] = Field(default_factory=list)


class CharacterCondition(BaseModel):
    model_config = ConfigDict(extra="ignore")
    injury: Optional[str] = None
    fatigue: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    spirituality: Optional[float] = None
    corruption: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class CharacterState(BaseModel):
    model_config = ConfigDict(extra="ignore")
    location_id: Optional[str] = None
    goals: CharacterGoals
    emotion: Optional[CharacterEmotion] = None
    condition: Optional[CharacterCondition] = None


class Character(ContractBase):
    id: str = Field(min_length=1)
    kind: CharacterKind
    identity: CharacterIdentity
    canon_anchor: Optional[dict[str, Any]] = None
    core: CharacterCore
    state: CharacterState
    revision: int = Field(ge=0)


# ---------------------------------------------------------
# World Models (contracts/schemas/world_snapshot.schema.json)
# ---------------------------------------------------------
class WorldLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    city: Optional[str] = None
    district: Optional[str] = None
    open: Optional[bool] = None
    closes_at: Optional[str] = None
    rooms: list[str] = Field(default_factory=list)
    discovered_rooms: list[str] = Field(default_factory=list)


class WorldSnapshot(ContractBase):
    world_id: str
    worldline_id: str
    world_time: Optional[str] = None
    revision: int = Field(ge=0)
    location: Optional[WorldLocation] = None
    weather: Optional[str] = None


# ---------------------------------------------------------
# Player Advice (contracts/schemas/player_advice.schema.json)
# ---------------------------------------------------------
class PlayerAdvice(ContractBase):
    id: str
    turn_id: Optional[str] = None
    raw_input: str
    input_mode: InputMode = InputMode.TEXT
    primary_intent: str
    secondary_intents: list[str] = Field(default_factory=list)
    proposed_actions: list[str] = Field(default_factory=list)
    risk_preference: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


# ---------------------------------------------------------
# Action Intent (contracts/schemas/action_intent.schema.json)
# ---------------------------------------------------------
class ActionIntent(ContractBase):
    id: str
    turn_id: str
    character_id: str
    primary_intent: str
    concrete_actions: list[str] = Field(default_factory=list)
    adherence_to_advice: AdherenceType = AdherenceType.FULL
    divergence_reason: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


# ---------------------------------------------------------
# Beat Plan (contracts/schemas/beat_plan.schema.json)
# ---------------------------------------------------------
class Beat(BaseModel):
    model_config = ConfigDict(extra="ignore")
    beat_id: str
    kind: str
    tension: float = Field(ge=0.0, le=1.0)
    focus: str
    details: Optional[dict[str, Any]] = None


class BeatPlan(ContractBase):
    id: str
    turn_id: str
    narrative_phase: str
    target_pace: str
    beats: list[Beat] = Field(default_factory=list)


# ---------------------------------------------------------
# Narrative Block (contracts/schemas/narrative_block.schema.json)
# ---------------------------------------------------------
class NarrativeBlock(ContractBase):
    id: str
    turn_id: str
    text: str
    speaker_id: Optional[str] = None
    point_of_view: Optional[str] = None
    tone: Optional[str] = None
    audio_asset_id: Optional[str] = None


# ---------------------------------------------------------
# State Delta (contracts/schemas/state_delta.schema.json)
# ---------------------------------------------------------
class StateDelta(ContractBase):
    id: str
    turn_id: str
    world_changes: dict[str, Any] = Field(default_factory=dict)
    character_changes: dict[str, Any] = Field(default_factory=dict)
    discovered_clues: list[str] = Field(default_factory=list)
    secret_state_updates: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------
# Episode (contracts/schemas/episode.schema.json)
# ---------------------------------------------------------
class EpisodeEnding(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: str
    main_problem: Optional[str] = None


class Episode(ContractBase):
    id: str
    world_id: str
    worldline_id: str
    story_seed_id: str
    protagonist_ids: list[str]
    title: str
    start_world_time: Optional[str] = None
    end_world_time: Optional[str] = None
    ending: EpisodeEnding
    secret_states: dict[str, str] = Field(default_factory=dict)
    narrative_block_ids: list[str] = Field(default_factory=list)
    discovered_clue_ids: list[str] = Field(default_factory=list)
    unresolved_threads: list[str] = Field(default_factory=list)
    worldline_divergence: bool = False
    character_event_ids: list[str] = Field(default_factory=list)
    relationship_event_ids: list[str] = Field(default_factory=list)
    knowledge_change_ids: list[str] = Field(default_factory=list)
    memory_ids: list[str] = Field(default_factory=list)
    world_event_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------
# Knowledge (contracts/schemas/character_knowledge.schema.json)
# ---------------------------------------------------------
class KnowledgeSource(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: KnowledgeSourceType
    ref: str
    reliability: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class CharacterKnowledge(ContractBase):
    id: str
    character_id: str
    worldline_id: str
    proposition_id: str
    certainty: float = Field(ge=0.0, le=1.0)
    source: KnowledgeSource
    acquired_world_time: Optional[str] = None
    status: KnowledgeStatus
    revision: int = Field(ge=0)
