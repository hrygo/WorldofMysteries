from dataclasses import replace
import pytest

from engine.application.context_compiler import CacheAwareContextCompiler
from engine.application.context_plan import (
    AuthorizationView, ContextError, Evidence, Layer, WorkerProfile,
)
from engine.application.gameplay_context import (
    CacheHorizon, ContextFacet, ContextSnapshot, EligibilityTicket, GameplayCall,
    GameplayContextCoordinator, GameplayMode, ModelUse, ProviderCachePreference,
    gameplay_recipe,
)


SCHEMA = '{"type":"object","properties":{"action":{"type":"string"}},"required":["action"],"additionalProperties":false}'


def call(mode=GameplayMode.CHARACTER_REASONING, *, reuse=None):
    return GameplayCall(mode, "owner", "world", "line", "char", "session",
                        '{"advice":"observe"}', "req", reuse)


class Snapshot:
    def __init__(self, dims=None):
        self.value = ContextSnapshot(
            10, 3, 20, "policy1", "lineage1", (),
            tuple((dims or {
                "content_pack":"cp1", "character_core":"cc1", "story_seed":"seed1",
                "checkpoint":"chk1", "scene":"scene1", "world_checkpoint":"w1",
                "spoiler_profile":"sp1", "era":"era1", "sequence_profile":"seq1",
                "episode_seed":"epseed1", "narrative_dna":"dna1", "voice_persona":"v1",
                "episode":"episode1",
            }).items()),
        )
        self.calls = 0
    async def resolve(self, call, recipe):
        self.calls += 1
        return self.value


class Port:
    def __init__(self, evidence=()):
        self.evidence = tuple(evidence)
        self.tickets = []
        self.snapshots = []
    async def load(self, call, snapshot, recipe, eligibility):
        self.tickets.append(eligibility)
        self.snapshots.append(snapshot)
        return self.evidence


class Auth:
    def __init__(self):
        self.drop = set()
        self.extra_grant = None
        self.bad_ticket_scope = False
        self.bad_view_revision = False
        self.eligibility_calls = 0
        self.authorization_calls = 0
    async def eligibility(self, scope, snapshot, recipe):
        self.eligibility_calls += 1
        if self.bad_ticket_scope:
            scope = replace(scope, world_id="other")
        return EligibilityTicket(scope, "eligible-token")
    async def authorize(self, request, recipe):
        self.authorization_calls += 1
        grants = {e.fingerprint for e in request.evidence if e.source_id not in self.drop}
        if self.extra_grant:
            grants.add(self.extra_grant)
        return AuthorizationView(request.scope, request.world_revision + (1 if self.bad_view_revision else 0),
                                 request.story_revision, 20, frozenset(grants))


class Profiles:
    def __init__(self): self.bad = False
    def profile(self, mode, consumer):
        return WorkerProfile("other" if self.bad else consumer, "v1", "Return a typed proposal.", SCHEMA)


def evidence_set():
    lore = Evidence("canon", 1, "canon_known", Layer.STATIC, '{"rule":"known"}')
    core = Evidence("core", 2, "character_core", Layer.CORE, '{"identity":"investigator"}', subject_id="char")
    checkpoint = Evidence("checkpoint", 2, "checkpoint", Layer.CHECKPOINT, '{"summary":"stable"}',
                          world_id="world", worldline_id="line", committed_revision=8)
    history = Evidence("event9", 1, "observation", Layer.HISTORY, '{"event":"bell"}',
                       world_id="world", worldline_id="line", committed_revision=9, sequence=9)
    state = Evidence("state", 3, "observation", Layer.STATE, '{"location":"station"}',
                     world_id="world", worldline_id="line", committed_revision=10)
    memory = Evidence("memory", 1, "memory", Layer.RECALL, '{"summary":"warning"}', subject_id="char")
    return lore, core, checkpoint, history, state, memory


def coordinator(snapshot=None, auth=None, profiles=None, missing=None):
    lore, core, checkpoint, history, state, memory = evidence_set()
    ports = {
        "lore": Port((lore,)),
        "world": Port((state,)),
        "character": Port((core,)),
        "story": Port((checkpoint, history)),
        "memory": Port((memory,)),
    }
    if missing: ports[missing] = None
    c = GameplayContextCoordinator(snapshot=snapshot or Snapshot(), authorization=auth or Auth(),
        profiles=profiles or Profiles(), lore=ports["lore"], world=ports["world"],
        character=ports["character"], story=ports["story"], memory=ports["memory"])
    return c, ports


def test_gameplay_recipe_matches_product_locality_and_no_model_paths():
    assert gameplay_recipe(GameplayMode.WORLD_HOME).model_use == ModelUse.NONE
    assert gameplay_recipe(GameplayMode.STORY_BOOK_REPLAY).model_use == ModelUse.NONE
    reason = gameplay_recipe(GameplayMode.CHARACTER_REASONING)
    assert reason.cache_horizon == CacheHorizon.SESSION
    assert reason.provider_cache == ProviderCachePreference.PREFER_EXPLICIT
    assert reason.expected_reuse >= 4
    assert gameplay_recipe(GameplayMode.WORLD_PULSE).provider_cache == ProviderCachePreference.AVOID_EXPLICIT
    assert gameplay_recipe(GameplayMode.HIGH_ORDER_INTERVENTION).model_use == ModelUse.BOUNDED_AGENT


