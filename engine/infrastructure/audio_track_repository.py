"""W-V08 immutable StoryBook audio track revisions.

Tracks are presentation/media history, not world facts. They are insert-only and
pin complete AudioTakes by foreign key. A redub creates a new revision whose
narrative identity must exactly match the immediately superseded track; only the
sealed speech unit / take may change.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json

from contracts import NarrativeBlock

from .database_manager import AudioAssetTransaction, DatabaseManager
from .database_schema import StorageError


_ID_LIMIT = 256
_MAX_UNITS = 10_000


def _identifier(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > _ID_LIMIT
        or "\x00" in value
    ):
        raise StorageError(f"Invalid AudioTrack {field}")
    return value


class AudioTrackKind(str, Enum):
    ORIGINAL = "original"
    REDUB = "redub"


@dataclass(frozen=True, slots=True)
class AudioTrackUnit:
    ordinal: int
    unit_id: str
    turn_id: str
    narrative_block_id: str
    segment_index: int
    story_revision: int
    take_id: str

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or self.ordinal < 0:
            raise StorageError("Invalid AudioTrack ordinal")
        for value, field in (
            (self.unit_id, "unit id"),
            (self.turn_id, "turn id"),
            (self.narrative_block_id, "narrative block id"),
            (self.take_id, "take id"),
        ):
            _identifier(value, field)
        if type(self.segment_index) is not int or self.segment_index < 0:
            raise StorageError("Invalid AudioTrack segment index")
        if type(self.story_revision) is not int or self.story_revision < 0:
            raise StorageError("Invalid AudioTrack story revision")


@dataclass(frozen=True, slots=True)
class AudioTrackRevision:
    track_id: str
    track_family_id: str
    story_session_id: str
    revision: int
    kind: AudioTrackKind
    supersedes_track_id: str | None
    units: tuple[AudioTrackUnit, ...]

    def __post_init__(self) -> None:
        for value, field in (
            (self.track_id, "track id"),
            (self.track_family_id, "track family id"),
            (self.story_session_id, "story session id"),
        ):
            _identifier(value, field)
        if type(self.revision) is not int or self.revision < 1:
            raise StorageError("Invalid AudioTrack revision")
        if not isinstance(self.kind, AudioTrackKind):
            raise StorageError("Invalid AudioTrack kind")
        if not isinstance(self.units, tuple) or not 1 <= len(self.units) <= _MAX_UNITS:
            raise StorageError("AudioTrack requires bounded units")
        if tuple(unit.ordinal for unit in self.units) != tuple(range(len(self.units))):
            raise StorageError("AudioTrack ordinals must be contiguous from zero")
        if len({unit.unit_id for unit in self.units}) != len(self.units):
            raise StorageError("AudioTrack unit ids must be unique")
        if len(
            {(unit.narrative_block_id, unit.segment_index) for unit in self.units}
        ) != len(self.units):
            raise StorageError("AudioTrack narrative segments must be unique")

        if self.revision == 1:
            if self.kind is not AudioTrackKind.ORIGINAL or self.supersedes_track_id is not None:
                raise StorageError("Original AudioTrack must be revision one")
        else:
            if self.kind is not AudioTrackKind.REDUB or self.supersedes_track_id is None:
                raise StorageError("Redub AudioTrack must supersede a prior revision")
            _identifier(self.supersedes_track_id, "superseded track id")


@dataclass(frozen=True, slots=True)
class AudioTrackPublishResult:
    track: AudioTrackRevision
    replayed: bool


def _narrative_identity(unit: AudioTrackUnit) -> tuple[object, ...]:
    return (
        unit.ordinal,
        unit.turn_id,
        unit.narrative_block_id,
        unit.segment_index,
        unit.story_revision,
    )


def _from_rows(track_row: dict, unit_rows: list[dict]) -> AudioTrackRevision:
    return AudioTrackRevision(
        track_id=track_row["track_id"],
        track_family_id=track_row["track_family_id"],
        story_session_id=track_row["story_session_id"],
        revision=track_row["revision"],
        kind=AudioTrackKind(track_row["kind"]),
        supersedes_track_id=track_row["supersedes_track_id"],
        units=tuple(
            AudioTrackUnit(
                ordinal=row["ordinal"],
                unit_id=row["unit_id"],
                turn_id=row["turn_id"],
                narrative_block_id=row["narrative_block_id"],
                segment_index=row["segment_index"],
                story_revision=row["story_revision"],
                take_id=row["take_id"],
            )
            for row in unit_rows
        ),
    )


class SQLiteAudioTrackRepository:
    """Insert-only StoryBook track revisions and authoritative AudioTake pins."""

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    async def load(self, track_id: str) -> AudioTrackRevision | None:
        _identifier(track_id, "track id")
        tracks = await self.database.read_world(
            "SELECT * FROM audio_tracks WHERE track_id=?",
            (track_id,),
        )
        if not tracks:
            return None
        if len(tracks) != 1:
            raise StorageError("AudioTrack identity is ambiguous")
        units = await self.database.read_world(
            "SELECT * FROM audio_track_units WHERE track_id=? ORDER BY ordinal",
            (track_id,),
        )
        return _from_rows(tracks[0], units)

    async def latest(self, track_family_id: str) -> AudioTrackRevision | None:
        _identifier(track_family_id, "track family id")
        rows = await self.database.read_world(
            "SELECT track_id FROM audio_tracks WHERE track_family_id=? "
            "ORDER BY revision DESC LIMIT 1",
            (track_family_id,),
        )
        return None if not rows else await self.load(rows[0]["track_id"])

    async def is_take_pinned(self, take_id: str) -> bool:
        _identifier(take_id, "take id")
        rows = await self.database.read_world(
            "SELECT 1 AS pinned FROM audio_track_units WHERE take_id=? LIMIT 1",
            (take_id,),
        )
        return bool(rows)

    async def pinned_take_ids(self) -> frozenset[str]:
        rows = await self.database.read_world(
            "SELECT DISTINCT take_id FROM audio_track_units"
        )
        return frozenset(row["take_id"] for row in rows)

    async def publish(self, track: AudioTrackRevision) -> AudioTrackPublishResult:
        if not isinstance(track, AudioTrackRevision):
            raise StorageError("AudioTrack publication requires a typed revision")

        def apply(tx: AudioAssetTransaction):
            existing = tx.execute(
                "SELECT * FROM audio_tracks WHERE track_id=?",
                (track.track_id,),
            )
            if existing:
                if len(existing) != 1:
                    raise StorageError("AudioTrack identity is corrupted")
                unit_rows = tx.execute(
                    "SELECT * FROM audio_track_units WHERE track_id=? ORDER BY ordinal",
                    (track.track_id,),
                )
                current = _from_rows(existing[0], unit_rows)
                if current != track:
                    raise StorageError("AudioTrack id is already bound to different content")
                return True

            session = tx.execute(
                "SELECT id FROM story_sessions WHERE id=?",
                (track.story_session_id,),
            )
            if len(session) != 1:
                raise StorageError("AudioTrack StorySession not found")

            family = tx.execute(
                "SELECT track_id,revision FROM audio_tracks "
                "WHERE track_family_id=? ORDER BY revision",
                (track.track_family_id,),
            )
            previous: AudioTrackRevision | None = None
            if track.revision == 1:
                if family:
                    raise StorageError("AudioTrack family already has an original revision")
            else:
                if track.supersedes_track_id is None:
                    raise StorageError("Redub AudioTrack requires a predecessor")
                previous_rows = tx.execute(
                    "SELECT * FROM audio_tracks WHERE track_id=?",
                    (track.supersedes_track_id,),
                )
                if len(previous_rows) != 1:
                    raise StorageError("Superseded AudioTrack not found")
                previous_unit_rows = tx.execute(
                    "SELECT * FROM audio_track_units WHERE track_id=? ORDER BY ordinal",
                    (track.supersedes_track_id,),
                )
                previous = _from_rows(previous_rows[0], previous_unit_rows)
                if (
                    previous.track_family_id != track.track_family_id
                    or previous.story_session_id != track.story_session_id
                    or previous.revision + 1 != track.revision
                ):
                    raise StorageError("Redub AudioTrack revision chain is invalid")
                if family and family[-1]["track_id"] != previous.track_id:
                    raise StorageError("Redub AudioTrack must supersede the latest revision")
                if tuple(_narrative_identity(unit) for unit in previous.units) != tuple(
                    _narrative_identity(unit) for unit in track.units
                ):
                    raise StorageError("Redub AudioTrack cannot change narrative identity")

            for unit in track.units:
                turn_rows = tx.execute(
                    "SELECT session_id,committed_story_revision,narrative_block_id "
                    "FROM turn_transactions WHERE id=?",
                    (unit.turn_id,),
                )
                if len(turn_rows) != 1:
                    raise StorageError("AudioTrack TurnTransaction not found")
                turn = turn_rows[0]
                if (
                    turn["session_id"] != track.story_session_id
                    or turn["committed_story_revision"] != unit.story_revision
                    or turn["narrative_block_id"] != unit.narrative_block_id
                ):
                    raise StorageError("AudioTrack unit does not match committed turn")

                narrative_rows = tx.execute(
                    "SELECT turn_id,session_id,source_story_revision,payload_json "
                    "FROM narrative_blocks WHERE id=?",
                    (unit.narrative_block_id,),
                )
                if len(narrative_rows) != 1:
                    raise StorageError("AudioTrack NarrativeBlock not found")
                narrative_row = narrative_rows[0]
                if (
                    narrative_row["turn_id"] != unit.turn_id
                    or narrative_row["session_id"] != track.story_session_id
                    or narrative_row["source_story_revision"] != unit.story_revision
                ):
                    raise StorageError("AudioTrack NarrativeBlock provenance mismatch")
                try:
                    narrative = NarrativeBlock.model_validate(
                        json.loads(narrative_row["payload_json"])
                    )
                except (TypeError, ValueError, json.JSONDecodeError):
                    raise StorageError("Stored NarrativeBlock is invalid") from None
                if unit.segment_index >= len(narrative.segments):
                    raise StorageError("AudioTrack segment index is out of bounds")

                take_rows = tx.execute(
                    "SELECT status FROM audio_takes WHERE take_id=?",
                    (unit.take_id,),
                )
                if len(take_rows) != 1 or take_rows[0]["status"] != "complete":
                    raise StorageError("AudioTrack requires a complete AudioTake")

            tx.execute(
                "INSERT INTO audio_tracks("
                "track_id,track_family_id,story_session_id,revision,kind,supersedes_track_id"
                ") VALUES (?,?,?,?,?,?)",
                (
                    track.track_id,
                    track.track_family_id,
                    track.story_session_id,
                    track.revision,
                    track.kind.value,
                    track.supersedes_track_id,
                ),
            )
            for unit in track.units:
                tx.execute(
                    "INSERT INTO audio_track_units("
                    "track_id,ordinal,unit_id,turn_id,narrative_block_id,segment_index,"
                    "story_revision,take_id"
                    ") VALUES (?,?,?,?,?,?,?,?)",
                    (
                        track.track_id,
                        unit.ordinal,
                        unit.unit_id,
                        unit.turn_id,
                        unit.narrative_block_id,
                        unit.segment_index,
                        unit.story_revision,
                        unit.take_id,
                    ),
                )
            return False

        replayed = bool(await self.database.audio_asset_write(apply))
        persisted = await self.load(track.track_id)
        if persisted != track:
            raise StorageError("Published AudioTrack differs from durable state")
        return AudioTrackPublishResult(track=track, replayed=replayed)
