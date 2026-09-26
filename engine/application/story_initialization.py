"""Trusted Golden 001 content validation and initial Story Session construction.

This module is deliberately storage-agnostic. It accepts a validated
``TrustedScenarioBundle`` from a trusted source adapter, verifies its content
digest and cross-file identities, then constructs the turn=0 session and the
frozen bootstrap that later persistence must write atomically with the open.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from contracts import (
    ActionIntent,
    Character,
    CharacterKnowledge,
    InputMode,
    PlayerAdvice,
    StorySession,
    StorySessionStatus,
    StoryState,
    WorldSnapshot,
)

GOLDEN_SCENARIO_ID = "golden_001"
GOLDEN_CONTENT_VERSION = "1"
GOLDEN_POLICY_VERSION = "golden001-opening-policy"
ENGINEERING_NAMESPACE = "engineering-golden001"
SUPPORTED_ADVICE = "先别问医生病人的事，我想看看他的反应。"
SCENE_ID = "consultation_room"
SCENE_DISPLAY_NAME = "哈维诊所 · 诊室"
SCENARIO_TITLE = "不存在的预约"
DOCTOR_ACTOR_ID = "npc_doctor_morris"
_MAX_TEXT = 256
_HEX_DIGEST = r"^[0-9a-f]{64}$"


class StoryInitializationError(RuntimeError):
    """Stable, non-sensitive initialization failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ScenarioPresentation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_title: str = Field(min_length=1, max_length=_MAX_TEXT)
    scene_display_name: str = Field(min_length=1, max_length=_MAX_TEXT)
    clue_display_names: dict[str, str]


