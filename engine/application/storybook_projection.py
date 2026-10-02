"""Story Book reading-mode projection over one finalized Episode (PRD §20.1).

A Story Book is a **read** of what already happened, never a rewrite. This
projection assembles the book from the Episode's own references — the very
Narrative Blocks that were published while the story was being played — plus the
committed Episode metadata. It performs no resolver call, no model call and no
text generation of its own: §20.1 forbids letting the model rewrite an
"approximately the same" novel after the fact, and the only way to guarantee
that is to have no model in this path at all.

Speaker disclosure is fail-closed, matching ``story_disclosure``: a segment's
``speaker_id`` is a canonical identifier and must never reach a reader. It is
resolved through the scenario's public-name allowlist; a speaker with no public
label renders as ``null`` rather than degrading to the canonical id. Emitting
the id would turn a missing label into a disclosure.

The same rule governs the additive sections added for PRD §20's remaining
reading list — 已发现秘密 / 关键人物 / 重要关系变化 / 世界影响. Every canonical
identifier in an Episode artifact is resolved through a public-name allowlist
before it may appear, and an artifact that cannot be resolved is **skipped**
rather than rendered with the identifier still in it. Skipping is deliberate and
is not the chapter-missing case: a chapter the Episode references but that
cannot be read makes the book incomplete and raises, whereas one unnameable
artifact costs the reader a line in one section and must not cost them the book.

Every section is emitted in a total order. The projection is a pure function of
committed state, and a reading view whose order depended on dict or storage
iteration order would let two reads of the same Episode disagree.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from contracts import Episode, NarrativeBlock

SCHEMA_VERSION = "1.0"

#: The relationship axes ``RelationshipDimensions`` defines. A delta naming
#: anything else is not a relationship change this build knows how to render.
RELATIONSHIP_DIMENSIONS = (
    "trust",
    "affection",
    "respect",
    "fear",
    "dependency",
    "hostility",
)

#: §20.4 asks for the results that actually reached the world, so the most
#: far-reaching importance leads. The rank is total: every value in the schema's
#: enum has an entry.
_IMPORTANCE_RANK = {"world": 3, "local": 2, "relationship": 1, "personal": 0}
_PERSISTENCE = frozenset({"episode", "character", "world"})


class StoryBookProjectionError(RuntimeError):
    """A finalized Episode cannot be projected into a Story Book."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class StoryBookArtifacts:
    """The committed Episode artifacts a Story Book reads beyond the narrative.

    Declared here rather than reused from ``infrastructure`` so this projection
    keeps its zero-storage-import property; the repository adapts its own result
    type into this one at the boundary. Each entry is the artifact payload as it
    was committed — the knowledge and world-event groups are contract-validated
    on write, the character and relationship groups are not, so every field is
    read defensively below.
    """

    character_events: tuple[Mapping[str, Any], ...] = ()
    relationship_events: tuple[Mapping[str, Any], ...] = ()
    knowledge_changes: tuple[Mapping[str, Any], ...] = ()
    world_events: tuple[Mapping[str, Any], ...] = ()


def _label(names: Mapping[str, str], identifier: Any) -> str | None:
    """The public label for a canonical id, or ``None`` when it has none."""
    if not isinstance(identifier, str):
        return None
    return names.get(identifier)


def _labels(names: Mapping[str, str], identifiers: Any) -> list[str]:
    """Public labels for a list of ids, dropping what cannot be resolved.

    Order follows the committed list so the reader sees the world's own
    ordering, and duplicates collapse because a name repeated twice carries no
    more than the name itself.
    """
    if not isinstance(identifiers, (list, tuple)):
        return []
    seen: set[str] = set()
    resolved: list[str] = []
    for identifier in identifiers:
        label = _label(names, identifier)
        if label is None or label in seen:
            continue
        seen.add(label)
        resolved.append(label)
    return resolved


