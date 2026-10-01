"""One projection of committed state into player-disclosable text.

Two post-COMMIT paths build the string the narrator sees from a committed turn:
the live delivery coordinator in ``story_runtime`` and the scenario post-COMMIT
handler. They existed as two copies of the same logic, differing only in
comments and local variable names.

That duplication was a standing leak. Both copies exist for one reason — a
canonical or hidden identifier must never reach the narrator — and a change
applied to one but not the other would leave one post-COMMIT path disclosing
canonical clue ids while the other correctly did not. No test could see it:
the two paths are exercised by different suites, and each passes on its own.

So there is one function, and both paths call it.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .story_initialization import StorySessionBootstrap


def disclosed_turn_facts(
    *,
    delta: Any,
    bootstrap: StorySessionBootstrap,
) -> str:
    """Render the committed, player-disclosable facts for one turn.

    Clue identifiers are rendered through the scenario's display-name table.
    A clue whose public label is absent is **omitted**, not rendered as its
    canonical id: this is a post-COMMIT path, so an expression failure must
    never unwind the committed turn, and a canonical identifier must never
    reach the narrator. Omission is the fail-closed choice — the alternative,
    emitting the id, would turn a missing label into a disclosure.
    """
    names = bootstrap.presentation.clue_display_names
    added = [
        name
        for clue_id in delta.story_delta.clue_ids_add or ()
        if (name := names.get(clue_id)) is not None
    ]
    parts = [f"结果判定：{delta.outcome}"]
    if added:
        parts.append("玩家发现了：" + "、".join(added))
    story_delta = delta.story_delta
    if story_delta.scene_id:
        parts.append(f"场景转为：{story_delta.scene_id}")
    if story_delta.world_time_delta_minutes:
        parts.append(f"世界时间推进：{story_delta.world_time_delta_minutes} 分钟")
    return "\n".join(parts)


def disclosed_castable_roster(
    *,
    active_character_ids: Sequence[str] | None,
    protagonist_id: str,
    character_display_names: Mapping[str, str],
) -> tuple[tuple[str, str], ...] | None:
    """Project the world roster onto who may be *heard* this turn.

    The world roster says who is physically in the scene. This says who in
    that scene may speak aloud, which is a narrower question with a different
    answer, and the two are kept apart deliberately (ADR-006 D5).

    Two narrowings apply, for two unrelated reasons, and they must not share a
    switch:

    1. The player-avatar character is never cast — the player speaks in their
       own voice. This is product setting, not a permission.
    2. A character with no entry in ``character_display_names`` is omitted.
        This is the same fail-closed rule ``clue_display_names`` already obeys:
        having no public label means there is nothing to disclose, and emitting
        the canonical id instead would turn a missing label into a disclosure.

    Returns ``(canonical_id, public_label)`` pairs in scene order. The
    canonical id stays on the trusted side of the boundary — it is what the
    publication layer binds a voice to — while the label is what the narrator
    is given. Handing the narrator an id is the leak this whole projection
    exists to prevent.

    ``None`` in, ``None`` out. The world not having declared a roster is an
    absence of a fact, and the scene being empty is the assertion that nobody
    is there; collapsing them would make "we have not asked" indistinguishable
    from "nobody is here", and only one of those is a claim.

    The parameter is the public-name table itself rather than the bootstrap that
    carries it. That table is the whole of what this projection reads, and the
    world-side reader holds it as plain data: taking ``StorySessionBootstrap``
    would force that reader to fabricate a domain model it has no business
    building, and a fabricated one would be a second, unreviewed source of the
    same names.

    Pure in committed state and that table, so a retry of the expression layer
    cannot change who may speak — which is what lets the roster be hashed into
    published identity without becoming non-deterministic under retry.
    """
    if active_character_ids is None:
        return None
    roster: list[tuple[str, str]] = []
    for character_id in active_character_ids:
        if character_id == protagonist_id:
            continue
        label = character_display_names.get(character_id)
        if label is None:
            continue
        roster.append((character_id, label))
    return tuple(roster)


__all__ = ["disclosed_castable_roster", "disclosed_turn_facts"]
