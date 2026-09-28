"""Golden 001 adapters for scenario policy and deterministic workers.

The adapter reuses GoldenFiveTurnFactory as the sole source for authored input,
resolver policy, validation context, and the fixed turn limit. No general
Application or live Worker code depends on that factory.
"""
from __future__ import annotations

from ai.golden_five_turn import GoldenFiveTurnFactory
from application.scenario_policy import (
    ActionSignature,
    FinalizationRecipe,
    ScenarioIdentity,
    ScenarioPolicyError,
    TurnPolicyDecision,
)
from application.story_initialization import (
    GOLDEN_POLICY_VERSION,
    GOLDEN_SCENARIO_ID,
    StorySessionBootstrap,
    TrustedScenarioBundle,
)
from application.story_turn_commit import DomainValidationContext
from contracts import StorySession, StorySessionStatus

# This is the canonical digest produced from the shipped Golden 001 scenario
# bundle. Restored sessions are accepted only for a digest whose rules revision
# remains explicitly registered here.
_GOLDEN_RULES_BY_CONTENT_DIGEST = {
    "610ecbdb2875b86ac5ed52b100d5def3481408d5f4e16030cec2ed09da288d07":
        GOLDEN_POLICY_VERSION,
}


class GoldenScenarioPolicy:
    """Bind frozen Golden 001 rules to their trusted, content-addressed bundle."""

    def __init__(self, golden: GoldenFiveTurnFactory) -> None:
        self._golden = golden

    def identity(
        self,
        bootstrap: StorySessionBootstrap | TrustedScenarioBundle,
    ) -> ScenarioIdentity:
        expected_revision = _GOLDEN_RULES_BY_CONTENT_DIGEST.get(
            bootstrap.content_digest
        )
        if (
            bootstrap.scenario_id != GOLDEN_SCENARIO_ID
            or expected_revision is None
            or bootstrap.policy_version != expected_revision
        ):
            raise ScenarioPolicyError("unknown_scenario_identity")
        return ScenarioIdentity(
            scenario_id=bootstrap.scenario_id,
            content_digest=bootstrap.content_digest,
            rules_revision=expected_revision,
        )

    def decision(
        self,
        session: StorySession,
        committed_evidence: frozenset[str],
    ) -> TurnPolicyDecision:
        del committed_evidence
        terminal = session.story_state.turn >= self._golden.max_turn
        return TurnPolicyDecision(
            allowed_to_submit=(
                session.status is StorySessionStatus.ACTIVE and not terminal
            ),
            terminal=terminal,
            reason="iteration_limit_reached" if terminal else None,
        )

    def expected_input(
        self,
        bootstrap: StorySessionBootstrap,
        session: StorySession,
    ) -> str | None:
        self.identity(bootstrap)
        turn_number = session.story_state.turn + 1
        if turn_number > self._golden.max_turn:
            return None
        return self._golden.expected_input(bootstrap, turn_number)

    def resolution_policy(
        self,
        bootstrap: StorySessionBootstrap,
        session: StorySession,
    ):
        self.identity(bootstrap)
        return self._golden.policy_for_turn(
            bootstrap, session.story_state.turn + 1
        )

    def validation_context(
        self,
        bootstrap: StorySessionBootstrap,
        session: StorySession,
    ) -> DomainValidationContext:
        self.identity(bootstrap)
        return self._golden.domain_validation_for(
            bootstrap, session.story_state.turn + 1
        )

    def finalization_recipe(
        self,
        bootstrap: StorySessionBootstrap,
        committed_session: StorySession,
    ) -> FinalizationRecipe | None:
        self.identity(bootstrap)
        decision = self.decision(
            committed_session,
            frozenset(committed_session.story_state.discovered_clue_ids or ()),
        )
        if not decision.terminal:
            return None
        return FinalizationRecipe(
            episode_filename="episode.json",
            memory_filename="episode_memory.json",
        )


class GoldenScenarioWorkers:
    """Expose the frozen fixture as a worker factory without owning its rules."""

    supports_live_input = False

    def __init__(self, golden: GoldenFiveTurnFactory) -> None:
        self._golden = golden

    def interpreter_for(
        self,
        bootstrap: StorySessionBootstrap,
        turn_number: int,
    ):
        return self._golden.interpreter_for(bootstrap, turn_number)

    def proposer_for(
        self,
        bootstrap: StorySessionBootstrap,
        turn_number: int,
        allowed_signatures: tuple[ActionSignature, ...],
    ):
        del allowed_signatures
        return self._golden.proposer_for(bootstrap, turn_number)

    def narrative_compiler(
        self,
        bootstrap: StorySessionBootstrap,
    ):
        del bootstrap
        # Frozen narratives are published by post-COMMIT settlement.


__all__ = ["GoldenScenarioPolicy", "GoldenScenarioWorkers"]
