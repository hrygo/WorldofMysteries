"""Every acceptance checkpoint must still be reachable in the shipping wiring.

The eight Engine termination points are the project's proof that a crash at any
durable boundary leaves recoverable facts. A checkpoint that no production path
announces is not a passing test — it is a boundary nobody is exercising, and it
fails silently: the acceptance suite keeps its name while proving nothing.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3 as stdlib_sqlite3

import pytest

from application.story_session_open import OpenStorySessionCommand, StorySessionOpenService
from application.story_turn_commit import StoryTurnCommitService
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.sqlite_runtime import sqlite3 as runtime_sqlite3
from infrastructure.story_session_open_repository import SQLiteStorySessionOpenPort
from infrastructure.story_session_repository import SQLiteStorySessionCommitPort

from test_golden_turn1_durable import (
    _initial_session,
    _turn1_delta,
    _validated_turn,
)


async def _open_recording_database(tmp_path: Path, seen: list[str]) -> DatabaseManager:
    paths = DatabasePaths.for_world(tmp_path / "app-support", "world_001")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute(
            "CREATE TABLE canon_fixture(id TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT"
        )
        canon.execute("INSERT INTO canon_fixture VALUES ('canon','immutable')")
    return await DatabaseManager.open(
        paths,
        expected_sqlite_version=runtime_sqlite3.sqlite_version,
        fault_hook=seen.append,
    )


async def _open_session(database: DatabaseManager, request: str):
    return await StorySessionOpenService(
        SQLiteStorySessionOpenPort(database)
    ).open(
        OpenStorySessionCommand(
            initial_session=_initial_session(),
            open_request_id=f"open.g001.{request}",
            store_expected_revision=0,
            request_id=f"request.g001.{request}.open",
            trace_id=f"trace.g001.{request}.open",
        )
    )


@pytest.mark.asyncio
async def test_the_commit_port_announces_the_immediately_after_commit_boundary(tmp_path):
    """CP4 belongs to the commit itself, not to the optional settling decorator.

    Durable post-COMMIT work commits through the bare
    ``SQLiteStorySessionCommitPort``: the ``SettlingCommitPort`` decorator is
    only wired for the synchronous story methods. A checkpoint announced from
    the decorator therefore disappears from the shipping path, and "crash
    immediately after COMMIT" stops being a boundary the suite can reach.
    """
    seen: list[str] = []
    database = await _open_recording_database(tmp_path, seen)
    try:
        opened = await _open_session(database, "cp4")
        delta = _turn1_delta()
        result = await StoryTurnCommitService(
            SQLiteStorySessionCommitPort(database)
        ).commit_validated(
            opened.snapshot.session,
            delta,
            _validated_turn(delta),
            store_expected_revision=opened.opened_store_revision,
            request_id="request.g001.cp4",
            trace_id="trace.g001.cp4",
        )
    finally:
        await database.close()

    assert not result.replayed
    assert seen.count("after_turn_commit") == 1


@pytest.mark.asyncio
async def test_the_boundary_is_announced_once_per_committed_turn(tmp_path):
    """A replayed commit must not announce a fresh post-COMMIT boundary."""
    seen: list[str] = []
    database = await _open_recording_database(tmp_path, seen)
    try:
        opened = await _open_session(database, "cp4.replay")
        delta = _turn1_delta()
        turn = _validated_turn(delta)
        port = SQLiteStorySessionCommitPort(database)
        await StoryTurnCommitService(port).commit_validated(
            opened.snapshot.session,
            delta,
            turn,
            store_expected_revision=opened.opened_store_revision,
            request_id="request.g001.cp4.replay",
            trace_id="trace.g001.cp4.replay",
        )
        after_first = seen.count("after_turn_commit")
        replay = await StoryTurnCommitService(port).commit_validated(
            opened.snapshot.session,
            delta,
            turn,
            store_expected_revision=opened.opened_store_revision,
            request_id="request.g001.cp4.replay.retry",
            trace_id="trace.g001.cp4.replay.retry",
        )
    finally:
        await database.close()

    assert replay.replayed
    assert after_first == 1
    assert seen.count("after_turn_commit") == 1
