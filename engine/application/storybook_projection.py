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
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from contracts import Episode, NarrativeBlock

SCHEMA_VERSION = "1.0"


class StoryBookProjectionError(RuntimeError):
    """A finalized Episode cannot be projected into a Story Book."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def project_story_book(
    *,
    episode: Episode,
    narrative_blocks: Mapping[str, NarrativeBlock],
    character_display_names: Mapping[str, str],
) -> dict[str, Any]:
    """Assemble the reading-mode Story Book for one finalized ``episode``.

    ``narrative_blocks`` is keyed by block id and indexed here in the order the
    Episode references them, so the chapter order is the committed order rather
    than whatever order a caller happened to load blocks in.
    """
    block_ids = list(episode.narrative_block_ids or ())
    if not block_ids:
        raise StoryBookProjectionError("storybook_has_no_chapters")

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
        "start_world_time": episode.start_world_time,
        "end_world_time": episode.end_world_time,
        "chapters": chapters,
        "ending": {
            "type": episode.ending.type,
            "main_problem": episode.ending.main_problem,
        },
        "unresolved_threads": list(episode.unresolved_threads),
    }
