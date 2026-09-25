"""Concurrent and restart durability checks for explicit Story Session Open."""
from __future__ import annotations

import asyncio
import sqlite3 as stdlib_sqlite3
from pathlib import Path

import pytest

from application.story_session_open import (
    OpenStorySessionCommand,
    StorySessionOpenError,
    StorySessionOpenService,
)
from contracts import StorySession, StorySessionStatus, StoryState
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.sqlite_runtime import sqlite3
from infrastructure.story_session_open_repository import SQLiteStorySessionOpenPort


def _session(
    *,
    session_id: str = "session-1",
    worldline_id: str = "line-1",
) -> StorySession:
    state = StoryState.model_validate(
        {
            "schema_version": "1.0",
            "story_session_id": session_id,
            "revision": 0,
            "turn": 0,
            "phase": "opening",
            "scene": {
                "id": "scene-1",
                "location_id": "room-1",
                "active_character_ids": ["player-1"],
            },
            "world_time": "1349-06-12T21:45:00",
            "protagonist_goal": "investigate",
            "active_conflicts": [],
            "discovered_clue_ids": [],
            "secret_states": {"secret-1": "hidden"},
            "commitments": {"hard_ids": [], "soft_ids": []},
            "local_state": {},
            "pressure": {},
            "last_state_delta_id": None,
        }
    )
    return StorySession.model_validate(
        {
            "schema_version": "1.0",
            "id": session_id,
            "world_id": "world-1",
            "worldline_id": worldline_id,
            "protagonist_id": "player-1",
            "story_seed_id": "seed-1",
            "base_revisions": {"world": 103, "character": 27, "story": 0},
            "story_state": state.model_dump(mode="json", exclude_none=True),
            "status": "active",
        }
    )


def _command(
    initial: StorySession,
    *,
    expected_revision: int = 0,
    open_request_id: str = "open-1",
    request_id: str = "request-1",
    trace_id: str = "trace-1",
) -> OpenStorySessionCommand:
    return OpenStorySessionCommand(
        initial_session=initial,
        open_request_id=open_request_id,
        store_expected_revision=expected_revision,
        request_id=request_id,
        trace_id=trace_id,
    )


async def _open_database(tmp_path: Path) -> tuple[DatabaseManager, DatabasePaths]:
    paths = DatabasePaths.for_world(tmp_path / "app-support", "world-open-durable")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    database = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    return database, paths


async def _rows(database: DatabaseManager, table: str) -> list[dict]:
    return await database.read_world(f"SELECT * FROM {table}")


@pytest.mark.asyncio
async def test_same_key_concurrent_open_creates_one_commit_event_and_outbox(tmp_path):
    database, _ = await _open_database(tmp_path)
    try:
        command = _command(_session())
        service = StorySessionOpenService(SQLiteStorySessionOpenPort(database))

        results = await asyncio.gather(
            service.open(command),
            service.open(command),
        )

        assert sorted(result.replayed for result in results) == [False, True]
        assert {result.opened_store_revision for result in results} == {1}
        assert {result.snapshot.observed_store_revision for result in results} == {1}
        assert (await _rows(database, "story_sessions"))[0]["id"] == "session-1"
        assert len(await _rows(database, "domain_commits")) == 1
        events = await _rows(database, "domain_events")
        assert len(events) == 1
        assert events[0]["event_type"] == "story.session.opened"
        outbox = await _rows(database, "projection_outbox")
        assert len(outbox) == 1
        assert outbox[0]["revision"] == 1
        assert await database.read_world(
            "SELECT revision FROM world_meta WHERE singleton=1"
        ) == [{"revision": 1}]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_different_concurrent_opens_on_one_worldline_allow_only_one_success(
    tmp_path,
):
    database, _ = await _open_database(tmp_path)
    try:
        service = StorySessionOpenService(SQLiteStorySessionOpenPort(database))
        commands = (
            _command(
                _session(session_id="session-a"),
                open_request_id="open-a",
                request_id="request-a",
                trace_id="trace-a",
            ),
            _command(
                _session(session_id="session-b"),
                open_request_id="open-b",
                request_id="request-b",
                trace_id="trace-b",
            ),
        )

        outcomes = await asyncio.gather(
            *(service.open(value) for value in commands),
            return_exceptions=True,
        )

        successes = [value for value in outcomes if not isinstance(value, BaseException)]
        conflicts = [value for value in outcomes if isinstance(value, BaseException)]
        assert len(successes) == 1
        assert len(conflicts) == 1
        assert isinstance(conflicts[0], StorySessionOpenError)
        assert conflicts[0].code in {
            "revision_conflict",
            "worldline_has_open_session",
        }
        assert successes[0].opened_store_revision == 1
        sessions = await _rows(database, "story_sessions")
        assert len(sessions) == 1
        assert sessions[0]["worldline_id"] == "line-1"
        assert len(await _rows(database, "domain_commits")) == 1
        assert len(await _rows(database, "domain_events")) == 1
        assert len(await _rows(database, "projection_outbox")) == 1
        assert await database.read_world(
            "SELECT revision FROM world_meta WHERE singleton=1"
        ) == [{"revision": 1}]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_open_only_session_recovers_active_at_story_turn_zero_after_restart(
    tmp_path,
):
    database, paths = await _open_database(tmp_path)
    initial = _session()
    try:
        opened = await StorySessionOpenService(
            SQLiteStorySessionOpenPort(database)
        ).open(_command(initial))

        assert opened.opened_store_revision == 1
        assert opened.snapshot.session.status is StorySessionStatus.ACTIVE
        assert opened.snapshot.session.story_state.revision == 0
        assert opened.snapshot.session.story_state.turn == 0
        assert opened.snapshot.session.base_revisions == initial.base_revisions
        assert (
            opened.snapshot.session.story_state.world_time
            == initial.story_state.world_time
        )
    finally:
        await database.close()

    reopened, _ = await _open_database_from_paths(paths)
    try:
        recovered = await StorySessionOpenService(
            SQLiteStorySessionOpenPort(reopened)
        ).recover(initial.id)

        assert recovered.observed_store_revision == 1
        assert recovered.session.status is StorySessionStatus.ACTIVE
        assert recovered.session.story_state.revision == 0
        assert recovered.session.story_state.turn == 0
        assert recovered.session.base_revisions == initial.base_revisions
        assert recovered.session.story_state.world_time == initial.story_state.world_time
        assert len(await _rows(reopened, "domain_commits")) == 1
        assert len(await _rows(reopened, "domain_events")) == 1
        assert len(await _rows(reopened, "projection_outbox")) == 1
    finally:
        await reopened.close()


async def _open_database_from_paths(paths: DatabasePaths) -> tuple[DatabaseManager, DatabasePaths]:
    database = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    return database, paths
