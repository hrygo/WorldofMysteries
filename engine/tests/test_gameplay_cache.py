from dataclasses import replace
import pytest

from engine.application.context_plan import ContextError
from engine.application.gameplay_context import GameplayMode
from engine.ai.gameplay_cache import GameplayAIGateway, GameplayCachePlanner
from engine.ai.gateway import ExecutionBudget, ProposalResult
from engine.ai.prompt_cache_policy import CacheMode, Protocol, ProviderProfile, render_wire
from engine.tests.test_context_compiler import rendered
from engine.tests.test_gameplay_context import call


def explicit_target(mode=CacheMode.OPENAI_EXPLICIT):
    protocol = Protocol.CLAUDE if mode == CacheMode.CLAUDE_EXPLICIT else Protocol.RESPONSES
    ttl = "5m" if mode == CacheMode.CLAUDE_EXPLICIT else "30m"
    return ProviderProfile("endpoint", "model", protocol, mode, ("model",), ttl)


def test_gameplay_cache_avoids_paid_explicit_writes_for_one_shot_stages():
    planner = GameplayCachePlanner()
    for mode in (GameplayMode.STORY_GENESIS, GameplayMode.MEMORY_DISTILLATION,
                 GameplayMode.WORLD_PULSE, GameplayMode.TIME_SKIP):
        from engine.application.gameplay_context import gameplay_recipe
        decision = planner.decide(call(mode), gameplay_recipe(mode), explicit_target())
        assert decision.effective_target.mode == CacheMode.AUTO
        assert not decision.explicit_write_enabled
        assert not decision.network_prewarm


def test_gameplay_cache_keeps_explicit_for_hot_story_loop_and_high_order_play():
    planner = GameplayCachePlanner()
    from engine.application.gameplay_context import gameplay_recipe
    for mode in (GameplayMode.CHARACTER_REASONING, GameplayMode.STORY_DIRECTION,
                 GameplayMode.NARRATIVE_COMPILATION, GameplayMode.HIGH_ORDER_INTERVENTION):
        decision = planner.decide(call(mode), gameplay_recipe(mode), explicit_target())
        assert decision.effective_target.mode == CacheMode.OPENAI_EXPLICIT
        assert decision.explicit_write_enabled
        assert decision.reason == "reused_gameplay_prefix"


def test_gameplay_hot_only_uses_runtime_reuse_hint():
    planner = GameplayCachePlanner(); from engine.application.gameplay_context import gameplay_recipe
    recipe = gameplay_recipe(GameplayMode.CHARACTER_GENESIS)
    cold = planner.decide(call(GameplayMode.CHARACTER_GENESIS, reuse=1), recipe, explicit_target())
    hot = planner.decide(call(GameplayMode.CHARACTER_GENESIS, reuse=3), recipe, explicit_target())
    assert cold.effective_target.mode == CacheMode.AUTO
    assert hot.effective_target.mode == CacheMode.OPENAI_EXPLICIT


def test_gameplay_provider_auto_is_never_upgraded_by_guessing():
    planner = GameplayCachePlanner(); from engine.application.gameplay_context import gameplay_recipe
    target = ProviderProfile("compatible", "unknown", Protocol.CHAT)
    d = planner.decide(call(), gameplay_recipe(GameplayMode.CHARACTER_REASONING), target)
    assert d.effective_target.mode == CacheMode.AUTO
    assert not d.explicit_write_enabled


def test_provider_cache_mode_and_ttl_participate_in_wire_cache_identity():
    prompt = rendered()
    explicit = explicit_target()
    automatic = replace(explicit, mode=CacheMode.AUTO, ttl=None)
    assert render_wire(prompt, explicit, 32).cache_key != render_wire(prompt, automatic, 32).cache_key


class DummyCoordinator:
    def __init__(self, prepared=None): self.prepared = prepared; self.calls = []
    async def prepare(self, call): self.calls.append(call); return self.prepared
    async def authorize(self, request, recipe): raise AssertionError("fake base gateway should receive override")


class DummyBaseGateway:
    def __init__(self): self.args = None
    async def execute(self, request, profile, target, budget, authorize=None):
        self.args = request, profile, target, budget, authorize
        return ProposalResult('{"action":"ok"}', (), 1, 0.01, "k", "p")


@pytest.mark.asyncio
async def test_gameplay_gateway_bypasses_non_model_experience_before_context_loading():
    coordinator = DummyCoordinator()
    base = DummyBaseGateway()
    gateway = GameplayAIGateway(coordinator, base)
    with pytest.raises(ContextError, match="gameplay_mode_does_not_require_model"):
        await gateway.execute(call(GameplayMode.STORY_BOOK_REPLAY), explicit_target(), ExecutionBudget(1000,100))
    assert not coordinator.calls and base.args is None


@pytest.mark.asyncio
async def test_gameplay_gateway_applies_cache_economics_and_authorization_override():
    from engine.tests.test_gameplay_context import coordinator as make_coordinator
    coordinator, _ = make_coordinator()
    prepared = await coordinator.prepare(call())
    # use a coordinator proxy that returns the already-created deterministic input
    class Proxy:
        async def prepare(self, gameplay_call): return prepared
        async def authorize(self, request, recipe): return await coordinator.authorize(request, recipe)
    base = DummyBaseGateway()
    gateway = GameplayAIGateway(Proxy(), base)
    result = await gateway.execute(call(), explicit_target(), ExecutionBudget(1000,100))
    assert result.proposal() == {"action":"ok"}
    assert base.args[2].mode == CacheMode.OPENAI_EXPLICIT
    assert callable(base.args[4])
