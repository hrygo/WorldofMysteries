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


__all__ = ["disclosed_turn_facts"]
