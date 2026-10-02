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

# Digests produced from the shipped Golden 001 scenario bundle. Restored
# sessions are accepted only for a digest whose rules revision remains
# explicitly registered here, so changing product content — a public name, a
# clue label, a new presentation table — is a registered act rather than a
# silent one.
#
# Four entries, and the count is the point rather than an accident: the
# content digest covers the presentation tables, so it has moved three times
# for three unrelated reasons, and every move was registered as a separate
# act rather than inferred from the one before it.
#
# - 610ecbdb — the original bundle.
# - 0164030c — npc_jonathan_vale 中文化 (VF-111). A public name is what the
#   model attributes a line to and what a voice binds to, so renaming it is a
#   content change. This is the digest the builder produces today.
# - 789b9574 — SB-09's attempt at the same registration, measured by running
#   the builder against the *pre-VF-111* public names. VF-111 landed between
#   the measurement and the emitter, so this value is one rename away from
#   what the builder actually produces and never described a bundle that
#   shipped. It stays because deleting a registration is the one move here
#   that can strand a session, and because it is a real measurement of a real
#   content state — just not of the state this repository is in.
# - 69ddb609 — what the builder produces once the knowledge-proposition table
#   is actually emitted on top of the current names (SB-11). Measured by
#   running the builder with that one line added, not derived: the proposition
#   ids hash into the digest, so no arithmetic over 789b9574 would have
#   produced it. Registered *before* the emitter, which is the whole point —
#   no main is ever in the state "the bundle says X and nothing accepts X".
#
# The guard in ``test_scenario_policy`` asserts that whatever the builder
# produces is in here, rather than asserting a fixed value. That is what makes
# registering ahead of the emitter safe, and it is also what would have caught
# the gap between 789b9574 and 69ddb609.
_GOLDEN_RULES_BY_CONTENT_DIGEST = {
    "610ecbdb2875b86ac5ed52b100d5def3481408d5f4e16030cec2ed09da288d07":
        GOLDEN_POLICY_VERSION,
    "0164030c3004df83a087c7278e50c1d4d17752981fa86020df7b8d5d41d1a3ab":
        GOLDEN_POLICY_VERSION,
    "789b95741e72582946de8f3258d88cda7cbf3f5c17c0f7ad850d4ac0e44cb1b1":
        GOLDEN_POLICY_VERSION,
    "69ddb609d723db6af089b713a2b35b70d111cadbb4ffb4f1883a0f0f0eb98f8b":
        GOLDEN_POLICY_VERSION,
    # The same promise for the character display-name roster: what the builder
    # produces once ``character_display_names`` is emitted alongside the
    # proposition table (SB-20). Measured the same way, by running the builder
    # with that one line added -- not derived, because the canonical ids hash
    # into the digest.
    #
    # A prior author deliberately declined to ship that roster, on the grounds
    # that it would push the supporting cast into voice casting and speaker
    # binding. The concern is real, but the casting gate does not rest on this
    # table: ``resolve_voice_runtime`` refuses with ``voice_binding_not_reviewed``
    # unless a reviewed binding already exists, so a newly nameable character
    # can only become a foundry candidate awaiting the player's review.
    # ADR-006's "the player casts no voice" survives the roster, and PRD §20's
    # 关键人物 / 重要关系变化 sections stop being permanently empty.
    "b4657c86aa38b0ce18553b25ee1ed0b2284721b430e66eae3bb35f6330eec280":
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
