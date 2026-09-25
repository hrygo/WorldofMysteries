"""Offline W-V08 StoryBook replay resolution.

Resolving historical tracks is deliberately storage-only: it accepts no provider,
model, render, prefetch or network callback. Every referenced take is revalidated
against its authenticated RenderManifest and local file digest before replay use.
"""
from __future__ import annotations

from dataclasses import dataclass

from .audio_authorization import (
    StoryBookAuthorizationCheck,
    StoryBookAuthorizationRequest,
    require_storybook_authorization,
)
from .audio_take_store import PublishedAudioTake, SQLiteAudioTakeStore
from .audio_track_repository import (
    AudioTrackRevision,
    AudioTrackUnit,
    SQLiteAudioTrackRepository,
)
from .database_schema import StorageError


@dataclass(frozen=True, slots=True)
class ResolvedReplayUnit:
    track_unit: AudioTrackUnit
    take: PublishedAudioTake


@dataclass(frozen=True, slots=True)
class ResolvedReplayTrack:
    track: AudioTrackRevision
    units: tuple[ResolvedReplayUnit, ...]


class OfflineStoryBookReplayResolver:
    """Resolve one immutable StoryBook revision using local durable assets only."""

    def __init__(
        self,
        tracks: SQLiteAudioTrackRepository,
        takes: SQLiteAudioTakeStore,
        *,
        authorize: StoryBookAuthorizationCheck,
    ) -> None:
        if not callable(authorize):
            raise ValueError("StoryBook replay requires an authorization check")
        self._tracks = tracks
        self._takes = takes
        self._authorize = authorize

    async def resolve(self, track_id: str) -> ResolvedReplayTrack:
        track = await self._tracks.load(track_id)
        if track is None:
            raise StorageError("StoryBook AudioTrack not found")
        take_ids = tuple(unit.take_id for unit in track.units)
        await require_storybook_authorization(
            self._authorize,
            StoryBookAuthorizationRequest(
                action="replay",
                stage="before_lookup",
                track_id=track.track_id,
                track_family_id=track.track_family_id,
                story_session_id=track.story_session_id,
                revision=track.revision,
                take_ids=take_ids,
            ),
        )

        resolved: list[ResolvedReplayUnit] = []
        for unit in track.units:
            take = await self._takes.load_take(unit.take_id)
            if take is None:
                raise StorageError("StoryBook AudioTake is unavailable")
            resolved.append(ResolvedReplayUnit(track_unit=unit, take=take))

        await require_storybook_authorization(
            self._authorize,
            StoryBookAuthorizationRequest(
                action="replay",
                stage="before_delivery",
                track_id=track.track_id,
                track_family_id=track.track_family_id,
                story_session_id=track.story_session_id,
                revision=track.revision,
                take_ids=take_ids,
            ),
        )
        return ResolvedReplayTrack(track=track, units=tuple(resolved))
