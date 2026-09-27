"""Validated, deterministic resolution policy for the pure Domain layer.

The policy is *input* to the resolver. It does not come from per-turn narrative
text and it does not grant the model write authority. Production Story Genesis
will eventually create/validate these rules; Golden tests may inject fixed rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Sequence

from contracts.models import (
    CharacterDelta,
    KnowledgeCandidate,
    RelationshipDelta,
    WorldEventCandidate,
)


SECRET_STATES = frozenset({"hidden", "suspected", "partial", "revealed"})


class ResolutionPolicyError(ValueError):
    """The supplied policy is ambiguous, out of story bounds, or unmatched."""


@dataclass(frozen=True, slots=True)
class StoryEffect:
    outcome: str
    clue_ids_add: tuple[str, ...] = ()
    clue_ids_remove: tuple[str, ...] = ()
    secret_state_updates: tuple[tuple[str, str], ...] = ()
    world_time_delta_minutes: int | float | None = None
    pressure_delta: tuple[tuple[str, int | float], ...] = ()
    character_deltas: tuple[CharacterDelta, ...] = ()
    relationship_deltas: tuple[RelationshipDelta, ...] = ()
    knowledge_candidates: tuple[KnowledgeCandidate, ...] = ()
    world_event_candidates: tuple[WorldEventCandidate, ...] = ()

    def __post_init__(self) -> None:
        for field_name, expected_type in (
            ("character_deltas", CharacterDelta),
            ("relationship_deltas", RelationshipDelta),
            ("knowledge_candidates", KnowledgeCandidate),
            ("world_event_candidates", WorldEventCandidate),
        ):
            values = tuple(getattr(self, field_name))
            if any(not isinstance(value, expected_type) for value in values):
                raise ResolutionPolicyError(
                    f"Resolution {field_name} must contain validated domain contracts"
                )
            object.__setattr__(
                self,
                field_name,
                tuple(value.model_copy(deep=True) for value in values),
            )

    def story_delta(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.world_time_delta_minutes is not None:
            payload["world_time_delta_minutes"] = self.world_time_delta_minutes
        if self.clue_ids_add:
            payload["clue_ids_add"] = list(self.clue_ids_add)
        if self.clue_ids_remove:
            payload["clue_ids_remove"] = list(self.clue_ids_remove)
        if self.secret_state_updates:
            payload["secret_state_updates"] = dict(self.secret_state_updates)
        return payload


@dataclass(frozen=True, slots=True)
class ResolutionRule:
    rule_id: str
    intent: str
    action_types: tuple[str, ...]
    effect: StoryEffect
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.rule_id or not self.intent or not self.action_types:
            raise ResolutionPolicyError("Resolution rules require id, intent and action types")
        if any(not item for item in self.action_types):
            raise ResolutionPolicyError("Resolution action types must be nonempty")
        if len(set(self.action_types)) != len(self.action_types):
            raise ResolutionPolicyError("Resolution rule action types must be unique")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ResolutionPolicyError("Resolution rule evidence ids must be unique")

    @property
    def signature(self) -> tuple[str, tuple[str, ...]]:
        return self.intent, tuple(sorted(self.action_types))


@dataclass(frozen=True, slots=True)
class ResolutionPolicy:
    known_clue_ids: frozenset[str]
    known_secret_ids: frozenset[str]
    rules: tuple[ResolutionRule, ...]
    policy_id: str = "resolution-policy"
    _by_signature: Mapping[tuple[str, tuple[str, ...]], ResolutionRule] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise ResolutionPolicyError("Resolution policy id must be nonempty")
        index: dict[tuple[str, tuple[str, ...]], ResolutionRule] = {}
        for rule in self.rules:
            signature = rule.signature
            if signature in index:
                raise ResolutionPolicyError(
                    f"Ambiguous resolution rules for intent/action signature: {rule.intent}"
                )
            if (len(set(rule.effect.clue_ids_add)) != len(rule.effect.clue_ids_add)
                    or len(set(rule.effect.clue_ids_remove)) != len(rule.effect.clue_ids_remove)):
                raise ResolutionPolicyError("Resolution clue effects must be unique")
            unknown_add = set(rule.effect.clue_ids_add) - self.known_clue_ids
            unknown_remove = set(rule.effect.clue_ids_remove) - self.known_clue_ids
            if unknown_add or unknown_remove:
                raise ResolutionPolicyError("Resolution rule references an undeclared clue")
            if set(rule.effect.clue_ids_add) & set(rule.effect.clue_ids_remove):
                raise ResolutionPolicyError("A rule cannot add and remove the same clue")
            secret_updates = dict(rule.effect.secret_state_updates)
            if len(secret_updates) != len(rule.effect.secret_state_updates):
                raise ResolutionPolicyError("Secret updates must not contain duplicate ids")
            if set(secret_updates) - self.known_secret_ids:
                raise ResolutionPolicyError("Resolution rule references an undeclared secret")
            if any(state not in SECRET_STATES for state in secret_updates.values()):
                raise ResolutionPolicyError("Resolution rule uses an invalid secret state")
            pressure = dict(rule.effect.pressure_delta)
            if len(pressure) != len(rule.effect.pressure_delta) or any(not key for key in pressure):
                raise ResolutionPolicyError("Pressure deltas require unique nonempty ids")
            world_time_delta = rule.effect.world_time_delta_minutes
            if world_time_delta is not None and (
                isinstance(world_time_delta, bool)
                or not isinstance(world_time_delta, (int, float))
                or (isinstance(world_time_delta, float) and not math.isfinite(world_time_delta))
            ):
                raise ResolutionPolicyError(
                    "World time delta must be a finite number"
                )
            if any(
                isinstance(amount, bool) or not isinstance(amount, (int, float))
                or (isinstance(amount, float) and not math.isfinite(amount))
                for amount in pressure.values()
            ):
                raise ResolutionPolicyError("Pressure deltas must be finite numbers")
            for character_delta in rule.effect.character_deltas:
                if not character_delta.evidence_ids:
                    raise ResolutionPolicyError("Character deltas require evidence")
            for relationship_delta in rule.effect.relationship_deltas:
                if not relationship_delta.evidence_ids:
                    raise ResolutionPolicyError("Relationship deltas require evidence")
            for candidate in rule.effect.knowledge_candidates:
                if not candidate.source_ref:
                    raise ResolutionPolicyError("Knowledge candidates require a source reference")
            index[signature] = rule
        object.__setattr__(self, "_by_signature", index)

    @classmethod
    def from_story_seed(
        cls,
        seed: Mapping[str, Any],
        rules: Sequence[ResolutionRule],
        *,
        policy_id: str = "resolution-policy",
    ) -> "ResolutionPolicy":
        clues = seed.get("clues", [])
        secrets = seed.get("secrets", [])
        try:
            clue_ids = frozenset(item["id"] for item in clues)
            secret_ids = frozenset(item["id"] for item in secrets)
        except (KeyError, TypeError) as exc:
            raise ResolutionPolicyError("Story seed clue/secret registry is malformed") from exc
        if any(not item for item in clue_ids | secret_ids):
            raise ResolutionPolicyError("Story seed clue/secret ids must be nonempty")
        return cls(clue_ids, secret_ids, tuple(rules), policy_id=policy_id)

    def match(self, intent: str, action_types: Sequence[str]) -> ResolutionRule:
        signature = intent, tuple(sorted(action_types))
        try:
            return self._by_signature[signature]
        except KeyError as exc:
            raise ResolutionPolicyError(
                f"No validated resolution rule for intent/action signature: {intent}"
            ) from exc
