"""W-V08 fresh authorization boundary for StoryBook replay and track publication.

Track/take durability is not authorization. A trusted Application layer supplies
one immutable current authorization snapshot for an operation. Historical assets
remain intact when access is revoked, but replay consumption and new track
publication fail closed when any referenced provider voice revision is absent.
"""
from __future__ import annotations

from dataclasses import dataclass

from .audio_replay import OfflineStoryBookReplayResolver, ResolvedReplayTrack
from .audio_take_store import PublishedAudioTake, SQLiteAudioTakeStore
from .audio_track_repository import (
    AudioTrackPublishResult,
    AudioTrackRevision,
    SQLiteAudioTrackRepository,
)
from .database_schema import StorageError


VoiceRevisionKey = tuple[str, str, str]


def _bounded(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256 or "\x00" in value:
        raise StorageError(f"Invalid StoryBook {field}")
    return value


@dataclass(frozen=True, slots=True)
class VoiceAuthorizationSnapshot:
    """Immutable presentation-safe authorization view for one operation."""

    policy_revision: str
    authorized_voice_revisions: frozenset[VoiceRevisionKey]

    def __post_init__(self) -> None:
        _bounded(self.policy_revision, "authorization policy revision")
        normalized: set[VoiceRevisionKey] = set()
        for key in self.authorized_voice_revisions:
            if (
                type(key) is not tuple
                or len(key) != 3
                or any(not isinstance(value, str) or not value.strip() for value in key)
            ):
                raise StorageError("Invalid StoryBook authorized voice revision")
            normalized.add((_bounded(key[0], "provider"), _bounded(key[1], "voice"), _bounded(key[2], "voice revision")))
        object.__setattr__(self, "authorized_voice_revisions", frozenset(normalized))


@dataclass(frozen=True, slots=True)
class AuthorizedReplayTrack:
    replay: ResolvedReplayTrack
    policy_revision: str


@dataclass(frozen=True, slots=True)
class AuthorizedTrackPublishResult:
    result: AudioTrackPublishResult
    policy_revision: str


class StoryBookAudioAccessService:
    """Fresh access check around immutable local tracks/takes."""

    def __init__(
        self,
        tracks: SQLiteAudioTrackRepository,
        takes: SQLiteAudioTakeStore,
    ) -> None:
        self._tracks = tracks
        self._takes = takes
        self._replay = OfflineStoryBookReplayResolver(tracks, takes)

    async def resolve_for_replay(
        self,
        track_id: str,
        authorization: VoiceAuthorizationSnapshot,
    ) -> AuthorizedReplayTrack:
        self._require_snapshot(authorization)
        replay = await self._replay.resolve(track_id)
        for unit in replay.units:
            self._require_take_authorized(unit.take, authorization)
        return AuthorizedReplayTrack(
            replay=replay,
            policy_revision=authorization.policy_revision,
        )

    async def publish_authorized(
        self,
        track: AudioTrackRevision,
        authorization: VoiceAuthorizationSnapshot,
    ) -> AuthorizedTrackPublishResult:
        if not isinstance(track, AudioTrackRevision):
            raise StorageError("StoryBook publication requires an AudioTrack revision")
        self._require_snapshot(authorization)

        # Validate every immutable take under one frozen policy snapshot before
        # entering the single DB writer. No provider/model work is permitted here.
        for unit in track.units:
            take = await self._takes.load_take(unit.take_id)
            if take is None:
                raise StorageError("StoryBook AudioTake is unavailable")
            self._require_take_authorized(take, authorization)

        result = await self._tracks.publish(track)
        return AuthorizedTrackPublishResult(
            result=result,
            policy_revision=authorization.policy_revision,
        )

    @staticmethod
    def _require_snapshot(value: VoiceAuthorizationSnapshot) -> None:
        if not isinstance(value, VoiceAuthorizationSnapshot):
            raise StorageError("StoryBook voice authorization snapshot is required")

    @staticmethod
    def _require_take_authorized(
        take: PublishedAudioTake,
        authorization: VoiceAuthorizationSnapshot,
    ) -> None:
        resolved = take.manifest.get("resolved")
        if not isinstance(resolved, dict):
            raise StorageError("AudioTake resolved identity is unavailable")
        provider = resolved.get("provider_instance")
        voice = resolved.get("voice_id")
        revision = resolved.get("voice_revision")
        if not all(isinstance(value, str) and value for value in (provider, voice, revision)):
            raise StorageError("AudioTake voice identity is invalid")
        key = (provider, voice, revision)
        if key not in authorization.authorized_voice_revisions:
            raise StorageError("StoryBook AudioTake voice is not currently authorized")
