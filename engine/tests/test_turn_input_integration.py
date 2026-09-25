"""Real world.db integration for W-V09 StoryTurnInputService."""
from __future__ import annotations

from pathlib import Path
import sqlite3 as stdlib_sqlite3

from application.turn_input import (
    FinalizedStoryInput,
    StoryTurnInputService,
    TurnInputStatus,
)
from contracts import InputMode
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.sqlite_runtime import sqlite3
from infrastructure.turn_intake_repository import SQLiteTurnInputCommandPort

from test_turn_input import SessionPort, session


async def open_database(tmp_path: Path):
    paths = DatabasePaths.for_world(tmp_path / "app-support", "world-input-service")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    database = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    return database, paths


def finalized(text: str = "调查那扇门。") -> FinalizedStoryInput:
    return FinalizedStoryInput(
        input_turn_id="input-turn-real-1",
        session_id="session-1",
        input_mode=InputMode.VOICE,
        raw_input=text,
    )


async def test_real_sqlite_intake_recovers_before_newer_story_session_lookup(tmp_path):
    database, paths = await open_database(tmp_path)
    sessions = SessionPort()
    service = StoryTurnInputService(
        sessions=sessions,
        intake=SQLiteTurnInputCommandPort(database),
    )
    try:
        first = await service.receive(finalized())
        assert first.status is TurnInputStatus.RECEIVED
        assert first.base_revisions.story == 3
        assert sessions.loads == 1
    finally:
        await database.close()

    reopened = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    try:
        sessions.current = session(story_revision=12)
        recovered = await StoryTurnInputService(
            sessions=sessions,
            intake=SQLiteTurnInputCommandPort(reopened),
        ).receive(finalized())

        assert recovered.replayed
        assert recovered.turn_id == first.turn_id
        assert recovered.idempotency_key == first.idempotency_key
        assert recovered.base_revisions.story == 3
        assert sessions.loads == 1
    finally:
        await reopened.close()


async def test_real_sqlite_cancel_is_visible_to_application_recovery(tmp_path):
    database, _ = await open_database(tmp_path)
    sessions = SessionPort()
    service = StoryTurnInputService(
        sessions=sessions,
        intake=SQLiteTurnInputCommandPort(database),
    )
    try:
        first = await service.receive(finalized())
        cancelled = await service.cancel(first.input_turn_id)
        assert cancelled.status is TurnInputStatus.CANCELLED

        recovered = await service.recover(first.input_turn_id)
        assert recovered.status is TurnInputStatus.CANCELLED
        assert recovered.turn_id == first.turn_id
    finally:
        await database.close()
