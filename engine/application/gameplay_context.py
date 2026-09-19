"""Gameplay-aware composition of trusted Domain context for AI stages.

This module owns no Domain truth and performs no database access.  It is the
application-layer seam where existing/future Lore, World, Character, Story and
Memory services expose *read-only* context facets against one consistent snapshot.
The separate AuthorizationPort remains the only authority that can grant evidence.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from .context_plan import (
    AuthorizationView,
    ContextError,
    ContextInput,
    ContextScope,
    Evidence,
    WorkerProfile,
    canonical_json,
    digest,
    identifier,
    natural,
    parse_json,
)


class GameplayMode(str, Enum):
    # Deterministic/read-model experiences: best model call is no model call.
    WORLD_HOME = "world_home"
    CARD_BROWSE = "card_browse"
    CHARACTER_DOSSIER = "character_dossier"
    LOCATION_VIEW = "location_view"
    RELATIONSHIP_VIEW = "relationship_view"
    STORY_BOOK_REPLAY = "story_book_replay"
    WORLDLINE_COMPARE = "worldline_compare"

    # LLM-backed experiences.
    WORLD_OBSERVATION_QA = "world_observation_qa"
    CHARACTER_GENESIS = "character_genesis"
    STORY_GENESIS = "story_genesis"
    ADVICE_INTERPRETATION = "advice_interpretation"
    CHARACTER_REASONING = "character_reasoning"
    STORY_DIRECTION = "story_direction"
    NARRATIVE_COMPILATION = "narrative_compilation"
    CLOSURE = "closure"
    MEMORY_DISTILLATION = "memory_distillation"
    WORLD_PULSE = "world_pulse"
    TIME_SKIP = "time_skip"
    HIGH_ORDER_INTERVENTION = "high_order_intervention"


class ModelUse(str, Enum):
    NONE = "none"
    STRUCTURED = "structured"
    BOUNDED_AGENT = "bounded_agent"


class ContextFacet(str, Enum):
    LORE = "lore"
    WORLD = "world"
    CHARACTER = "character"
    STORY = "story"
    MEMORY = "memory"


class CacheHorizon(str, Enum):
    NONE = "none"
    BURST = "burst"
    WORLD = "world"
    CHARACTER = "character"
    SESSION = "session"
    SCENE = "scene"
    EPISODE = "episode"


class ProviderCachePreference(str, Enum):
    AVOID_EXPLICIT = "avoid_explicit"
    HOT_ONLY = "hot_only"
    PREFER_EXPLICIT = "prefer_explicit"


@dataclass(frozen=True)
class GameplayRecipe:
    mode: GameplayMode
    model_use: ModelUse
    consumer: str | None
    facets: tuple[ContextFacet, ...] = ()
    cache_horizon: CacheHorizon = CacheHorizon.NONE
    provider_cache: ProviderCachePreference = ProviderCachePreference.AVOID_EXPLICIT
    expected_reuse: int = 1
    epoch_dimensions: tuple[str, ...] = ()
    requires_subject: bool = False
    requires_session: bool = False

    def __post_init__(self) -> None:
        if self.model_use == ModelUse.NONE:
            if self.consumer is not None or self.facets or self.cache_horizon != CacheHorizon.NONE:
                raise ValueError("invalid_no_model_recipe")
        elif self.consumer is None or not self.facets:
            raise ValueError("invalid_model_recipe")
        if type(self.expected_reuse) is not int or self.expected_reuse < 1:
            raise ValueError("invalid_expected_reuse")
        if self.consumer is not None:
            identifier(self.consumer)
        for value in self.epoch_dimensions:
            identifier(value)


# Product-driven defaults.  These are execution/cache recipes, not gameplay truth.
_RECIPES: dict[GameplayMode, GameplayRecipe] = {
    # Projection/replay paths should not spend model latency at all.
    GameplayMode.WORLD_HOME: GameplayRecipe(GameplayMode.WORLD_HOME, ModelUse.NONE, None),
    GameplayMode.CARD_BROWSE: GameplayRecipe(GameplayMode.CARD_BROWSE, ModelUse.NONE, None),
    GameplayMode.CHARACTER_DOSSIER: GameplayRecipe(GameplayMode.CHARACTER_DOSSIER, ModelUse.NONE, None),
    GameplayMode.LOCATION_VIEW: GameplayRecipe(GameplayMode.LOCATION_VIEW, ModelUse.NONE, None),
    GameplayMode.RELATIONSHIP_VIEW: GameplayRecipe(GameplayMode.RELATIONSHIP_VIEW, ModelUse.NONE, None),
    GameplayMode.STORY_BOOK_REPLAY: GameplayRecipe(GameplayMode.STORY_BOOK_REPLAY, ModelUse.NONE, None),
    GameplayMode.WORLDLINE_COMPARE: GameplayRecipe(GameplayMode.WORLDLINE_COMPARE, ModelUse.NONE, None),

    # World-home conversational questions: reuse world observation checkpoint for a short burst.
    GameplayMode.WORLD_OBSERVATION_QA: GameplayRecipe(
        GameplayMode.WORLD_OBSERVATION_QA, ModelUse.STRUCTURED, "observation_narrator",
        (ContextFacet.LORE, ContextFacet.WORLD), CacheHorizon.WORLD,
        ProviderCachePreference.HOT_ONLY, 3, ("world_checkpoint", "spoiler_profile")),

    # User may reroll a generated original character; static sequence/canon pack dominates the prefix.
    GameplayMode.CHARACTER_GENESIS: GameplayRecipe(
        GameplayMode.CHARACTER_GENESIS, ModelUse.STRUCTURED, "character_genesis",
        (ContextFacet.LORE, ContextFacet.WORLD), CacheHorizon.BURST,
        ProviderCachePreference.HOT_ONLY, 2, ("content_pack", "era", "sequence_profile")),

    # Genesis is usually once per episode, so avoid paying explicit-write premiums by default.
    GameplayMode.STORY_GENESIS: GameplayRecipe(
        GameplayMode.STORY_GENESIS, ModelUse.STRUCTURED, "story_genesis",
        (ContextFacet.LORE, ContextFacet.WORLD, ContextFacet.CHARACTER, ContextFacet.MEMORY),
        CacheHorizon.EPISODE, ProviderCachePreference.AVOID_EXPLICIT, 1,
        ("content_pack", "character_core", "episode_seed"), True, True),

    # Advice is small/fast but repeated inside one StorySession.
    GameplayMode.ADVICE_INTERPRETATION: GameplayRecipe(
        GameplayMode.ADVICE_INTERPRETATION, ModelUse.STRUCTURED, "advice_interpreter",
        (ContextFacet.WORLD, ContextFacet.CHARACTER, ContextFacet.STORY), CacheHorizon.SCENE,
        ProviderCachePreference.HOT_ONLY, 6, ("story_seed", "checkpoint", "scene"), True, True),

    # Highest-value prefix reuse: stable Character Core + session checkpoint + append-only committed history.
    GameplayMode.CHARACTER_REASONING: GameplayRecipe(
        GameplayMode.CHARACTER_REASONING, ModelUse.STRUCTURED, "character_reasoner",
        (ContextFacet.LORE, ContextFacet.WORLD, ContextFacet.CHARACTER, ContextFacet.STORY, ContextFacet.MEMORY),
        CacheHorizon.SESSION, ProviderCachePreference.PREFER_EXPLICIT, 8,
        ("content_pack", "character_core", "story_seed", "checkpoint"), True, True),

    GameplayMode.STORY_DIRECTION: GameplayRecipe(
        GameplayMode.STORY_DIRECTION, ModelUse.BOUNDED_AGENT, "story_director",
        (ContextFacet.LORE, ContextFacet.WORLD, ContextFacet.STORY), CacheHorizon.SESSION,
        ProviderCachePreference.PREFER_EXPLICIT, 8,
        ("content_pack", "story_seed", "checkpoint"), False, True),

    GameplayMode.NARRATIVE_COMPILATION: GameplayRecipe(
        GameplayMode.NARRATIVE_COMPILATION, ModelUse.STRUCTURED, "narrative_compiler",
        (ContextFacet.LORE, ContextFacet.CHARACTER, ContextFacet.STORY), CacheHorizon.SESSION,
        ProviderCachePreference.PREFER_EXPLICIT, 8,
        ("content_pack", "narrative_dna", "voice_persona", "checkpoint"), True, True),

    # Closure reuses the same session truth/commitments; do not build a separate persistent memory source.
    GameplayMode.CLOSURE: GameplayRecipe(
        GameplayMode.CLOSURE, ModelUse.STRUCTURED, "story_director",
        (ContextFacet.WORLD, ContextFacet.STORY), CacheHorizon.SESSION,
        ProviderCachePreference.PREFER_EXPLICIT, 2,
        ("story_seed", "checkpoint"), False, True),

    # Finalization is normally one call after an episode, so local fragment reuse matters more than paid writes.
    GameplayMode.MEMORY_DISTILLATION: GameplayRecipe(
        GameplayMode.MEMORY_DISTILLATION, ModelUse.STRUCTURED, "memory_distiller",
        (ContextFacet.CHARACTER, ContextFacet.STORY, ContextFacet.MEMORY), CacheHorizon.EPISODE,
        ProviderCachePreference.AVOID_EXPLICIT, 1, ("episode",), True, True),

    # Pulse/time-skip are explicit low-frequency world operations, never background keepalive loops.
    GameplayMode.WORLD_PULSE: GameplayRecipe(
        GameplayMode.WORLD_PULSE, ModelUse.STRUCTURED, "world_pulse_planner",
        (ContextFacet.LORE, ContextFacet.WORLD), CacheHorizon.WORLD,
        ProviderCachePreference.AVOID_EXPLICIT, 1, ("world_checkpoint", "content_pack")),
    GameplayMode.TIME_SKIP: GameplayRecipe(
        GameplayMode.TIME_SKIP, ModelUse.STRUCTURED, "world_pulse_planner",
        (ContextFacet.LORE, ContextFacet.WORLD), CacheHorizon.WORLD,
        ProviderCachePreference.AVOID_EXPLICIT, 1, ("world_checkpoint", "content_pack")),

    # Angels/gods/outer beings carry large, stable Narrative DNA and authority rules across several beats.
    GameplayMode.HIGH_ORDER_INTERVENTION: GameplayRecipe(
        GameplayMode.HIGH_ORDER_INTERVENTION, ModelUse.BOUNDED_AGENT, "story_director",
        (ContextFacet.LORE, ContextFacet.WORLD, ContextFacet.STORY), CacheHorizon.SESSION,
        ProviderCachePreference.PREFER_EXPLICIT, 6,
        ("content_pack", "narrative_dna", "story_seed", "checkpoint"), False, True),
}


def gameplay_recipe(mode: GameplayMode) -> GameplayRecipe:
    try:
        return _RECIPES[mode]
    except KeyError:
        raise ContextError("unknown_gameplay_mode") from None


@dataclass(frozen=True, repr=False)
class GameplayCall:
    mode: GameplayMode
    owner_id: str
    world_id: str
    worldline_id: str
    subject_id: str
    session_id: str
    task_json: str = field(repr=False)
    request_id: str = field(repr=False)
    anticipated_reuse: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, GameplayMode):
            raise ContextError("invalid_gameplay_mode")
        for value in (self.owner_id, self.world_id, self.worldline_id, self.subject_id,
                      self.session_id, self.request_id):
            identifier(value)
        object.__setattr__(self, "task_json", canonical_json(parse_json(self.task_json)))
        if self.anticipated_reuse is not None and (
            type(self.anticipated_reuse) is not int or self.anticipated_reuse < 1
        ):
            raise ContextError("invalid_anticipated_reuse")


@dataclass(frozen=True)
class ContextSnapshot:
    """One consistent Domain read boundary shared by all facet ports."""
    world_revision: int
    story_revision: int
    world_tick: int
    policy_revision: str
    lineage_digest: str
    ancestor_limits: tuple[tuple[str, int], ...] = ()
    cache_dimensions: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for value in (self.world_revision, self.story_revision, self.world_tick):
            natural(value)
        identifier(self.policy_revision)
        identifier(self.lineage_digest)
        limits = tuple(self.ancestor_limits)
        for line, revision in limits:
            identifier(line); natural(revision)
        if len({line for line, _ in limits}) != len(limits):
            raise ContextError("duplicate_ancestor")
        dims = tuple(self.cache_dimensions)
        if len({key for key, _ in dims}) != len(dims):
            raise ContextError("duplicate_cache_dimension")
        for key, value in dims:
            identifier(key); identifier(value)
        object.__setattr__(self, "ancestor_limits", limits)
        object.__setattr__(self, "cache_dimensions", dims)


@dataclass(frozen=True, repr=False)
class EligibilityTicket:
    """Opaque Domain-issued pre-retrieval eligibility capability.

    The token is never model-visible and is not authorization by string possession
    alone; concrete Domain ports must validate it with their issuing service.
    """
    scope: ContextScope
    token: str = field(repr=False)

    def __post_init__(self) -> None:
        identifier(self.token)


class ContextSnapshotPort(Protocol):
    async def resolve(self, call: GameplayCall, recipe: GameplayRecipe) -> ContextSnapshot: ...


class LoreContextPort(Protocol):
    async def load(self, call: GameplayCall, snapshot: ContextSnapshot,
                   recipe: GameplayRecipe, eligibility: EligibilityTicket) -> tuple[Evidence, ...]: ...


class WorldContextPort(Protocol):
    async def load(self, call: GameplayCall, snapshot: ContextSnapshot,
                   recipe: GameplayRecipe, eligibility: EligibilityTicket) -> tuple[Evidence, ...]: ...


class CharacterContextPort(Protocol):
    async def load(self, call: GameplayCall, snapshot: ContextSnapshot,
                   recipe: GameplayRecipe, eligibility: EligibilityTicket) -> tuple[Evidence, ...]: ...


class StoryContextPort(Protocol):
    async def load(self, call: GameplayCall, snapshot: ContextSnapshot,
                   recipe: GameplayRecipe, eligibility: EligibilityTicket) -> tuple[Evidence, ...]: ...


class MemoryContextPort(Protocol):
    async def load(self, call: GameplayCall, snapshot: ContextSnapshot,
                   recipe: GameplayRecipe, eligibility: EligibilityTicket) -> tuple[Evidence, ...]: ...


class GameplayAuthorizationPort(Protocol):
    async def eligibility(self, scope: ContextScope, snapshot: ContextSnapshot,
                          recipe: GameplayRecipe) -> EligibilityTicket: ...
    async def authorize(self, request: ContextInput, recipe: GameplayRecipe) -> AuthorizationView: ...


class WorkerProfilePort(Protocol):
    def profile(self, mode: GameplayMode, consumer: str) -> WorkerProfile: ...


@dataclass(frozen=True, repr=False)
class PreparedGameplayContext:
    call: GameplayCall
    recipe: GameplayRecipe
    request: ContextInput
    profile: WorkerProfile


class GameplayContextCoordinator:
    """Fan-in adapter for gameplay stages; Domain modules remain independently owned.

    Facets are loaded concurrently against the same immutable snapshot.  Ports must
    perform read-only snapshot reads; no port may infer authorization from retrieval
    similarity.  The AuthorizationPort can remove candidates but cannot add content.
    """
    def __init__(self, *, snapshot: ContextSnapshotPort, authorization: GameplayAuthorizationPort,
                 profiles: WorkerProfilePort, lore: LoreContextPort | None = None,
                 world: WorldContextPort | None = None, character: CharacterContextPort | None = None,
                 story: StoryContextPort | None = None, memory: MemoryContextPort | None = None):
        self.snapshot = snapshot
        self.authorization = authorization
        self.profiles = profiles
        self._ports = {
            ContextFacet.LORE: lore,
            ContextFacet.WORLD: world,
            ContextFacet.CHARACTER: character,
            ContextFacet.STORY: story,
            ContextFacet.MEMORY: memory,
        }

    @staticmethod
    def requires_model(mode: GameplayMode) -> bool:
        return gameplay_recipe(mode).model_use != ModelUse.NONE

    @staticmethod
    def _epoch_id(call: GameplayCall, snapshot: ContextSnapshot,
                  recipe: GameplayRecipe) -> str:
        dims = dict(snapshot.cache_dimensions)
        missing = [key for key in recipe.epoch_dimensions if key not in dims]
        if missing:
            raise ContextError("missing_cache_dimension")
        identity: dict[str, object] = {
            "mode": recipe.mode.value,
            "horizon": recipe.cache_horizon.value,
            "world": call.world_id,
            "worldline": call.worldline_id,
            "policy": snapshot.policy_revision,
            "lineage": snapshot.lineage_digest,
            "dimensions": {key: dims[key] for key in recipe.epoch_dimensions},
        }
        if recipe.cache_horizon in {CacheHorizon.CHARACTER, CacheHorizon.SESSION,
                                    CacheHorizon.SCENE, CacheHorizon.EPISODE, CacheHorizon.BURST}:
            identity["subject"] = call.subject_id
        if recipe.cache_horizon in {CacheHorizon.SESSION, CacheHorizon.SCENE, CacheHorizon.EPISODE}:
            identity["session"] = call.session_id
        return digest(identity)[:40]

    @staticmethod
    def _scope(call: GameplayCall, snapshot: ContextSnapshot, consumer: str) -> ContextScope:
        return ContextScope(call.owner_id, call.world_id, call.worldline_id, consumer,
                            call.subject_id, call.session_id, snapshot.policy_revision,
                            snapshot.lineage_digest)

    async def prepare(self, call: GameplayCall) -> PreparedGameplayContext:
        recipe = gameplay_recipe(call.mode)
        if recipe.model_use == ModelUse.NONE:
            raise ContextError("gameplay_mode_does_not_require_model")
        if recipe.requires_subject and call.subject_id == "-":
            raise ContextError("gameplay_subject_required")
        if recipe.requires_session and call.session_id == "-":
            raise ContextError("gameplay_session_required")
        snapshot = await self.snapshot.resolve(call, recipe)
        consumer = recipe.consumer
        assert consumer is not None
        scope = self._scope(call, snapshot, consumer)
        eligibility = await self.authorization.eligibility(scope, snapshot, recipe)
        if eligibility.scope != scope:
            raise ContextError("eligibility_scope_mismatch")
        ports = []
        for facet in recipe.facets:
            port = self._ports.get(facet)
            if port is None:
                raise ContextError(f"missing_{facet.value}_context_port")
            ports.append(port)
        # Every retrieval port receives the Domain-issued eligibility ticket before
        # it may execute structured/graph/FTS/vector retrieval.
        loaded = await asyncio.gather(*(port.load(call, snapshot, recipe, eligibility) for port in ports))
        evidence = tuple(item for group in loaded for item in group)
        if any(not isinstance(item, Evidence) for item in evidence):
            raise ContextError("invalid_context_port_result")
        request = ContextInput(scope, snapshot.world_revision, snapshot.story_revision,
                               self._epoch_id(call, snapshot, recipe), evidence,
                               call.task_json, call.request_id)
        # Authorization is a separate Domain capability; sources never self-authorize.
        view = await self.authorization.authorize(request, recipe)
        if view.scope != scope or (view.world_revision, view.story_revision, view.world_tick) != (
            snapshot.world_revision, snapshot.story_revision, snapshot.world_tick
        ) or view.ancestor_limits != snapshot.ancestor_limits:
            raise ContextError("authorization_snapshot_mismatch")
        candidate = {item.fingerprint for item in evidence}
        if not view.grants.issubset(candidate):
            raise ContextError("authorization_grant_outside_candidates")
        allowed = tuple(item for item in evidence if item.fingerprint in view.grants)
        request = ContextInput(scope, snapshot.world_revision, snapshot.story_revision,
                               request.epoch_id, allowed, call.task_json, call.request_id)
        profile = self.profiles.profile(call.mode, consumer)
        if profile.consumer != consumer:
            raise ContextError("profile_consumer_mismatch")
        return PreparedGameplayContext(call, recipe, request, profile)

    async def authorize(self, request: ContextInput, recipe: GameplayRecipe) -> AuthorizationView:
        """Gateway freshness seam: re-check the same evidence before/after model await."""
        view = await self.authorization.authorize(request, recipe)
        if view.scope != request.scope:
            raise ContextError("authorization_scope_mismatch")
        return view
