"""Pure boundary validation for ActionIntent and StateDelta domain candidates."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from contracts import ActionIntent, Character, PlayerAdvice, StateDelta
from contracts.models import KnowledgeCandidate, RelationshipDelta, WorldEventCandidate

from .character_state_reducer import CharacterStateTransitionError, validate_character_delta
from .resolution_policy import ResolutionPolicy
from .resolver import DeterministicOutcomeResolver


class DomainCandidateValidationError(ValueError):
    """A proposal or cross-domain candidate exceeds its authorized boundary."""


def validate_action_intent(
    advice: PlayerAdvice,
    intent: ActionIntent,
    character: Character,
    *,
    authorized_evidence_ids: Collection[str],
) -> None:
    """Validate intent identity and provenance without turning Advice into a command.

    The intent is independently selected by the Character Reasoner. This check
    binds it to the correct turn and character and prevents it from citing
    evidence outside the authorized context; it does not require the chosen
    actions to copy the player's proposed actions.
    """
    if intent.turn_id != advice.turn_id:
        raise DomainCandidateValidationError("action intent turn does not match advice")
    if intent.character_id != character.id:
        raise DomainCandidateValidationError("action intent character does not match")
    if advice.id not in intent.evidence_ids:
        raise DomainCandidateValidationError("action intent must cite its player advice")
    if not set(intent.evidence_ids).issubset(set(authorized_evidence_ids)):
        raise DomainCandidateValidationError("action intent cites unauthorized evidence")


def _strings_in(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from _strings_in(key)
            yield from _strings_in(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings_in(item)


def _validate_relationship_reference(
    delta: RelationshipDelta,
    *,
    known_character_ids: set[str],
    evidence_ids: set[str],
) -> None:
    if delta.from_character_id not in known_character_ids or delta.to_character_id not in known_character_ids:
        raise DomainCandidateValidationError("relationship delta references an unknown character")
    if not delta.evidence_ids or not set(delta.evidence_ids).issubset(evidence_ids):
        raise DomainCandidateValidationError("relationship delta has unauthorized evidence")


def _validate_knowledge_candidate(
    candidate: KnowledgeCandidate,
    *,
    known_character_ids: set[str],
    evidence_ids: set[str],
) -> None:
    if candidate.character_id not in known_character_ids:
        raise DomainCandidateValidationError("knowledge candidate references an unknown character")
    if candidate.source_ref not in evidence_ids:
        raise DomainCandidateValidationError("knowledge candidate source is not authorized evidence")


def _validate_world_event_candidate(
    candidate: WorldEventCandidate,
    *,
    known_character_ids: set[str],
    hidden_fact_literals: set[str],
) -> None:
    references = set(candidate.actors) | set(candidate.targets)
    if not references.issubset(known_character_ids):
        raise DomainCandidateValidationError("world event references an unknown character")
    visibility = candidate.visibility
    visible_to = set(visibility.known_by or ()) | set(visibility.possibly_known_by or ())
    if not visible_to.issubset(known_character_ids):
        raise DomainCandidateValidationError("world event visibility references an unknown character")
    if visibility.public and hidden_fact_literals:
        payload_strings = tuple(_strings_in(candidate.payload))
        if any(
            hidden and any(hidden in value for value in payload_strings)
            for hidden in hidden_fact_literals
        ):
            raise DomainCandidateValidationError(
                "public world event exposes a hidden fact"
            )


def validate_state_delta_overlays(
    delta: StateDelta,
    *,
    known_character_ids: Collection[str],
    authorized_evidence_ids: Collection[str],
    hidden_fact_literals: Collection[str] = (),
) -> None:
    """Validate overlay references and provenance without performing I/O."""
    known = set(known_character_ids)
    authorized = set(authorized_evidence_ids)
    delta_evidence = set(delta.evidence_ids)
    if not delta_evidence.issubset(authorized):
        raise DomainCandidateValidationError("state delta cites unauthorized evidence")

    for character_delta in delta.character_deltas:
        try:
            validate_character_delta(
                character_delta,
                character_id=character_delta.character_id,
                authorized_evidence_ids=delta_evidence,
            )
        except CharacterStateTransitionError as exc:
            raise DomainCandidateValidationError(str(exc)) from exc
        if character_delta.character_id not in known:
            raise DomainCandidateValidationError(
                "character delta references an unknown character"
            )

    for relationship_delta in delta.relationship_deltas or ():
        _validate_relationship_reference(
            relationship_delta,
            known_character_ids=known,
            evidence_ids=delta_evidence,
        )

    for candidate in delta.knowledge_candidates or ():
        _validate_knowledge_candidate(
            candidate,
            known_character_ids=known,
            evidence_ids=delta_evidence,
        )

    hidden_literals = {value for value in hidden_fact_literals if value}
    for candidate in delta.world_event_candidates:
        _validate_world_event_candidate(
            candidate,
            known_character_ids=known,
            hidden_fact_literals=hidden_literals,
        )


def validate_resolved_state_delta(
    intent: ActionIntent,
    policy: ResolutionPolicy,
    delta: StateDelta,
    *,
    known_character_ids: Collection[str],
    authorized_evidence_ids: Collection[str],
    hidden_fact_literals: Collection[str] = (),
) -> None:
    """Require an exact deterministic Resolver result before overlay validation."""
    expected = DeterministicOutcomeResolver().resolve(
        intent,
        policy,
        delta_id=delta.id,
    )
    if delta != expected:
        raise DomainCandidateValidationError(
            "state delta differs from the deterministic resolver result"
        )
    if delta.turn_id != intent.turn_id:
        raise DomainCandidateValidationError("state delta turn does not match action intent")
    validate_state_delta_overlays(
        delta,
        known_character_ids=known_character_ids,
        authorized_evidence_ids=authorized_evidence_ids,
        hidden_fact_literals=hidden_fact_literals,
    )
