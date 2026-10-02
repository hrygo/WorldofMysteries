"""Story Book assembly over a finalized session (PRD §20.1).

This is the loading layer between the wire and the pure projection in
``storybook_projection``: given a session, it resolves the committed Episode,
loads exactly the Narrative Blocks that Episode references, and hands them to
the projection with the scenario's public-name table for fail-closed speaker
resolution.

Every read is of already-committed world.db authority. Nothing here calls the
resolver or a model, so §20.1 — never let the model rewrite an "approximately
the same" novel after the fact — holds by construction.

Ports are ``Optional``-returning rather than raising: the concrete SQLite
adapters translate their ``StorageError`` into ``None`` at the boundary, which
keeps the domain layer free of any infrastructure import.
"""

from __future__ import annotations

from typing import Protocol

from contracts import Episode, NarrativeBlock

from .story_initialization import StorySessionBootstrap
from .storybook_projection import StoryBookProjectionError, project_story_book


class StoryBookBootstrapPort(Protocol):
    async def load(self, session_id: str) -> StorySessionBootstrap | None: ...


class StoryBookEpisodePort(Protocol):
    async def load_finalized_episode(self, session_id: str) -> Episode | None: ...


class StoryBookNarrativePort(Protocol):
    async def load_narrative_block(self, block_id: str) -> NarrativeBlock | None: ...


class StoryBookService:
    """Assemble one session's Story Book from committed facts only."""

    def __init__(
        self,
        *,
        bootstraps: StoryBookBootstrapPort,
        episodes: StoryBookEpisodePort,
        narratives: StoryBookNarrativePort,
    ) -> None:
        self._bootstraps = bootstraps
        self._episodes = episodes
        self._narratives = narratives

    async def story_book(self, session_id: str) -> dict:
        bootstrap = await self._bootstraps.load(session_id)
        if bootstrap is None:
            raise StoryBookProjectionError("storybook_session_unknown")

        episode = await self._episodes.load_finalized_episode(session_id)
        if episode is None:
            raise StoryBookProjectionError("storybook_not_finalized")

        blocks: dict[str, NarrativeBlock] = {}
        for block_id in episode.narrative_block_ids or ():
            block = await self._narratives.load_narrative_block(block_id)
            if block is None:
                raise StoryBookProjectionError("storybook_chapter_missing")
            blocks[block_id] = block

        return project_story_book(
            episode=episode,
            narrative_blocks=blocks,
            character_display_names=bootstrap.presentation.character_display_names,
        )
