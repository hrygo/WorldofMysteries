"""Idempotency must bind durable story commits to StateDelta semantics."""
from __future__ import annotations

import sqlite3 as stdlib_sqlite3
from pathlib import Path

import pytest

from application.story_turn_commit import StoryTurnCommitService
from contracts import StateDelta, StorySession, TurnTransaction
from infrastructure.database_manager import (
    DatabaseManager,
    DatabasePaths,
    IdempotencyConflict,
)
from infrastructure.sqlite_runtime import sqlite3
from infrastructure.story_session_repository import SQLiteStorySessionCommitPort


def _session() -> StorySession:
    return StorySession.model_validate(
        {
            "schema_version": "1.0",
            "id": "session-idem-content",
            "world_id": "world-idem-content",
            "worldline_id": "worldline-idem-content",
            "protagonist_id": "protagonist-idem-content",
            "story_seed_id": "seed-idem-content",
            "base_revisions": {"world": 10, "character": 4, "story": 0},
            "story_state": {
                "schema_version": "1.0",
                "story_session_id": "session-idem-content",
                "revision": 0,
                "turn": 0,
                "phase": "opening",
                "scene": {"id": "scene-before"},
                "world_time": "1349-01-01T00:00:00Z",
                "secret_states": {},
                "commitments": {"hard_ids": [], "soft_ids": []},
                "pressure": {},
            },
            "status": "active",
        }
    )


def _delta(scene_id: str) -> StateDelta:
    return StateDelta.model_validate(
        {
            "schema_version": "1.0",
            "id": "delta-idem-content",
            "turn_id": "turn-idem-content",
            "outcome": "clean_success",
            "story_delta": {"scene_id": scene_id},
            "character_deltas": [],
            "world_event_candidates": [],
            "evidence_ids": ["evidence-original"],
        }
    )


def _turn() -> TurnTransaction:
    return TurnTransaction.model_validate(
        {
            "schema_version": "1.0",
            "id": "turn-idem-content",
            "session_id": "session-idem-content",
            "idempotency_key": "idempotency-story-turn-content",
            "status": "validated",
            "base_revisions": {"world": 10, "character": 4, "story": 0},
            "state_delta_id": "delta-idem-content",
        }
    )


async def _database(tmp_path: Path) -> DatabaseManager:
    paths = DatabasePaths.for_world(tmp_path / "app-support", "world-idem-content")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    return await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )


@pytest.mark.asyncio
async def test_same_idempotency_key_rejects_changed_state_delta_semantics(tmp_path):
    database = await _database(tmp_path)
    service = StoryTurnCommitService(SQLiteStorySessionCommitPort(database))
    session = _session()
    turn = _turn()
    original_delta = _delta("scene-committed")
    changed_delta = _delta("scene-alternate")

    try:
        await service.commit_validated(
            session,
            original_delta,
            turn,
            store_expected_revision=0,
            request_id="request-original",
            trace_id="trace-original",
        )

        assert changed_delta.id == original_delta.id
        assert changed_delta.turn_id == original_delta.turn_id
        assert changed_delta.story_delta.scene_id != original_delta.story_delta.scene_id
        assert turn.idempotency_key == "idempotency-story-turn-content"

        with pytest.raises(IdempotencyConflict, match="already bound"):
            await service.commit_validated(
                session,
                changed_delta,
                turn,
                store_expected_revision=0,
                request_id="request-retry",
                trace_id="trace-retry",
            )
    finally:
        await database.close()
