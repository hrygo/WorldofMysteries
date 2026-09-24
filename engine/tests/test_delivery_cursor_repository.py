"""W-V06 durable DeliveryCursor semantics."""
from __future__ import annotations

import pytest

from infrastructure.delivery_cursor_repository import (
    DeliveryCursor,
    DeliveryCursorConflict,
    DeliveryEvidence,
    DeliveryStopReason,
    SQLiteDeliveryCursorRepository,
)
from infrastructure.database_schema import StorageError


async def world_revision(database) -> int:
    rows = await database.read_world(
        "SELECT revision FROM world_meta WHERE singleton=1"
    )
    return rows[0]["revision"]


async def test_cursor_progress_is_monotonic_and_never_advances_world_revision(database):
    repo = SQLiteDeliveryCursorRepository(database)
    cursor = await repo.create(
        DeliveryCursor.queued(
            track_id="track-1",
            consumer_id="local-playback",
            unit_id="speech-1",
            generation=7,
            total_source_frames=1000,
        )
    )
    assert cursor.cursor_revision == 1
    assert await world_revision(database) == 0

    cursor = await repo.advance(
        "track-1",
        "local-playback",
        expected_cursor_revision=1,
        generation=7,
        unit_id="speech-1",
        source_offset_frames=600,
        total_source_frames=1000,
        evidence=DeliveryEvidence.SCHEDULED,
    )
    assert cursor.source_offset_frames == 600
    assert not cursor.fully_output

    cursor = await repo.advance(
        "track-1",
        "local-playback",
        expected_cursor_revision=2,
        generation=7,
        unit_id="speech-1",
        source_offset_frames=1000,
        total_source_frames=1000,
        evidence=DeliveryEvidence.RENDERED_ESTIMATE,
        stop_reason=DeliveryStopReason.COMPLETED,
    )
    assert cursor.source_offset_frames == 1000
    assert not cursor.fully_output

    proven = await repo.advance(
        "track-1",
        "local-playback",
        expected_cursor_revision=cursor.cursor_revision,
        generation=7,
        unit_id="speech-1",
        source_offset_frames=1000,
        total_source_frames=1000,
        evidence=DeliveryEvidence.MEASURED_LOOPBACK,
    )
    assert proven.fully_output
    assert proven.stop_reason is DeliveryStopReason.COMPLETED
    assert await world_revision(database) == 0


async def test_only_measured_loopback_at_total_frames_is_fully_output(database):
    repo = SQLiteDeliveryCursorRepository(database)
    await repo.create(
        DeliveryCursor.queued(
            track_id="track-2",
            consumer_id="local-playback",
            unit_id="speech-2",
            generation=1,
            total_source_frames=240,
        )
    )
    scheduled = await repo.advance(
        "track-2",
        "local-playback",
        expected_cursor_revision=1,
        generation=1,
        unit_id="speech-2",
        source_offset_frames=240,
        total_source_frames=240,
        evidence=DeliveryEvidence.SCHEDULED,
    )
    assert not scheduled.fully_output

    measured = await repo.advance(
        "track-2",
        "local-playback",
        expected_cursor_revision=2,
        generation=1,
        unit_id="speech-2",
        source_offset_frames=240,
        total_source_frames=240,
        evidence=DeliveryEvidence.MEASURED_LOOPBACK,
        stop_reason=DeliveryStopReason.COMPLETED,
    )
    assert measured.fully_output


async def test_cursor_rejects_offset_evidence_and_unit_regression(database):
    repo = SQLiteDeliveryCursorRepository(database)
    await repo.create(
        DeliveryCursor.queued(
            track_id="track-3",
            consumer_id="local-playback",
            unit_id="speech-3",
            generation=2,
        )
    )
    current = await repo.advance(
        "track-3",
        "local-playback",
        expected_cursor_revision=1,
        generation=2,
        unit_id="speech-3",
        source_offset_frames=80,
        total_source_frames=None,
        evidence=DeliveryEvidence.RENDERED_ESTIMATE,
    )

    with pytest.raises(DeliveryCursorConflict, match="source offset moved backwards"):
        await repo.advance(
            "track-3",
            "local-playback",
            expected_cursor_revision=current.cursor_revision,
            generation=2,
            unit_id="speech-3",
            source_offset_frames=79,
            total_source_frames=None,
            evidence=DeliveryEvidence.RENDERED_ESTIMATE,
        )

    with pytest.raises(DeliveryCursorConflict, match="evidence regressed"):
        await repo.advance(
            "track-3",
            "local-playback",
            expected_cursor_revision=current.cursor_revision,
            generation=2,
            unit_id="speech-3",
            source_offset_frames=80,
            total_source_frames=None,
            evidence=DeliveryEvidence.SCHEDULED,
        )

    with pytest.raises(DeliveryCursorConflict, match="unit cannot change"):
        await repo.advance(
            "track-3",
            "local-playback",
            expected_cursor_revision=current.cursor_revision,
            generation=2,
            unit_id="speech-other",
            source_offset_frames=80,
            total_source_frames=None,
            evidence=DeliveryEvidence.RENDERED_ESTIMATE,
        )


