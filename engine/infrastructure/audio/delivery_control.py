"""Authenticated IPC control surface for W-V06 DeliveryCursor.

The service is injected into LocalIPCServer.control_handlers only when a real,
world-bound SQLiteDeliveryCursorRepository exists. The default Engine remains
system-only and therefore cannot fabricate persistent playback state.
"""
from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from infrastructure.delivery_cursor_repository import (
    DeliveryCursor,
    DeliveryCursorConflict,
    DeliveryEvidence,
    DeliveryStopReason,
    SQLiteDeliveryCursorRepository,
)
from infrastructure.database_schema import StorageError


class DeliveryCursorGetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: str = Field(pattern=r"^1\.0$")
    operation: str = Field(pattern=r"^get$")
    track_id: str = Field(min_length=1, max_length=256)
    consumer_id: str = Field(min_length=1, max_length=256)


class DeliveryCursorUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: str = Field(pattern=r"^1\.0$")
    operation: str = Field(pattern=r"^update$")
    track_id: str = Field(min_length=1, max_length=256)
    consumer_id: str = Field(min_length=1, max_length=256)
    unit_id: str = Field(min_length=1, max_length=256)
    generation: StrictInt = Field(ge=0)
    source_offset_frames: StrictInt = Field(ge=0)
    total_source_frames: StrictInt | None = Field(default=None, ge=1)
    evidence: DeliveryEvidence
    stop_reason: DeliveryStopReason | None = None
    expected_cursor_revision: StrictInt = Field(ge=0)


def _payload(cursor: DeliveryCursor | None) -> dict[str, object]:
    if cursor is None:
        return {"schema_version": "1.0", "cursor": None}
    return {
        "schema_version": "1.0",
        "cursor": {
            "track_id": cursor.track_id,
            "consumer_id": cursor.consumer_id,
            "unit_id": cursor.unit_id,
            "generation": cursor.generation,
            "source_offset_frames": cursor.source_offset_frames,
            "total_source_frames": cursor.total_source_frames,
            "evidence": cursor.evidence.value,
            "stop_reason": (
                None if cursor.stop_reason is None else cursor.stop_reason.value
            ),
            "cursor_revision": cursor.cursor_revision,
            "fully_output": cursor.fully_output,
        },
    }


class DeliveryCursorControlRuntime:
    """Strict get/update handlers backed by one world-bound cursor repository."""

    GET_METHOD = "voice.delivery.get"
    UPDATE_METHOD = "voice.delivery.update"

    def __init__(self, repository: SQLiteDeliveryCursorRepository) -> None:
        self._repository = repository

    def control_handlers(self):
        return {
            self.GET_METHOD: self.handle_get,
            self.UPDATE_METHOD: self.handle_update,
        }

    async def handle_get(
        self, payload: Mapping[str, object]
    ) -> tuple[dict[str, object] | None, str | None]:
        try:
            request = DeliveryCursorGetRequest.model_validate(dict(payload))
            cursor = await self._repository.load(
                request.track_id,
                request.consumer_id,
            )
            return _payload(cursor), None
        except (ValidationError, TypeError, ValueError):
            return None, "schema_invalid"
        except StorageError:
            return None, "delivery_cursor_storage_error"

    async def handle_update(
        self, payload: Mapping[str, object]
    ) -> tuple[dict[str, object] | None, str | None]:
        try:
            request = DeliveryCursorUpdateRequest.model_validate(dict(payload))
        except (ValidationError, TypeError, ValueError):
            return None, "schema_invalid"

        try:
            if request.expected_cursor_revision == 0:
                if (
                    request.source_offset_frames != 0
                    or request.evidence is not DeliveryEvidence.QUEUED
                    or request.stop_reason is not None
                ):
                    return None, "delivery_cursor_create_requires_queued_start"
                cursor = await self._repository.create(
                    DeliveryCursor.queued(
                        track_id=request.track_id,
                        consumer_id=request.consumer_id,
                        unit_id=request.unit_id,
                        generation=request.generation,
                        total_source_frames=request.total_source_frames,
                    )
                )
            else:
                cursor = await self._repository.advance(
                    request.track_id,
                    request.consumer_id,
                    expected_cursor_revision=request.expected_cursor_revision,
                    generation=request.generation,
                    unit_id=request.unit_id,
                    source_offset_frames=request.source_offset_frames,
                    total_source_frames=request.total_source_frames,
                    evidence=request.evidence,
                    stop_reason=request.stop_reason,
                )
            return _payload(cursor), None
        except DeliveryCursorConflict:
            return None, "delivery_cursor_conflict"
        except StorageError:
            return None, "delivery_cursor_storage_error"
