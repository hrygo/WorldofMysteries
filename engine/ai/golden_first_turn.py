"""Deterministic Golden 001 interpreter/proposer templates.

Only model-equivalent semantic fields are taken from the frozen bundle.
Input identity, turn identity, actor identity and evidence IDs remain owned by
the existing Application services.
"""
from __future__ import annotations

from application.advice_action import (
    ActionIntentCandidate,
    AdviceActionError,
)
from application.advice_interpretation import (
    AdviceInterpretationCandidate,
    AdviceInterpretationError,
    FrozenTurnInput,
)
from application.story_initialization import StorySessionBootstrap
from contracts import AdherenceType, InputMode, PlayerAdvice
from contracts.models import ExpectedCost, IntentAction, PerceivedRisk


class GoldenFirstTurnInterpreter:
    def __init__(self, bootstrap: StorySessionBootstrap) -> None:
        self._bootstrap = bootstrap

    async def interpret(
        self, value: FrozenTurnInput
    ) -> AdviceInterpretationCandidate:
        template = PlayerAdvice.model_validate(self._bootstrap.advice_template)
        if (
            value.input_mode is not InputMode.TEXT
            or value.raw_input != template.raw_input
        ):
            raise AdviceInterpretationError("deterministic_input_unsupported")
        return AdviceInterpretationCandidate(
            interpreter_revision="golden001-advice-template-v1",
            primary_intent=template.primary_intent,
            secondary_intents=tuple(template.secondary_intents or ()),
            proposed_actions=tuple(template.proposed_actions),
            risk_preference=template.risk_preference,
            confidence=template.confidence,
        )


class GoldenFirstTurnProposer:
    def __init__(self, bootstrap: StorySessionBootstrap) -> None:
        self._bootstrap = bootstrap

    async def propose(self, *, frozen, advice, scope) -> ActionIntentCandidate:
        if not isinstance(advice, PlayerAdvice):
            raise AdviceActionError("invalid_player_advice")
        if (
            advice.turn_id != frozen.turn_id
            or advice.raw_input != frozen.raw_input
            or advice.input_mode is not frozen.input_mode
        ):
            raise AdviceActionError("player_advice_binding_mismatch")
        template = self._bootstrap.action_intent_template
        try:
            actions = tuple(
                IntentAction.model_validate(action)
                for action in template["actions"]
            )
            expected_costs = tuple(
                ExpectedCost.model_validate(cost)
                for cost in template.get("expected_costs", [])
            )
            perceived_risks = tuple(
                PerceivedRisk.model_validate(risk)
                for risk in template.get("perceived_risks", [])
            )
            return ActionIntentCandidate(
                proposer_revision="golden001-action-intent-template-v1",
                intent=template["intent"],
                adherence=AdherenceType(template["adherence"]),
                actions=actions,
                reason_summary=template.get("reason_summary"),
                speech_intent=template.get("speech_intent"),
                expected_costs=expected_costs,
                perceived_risks=perceived_risks,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AdviceActionError("invalid_action_intent_template") from exc


class GoldenFirstTurnFactory:
    """Create per-session deterministic adapters from the frozen bootstrap."""

    def interpreter_for(self, bootstrap: StorySessionBootstrap):
        return GoldenFirstTurnInterpreter(bootstrap)

    def proposer_for(self, bootstrap: StorySessionBootstrap):
        return GoldenFirstTurnProposer(bootstrap)
