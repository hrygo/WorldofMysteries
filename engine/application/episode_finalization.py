"""Application use case for atomic Episode finalization."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from contracts import Episode


class EpisodeFinalizationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class EpisodeFinalizationArtifacts:
    character_events: tuple[dict[str, object], ...] = ()
    relationship_events: tuple[dict[str, object], ...] = ()
    knowledge_changes: tuple[dict[str, object], ...] = ()
    memories: tuple[dict[str, object], ...] = ()
    world_events: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class EpisodeFinalizationCommand:
    session_id: str
    expected_story_revision: int
    world_time: str
    expected_store_revision: int
    idempotency_key: str
    request_id: str
    trace_id: str
    episode: Episode
    artifacts: EpisodeFinalizationArtifacts


class EpisodeFinalizationPort(Protocol):
    async def finalize(self, command: EpisodeFinalizationCommand): ...


class EpisodeFinalizationService:
    def __init__(self, *, port: EpisodeFinalizationPort) -> None:
        self._port = port

    async def finalize(self, command: EpisodeFinalizationCommand):
        if not isinstance(command, EpisodeFinalizationCommand):
            raise EpisodeFinalizationError("invalid_finalization_command")
        if not isinstance(command.episode, Episode):
            raise EpisodeFinalizationError("invalid_episode")
        if not isinstance(command.artifacts, EpisodeFinalizationArtifacts):
            raise EpisodeFinalizationError("invalid_episode_artifacts")
        if command.expected_story_revision != 5:
            raise EpisodeFinalizationError("expected_story_revision_mismatch")
        if command.episode.ending.type != "partial_truth":
            raise EpisodeFinalizationError("invalid_episode_ending")
        if not command.artifacts.memories:
            raise EpisodeFinalizationError("missing_episode_memory")
        return await self._port.finalize(command)
