"""Gameplay-specific cache economics and the bridge into CacheAwareGateway."""
from __future__ import annotations

from dataclasses import dataclass, replace

from engine.application.context_plan import ContextError
from engine.application.gameplay_context import (
    GameplayCall, GameplayContextCoordinator, GameplayRecipe, ModelUse,
    ProviderCachePreference, gameplay_recipe,
)
from .gateway import CacheAwareGateway, ExecutionBudget, ProposalResult
from .prompt_cache_policy import CacheMode, ProviderProfile


@dataclass(frozen=True)
class GameplayCacheDecision:
    effective_target: ProviderProfile
    expected_reuse: int
    explicit_write_enabled: bool
    network_prewarm: bool
    reason: str


class GameplayCachePlanner:
    """Choose paid/explicit writes from gameplay reuse, never from hit-rate vanity.

    AUTO means provider/default behavior is left untouched.  This planner never sends
    a keepalive/prewarm request: app-open, World Pulse and background NPC activity must
    not spend tokens merely to keep a cache hot.
    """
    def decide(self, call: GameplayCall, recipe: GameplayRecipe,
               target: ProviderProfile) -> GameplayCacheDecision:
        if recipe.model_use == ModelUse.NONE:
            raise ContextError("gameplay_mode_does_not_require_model")
        reuse = call.anticipated_reuse or recipe.expected_reuse
        enabled = target.mode != CacheMode.AUTO
        reason = "provider_auto_or_unspecified"
        effective = target
        if target.mode != CacheMode.AUTO:
            if recipe.provider_cache == ProviderCachePreference.AVOID_EXPLICIT:
                enabled = False
                reason = "one_shot_or_low_locality"
            elif recipe.provider_cache == ProviderCachePreference.HOT_ONLY and reuse < 2:
                enabled = False
                reason = "insufficient_expected_reuse"
            else:
                enabled = True
                reason = "reused_gameplay_prefix"
            if not enabled:
                # Preserve the endpoint/model/protocol but stop requesting explicit writes.
                effective = replace(target, mode=CacheMode.AUTO, ttl=None)
        return GameplayCacheDecision(effective, reuse, enabled, False, reason)


class GameplayAIGateway:
    """Connect gameplay composition to the generic gateway without owning Domain state."""
    def __init__(self, coordinator: GameplayContextCoordinator, gateway: CacheAwareGateway,
                 planner: GameplayCachePlanner | None = None):
        self.coordinator = coordinator
        self.gateway = gateway
        self.planner = planner or GameplayCachePlanner()

    async def execute(self, call: GameplayCall, target: ProviderProfile,
                      budget: ExecutionBudget) -> ProposalResult:
        recipe = gameplay_recipe(call.mode)
        if recipe.model_use == ModelUse.NONE:
            raise ContextError("gameplay_mode_does_not_require_model")
        prepared = await self.coordinator.prepare(call)
        decision = self.planner.decide(call, recipe, target)
        return await self.gateway.execute(
            prepared.request, prepared.profile, decision.effective_target, budget,
            authorize=lambda request: self.coordinator.authorize(request, recipe),
        )
