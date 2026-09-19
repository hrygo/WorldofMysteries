"""Executable foundation tests for deterministic Outcome Resolution."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from contracts import ActionIntent
from domain.resolution_policy import (
    ResolutionPolicy,
    ResolutionPolicyError,
    ResolutionRule,
    StoryEffect,
)
from domain.resolver import DeterministicOutcomeResolver


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "docs" / "07_工程启动" / "golden_001_runtime"
FIXTURES = ROOT / "fixtures" / "golden_001"
STATE_DELTA_SCHEMA = json.loads(
    (ROOT / "contracts" / "schemas" / "state_delta.schema.json").read_text(encoding="utf-8")
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _turn1_policy() -> ResolutionPolicy:
    expected = _read(FIXTURES / "turns" / "01_expected.json")
    rule = ResolutionRule(
        rule_id="rule_observe_subject_continue_conversation",
        intent="observe_subject",
        action_types=("continue_conversation",),
        effect=StoryEffect(
            outcome=expected["outcome"],
            clue_ids_add=tuple(expected["clues_added"]),
            pressure_delta=(("doctor_suspicion", expected["doctor_suspicion_delta"]),),
        ),
        evidence_ids=("policy.observe_subject",),
    )
    return ResolutionPolicy.from_story_seed(
        _read(FIXTURES / "seed.json"),
        [rule],
        policy_id="golden-turn-1-policy",
    )


def _turn1_intent() -> ActionIntent:
    return ActionIntent.model_validate(
        _read(RUNTIME / "mock" / "01_action_intent.json")
    )


def test_golden_turn_1_resolves_with_real_domain_resolver():
    intent = _turn1_intent()
    delta = DeterministicOutcomeResolver().resolve(
        intent, _turn1_policy(), delta_id="delta_g001_t01"
    )
    expected = _read(FIXTURES / "turns" / "01_expected.json")

    assert delta.outcome == expected["outcome"]
    assert delta.story_delta.clue_ids_add == expected["clues_added"]
    assert delta.pressure_delta == {
        "doctor_suspicion": expected["doctor_suspicion_delta"]
    }
    wire = delta.model_dump(mode="json", exclude_none=True)
    Draft202012Validator(STATE_DELTA_SCHEMA).validate(wire)


def test_resolution_is_deterministic_for_identical_inputs():
    resolver = DeterministicOutcomeResolver()
    intent = _turn1_intent()
    policy = _turn1_policy()
    first = resolver.resolve(intent, policy, delta_id="delta_g001_t01")
    second = resolver.resolve(intent, policy, delta_id="delta_g001_t01")
    assert first == second
    assert first.model_dump(mode="json", exclude_none=True) == second.model_dump(
        mode="json", exclude_none=True
    )


def test_unmatched_intent_fails_closed():
    intent = _turn1_intent().model_copy(update={"intent": "confront_subject"})
    with pytest.raises(ResolutionPolicyError, match="No validated resolution rule"):
        DeterministicOutcomeResolver().resolve(
            intent, _turn1_policy(), delta_id="delta_unmatched"
        )


def test_duplicate_rule_signature_is_rejected():
    effect = StoryEffect(outcome="partial_success")
    first = ResolutionRule("rule-a", "observe", ("wait",), effect)
    second = ResolutionRule("rule-b", "observe", ("wait",), effect)
    with pytest.raises(ResolutionPolicyError, match="Ambiguous"):
        ResolutionPolicy(frozenset(), frozenset(), (first, second))


def test_policy_cannot_introduce_undeclared_clue_or_secret():
    seed = _read(FIXTURES / "seed.json")
    bad_clue = ResolutionRule(
        "bad-clue",
        "observe",
        ("wait",),
        StoryEffect(outcome="partial_success", clue_ids_add=("clue_not_in_seed",)),
    )
    with pytest.raises(ResolutionPolicyError, match="undeclared clue"):
        ResolutionPolicy.from_story_seed(seed, [bad_clue])

    bad_secret = ResolutionRule(
        "bad-secret",
        "observe",
        ("wait",),
        StoryEffect(
            outcome="partial_success",
            secret_state_updates=(("secret_not_in_seed", "revealed"),),
        ),
    )
    with pytest.raises(ResolutionPolicyError, match="undeclared secret"):
        ResolutionPolicy.from_story_seed(seed, [bad_secret])


def test_user_hypothesis_in_action_parameters_cannot_become_fact():
    raw = _read(RUNTIME / "mock" / "01_action_intent.json")
    raw = copy.deepcopy(raw)
    raw["actions"][0]["parameters"] = {
        "user_hypothesis": "secret_04",
        "assert_as_truth": True,
    }
    intent = ActionIntent.model_validate(raw)
    delta = DeterministicOutcomeResolver().resolve(
        intent, _turn1_policy(), delta_id="delta_hypothesis_probe"
    )

    assert not delta.story_delta.secret_state_updates
    assert not delta.world_event_candidates
    assert "secret_04" not in json.dumps(
        delta.model_dump(mode="json", exclude_none=True), ensure_ascii=False
    )


def test_resolver_contains_no_golden_scenario_special_case():
    source = (
        (ROOT / "engine" / "domain" / "resolver.py").read_text(encoding="utf-8")
        + (ROOT / "engine" / "domain" / "resolution_policy.py").read_text(encoding="utf-8")
    )
    assert "golden_001" not in source.lower()
    assert "sqlite" not in source.lower()
    assert "agentscope" not in source.lower()

def test_policy_rejects_duplicate_clue_effects_before_resolution():
    seed = _read(FIXTURES / "seed.json")
    duplicated = ResolutionRule(
        "duplicate-clue",
        "observe",
        ("wait",),
        StoryEffect(
            outcome="partial_success",
            clue_ids_add=("clue_doctor_pause", "clue_doctor_pause"),
        ),
    )
    with pytest.raises(ResolutionPolicyError, match="clue effects must be unique"):
        ResolutionPolicy.from_story_seed(seed, [duplicated])