class StorySessionBootstrap(BaseModel):
    """Immutable product content bound to a session at first open."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    scenario_id: str = Field(min_length=1, max_length=_MAX_TEXT)
    content_version: str = Field(min_length=1, max_length=_MAX_TEXT)
    content_digest: str = Field(pattern=_HEX_DIGEST)
    policy_version: str = Field(min_length=1, max_length=_MAX_TEXT)
    seed: dict[str, Any]
    world: dict[str, Any]
    character: dict[str, Any]
    knowledge: list[dict[str, Any]]
    presentation: ScenarioPresentation
    advice_template: dict[str, Any]
    action_intent_template: dict[str, Any]
    initial_session: StorySession


class TrustedScenarioBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1, max_length=_MAX_TEXT)
    content_version: str = Field(min_length=1, max_length=_MAX_TEXT)
    content_digest: str = Field(pattern=_HEX_DIGEST)
    policy_version: str = Field(min_length=1, max_length=_MAX_TEXT)
    seed: dict[str, Any]
    world: WorldSnapshot
    character: Character
    knowledge: list[CharacterKnowledge]
    presentation: ScenarioPresentation
    advice_template: PlayerAdvice
    action_intent_template: ActionIntent


class ScenarioSourcePort(Protocol):
    async def load(self, scenario_id: str) -> TrustedScenarioBundle: ...


class InitializedSessionPort(Protocol):
    async def load_bootstrap(self, session_id: str) -> StorySessionBootstrap | None: ...


@dataclass(frozen=True, slots=True)
class InitializedStorySession:
    bootstrap: StorySessionBootstrap

    @property
    def initial_session(self) -> StorySession:
        return self.bootstrap.initial_session


class StoryInitializationService:
    """Validate trusted content and build a deterministic turn=0 session."""

    def __init__(self, source: ScenarioSourcePort) -> None:
        self._source = source

    async def initialize(
        self,
        *,
        scenario_id: str,
        open_request_id: str,
    ) -> InitializedStorySession:
        _require_text(scenario_id, "unsupported_scenario")
        _require_text(open_request_id, "invalid_open_identity")
        if scenario_id != GOLDEN_SCENARIO_ID:
            raise StoryInitializationError("unsupported_scenario")

        loaded = await self._source.load(scenario_id)
        if not isinstance(loaded, TrustedScenarioBundle):
            raise StoryInitializationError("invalid_trusted_bundle")
        bundle = loaded.model_copy(deep=True)

        computed_digest = _content_digest(bundle)
        if bundle.content_digest != computed_digest:
            raise StoryInitializationError("content_digest_mismatch")

        session_id = _session_id(open_request_id)
        initial_session = _build_initial_session(bundle, session_id)
        bootstrap = StorySessionBootstrap.model_validate(
            {
                "schema_version": "1.0",
                "scenario_id": bundle.scenario_id,
                "content_version": bundle.content_version,
                "content_digest": bundle.content_digest,
                "policy_version": bundle.policy_version,
                "seed": bundle.seed,
                "world": bundle.world.model_dump(
                    mode="json", exclude_none=False, exclude_unset=True
                ),
                "character": bundle.character.model_dump(
                    mode="json", exclude_none=False, exclude_unset=True
                ),
                "knowledge": [
                    item.model_dump(
                        mode="json", exclude_none=False, exclude_unset=True
                    )
                    for item in bundle.knowledge
                ],
                "presentation": bundle.presentation.model_dump(
                    mode="json", exclude_none=False, exclude_unset=True
                ),
                "advice_template": bundle.advice_template.model_dump(
                    mode="json", exclude_none=False, exclude_unset=True
                ),
                "action_intent_template": bundle.action_intent_template.model_dump(
                    mode="json", exclude_none=False, exclude_unset=True
                ),
                "initial_session": initial_session,
            }
        )
        return InitializedStorySession(bootstrap=bootstrap)


def _build_initial_session(
    bundle: TrustedScenarioBundle,
    session_id: str,
) -> StorySession:
    seed = bundle.seed
    world = bundle.world
    character = bundle.character

    if bundle.scenario_id != GOLDEN_SCENARIO_ID:
        raise StoryInitializationError("unsupported_scenario")
    if bundle.content_version != GOLDEN_CONTENT_VERSION:
        raise StoryInitializationError("unsupported_content_version")
    if bundle.policy_version != GOLDEN_POLICY_VERSION:
        raise StoryInitializationError("unsupported_policy_version")

    seed_id = _require_text(seed.get("id"), "invalid_seed")
    if seed.get("schema_version") != "1.0":
        raise StoryInitializationError("invalid_seed")
    protagonist_id = _require_text(seed.get("protagonist_id"), "invalid_seed")
    if protagonist_id != character.id:
        raise StoryInitializationError("protagonist_mismatch")
    if world.world_id != "world_001" or world.worldline_id != "wl_main":
        raise StoryInitializationError("unsupported_world")
    setting = seed.get("setting")
    if not isinstance(setting, dict):
        raise StoryInitializationError("invalid_seed")
    if setting.get("location_id") != world.location.id:
        raise StoryInitializationError("location_mismatch")
    start_world_time = _require_text(
        setting.get("start_world_time"), "invalid_world_time"
    )
    if world.world_time != start_world_time:
        raise StoryInitializationError("world_time_mismatch")
    if (
        world.location.rooms is None
        or SCENE_ID not in world.location.rooms
        or world.location.discovered_rooms is None
        or SCENE_ID not in world.location.discovered_rooms
    ):
        raise StoryInitializationError("unsupported_scene")

    actor_ids = _unique_ids(seed.get("actor_ids"), "invalid_actor_ids")
    if protagonist_id not in actor_ids or DOCTOR_ACTOR_ID not in actor_ids:
        raise StoryInitializationError("invalid_actor_ids")

    knowledge = _validate_knowledge(
        bundle.knowledge,
        protagonist_id=protagonist_id,
        worldline_id=world.worldline_id,
        opening_world_time=start_world_time,
    )
    if len({item.id for item in knowledge}) != len(knowledge):
        raise StoryInitializationError("duplicate_knowledge_id")

    secret_states = _secret_states(seed)
    pressure = _pressure(seed)
    clue_ids = _unique_ids(
        [
            item.get("id")
            for item in seed.get("clues", [])
            if isinstance(item, dict)
        ],
        "invalid_clues",
    )
    if "clue_doctor_pause" not in clue_ids:
        raise StoryInitializationError("clue_missing")

    _validate_presentation(bundle.presentation)
    if bundle.advice_template.raw_input != SUPPORTED_ADVICE:
        raise StoryInitializationError("unsupported_advice")
    if bundle.advice_template.input_mode is not InputMode.TEXT:
        raise StoryInitializationError("unsupported_input_mode")
    if bundle.action_intent_template.character_id != protagonist_id:
        raise StoryInitializationError("action_intent_template_mismatch")

    try:
        state = StoryState.model_validate(
            {
                "schema_version": "1.0",
                "story_session_id": session_id,
                "revision": 0,
                "turn": 0,
                "phase": "discovery",
                "scene": {
                    "id": SCENE_ID,
                    "location_id": world.location.id,
                    "active_character_ids": [protagonist_id, DOCTOR_ACTOR_ID],
                },
                "world_time": start_world_time,
                "protagonist_goal": character.state.goals.immediate,
                "active_conflicts": [
                    _require_text(seed.get("surface_problem"), "invalid_seed")
                ],
                "discovered_clue_ids": [],
                "secret_states": secret_states,
                "commitments": {"hard_ids": [], "soft_ids": []},
                "local_state": {},
                "pressure": pressure,
                "last_state_delta_id": None,
            }
        )
        return StorySession.model_validate(
            {
                "schema_version": "1.0",
                "id": session_id,
                "world_id": world.world_id,
                "worldline_id": world.worldline_id,
                "protagonist_id": protagonist_id,
                "story_seed_id": seed_id,
                "base_revisions": {
                    "world": world.revision,
                    "character": character.revision,
                    "story": 0,
                },
                "story_state": state.model_dump(mode="json", exclude_none=True),
                "status": StorySessionStatus.ACTIVE.value,
            }
        )
    except (TypeError, ValueError, ValidationError):
        raise StoryInitializationError("invalid_initial_session") from None


def _validate_knowledge(
    knowledge: list[CharacterKnowledge],
    *,
    protagonist_id: str,
    worldline_id: str,
    opening_world_time: str,
) -> list[CharacterKnowledge]:
    for item in knowledge:
        if item.character_id != protagonist_id:
            raise StoryInitializationError("knowledge_owner_mismatch")
        if item.worldline_id != worldline_id:
            raise StoryInitializationError("knowledge_worldline_mismatch")
        if (
            item.acquired_world_time is not None
            and item.acquired_world_time > opening_world_time
        ):
            raise StoryInitializationError("knowledge_after_opening")
    return knowledge


def _secret_states(seed: dict[str, Any]) -> dict[str, str]:
    secrets = seed.get("secrets")
    if not isinstance(secrets, list) or not secrets:
        raise StoryInitializationError("invalid_secrets")
    states: dict[str, str] = {}
    for item in secrets:
        if not isinstance(item, dict):
            raise StoryInitializationError("invalid_secrets")
        secret_id = _require_text(item.get("id"), "invalid_secrets")
        initial_state = _require_text(item.get("initial_state"), "invalid_secrets")
        if initial_state not in {"hidden", "suspected", "partial", "revealed"}:
            raise StoryInitializationError("invalid_secrets")
        if secret_id in states:
            raise StoryInitializationError("duplicate_secret_id")
        states[secret_id] = initial_state
    return states


def _pressure(seed: dict[str, Any]) -> dict[str, float]:
    pressures = seed.get("pressures")
    if not isinstance(pressures, list) or not pressures:
        raise StoryInitializationError("invalid_pressures")
    result: dict[str, float] = {}
    for item in pressures:
        if not isinstance(item, dict):
            raise StoryInitializationError("invalid_pressures")
        pressure_id = _require_text(item.get("id"), "invalid_pressures")
        value = item.get("initial_value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise StoryInitializationError("invalid_pressures")
        if pressure_id in result:
            raise StoryInitializationError("duplicate_pressure_id")
        result[pressure_id] = float(value)
    return result


def _validate_presentation(presentation: ScenarioPresentation) -> None:
    if (
        presentation.scenario_title != SCENARIO_TITLE
        or presentation.scene_display_name != SCENE_DISPLAY_NAME
        or presentation.clue_display_names != {"clue_doctor_pause": "医生的停顿"}
    ):
        raise StoryInitializationError("unsupported_presentation")


def _session_id(open_request_id: str) -> str:
    digest = hashlib.sha256(
        (
            "story-open/v1\0"
            f"{ENGINEERING_NAMESPACE}\0"
            f"{GOLDEN_SCENARIO_ID}\0"
            f"{open_request_id}"
        ).encode("utf-8")
    ).hexdigest()
    return f"session_{digest[:32]}"


def _content_digest(bundle: TrustedScenarioBundle) -> str:
    payload = {
        "scenario_id": bundle.scenario_id,
        "content_version": bundle.content_version,
        "policy_version": bundle.policy_version,
        "seed": bundle.seed,
        "world": bundle.world.model_dump(
            mode="json", exclude_none=False, exclude_unset=True
        ),
        "character": bundle.character.model_dump(
            mode="json", exclude_none=False, exclude_unset=True
        ),
        "knowledge": [
            item.model_dump(mode="json", exclude_none=False, exclude_unset=True)
            for item in bundle.knowledge
        ],
        "presentation": bundle.presentation.model_dump(
            mode="json", exclude_none=False, exclude_unset=True
        ),
        "advice_template": bundle.advice_template.model_dump(
            mode="json", exclude_none=False, exclude_unset=True
        ),
        "action_intent_template": bundle.action_intent_template.model_dump(
            mode="json", exclude_none=False, exclude_unset=True
        ),
    }
    try:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise StoryInitializationError("invalid_trusted_bundle") from None
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _unique_ids(values: Any, code: str) -> list[str]:
    if not isinstance(values, list):
        raise StoryInitializationError(code)
    result: list[str] = []
    for value in values:
        result.append(_require_text(value, code))
    if len(set(result)) != len(result):
        raise StoryInitializationError(code)
    return result


def _require_text(value: object, code: str, *, limit: int = _MAX_TEXT) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or "\x00" in value
    ):
        raise StoryInitializationError(code)
    return value