def _payload(entry: Any) -> Mapping[str, Any] | None:
    """The ``change`` payload of a turn-scoped artifact, when it is usable."""
    if not isinstance(entry, Mapping):
        return None
    change = entry.get("change")
    return change if isinstance(change, Mapping) else None


def _key_characters(
    events: tuple[Mapping[str, Any], ...],
    character_names: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Characters whose state this Episode committed changes to.

    One character can be changed in several turns; the book counts the total
    committed patches rather than listing each turn, because a reader wants to
    know who mattered, not how many rows they produced.
    """
    counts: dict[str, int] = {}
    for entry in events:
        change = _payload(entry)
        if change is None:
            continue
        character_id = change.get("character_id")
        patches = change.get("patches")
        if not isinstance(character_id, str) or not isinstance(patches, list):
            continue
        counts[character_id] = counts.get(character_id, 0) + len(patches)

    rows = [
        {"label": label, "change_count": count}
        for character_id, count in counts.items()
        if count > 0 and (label := character_names.get(character_id)) is not None
    ]
    rows.sort(key=lambda row: (-row["change_count"], row["label"]))
    return rows


def _relationship_changes(
    events: tuple[Mapping[str, Any], ...],
    character_names: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Relationship dimension changes this Episode committed.

    Only the dimensions that actually moved are projected: a full axis set with
    nulls everywhere would assert that six relationships changed when one number
    did.
    """
    rows: list[dict[str, Any]] = []
    for entry in events:
        change = _payload(entry)
        if change is None:
            continue
        raw = change.get("dimension_deltas")
        if not isinstance(raw, Mapping):
            continue
        dimensions = {
            axis: value
            for axis, value in raw.items()
            if axis in RELATIONSHIP_DIMENSIONS and value is not None
        }
        if not dimensions:
            continue
        source = _label(character_names, change.get("from_character_id"))
        target = _label(character_names, change.get("to_character_id"))
        # Neither endpoint nameable means the reader gets a stranger changing a
        # stranger: no information, and the alternative is emitting two ids.
        if source is None and target is None:
            continue
        rows.append(
            {
                "from": source,
                "to": target,
                "dimensions": {
                    axis: dimensions[axis]
                    for axis in RELATIONSHIP_DIMENSIONS
                    if axis in dimensions
                },
            }
        )
    rows.sort(
        key=lambda row: (
            row["from"] or "",
            row["to"] or "",
            tuple(sorted(row["dimensions"].items())),
        )
    )
    return rows


def _discovered_secrets(
    changes: tuple[Mapping[str, Any], ...],
    character_names: Mapping[str, str],
    proposition_names: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Facts this Episode committed as known.

    A proposition with no public label is dropped whole. Unlike a character's
    name — where a null holder still leaves a readable fact — a proposition *is*
    the fact here, so an unnamed one has nothing to show and its id must not
    stand in for the missing label.
    """
    rows: list[dict[str, Any]] = []
    for item in changes:
        if not isinstance(item, Mapping):
            continue
        label = _label(proposition_names, item.get("proposition_id"))
        status = item.get("status")
        certainty = item.get("certainty")
        if label is None or not isinstance(status, str):
            continue
        if isinstance(certainty, bool) or not isinstance(certainty, (int, float)):
            continue
        acquired = item.get("acquired_world_time")
        rows.append(
            {
                "proposition": label,
                "holder": _label(character_names, item.get("character_id")),
                "certainty": float(certainty),
                "status": status,
                "acquired_world_time": acquired if isinstance(acquired, str) else None,
            }
        )
    rows.sort(
        key=lambda row: (row["proposition"], row["holder"] or "", -row["certainty"])
    )
    return rows


def _world_impacts(
    events: tuple[Mapping[str, Any], ...],
    character_names: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Results this Episode actually wrote into World State (§20.4).

    The free-form ``payload`` of a world event is deliberately not projected: it
    is model-authored internal data, and a reading view has no reason to carry
    it. ``event_type`` is kept — it is the committed category of what happened,
    which is exactly the line §20.4 asks to show.
    """
    rows: list[dict[str, Any]] = []
    for item in events:
        if not isinstance(item, Mapping):
            continue
        event_type = item.get("event_type")
        importance = item.get("importance")
        persistence = item.get("persistence")
        if not isinstance(event_type, str) or not event_type:
            continue
        if importance not in _IMPORTANCE_RANK or persistence not in _PERSISTENCE:
            continue
        world_time = item.get("world_time")
        rows.append(
            {
                "event_type": event_type,
                "world_time": world_time if isinstance(world_time, str) else None,
                "importance": importance,
                "persistence": persistence,
                "actors": _labels(character_names, item.get("actors")),
                "targets": _labels(character_names, item.get("targets")),
            }
        )
    rows.sort(
        key=lambda row: (
            -_IMPORTANCE_RANK[row["importance"]],
            row["event_type"],
            row["world_time"] or "",
            tuple(row["actors"]),
            tuple(row["targets"]),
        )
    )
    return rows


def project_story_book(
    *,
    episode: Episode,
    narrative_blocks: Mapping[str, NarrativeBlock],
    character_display_names: Mapping[str, str],
    artifacts: StoryBookArtifacts | None = None,
    proposition_display_names: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble the reading-mode Story Book for one finalized ``episode``.

    ``narrative_blocks`` is keyed by block id and indexed here in the order the
    Episode references them, so the chapter order is the committed order rather
    than whatever order a caller happened to load blocks in.

    ``artifacts`` carries the rest of the Episode's committed record for PRD §20's
    remaining reading list, and ``proposition_display_names`` is the allowlist
    that makes 已发现秘密 projectable at all. Both are optional: a caller that
    only wants the narrative — and every bundle written before these sections
    existed — gets the SB-01 book with four empty sections rather than an error.
    """
    block_ids = list(episode.narrative_block_ids or ())
    if not block_ids:
        raise StoryBookProjectionError("storybook_has_no_chapters")

    bundle = artifacts if artifacts is not None else StoryBookArtifacts()
    propositions = proposition_display_names or {}

    chapters: list[dict[str, Any]] = []
    for block_id in block_ids:
        block = narrative_blocks.get(block_id)
        if block is None:
            raise StoryBookProjectionError("storybook_chapter_missing")
        segments: list[dict[str, Any]] = []
        for segment in block.segments:
            # Fail-closed: an absent public label yields ``speaker: null``; the
            # canonical speaker_id is never carried into the book.
            speaker = (
                character_display_names.get(segment.speaker_id)
                if segment.speaker_id
                else None
            )
            segments.append(
                {"type": segment.type, "speaker": speaker, "text": segment.text}
            )
        chapters.append(
            {
                "block_id": block.id,
                "scene_id": block.scene_id,
                "segments": segments,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode.id,
        "world_id": episode.world_id,
        "worldline_id": episode.worldline_id,
        "title": episode.title,
        "protagonist_ids": list(episode.protagonist_ids),
        # Positional, not a filtered roster: a protagonist the allowlist cannot
        # name still occupies a slot in the book, and the reader is better served
        # by "someone" than by silently losing a lead. This is the same rule
        # ``_relationship_changes`` already applies to its two endpoints.
        "protagonist_labels": [
            _label(character_display_names, identifier)
            for identifier in episode.protagonist_ids
        ],
        "start_world_time": episode.start_world_time,
        "end_world_time": episode.end_world_time,
        "chapters": chapters,
        "ending": {
            "type": episode.ending.type,
            "main_problem": episode.ending.main_problem,
        },
        "unresolved_threads": list(episode.unresolved_threads),
        "discovered_secrets": _discovered_secrets(
            bundle.knowledge_changes,
            character_display_names,
            propositions,
        ),
        "key_characters": _key_characters(
            bundle.character_events,
            character_display_names,
        ),
        "relationship_changes": _relationship_changes(
            bundle.relationship_events,
            character_display_names,
        ),
        "world_impacts": _world_impacts(
            bundle.world_events,
            character_display_names,
        ),
    }
