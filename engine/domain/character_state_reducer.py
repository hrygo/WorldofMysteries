"""Pure reducer for evidence-backed mutable Character State patches.

CharacterPatch paths use slash-separated model fields rooted at ``/state``.
Identity, core traits, Canon anchors, IDs, and domain revisions are immutable
through this reducer. Paths are deliberately limited to existing object fields;
list indexes and arbitrary object creation are not supported.
"""

from __future__ import annotations

from copy import deepcopy
import math
from collections.abc import Collection
from typing import Any

from pydantic import ValidationError

from contracts import Character
from contracts.models import CharacterState
from contracts.models import CharacterDelta


class CharacterStateTransitionError(ValueError):
    """A CharacterDelta cannot be safely applied to the current Character."""


def _tokens(path: str) -> tuple[str, ...]:
    if not path.startswith("/") or path == "/":
        raise CharacterStateTransitionError("character patch path must be rooted at /state")
    parts = tuple(path[1:].split("/"))
    if any(not item or "~" in item for item in parts):
        raise CharacterStateTransitionError("character patch path is malformed")
    if len(parts) < 2 or parts[0] != "state":
        raise CharacterStateTransitionError(
            "character patches may only target mutable state fields"
        )
    # Character.state is already the reducer document, so the public /state
    # root is a boundary marker rather than a key inside that document.
    return parts[1:]


def validate_character_delta(
    delta: CharacterDelta,
    *,
    character_id: str,
    authorized_evidence_ids: Collection[str],
) -> None:
    """Check the CharacterDelta identity, provenance, and mutable path boundary."""
    if delta.character_id != character_id:
        raise CharacterStateTransitionError("character delta targets a different character")
    if not delta.patches:
        raise CharacterStateTransitionError("character delta must contain a patch")
    if not delta.evidence_ids:
        raise CharacterStateTransitionError("character delta requires evidence")
    if not set(delta.evidence_ids).issubset(set(authorized_evidence_ids)):
        raise CharacterStateTransitionError("character delta evidence is not authorized")
    for patch in delta.patches:
        _tokens(patch.path)


def _parent_for(document: dict[str, Any], parts: tuple[str, ...]) -> tuple[dict[str, Any], str]:
    node: Any = document
    for token in parts[:-1]:
        if not isinstance(node, dict) or token not in node:
            raise CharacterStateTransitionError("character patch path does not exist")
        node = node[token]
    if not isinstance(node, dict) or parts[-1] not in node:
        raise CharacterStateTransitionError("character patch path does not exist")
    return node, parts[-1]


def _apply_patch(document: dict[str, Any], patch: Any) -> None:
    parts = _tokens(patch.path)
    parent, field = _parent_for(document, parts)
    operation = patch.operation

    if operation == "set":
        parent[field] = deepcopy(patch.value)
        return

    if operation == "remove":
        del parent[field]
        return

    if operation == "increment":
        current = parent[field]
        amount = patch.value
        if (
            isinstance(current, bool)
            or not isinstance(current, (int, float))
            or isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or (isinstance(current, float) and not math.isfinite(current))
            or (isinstance(amount, float) and not math.isfinite(amount))
        ):
            raise CharacterStateTransitionError(
                "character increment requires finite numeric values"
            )
        try:
            updated = current + amount
        except OverflowError as exc:
            raise CharacterStateTransitionError(
                "character increment result is not finite"
            ) from exc
        if isinstance(updated, float) and not math.isfinite(updated):
            raise CharacterStateTransitionError("character increment result is not finite")
        parent[field] = updated
        return

    if operation in {"add_to_set", "remove_from_set"}:
        current = parent[field]
        if not isinstance(current, list) or patch.value is None:
            raise CharacterStateTransitionError(
                "character set operation requires a list and a non-null value"
            )
        if operation == "add_to_set":
            if patch.value not in current:
                current.append(deepcopy(patch.value))
        else:
            parent[field] = [item for item in current if item != patch.value]
        return

    raise CharacterStateTransitionError("unsupported character patch operation")


def apply_character_delta(
    character: Character,
    delta: CharacterDelta,
    *,
    authorized_evidence_ids: Collection[str],
) -> Character:
    """Return a validated Character with a single domain-revision increment."""
    validate_character_delta(
        delta,
        character_id=character.id,
        authorized_evidence_ids=authorized_evidence_ids,
    )
    document = character.state.model_dump(mode="python", exclude_none=True)
    document = deepcopy(document)
    try:
        for patch in delta.patches:
            _apply_patch(document, patch)
        state = CharacterState.model_validate(document)
        return character.model_copy(
            update={"state": state, "revision": character.revision + 1}
        )
    except ValidationError as exc:
        raise CharacterStateTransitionError(
            "character patch produces an invalid Character state"
        ) from exc