async def test_new_generation_must_restart_at_sentence_start(database):
    repo = SQLiteDeliveryCursorRepository(database)
    current = await repo.create(
        DeliveryCursor.queued(
            track_id="track-4",
            consumer_id="local-playback",
            unit_id="speech-4",
            generation=3,
            total_source_frames=500,
        )
    )
    current = await repo.advance(
        "track-4",
        "local-playback",
        expected_cursor_revision=current.cursor_revision,
        generation=3,
        unit_id="speech-4",
        source_offset_frames=200,
        total_source_frames=500,
        evidence=DeliveryEvidence.RENDERED_ESTIMATE,
        stop_reason=DeliveryStopReason.DEVICE_ROUTE_CHANGE,
    )

    with pytest.raises(DeliveryCursorConflict, match="queued sentence start"):
        await repo.advance(
            "track-4",
            "local-playback",
            expected_cursor_revision=current.cursor_revision,
            generation=4,
            unit_id="speech-4",
            source_offset_frames=200,
            total_source_frames=500,
            evidence=DeliveryEvidence.RENDERED_ESTIMATE,
        )

    restarted = await repo.advance(
        "track-4",
        "local-playback",
        expected_cursor_revision=current.cursor_revision,
        generation=4,
        unit_id="speech-4",
        source_offset_frames=0,
        total_source_frames=500,
        evidence=DeliveryEvidence.QUEUED,
    )
    assert restarted.generation == 4
    assert restarted.source_offset_frames == 0
    assert restarted.stop_reason is None


async def test_stopped_generation_cannot_advance_and_stale_cas_fails(database):
    repo = SQLiteDeliveryCursorRepository(database)
    current = await repo.create(
        DeliveryCursor.queued(
            track_id="track-5",
            consumer_id="local-playback",
            unit_id="speech-5",
            generation=1,
        )
    )
    stopped = await repo.advance(
        "track-5",
        "local-playback",
        expected_cursor_revision=1,
        generation=1,
        unit_id="speech-5",
        source_offset_frames=0,
        total_source_frames=None,
        evidence=DeliveryEvidence.QUEUED,
        stop_reason=DeliveryStopReason.USER_STOP,
    )
    with pytest.raises(DeliveryCursorConflict, match="cannot advance its offset"):
        await repo.advance(
            "track-5",
            "local-playback",
            expected_cursor_revision=stopped.cursor_revision,
            generation=1,
            unit_id="speech-5",
            source_offset_frames=1,
            total_source_frames=None,
            evidence=DeliveryEvidence.SCHEDULED,
        )
    with pytest.raises(DeliveryCursorConflict, match="revision mismatch"):
        await repo.advance(
            "track-5",
            "local-playback",
            expected_cursor_revision=1,
            generation=2,
            unit_id="speech-5",
            source_offset_frames=0,
            total_source_frames=None,
            evidence=DeliveryEvidence.QUEUED,
        )


async def test_cursor_survives_database_restart(database, db_paths):
    repo = SQLiteDeliveryCursorRepository(database)
    saved = await repo.create(
        DeliveryCursor.queued(
            track_id="track-restart",
            consumer_id="local-playback",
            unit_id="speech-restart",
            generation=9,
            total_source_frames=321,
        )
    )
    saved = await repo.advance(
        "track-restart",
        "local-playback",
        expected_cursor_revision=saved.cursor_revision,
        generation=9,
        unit_id="speech-restart",
        source_offset_frames=123,
        total_source_frames=321,
        evidence=DeliveryEvidence.RENDERED_ESTIMATE,
        stop_reason=DeliveryStopReason.SUSPEND,
    )
    await database.close()

    from infrastructure.database_manager import DatabaseManager

    reopened = await DatabaseManager.open(db_paths)
    try:
        assert await SQLiteDeliveryCursorRepository(reopened).load(
            "track-restart", "local-playback"
        ) == saved
    finally:
        await reopened.close()


async def test_stopped_cursor_allows_evidence_refinement_but_not_reason_rewrite(database):
    repo = SQLiteDeliveryCursorRepository(database)
    current = await repo.create(
        DeliveryCursor.queued(
            track_id="track-proof",
            consumer_id="local-playback",
            unit_id="speech-proof",
            generation=3,
            total_source_frames=100,
        )
    )
    stopped = await repo.advance(
        "track-proof",
        "local-playback",
        expected_cursor_revision=current.cursor_revision,
        generation=3,
        unit_id="speech-proof",
        source_offset_frames=100,
        total_source_frames=100,
        evidence=DeliveryEvidence.RENDERED_ESTIMATE,
        stop_reason=DeliveryStopReason.COMPLETED,
    )
    proven = await repo.advance(
        "track-proof",
        "local-playback",
        expected_cursor_revision=stopped.cursor_revision,
        generation=3,
        unit_id="speech-proof",
        source_offset_frames=100,
        total_source_frames=100,
        evidence=DeliveryEvidence.MEASURED_LOOPBACK,
    )
    assert proven.fully_output
    assert proven.stop_reason is DeliveryStopReason.COMPLETED

    with pytest.raises(DeliveryCursorConflict, match="reason cannot change"):
        await repo.advance(
            "track-proof",
            "local-playback",
            expected_cursor_revision=proven.cursor_revision,
            generation=3,
            unit_id="speech-proof",
            source_offset_frames=100,
            total_source_frames=100,
            evidence=DeliveryEvidence.MEASURED_LOOPBACK,
            stop_reason=DeliveryStopReason.USER_STOP,
        )
