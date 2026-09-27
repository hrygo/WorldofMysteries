"""Pure reducer for bounded, evidence-backed Relationship dimension changes."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
import math
from types import MappingProxyType

from contracts.models import RelationshipDelta


class RelationshipTransitionError(ValueError):
    """A RelationshipDelta cannot be applied to the supplied relationship."""


_DIMENSION_BOUNDS = {
    "trust": (-1.0, 1.0),
    "affection": (-1.0, 1.0),
    "respect": (-1.0, 1.0),
    "fear": (0.0, 1.0),
    "hostility": (0.0, 1.0),
    "dependency": (0.0, 1.0),
}


@dataclass(frozen=True, slots=True)
class RelationshipState:
    """Minimal immutable relationship aggregate consumed by the pure reducer."""

    id: str
    worldline_id: str
    from_character_id: str
    to_character_id: str
    dimensions: Mapping[str, float]
    evidence_ids: tuple[str, ...]
    revision: int

    def __post_init__(self) -> None:
        if not all(
            (
                self.id,
                self.worldline_id,
                self.from_character_id,
                self.to_character_id,
            )
        ):
            raise RelationshipTransitionError("relationship identity fields are required")
        if type(self.revision) is not int or self.revision < 0:
            raise RelationshipTransitionError("relationship revision must be nonnegative")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise RelationshipTransitionError("relationship evidence ids must be unique")
        if set(self.dimensions) != set(_DIMENSION_BOUNDS):
            raise RelationshipTransitionError("relationship dimensions are incomplete")
        normalized: dict[str, float] = {}
        for key, value in self.dimensions.items():
            numeric = _finite_number(value, f"relationship {key}")
            low, high = _DIMENSION_BOUNDS[key]
            if not low <= numeric <= high:
                raise RelationshipTransitionError(
                    f"relationship {key} is outside its allowed range"
                )
            normalized[key] = float(numeric)
        object.__setattr__(self, "dimensions", MappingProxyType(normalized))
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))


def _finite_number(value: object, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RelationshipTransitionError(f"{label} must be numeric")
    if isinstance(value, float) and not math.isfinite(value):
        raise RelationshipTransitionError(f"{label} must be finite")
    return value


def apply_relationship_delta(
    relationship: RelationshipState,
    delta: RelationshipDelta,
    *,
    authorized_evidence_ids: Collection[str],
) -> RelationshipState:
    """Apply dimension increments without clamping or changing relationship identity."""
    if (
        delta.from_character_id != relationship.from_character_id
        or delta.to_character_id != relationship.to_character_id
    ):
        raise RelationshipTransitionError("relationship delta targets a different pair")
    if not delta.evidence_ids:
        raise RelationshipTransitionError("relationship delta requires evidence")
    if not set(delta.evidence_ids).issubset(set(authorized_evidence_ids)):
        raise RelationshipTransitionError("relationship delta evidence is not authorized")

    increments = delta.dimension_deltas.model_dump(exclude_none=True)
    if not increments:
        raise RelationshipTransitionError("relationship delta must change a dimension")

    updated = dict(relationship.dimensions)
    for key, amount in increments.items():
        if key not in _DIMENSION_BOUNDS:
            raise RelationshipTransitionError("relationship delta references an unknown dimension")
        numeric = _finite_number(amount, f"relationship delta {key}")
        low, high = _DIMENSION_BOUNDS[key]
        if not low - updated[key] <= numeric <= high - updated[key]:
            raise RelationshipTransitionError(
                f"relationship {key} result is outside its allowed range"
            )
        updated[key] = float(updated[key] + numeric)

    evidence = tuple(dict.fromkeys((*relationship.evidence_ids, *delta.evidence_ids)))
    return RelationshipState(
        id=relationship.id,
        worldline_id=relationship.worldline_id,
        from_character_id=relationship.from_character_id,
        to_character_id=relationship.to_character_id,
        dimensions=updated,
        evidence_ids=evidence,
        revision=relationship.revision + 1,
    )
