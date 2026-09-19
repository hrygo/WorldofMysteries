"""Deterministic Outcome Resolver (Invariants 5 & 9).

AI/character reasoning may produce an ActionIntent. Only this pure resolver,
operating on a previously validated ResolutionPolicy, may turn that proposal
into a typed StateDelta candidate. Persistence happens later.
"""
from __future__ import annotations

from typing import Protocol

from contracts import ActionIntent, StateDelta

from .resolution_policy import ResolutionPolicy, ResolutionPolicyError


class OutcomeResolverProtocol(Protocol):
    def resolve(
        self,
        intent: ActionIntent,
        policy: ResolutionPolicy,
        *,
        delta_id: str,
    ) -> StateDelta: ...


class DeterministicOutcomeResolver:
    """Resolve exact intent/action signatures with no narrative or model side effects."""

    def resolve(
        self,
        intent: ActionIntent,
        policy: ResolutionPolicy,
        *,
        delta_id: str,
    ) -> StateDelta:
        if not delta_id:
            raise ResolutionPolicyError("StateDelta id must be nonempty")

        action_types = tuple(action.type for action in intent.actions)
        rule = policy.match(intent.intent, action_types)

        evidence_ids: list[str] = []
        for evidence_id in (*intent.evidence_ids, intent.id, *rule.evidence_ids):
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)

        payload: dict[str, object] = {
            "schema_version": "1.0",
            "id": delta_id,
            "turn_id": intent.turn_id,
            "outcome": rule.effect.outcome,
            "story_delta": rule.effect.story_delta(),
            "character_deltas": [],
            "world_event_candidates": [],
            "evidence_ids": evidence_ids,
        }
        if rule.effect.pressure_delta:
            payload["pressure_delta"] = dict(rule.effect.pressure_delta)

        # StateDelta is the canonical product contract. Its Pydantic projection
        # performs the final structural validation before later Domain validators.
        return StateDelta.model_validate(payload)
