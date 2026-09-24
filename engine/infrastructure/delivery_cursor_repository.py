"""Durable W-V06 DeliveryCursor presentation state.

A cursor records source-audio progress evidence; it is never a world fact and it
never promotes scheduling or rendered estimates into proven audible completion.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from .database_manager import DatabaseManager, PresentationTransaction, StorageError


class DeliveryCursorConflict(StorageError):
    pass


class DeliveryEvidence(str, Enum):
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    RENDERED_ESTIMATE = "rendered_estimate"
    MEASURED_LOOPBACK = "measured_loopback"


class DeliveryStopReason(str, Enum):
    USER_STOP = "user_stop"
    SUPERSEDED = "superseded"
    DEVICE_ROUTE_CHANGE = "device_route_change"
    SUSPEND = "suspend"
    PROVIDER_ERROR = "provider_error"
    MEDIA_ERROR = "media_error"
    COMPLETED = "completed"


_EVIDENCE_RANK = {
    DeliveryEvidence.QUEUED: 0,
    DeliveryEvidence.SCHEDULED: 1,
    DeliveryEvidence.RENDERED_ESTIMATE: 2,
    DeliveryEvidence.MEASURED_LOOPBACK: 3,
}


def _identifier(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 256
        or "\x00" in value
    ):
        raise StorageError(f"Invalid DeliveryCursor {field}")
    return value


@dataclass(frozen=True, slots=True)
class DeliveryCursor:
    track_id: str
    consumer_id: str
    unit_id: str
    generation: int
    source_offset_frames: int
    total_source_frames: int | None
    evidence: DeliveryEvidence
    stop_reason: DeliveryStopReason | None
    cursor_revision: int

    def __post_init__(self) -> None:
        _identifier(self.track_id, "track_id")
        _identifier(self.consumer_id, "consumer_id")
        _identifier(self.unit_id, "unit_id")
        if type(self.generation) is not int or self.generation < 0:
            raise StorageError("Invalid DeliveryCursor generation")
        if (
            type(self.source_offset_frames) is not int
            or self.source_offset_frames < 0
        ):
            raise StorageError("Invalid DeliveryCursor source offset")
        if self.total_source_frames is not None and (
            type(self.total_source_frames) is not int
            or self.total_source_frames <= 0
            or self.source_offset_frames > self.total_source_frames
        ):
            raise StorageError("Invalid DeliveryCursor total frames")
        if not isinstance(self.evidence, DeliveryEvidence):
            raise StorageError("Invalid DeliveryCursor evidence")
        if self.stop_reason is not None and not isinstance(
            self.stop_reason, DeliveryStopReason
        ):
            raise StorageError("Invalid DeliveryCursor stop reason")
        if type(self.cursor_revision) is not int or self.cursor_revision < 1:
            raise StorageError("Invalid DeliveryCursor revision")

    @property
    def fully_output(self) -> bool:
        return (
            self.total_source_frames is not None
            and self.source_offset_frames == self.total_source_frames
            and self.evidence is DeliveryEvidence.MEASURED_LOOPBACK
        )

    @classmethod
    def queued(
        cls,
        *,
        track_id: str,
        consumer_id: str,
        unit_id: str,
        generation: int,
        total_source_frames: int | None = None,
    ) -> "DeliveryCursor":
        return cls(
            track_id=track_id,
            consumer_id=consumer_id,
            unit_id=unit_id,
            generation=generation,
            source_offset_frames=0,
            total_source_frames=total_source_frames,
            evidence=DeliveryEvidence.QUEUED,
            stop_reason=None,
            cursor_revision=1,
        )

    def advance(
        self,
        *,
        expected_cursor_revision: int,
        generation: int,
        unit_id: str,
        source_offset_frames: int,
        total_source_frames: int | None,
        evidence: DeliveryEvidence,
        stop_reason: DeliveryStopReason | None = None,
    ) -> "DeliveryCursor":
        if expected_cursor_revision != self.cursor_revision:
            raise DeliveryCursorConflict("DeliveryCursor revision mismatch")
        _identifier(unit_id, "unit_id")
        if type(generation) is not int or generation < self.generation:
            raise DeliveryCursorConflict("DeliveryCursor generation moved backwards")
        if not isinstance(evidence, DeliveryEvidence):
            raise StorageError("Invalid DeliveryCursor evidence")
        if stop_reason is not None and not isinstance(stop_reason, DeliveryStopReason):
            raise StorageError("Invalid DeliveryCursor stop reason")
        if type(source_offset_frames) is not int or source_offset_frames < 0:
            raise StorageError("Invalid DeliveryCursor source offset")
        if total_source_frames is not None and (
            type(total_source_frames) is not int
            or total_source_frames <= 0
            or source_offset_frames > total_source_frames
        ):
            raise StorageError("Invalid DeliveryCursor total frames")

        if generation > self.generation:
            if source_offset_frames != 0 or evidence is not DeliveryEvidence.QUEUED:
                raise DeliveryCursorConflict(
                    "A new DeliveryCursor generation must restart at queued sentence start"
                )
            if stop_reason is not None:
                raise DeliveryCursorConflict(
                    "A new DeliveryCursor generation cannot begin already stopped"
                )
            return replace(
                self,
                unit_id=unit_id,
                generation=generation,
                source_offset_frames=0,
                total_source_frames=total_source_frames,
                evidence=evidence,
                stop_reason=None,
                cursor_revision=self.cursor_revision + 1,
            )

        if unit_id != self.unit_id:
            raise DeliveryCursorConflict(
                "DeliveryCursor unit cannot change within a generation"
            )
        if self.stop_reason is not None:
            if source_offset_frames != self.source_offset_frames:
                raise DeliveryCursorConflict(
                    "A stopped DeliveryCursor generation cannot advance its offset"
                )
            if (
                stop_reason is not None
                and stop_reason is not self.stop_reason
            ):
                raise DeliveryCursorConflict(
                    "A stopped DeliveryCursor reason cannot change"
                )
            if _EVIDENCE_RANK[evidence] < _EVIDENCE_RANK[self.evidence]:
                raise DeliveryCursorConflict("DeliveryCursor evidence regressed")
            if self.total_source_frames is not None:
                if total_source_frames != self.total_source_frames:
                    raise DeliveryCursorConflict("DeliveryCursor total frames changed")
                resolved_total = self.total_source_frames
            else:
                resolved_total = total_source_frames
            return replace(
                self,
                total_source_frames=resolved_total,
                evidence=evidence,
                stop_reason=self.stop_reason,
                cursor_revision=self.cursor_revision + 1,
            )
        if source_offset_frames < self.source_offset_frames:
            raise DeliveryCursorConflict("DeliveryCursor source offset moved backwards")
        if _EVIDENCE_RANK[evidence] < _EVIDENCE_RANK[self.evidence]:
            raise DeliveryCursorConflict("DeliveryCursor evidence regressed")
        if self.total_source_frames is not None:
            if total_source_frames != self.total_source_frames:
                raise DeliveryCursorConflict("DeliveryCursor total frames changed")
        elif total_source_frames is not None and source_offset_frames > total_source_frames:
            raise StorageError("Invalid DeliveryCursor total frames")

        return replace(
            self,
            source_offset_frames=source_offset_frames,
            total_source_frames=(
                self.total_source_frames
                if self.total_source_frames is not None
                else total_source_frames
            ),
            evidence=evidence,
            stop_reason=stop_reason,
            cursor_revision=self.cursor_revision + 1,
        )


def _from_row(row: dict) -> DeliveryCursor:
    return DeliveryCursor(
        track_id=row["track_id"],
        consumer_id=row["consumer_id"],
        unit_id=row["unit_id"],
        generation=row["generation"],
        source_offset_frames=row["source_offset_frames"],
        total_source_frames=row["total_source_frames"],
        evidence=DeliveryEvidence(row["evidence"]),
        stop_reason=(
            None
            if row["stop_reason"] is None
            else DeliveryStopReason(row["stop_reason"])
        ),
        cursor_revision=row["cursor_revision"],
    )


def _values(cursor: DeliveryCursor) -> tuple:
    return (
        cursor.track_id,
        cursor.consumer_id,
        cursor.unit_id,
        cursor.generation,
        cursor.source_offset_frames,
        cursor.total_source_frames,
        cursor.evidence.value,
        None if cursor.stop_reason is None else cursor.stop_reason.value,
        cursor.cursor_revision,
    )


class SQLiteDeliveryCursorRepository:
    """Single-writer CAS repository for persistent presentation delivery progress."""

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    async def load(self, track_id: str, consumer_id: str) -> DeliveryCursor | None:
        rows = await self.database.read_world(
            "SELECT * FROM delivery_cursors WHERE track_id=? AND consumer_id=?",
            (track_id, consumer_id),
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise StorageError("DeliveryCursor uniqueness is corrupted")
        return _from_row(rows[0])

    async def create(self, cursor: DeliveryCursor) -> DeliveryCursor:
        if cursor.cursor_revision != 1:
            raise StorageError("DeliveryCursor must start at revision 1")

        def apply(tx: PresentationTransaction):
            rows = tx.execute(
                "SELECT * FROM delivery_cursors WHERE track_id=? AND consumer_id=?",
                (cursor.track_id, cursor.consumer_id),
            )
            if rows:
                current = _from_row(rows[0])
                if current == cursor:
                    return current
                raise DeliveryCursorConflict("DeliveryCursor already exists")
            tx.execute(
                "INSERT INTO delivery_cursors("
                "track_id,consumer_id,unit_id,generation,source_offset_frames,"
                "total_source_frames,evidence,stop_reason,cursor_revision"
                ") VALUES (?,?,?,?,?,?,?,?,?)",
                _values(cursor),
            )
            return cursor

        return await self.database.presentation_write(apply)

    async def advance(
        self,
        track_id: str,
        consumer_id: str,
        *,
        expected_cursor_revision: int,
        generation: int,
        unit_id: str,
        source_offset_frames: int,
        total_source_frames: int | None,
        evidence: DeliveryEvidence,
        stop_reason: DeliveryStopReason | None = None,
    ) -> DeliveryCursor:
        def apply(tx: PresentationTransaction):
            rows = tx.execute(
                "SELECT * FROM delivery_cursors WHERE track_id=? AND consumer_id=?",
                (track_id, consumer_id),
            )
            if len(rows) != 1:
                raise StorageError("DeliveryCursor not found")
            current = _from_row(rows[0])
            updated = current.advance(
                expected_cursor_revision=expected_cursor_revision,
                generation=generation,
                unit_id=unit_id,
                source_offset_frames=source_offset_frames,
                total_source_frames=total_source_frames,
                evidence=evidence,
                stop_reason=stop_reason,
            )
            tx.execute(
                "UPDATE delivery_cursors SET unit_id=?,generation=?,"
                "source_offset_frames=?,total_source_frames=?,evidence=?,"
                "stop_reason=?,cursor_revision=? "
                "WHERE track_id=? AND consumer_id=? AND cursor_revision=?",
                (
                    updated.unit_id,
                    updated.generation,
                    updated.source_offset_frames,
                    updated.total_source_frames,
                    updated.evidence.value,
                    None
                    if updated.stop_reason is None
                    else updated.stop_reason.value,
                    updated.cursor_revision,
                    track_id,
                    consumer_id,
                    expected_cursor_revision,
                ),
            )
            return updated

        return await self.database.presentation_write(apply)
