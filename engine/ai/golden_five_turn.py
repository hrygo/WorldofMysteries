"""Frozen model-equivalent adapters for the Golden 001 five-turn run.

Only the four model-equivalent roles are fixed here: Advice Interpreter,
Character Reasoner, Story Director and Narrative Compiler. Session
orchestration, deterministic resolution, validation, transactions and
finalization remain real Application/Domain/Infrastructure behavior.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from application.advice_action import ActionIntentCandidate, AdviceActionError
from application.advice_interpretation import (
    AdviceInterpretationCandidate,
    AdviceInterpretationError,
    FrozenTurnInput,
)
from application.story_initialization import StorySessionBootstrap
from contracts import BeatPlan, InputMode, NarrativeBlock, PlayerAdvice
from contracts.models import (
    AdherenceType,
    CharacterDelta,
    CharacterPatch,
    ExpectedCost,
    IntentAction,
    KnowledgeCandidate,
    KnowledgeStatus,
    PerceivedRisk,
    RelationshipDelta,
    RelationshipDimensions,
    WorldEventCandidate,
    WorldEventVisibility,
)
from domain.resolution_policy import (
    ResolutionPolicy,
    ResolutionRule,
    StoryEffect,
)

GOLDEN_TURN_COUNT = 5


@dataclass(frozen=True, slots=True)
class GoldenExpressionTemplate:
    beat_plan: BeatPlan
    narrative_block: NarrativeBlock


@dataclass(frozen=True, slots=True)
class GoldenTurnTemplate:
    advice: PlayerAdvice
    action_intent: dict[str, object]
    policy: ResolutionPolicy
    expression: GoldenExpressionTemplate


class GoldenFiveTurnCatalog:
    """Validated immutable content for one Golden 001 session."""

    def __init__(self, templates: Mapping[int, GoldenTurnTemplate]) -> None:
        if set(templates) != set(range(1, GOLDEN_TURN_COUNT + 1)):
            raise ValueError("Golden catalog requires exactly turns 1 through 5")
        self._templates = {
            number: GoldenTurnTemplate(
                advice=template.advice.model_copy(deep=True),
                action_intent=json.loads(
                    json.dumps(template.action_intent, ensure_ascii=False)
                ),
                policy=template.policy,
                expression=template.expression,
            )
            for number, template in templates.items()
        }

    @property
    def advice_templates(self) -> Mapping[int, PlayerAdvice]:
        return {number: item.advice for number, item in self._templates.items()}

    @property
    def expression_templates(self) -> Mapping[int, GoldenExpressionTemplate]:
        return {number: item.expression for number, item in self._templates.items()}

    def template(self, turn_number: int) -> GoldenTurnTemplate:
        try:
            return self._templates[turn_number]
        except KeyError:
            raise ValueError("unsupported_golden_turn") from None

    def policy(self, turn_number: int) -> ResolutionPolicy:
        return self.template(turn_number).policy

    def authorized_evidence(self, turn_number: int) -> frozenset[str]:
        template = self.template(turn_number)
        return frozenset(
            {
                *(
                    evidence
                    for rule in template.policy.rules
                    for evidence in rule.evidence_ids
                ),
            }
        )

    @classmethod
    def from_directory(
        cls,
        turns_directory: Path,
        mock_directory: Path,
        *,
        seed: dict[str, object],
    ) -> GoldenFiveTurnCatalog:
        templates: dict[int, GoldenTurnTemplate] = {}
        for number in range(1, GOLDEN_TURN_COUNT + 1):
            prefix = f"{number:02d}"
            advice_payload = json.loads(
                (turns_directory / f"{prefix}_advice.json").read_text(
                    encoding="utf-8"
                )
            )
            advice_payload["input_mode"] = InputMode.TEXT.value
            advice = PlayerAdvice.model_validate(advice_payload)
            action_intent = json.loads(
                (mock_directory / f"{prefix}_action_intent.json").read_text(
                    encoding="utf-8"
                )
            )
            beat_plan = BeatPlan.model_validate(
                json.loads(
                    (mock_directory / f"{prefix}_beat_plan.json").read_text(
                        encoding="utf-8"
                    )
                )
            )
            narrative = NarrativeBlock.model_validate(
                json.loads(
                    (
                        mock_directory / f"{prefix}_narrative_block.json"
                    ).read_text(encoding="utf-8")
                )
            )
            templates[number] = GoldenTurnTemplate(
                advice=advice,
                action_intent=action_intent,
                policy=_policy(number, seed),
                expression=GoldenExpressionTemplate(
                    beat_plan=beat_plan,
                    narrative_block=narrative,
                ),
            )
        return cls(templates)


class GoldenTurnInterpreter:
    def __init__(self, template: PlayerAdvice, *, on_call=None) -> None:
        self._template = template
        self._on_call = on_call

    async def interpret(
        self, value: FrozenTurnInput
    ) -> AdviceInterpretationCandidate:
        if self._on_call is not None:
            self._on_call()
        if (
            value.input_mode is not InputMode.TEXT
            or value.raw_input != self._template.raw_input
        ):
            raise AdviceInterpretationError("deterministic_input_unsupported")
        return AdviceInterpretationCandidate(
            interpreter_revision=f"golden001-turn-{_turn_number(self._template)}-advice-v1",
            primary_intent=self._template.primary_intent,
            secondary_intents=tuple(self._template.secondary_intents or ()),
            proposed_actions=tuple(self._template.proposed_actions),
            risk_preference=self._template.risk_preference,
            confidence=self._template.confidence,
        )


class GoldenTurnProposer:
    def __init__(self, template: dict[str, object], *, on_call=None) -> None:
        self._template = template
        self._on_call = on_call

    async def propose(self, *, frozen, advice, scope) -> ActionIntentCandidate:
        if self._on_call is not None:
            self._on_call()
        if advice.raw_input != frozen.raw_input:
            raise AdviceActionError("player_advice_binding_mismatch")
        try:
            return ActionIntentCandidate(
                proposer_revision=(
                    f"golden001-turn-{_turn_number(self._template)}-reasoner-v1"
                ),
                intent=self._template["intent"],
                adherence=AdherenceType(self._template["adherence"]),
                actions=tuple(
                    IntentAction.model_validate(action)
                    for action in self._template["actions"]
                ),
                reason_summary=self._template.get("reason_summary"),
                speech_intent=self._template.get("speech_intent"),
                expected_costs=tuple(
                    ExpectedCost.model_validate(cost)
                    for cost in self._template.get("expected_costs", [])
                ),
                perceived_risks=tuple(
                    PerceivedRisk.model_validate(risk)
                    for risk in self._template.get("perceived_risks", [])
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AdviceActionError("invalid_action_intent_template") from exc


class GoldenFiveTurnFactory:
    """Select the frozen template bound to the current committed turn."""

    def __init__(self, catalog: GoldenFiveTurnCatalog) -> None:
        self._catalog = catalog
        self.interpreter_calls = 0
        self.proposer_calls = 0

    @property
    def expression_templates(self) -> Mapping[int, GoldenExpressionTemplate]:
        return self._catalog.expression_templates

    @property
    def max_turn(self) -> int:
        return GOLDEN_TURN_COUNT

    def expected_input(
        self, bootstrap: StorySessionBootstrap, turn_number: int
    ) -> str:
        if turn_number == 1:
            opening = str(bootstrap.advice_template["raw_input"])
            if opening != self._catalog.template(1).advice.raw_input:
                raise AdviceActionError("golden_turn_content_mismatch")
            return opening
        return self._catalog.template(turn_number).advice.raw_input

    def interpreter_for(
        self, bootstrap: StorySessionBootstrap, turn_number: int = 1
    ) -> GoldenTurnInterpreter:
        self.expected_input(bootstrap, turn_number)
        return GoldenTurnInterpreter(
            self._catalog.template(turn_number).advice,
            on_call=self._count_interpreter,
        )

    def proposer_for(
        self, bootstrap: StorySessionBootstrap, turn_number: int = 1
    ) -> GoldenTurnProposer:
        self.expected_input(bootstrap, turn_number)
        return GoldenTurnProposer(
            self._catalog.template(turn_number).action_intent,
            on_call=self._count_proposer,
        )

    def _count_interpreter(self) -> None:
        self.interpreter_calls += 1

    def _count_proposer(self) -> None:
        self.proposer_calls += 1

    def policy_for_turn(
        self, bootstrap: StorySessionBootstrap, turn_number: int
    ) -> ResolutionPolicy:
        self.expected_input(bootstrap, turn_number)
        return self._catalog.policy(turn_number)

    def domain_validation_for(
        self, bootstrap: StorySessionBootstrap, turn_number: int
    ):
        from application.story_turn_commit import DomainValidationContext

        seed = bootstrap.seed
        hidden_truth = seed.get("hidden_truth", {})
        hidden_literals = tuple(
            str(value)
            for value in hidden_truth.values()
            if isinstance(value, str) and value
        )
        evidence = set(self._catalog.authorized_evidence(turn_number))
        evidence.update(
            str(item["id"])
            for item in seed.get("clues", [])
            if isinstance(item, dict) and item.get("id")
        )
        return DomainValidationContext(
            known_character_ids=tuple(
                str(item) for item in seed.get("actor_ids", []) if item
            ),
            authorized_evidence_ids=frozenset(evidence),
            hidden_fact_literals=hidden_literals,
        )


def _turn_number(advice: PlayerAdvice) -> int:
    identifier = (
        advice.id if isinstance(advice, PlayerAdvice) else str(advice["id"])
    )
    for number in range(1, GOLDEN_TURN_COUNT + 1):
        if identifier.endswith(f"t{number:02d}"):
            return number
    raise ValueError("golden advice template is not bound to a turn")


def _policy(number: int, seed: dict[str, object]) -> ResolutionPolicy:
    builder = {
        1: _turn_one,
        2: _turn_two,
        3: _turn_three,
        4: _turn_four,
        5: _turn_five,
    }[number]
    return ResolutionPolicy.from_story_seed(
        seed,
        builder(),
        policy_id=f"golden001-turn-{number:02d}-policy-v1",
    )


def _turn_one() -> tuple[ResolutionRule, ...]:
    return (
        ResolutionRule(
            rule_id="observe-morris-reaction",
            intent="observe_subject",
            action_types=("continue_conversation",),
            effect=StoryEffect(
                outcome="partial_success",
                clue_ids_add=("clue_doctor_pause",),
                world_event_candidates=(
                    WorldEventCandidate(
                        event_type="evidence_observed",
                        actors=("char_evelyn_gray",),
                        targets=("npc_doctor_morris",),
                        payload={"clue_id": "clue_doctor_pause"},
                        visibility=WorldEventVisibility(
                            public=False,
                            known_by=("char_evelyn_gray",),
                        ),
                    ),
                ),
            ),
            evidence_ids=("policy.golden001.turn01", "clue_doctor_pause"),
        ),
    )


def _turn_two() -> tuple[ResolutionRule, ...]:
    return (
        ResolutionRule(
            rule_id="inspect-appointment-book",
            intent="inspect_records_covertly",
            action_types=("conceal_attention", "inspect_appointment_book"),
            effect=StoryEffect(
                outcome="success_with_cost",
                clue_ids_add=("clue_appointment_book", "clue_removed_page"),
                secret_state_updates=(
                    ("secret_01", "suspected"),
                    ("secret_02", "suspected"),
                ),
                world_time_delta_minutes=30,
                pressure_delta=(("doctor_suspicion", 1),),
                world_event_candidates=(
                    WorldEventCandidate(
                        event_type="evidence_recovered",
                        actors=("char_evelyn_gray",),
                        targets=("npc_doctor_morris",),
                        payload={
                            "clue_ids": [
                                "clue_appointment_book",
                                "clue_removed_page",
                            ]
                        },
                        visibility=WorldEventVisibility(
                            public=False,
                            known_by=("char_evelyn_gray",),
                        ),
                    ),
                ),
            ),
            evidence_ids=(
                "policy.golden001.turn02",
                "clue_doctor_pause",
                "clue_appointment_book",
                "clue_removed_page",
            ),
        ),
    )


def _turn_three() -> tuple[ResolutionRule, ...]:
    character_delta = CharacterDelta(
        character_id="char_evelyn_gray",
        patches=(
            CharacterPatch(
                path="/state/emotion/primary",
                operation="set",
                value="alert_unease",
            ),
            CharacterPatch(
                path="/state/emotion/intensity",
                operation="increment",
                value=0.1,
            ),
        ),
        evidence_ids=("clue_basement_powder",),
    )
    return (
        ResolutionRule(
            rule_id="listen-near-basement",
            intent="inspect_environment",
            action_types=("listen_near_basement",),
            effect=StoryEffect(
                outcome="partial_success",
                clue_ids_add=("clue_basement_powder",),
                secret_state_updates=(("secret_03", "suspected"),),
                world_time_delta_minutes=20,
                character_deltas=(character_delta,),
            ),
            evidence_ids=("policy.golden001.turn03", "clue_basement_powder"),
        ),
    )


def _turn_four() -> tuple[ResolutionRule, ...]:
    relationship = RelationshipDelta(
        from_character_id="char_evelyn_gray",
        to_character_id="npc_doctor_morris",
        dimension_deltas=RelationshipDimensions(
            trust=-0.1,
            fear=0.1,
        ),
        evidence_ids=("clue_jonathan_note",),
    )
    knowledge = KnowledgeCandidate(
        character_id="char_evelyn_gray",
        proposition_id="jonathan_left_occult_note",
        certainty=0.7,
        source_ref="clue_jonathan_note",
        status=KnowledgeStatus.PROBABLE,
    )
    event = WorldEventCandidate(
        event_type="evidence_recovered",
        actors=("char_evelyn_gray",),
        targets=("npc_jonathan_vale",),
        payload={"clue_id": "clue_jonathan_note"},
        visibility=WorldEventVisibility(
            public=False,
            known_by=("char_evelyn_gray",),
        ),
    )
    return (
        ResolutionRule(
            rule_id="create-natural-exit",
            intent="create_distraction",
            action_types=("create_natural_reason_for_morris_to_leave",),
            effect=StoryEffect(
                outcome="success_with_cost",
                clue_ids_add=("clue_jonathan_note",),
                secret_state_updates=(
                    ("secret_01", "revealed"),
                    ("secret_02", "revealed"),
                    ("secret_03", "partial"),
                ),
                world_time_delta_minutes=30,
                pressure_delta=(("doctor_suspicion", 1),),
                relationship_deltas=(relationship,),
                knowledge_candidates=(knowledge,),
                world_event_candidates=(event,),
            ),
            evidence_ids=(
                "policy.golden001.turn04",
                "clue_doctor_pause",
                "clue_jonathan_note",
            ),
        ),
    )


def _turn_five() -> tuple[ResolutionRule, ...]:
    return (
        ResolutionRule(
            rule_id="close-and-leave",
            intent="close_and_leave",
            action_types=("leave_location", "organize_known_facts"),
            effect=StoryEffect(
                outcome="clean_success",
                world_time_delta_minutes=20,
            ),
            evidence_ids=("policy.golden001.turn05",),
        ),
    )
