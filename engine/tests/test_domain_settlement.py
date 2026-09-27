"""Pure domain invariants for turn and cross-domain settlement candidates."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from contracts import ActionIntent, Character, PlayerAdvice, StateDelta
from contracts.models import (
    CharacterDelta,
    CharacterPatch,
    KnowledgeCandidate,
    RelationshipDelta,
    RelationshipDimensions,
    WorldEventCandidate,
    WorldEventVisibility,
)
from domain.character_state_reducer import (
    CharacterStateTransitionError,
    apply_character_delta,
)
from domain.domain_candidate_validator import (
    DomainCandidateValidationError,
    validate_action_intent,
    validate_resolved_state_delta,
    validate_state_delta_overlays,
)
from domain.relationship_reducer import (
    RelationshipState,
    RelationshipTransitionError,
    apply_relationship_delta,
)
from domain.resolution_policy import (
    ResolutionPolicy,
    ResolutionPolicyError,
    ResolutionRule,
    StoryEffect,
)
from domain.resolver import DeterministicOutcomeResolver


ROOT = Path(__file__).resolve().parents[2]


def _golden_character() -> Character:
    value = json.loads((ROOT / "fixtures/golden_001/character.json").read_text())
    return Character.model_validate(value)


def _golden_advice_and_intent() -> tuple[PlayerAdvice, ActionIntent]:
    advice = PlayerAdvice.model_validate(
        json.loads((ROOT / "fixtures/golden_001/turns/01_advice.json").read_text())
    )
    intent = ActionIntent.model_validate(
        json.loads(
            (ROOT / "docs/07_工程启动/golden_001_runtime/mock/01_action_intent.json").read_text()
        )
    )
    return advice, intent


def _state_delta(**updates: object) -> StateDelta:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "id": "delta_g001_t01",
        "turn_id": "turn_g001_01",
        "outcome": "partial_success",
        "story_delta": {},
        "character_deltas": [],
        "world_event_candidates": [],
        "evidence_ids": ["advice_g001_t01", "intent_g001_t01"],
    }
    payload.update(updates)
    return StateDelta.model_validate(payload)


def _relationship_state() -> RelationshipState:
    return RelationshipState(
        id="relationship.evelyn.morris",
        worldline_id="wl_main",
        from_character_id="char_evelyn_gray",
        to_character_id="npc_doctor_morris",
        dimensions={
            "trust": 0.0,
            "affection": 0.0,
            "respect": 0.0,
            "fear": 0.0,
            "hostility": 0.0,
            "dependency": 0.0,
        },
        evidence_ids=(),
        revision=4,
    )


def test_character_delta_reduces_only_mutable_character_state_and_advances_revision():
    character = _golden_character()
    delta = CharacterDelta.model_validate(
        {
            "character_id": character.id,
            "patches": [
                {
                    "path": "/state/emotion/intensity",
                    "operation": "set",
                    "value": 0.5,
                }
            ],
            "evidence_ids": ["observation_g001_t01"],
        }
    )

    result = apply_character_delta(
        character,
        delta,
        authorized_evidence_ids={"observation_g001_t01"},
    )

    assert result.state.emotion is not None
    assert result.state.emotion.intensity == 0.5
    assert result.revision == character.revision + 1
    assert result.identity == character.identity
    assert result.core == character.core
    assert result.canon_anchor == character.canon_anchor


@pytest.mark.parametrize(
    "path",
    (
        "/id",
        "/identity/display_name",
        "/core/traits/cautious",
        "/canon_anchor/character_id",
        "/revision",
        "/state/unknown_field",
    ),
)
def test_character_delta_rejects_identity_canon_or_unknown_paths(path: str):
    character = _golden_character()
    delta = CharacterDelta.model_validate(
        {
            "character_id": character.id,
            "patches": [{"path": path, "operation": "set", "value": "rewritten"}],
            "evidence_ids": ["observation_g001_t01"],
        }
    )

    with pytest.raises(CharacterStateTransitionError):
        apply_character_delta(
            character,
            delta,
            authorized_evidence_ids={"observation_g001_t01"},
        )


def test_character_delta_rejects_unrecognized_path_syntax_and_missing_evidence():
    character = _golden_character()
    malformed = CharacterDelta.model_validate(
        {
            "character_id": character.id,
            "patches": [{"path": "state.location_id", "operation": "set", "value": "elsewhere"}],
            "evidence_ids": ["observation_g001_t01"],
        }
    )
    missing_evidence = CharacterDelta.model_validate(
        {
            "character_id": character.id,
            "patches": [{"path": "/state/location_id", "operation": "set", "value": "elsewhere"}],
            "evidence_ids": ["secret_04"],
        }
    )

    with pytest.raises(CharacterStateTransitionError):
        apply_character_delta(
            character,
            malformed,
            authorized_evidence_ids={"observation_g001_t01"},
        )
    with pytest.raises(CharacterStateTransitionError, match="evidence"):
        apply_character_delta(
            character,
            missing_evidence,
            authorized_evidence_ids={"observation_g001_t01"},
        )


def test_character_increment_rejects_an_unrepresentable_numeric_result():
    character = _golden_character()
    delta = CharacterDelta.model_validate(
        {
            "character_id": character.id,
            "patches": [
                {
                    "path": "/state/emotion/intensity",
                    "operation": "increment",
                    "value": 10**400,
                }
            ],
            "evidence_ids": ["observation_g001_t01"],
        }
    )

    with pytest.raises(CharacterStateTransitionError, match="finite"):
        apply_character_delta(
            character,
            delta,
            authorized_evidence_ids={"observation_g001_t01"},
        )


def test_relationship_delta_is_bounded_evidence_backed_and_revisioned():
    delta = RelationshipDelta.model_validate(
        {
            "from_character_id": "char_evelyn_gray",
            "to_character_id": "npc_doctor_morris",
            "dimension_deltas": {"trust": -0.2, "respect": 0.1},
            "evidence_ids": ["observation_g001_t04"],
        }
    )

    result = apply_relationship_delta(
        _relationship_state(),
        delta,
        authorized_evidence_ids={"observation_g001_t04"},
    )

    assert result.dimensions["trust"] == -0.2
    assert result.dimensions["respect"] == 0.1
    assert result.revision == 5
    assert result.evidence_ids == ("observation_g001_t04",)


def test_relationship_delta_rejects_out_of_range_values_and_unrelated_pair():
    relationship = _relationship_state()
    outside_range = RelationshipDelta.model_validate(
        {
            "from_character_id": relationship.from_character_id,
            "to_character_id": relationship.to_character_id,
            "dimension_deltas": {"trust": 1.5},
            "evidence_ids": ["observation_g001_t04"],
        }
    )
    wrong_pair = RelationshipDelta.model_validate(
        {
            "from_character_id": relationship.to_character_id,
            "to_character_id": relationship.from_character_id,
            "dimension_deltas": {"trust": 0.1},
            "evidence_ids": ["observation_g001_t04"],
        }
    )

    with pytest.raises(RelationshipTransitionError, match="range"):
        apply_relationship_delta(
            relationship,
            outside_range,
            authorized_evidence_ids={"observation_g001_t04"},
        )
    with pytest.raises(RelationshipTransitionError, match="pair"):
        apply_relationship_delta(
            relationship,
            wrong_pair,
            authorized_evidence_ids={"observation_g001_t04"},
        )


def test_relationship_delta_rejects_extreme_integer_without_float_overflow():
    relationship = _relationship_state()
    delta = RelationshipDelta.model_validate(
        {
            "from_character_id": relationship.from_character_id,
            "to_character_id": relationship.to_character_id,
            "dimension_deltas": {"trust": 10**400},
            "evidence_ids": ["observation_g001_t04"],
        }
    )

    with pytest.raises(RelationshipTransitionError, match="range"):
        apply_relationship_delta(
            relationship,
            delta,
            authorized_evidence_ids={"observation_g001_t04"},
        )


def test_action_intent_preserves_character_autonomy_and_authorized_evidence():
    advice, intent = _golden_advice_and_intent()
    character = _golden_character()

    validate_action_intent(
        advice,
        intent,
        character,
        authorized_evidence_ids={advice.id},
    )

    wrong_actor = intent.model_copy(update={"character_id": "npc_doctor_morris"})
    leaked_evidence = intent.model_copy(
        update={"evidence_ids": [advice.id, "secret_04"]}
    )
    with pytest.raises(DomainCandidateValidationError, match="character"):
        validate_action_intent(
            advice,
            wrong_actor,
            character,
            authorized_evidence_ids={advice.id},
        )
    with pytest.raises(DomainCandidateValidationError, match="evidence"):
        validate_action_intent(
            advice,
            leaked_evidence,
            character,
            authorized_evidence_ids={advice.id},
        )


def test_knowledge_candidate_requires_authorized_source_and_matching_character():
    candidate = KnowledgeCandidate.model_validate(
        {
            "character_id": "char_evelyn_gray",
            "proposition_id": "fact.jonathan_returned",
            "certainty": 0.8,
            "source_ref": "clue_jonathan_note",
            "status": "probable",
        }
    )
    delta = _state_delta(
        knowledge_candidates=[candidate.model_dump(mode="json", exclude_none=True)],
        evidence_ids=[
            "advice_g001_t01",
            "intent_g001_t01",
            "clue_jonathan_note",
        ],
    )

    validate_state_delta_overlays(
        delta,
        known_character_ids={"char_evelyn_gray", "npc_doctor_morris"},
        authorized_evidence_ids={"advice_g001_t01", "intent_g001_t01", "clue_jonathan_note"},
    )

    unauthorized = candidate.model_copy(update={"source_ref": "secret_04"})
    bad_delta = _state_delta(
        knowledge_candidates=[unauthorized.model_dump(mode="json", exclude_none=True)]
    )
    with pytest.raises(DomainCandidateValidationError, match="source"):
        validate_state_delta_overlays(
            bad_delta,
            known_character_ids={"char_evelyn_gray", "npc_doctor_morris"},
            authorized_evidence_ids={"advice_g001_t01", "intent_g001_t01"},
        )


@pytest.mark.parametrize(
    "effect_kwargs",
    (
        {"world_time_delta_minutes": math.nan},
        {"world_time_delta_minutes": math.inf},
        {"pressure_delta": (("doctor_suspicion", math.nan),)},
        {"pressure_delta": (("doctor_suspicion", math.inf),)},
    ),
)
def test_resolution_policy_rejects_nonfinite_numeric_effects(effect_kwargs: dict[str, object]):
    rule = ResolutionRule(
        rule_id="nonfinite-effect",
        intent="observe",
        action_types=("wait",),
        effect=StoryEffect(outcome="partial_success", **effect_kwargs),
    )

    with pytest.raises(ResolutionPolicyError, match="finite"):
        ResolutionPolicy(frozenset(), frozenset(), (rule,))


def test_world_event_candidate_cannot_publish_hidden_golden_truth():
    candidate = WorldEventCandidate(
        event_type="occult_evidence",
        actors=["char_evelyn_gray"],
        targets=["npc_jonathan_vale"],
        payload={"secret_id": "secret_04"},
        visibility=WorldEventVisibility(public=True),
    )
    delta = _state_delta(
        world_event_candidates=[candidate.model_dump(mode="json", exclude_none=True)]
    )

    with pytest.raises(DomainCandidateValidationError, match="hidden"):
        validate_state_delta_overlays(
            delta,
            known_character_ids={
                "char_evelyn_gray",
                "npc_doctor_morris",
                "npc_jonathan_vale",
            },
            authorized_evidence_ids={"advice_g001_t01", "intent_g001_t01"},
            hidden_fact_literals={"secret_04", "unknown_external_group"},
        )

    private_candidate = candidate.model_copy(
        update={"visibility": WorldEventVisibility(public=False, known_by=["char_evelyn_gray"])}
    )
    private_delta = _state_delta(
        world_event_candidates=[private_candidate.model_dump(mode="json", exclude_none=True)]
    )
    validate_state_delta_overlays(
        private_delta,
        known_character_ids={
            "char_evelyn_gray",
            "npc_doctor_morris",
            "npc_jonathan_vale",
        },
        authorized_evidence_ids={"advice_g001_t01", "intent_g001_t01"},
        hidden_fact_literals={"secret_04", "unknown_external_group"},
    )


def test_resolver_emits_only_policy_defined_cross_domain_candidates():
    advice, intent = _golden_advice_and_intent()
    character_delta = CharacterDelta(
        character_id="char_evelyn_gray",
        patches=[
            CharacterPatch(
                path="/state/location_id",
                operation="set",
                value="loc_morris_clinic",
            )
        ],
        evidence_ids=["advice_g001_t01"],
    )
    relationship_delta = RelationshipDelta(
        from_character_id="char_evelyn_gray",
        to_character_id="npc_doctor_morris",
        dimension_deltas=RelationshipDimensions(trust=-0.1),
        evidence_ids=["advice_g001_t01"],
    )
    knowledge_candidate = KnowledgeCandidate(
        character_id="char_evelyn_gray",
        proposition_id="fact.morris_reaction",
        certainty=0.4,
        source_ref="advice_g001_t01",
        status="uncertain",
    )
    world_event_candidate = WorldEventCandidate(
        event_type="observed_reaction",
        actors=["char_evelyn_gray"],
        targets=["npc_doctor_morris"],
        payload={"observation": "morris_paused"},
        visibility=WorldEventVisibility(public=False, known_by=["char_evelyn_gray"]),
    )
    policy = ResolutionPolicy(
        known_clue_ids=frozenset({"clue_doctor_pause"}),
        known_secret_ids=frozenset({"secret_01"}),
        policy_id="golden-overlay-test",
        rules=(
            ResolutionRule(
                rule_id="observe-morris",
                intent=intent.intent,
                action_types=tuple(action.type for action in intent.actions),
                effect=StoryEffect(
                    outcome="partial_success",
                    clue_ids_add=("clue_doctor_pause",),
                    character_deltas=(character_delta,),
                    relationship_deltas=(relationship_delta,),
                    knowledge_candidates=(knowledge_candidate,),
                    world_event_candidates=(world_event_candidate,),
                ),
            ),
        ),
    )

    result = DeterministicOutcomeResolver().resolve(
        intent,
        policy,
        delta_id="delta_g001_t01",
    )

    assert result.character_deltas == [character_delta]
    assert result.relationship_deltas == [relationship_delta]
    assert result.knowledge_candidates == [knowledge_candidate]
    assert result.world_event_candidates == [world_event_candidate]
    assert advice.id in result.evidence_ids
    validate_resolved_state_delta(
        intent,
        policy,
        result,
        known_character_ids={"char_evelyn_gray", "npc_doctor_morris"},
        authorized_evidence_ids={*intent.evidence_ids, intent.id},
    )

    altered = result.model_copy(update={"outcome": "failure"})
    with pytest.raises(DomainCandidateValidationError, match="deterministic resolver"):
        validate_resolved_state_delta(
            intent,
            policy,
            altered,
            known_character_ids={"char_evelyn_gray", "npc_doctor_morris"},
            authorized_evidence_ids={*intent.evidence_ids, intent.id},
        )