@pytest.mark.asyncio
async def test_gameplay_no_model_mode_bypasses_context_and_model_work():
    snap = Snapshot()
    c, _ = coordinator(snapshot=snap)
    assert not c.requires_model(GameplayMode.WORLD_HOME)
    with pytest.raises(ContextError, match="gameplay_mode_does_not_require_model"):
        await c.prepare(call(GameplayMode.WORLD_HOME))
    assert snap.calls == 0


@pytest.mark.asyncio
async def test_gameplay_character_reasoning_connects_all_domain_facets_with_pre_retrieval_ticket():
    auth = Auth()
    c, ports = coordinator(auth=auth)
    prepared = await c.prepare(call())
    assert prepared.recipe.consumer == "character_reasoner"
    assert auth.eligibility_calls == auth.authorization_calls == 1
    assert {e.source_id for e in prepared.request.evidence} == {
        "canon", "core", "checkpoint", "event9", "state", "memory"
    }
    assert all(port.tickets and port.tickets[0].token == "eligible-token" for port in ports.values())
    # The final compiler is still the hard model-boundary check.
    CacheAwareContextCompiler().compile(
        prepared.request,
        await c.authorize(prepared.request, prepared.recipe),
        prepared.profile,
    )


@pytest.mark.asyncio
async def test_gameplay_epoch_ignores_turn_revision_but_rotates_on_checkpoint_dimension():
    snap = Snapshot()
    c, _ = coordinator(snapshot=snap)
    a = await c.prepare(call())
    snap.value = replace(snap.value, world_revision=11, story_revision=4)
    b = await c.prepare(call())
    assert a.request.epoch_id == b.request.epoch_id
    dims = dict(snap.value.cache_dimensions); dims["checkpoint"] = "chk2"
    snap.value = replace(snap.value, cache_dimensions=tuple(dims.items()))
    c2, _ = coordinator(snapshot=snap)
    d = await c2.prepare(call())
    assert d.request.epoch_id != a.request.epoch_id


@pytest.mark.asyncio
async def test_gameplay_authorization_can_remove_candidates_but_cannot_add_grants():
    auth = Auth(); auth.drop = {"memory"}
    c, _ = coordinator(auth=auth)
    prepared = await c.prepare(call())
    assert "memory" not in {e.source_id for e in prepared.request.evidence}
    auth2 = Auth(); auth2.extra_grant = "f" * 64
    c2, _ = coordinator(auth=auth2)
    with pytest.raises(ContextError, match="authorization_grant_outside_candidates"):
        await c2.prepare(call())


@pytest.mark.asyncio
async def test_gameplay_missing_module_interface_is_explicit_not_silent():
    c, _ = coordinator(missing="memory")
    with pytest.raises(ContextError, match="missing_memory_context_port"):
        await c.prepare(call())


@pytest.mark.asyncio
async def test_gameplay_eligibility_and_snapshot_mismatch_fail_before_model():
    auth = Auth(); auth.bad_ticket_scope = True
    c, _ = coordinator(auth=auth)
    with pytest.raises(ContextError, match="eligibility_scope_mismatch"):
        await c.prepare(call())
    auth = Auth(); auth.bad_view_revision = True
    c, _ = coordinator(auth=auth)
    with pytest.raises(ContextError, match="authorization_snapshot_mismatch"):
        await c.prepare(call())


@pytest.mark.asyncio
async def test_gameplay_profile_is_application_owned_and_consumer_bound():
    profiles = Profiles(); profiles.bad = True
    c, _ = coordinator(profiles=profiles)
    with pytest.raises(ContextError, match="profile_consumer_mismatch"):
        await c.prepare(call())


@pytest.mark.asyncio
async def test_memory_distillation_does_not_require_fake_current_state():
    recipe = gameplay_recipe(GameplayMode.MEMORY_DISTILLATION)
    scope_call = call(GameplayMode.MEMORY_DISTILLATION)
    snap = Snapshot()
    episode = Evidence("episode", 1, "committed_episode", Layer.CHECKPOINT,
                       '{"ending":"open"}', world_id="world", worldline_id="line", committed_revision=10)
    story = Port((episode,)); char = Port(()); memory = Port(())
    c = GameplayContextCoordinator(snapshot=snap, authorization=Auth(), profiles=Profiles(),
                                   character=char, story=story, memory=memory)
    prepared = await c.prepare(scope_call)
    view = await c.authorize(prepared.request, recipe)
    CacheAwareContextCompiler().compile(prepared.request, view, prepared.profile)
