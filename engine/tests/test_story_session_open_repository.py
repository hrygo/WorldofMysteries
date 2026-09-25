"""SQLite persistence tests for durable Story Session Open."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from dataclasses import replace
from pathlib import Path

import pytest
import pytest_asyncio
from engine.infrastructure.database_manager import (
    CommitRequest,
    DatabaseManager,
    DatabasePaths,
    StoredEvent,
)
from engine.infrastructure.story_session_open_repository import (
    SQLiteStorySessionOpenPort,
)

from application.story_session_open import (
    OpenStorySessionCommand,
    StorySessionOpenError,
)
from contracts import StorySession, StoryState


def session(
    *,
    session_id: str = "session-1",
    worldline_id: str = "line-1",
    story_revision: int = 0,
    turn: int = 0,
    world_time: str = "1349-06-12T21:45:00",
    secret_state: str = "hidden",
) -> StorySession:
    state = StoryState.model_validate(
        {
            "schema_version": "1.0",
            "story_session_id": session_id,
            "revision": story_revision,
            "turn": turn,
            "phase": "opening",
            "scene": {
                "id": "scene-1",
                "location_id": "room-1",
                "active_character_ids": ["player-1"],
            },
            "world_time": world_time,
            "protagonist_goal": "investigate",
            "active_conflicts": [],
            "discovered_clue_ids": [],
            "secret_states": {"secret-1": secret_state},
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


def command(
    initial: StorySession | None = None,
    *,
    expected_revision: int = 0,
    open_request_id: str = "open-1",
    request_id: str = "request-1",
    trace_id: str = "trace-1",
) -> OpenStorySessionCommand:
    return OpenStorySessionCommand(
        initial_session=initial or session(),
        open_request_id=open_request_id,
        store_expected_revision=expected_revision,
        request_id=request_id,
        trace_id=trace_id,
    )


@pytest.fixture
def paths(tmp_path: Path) -> DatabasePaths:
    layout = DatabasePaths.for_world(tmp_path / "worlds", "test-world")
    layout.canon.parent.mkdir(parents=True)
    with sqlite3.connect(layout.canon) as connection:
        connection.execute(
            "CREATE TABLE canon_fixture(id TEXT PRIMARY KEY, value TEXT) STRICT"
        )
        connection.execute(
            "INSERT INTO canon_fixture VALUES ('canon-1', 'immutable')"
        )
    return layout


async def open_database(paths: DatabasePaths) -> DatabaseManager:
    return await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )


@pytest_asyncio.fixture
async def database(paths: DatabasePaths):
    opened = await open_database(paths)
    try:
        yield opened
    finally:
        await opened.close()


async def row_count(database: DatabaseManager, table: str) -> int:
    rows = await database.read_world(f"SELECT count(*) AS count FROM {table}")
    return rows[0]["count"]


async def counts(database: DatabaseManager) -> tuple[int, int, int, int, int]:
    return (
        await row_count(database, "story_sessions"),
        await row_count(database, "turn_transactions"),
        await row_count(database, "story_state_deltas"),
        await row_count(database, "domain_events"),
        await row_count(database, "projection_outbox"),
    )


async def commit_status(
    database: DatabaseManager,
    *,
    session_id: str,
    worldline_id: str,
    world_time: str,
    expected_revision: int,
    status: str,
) -> int:
    request = CommitRequest(
        worldline_id=worldline_id,
        world_time=world_time,
        expected_revision=expected_revision,
        idempotency_key=f"status:{session_id}:{status}",
        request_id=f"status-request:{status}",
        trace_id=f"status-trace:{status}",
        operation={"kind": "test.story.session.status", "session_id": session_id},
        events=(
            StoredEvent(
                event_id=f"status-event:{session_id}:{status}",
                aggregate_id=session_id,
                event_type="story.session.status_changed",
                payload={"status": status},
            ),
        ),
    )

    def apply(tx):
        tx.execute(
            "UPDATE story_sessions "
            "SET status=?,committed_world_revision=? WHERE id=?",
            (status, tx.revision, session_id),
        )
        return {"session_id": session_id, "status": status}

    result = await database.commit_resolved(request, apply)
    return result.revision


@pytest.mark.asyncio
async def test_database_open_persists_initial_session_with_atomic_journal_and_outbox(
    database: DatabaseManager, paths: DatabasePaths
):
    initial = session()
    before_canon = paths.canon.read_bytes()
    result = await SQLiteStorySessionOpenPort(database).open_session(command(initial))

    assert result.opened_store_revision == 1
    assert result.snapshot.observed_store_revision == 1
    assert result.replayed is False
    assert result.snapshot.session == initial
    assert result.snapshot.session.story_state.revision == 0
    assert result.snapshot.session.story_state.turn == 0
    assert result.snapshot.session.base_revisions.world == 103
    assert result.snapshot.session.base_revisions.character == 27
    assert result.snapshot.session.story_state.world_time == "1349-06-12T21:45:00"
    assert await counts(database) == (1, 0, 0, 1, 1)

    rows = await database.read_world("SELECT * FROM story_sessions WHERE id=?", ("session-1",))
    assert len(rows) == 1
    assert rows[0]["base_world_revision"] == 103
    assert rows[0]["base_character_revision"] == 27
    assert rows[0]["base_story_revision"] == 0
    assert rows[0]["story_revision"] == 0
    assert rows[0]["status"] == "active"
    assert rows[0]["committed_world_revision"] == 1
    assert json.loads(rows[0]["story_state_json"]) == initial.story_state.model_dump(
        mode="json", exclude_none=True
    )

    journal = await database.read_world(
        "SELECT revision,operation_json FROM domain_commits"
    )
    event = (await database.read_world("SELECT * FROM domain_events"))[0]
    assert journal[0]["revision"] == 1
    assert json.loads(journal[0]["operation_json"])["initial_session"] == (
        initial.model_dump(mode="json", exclude_none=True)
    )
    assert event["event_type"] == "story.session.opened"
    assert json.loads(event["payload_json"]) == {
        "session_id": "session-1",
        "story_revision": 0,
    }
    assert "secret-1" not in event["payload_json"]
    assert "hidden" not in event["payload_json"]
    assert paths.canon.read_bytes() == before_canon
    with sqlite3.connect(paths.world) as connection:
        assert list(connection.execute("PRAGMA foreign_key_check")) == []
        assert connection.execute(
            "SELECT revision FROM world_meta WHERE singleton=1"
        ).fetchone()[0] == 1


@pytest.mark.asyncio
async def test_database_open_replay_keeps_original_revision_and_reads_current_authority(
    database: DatabaseManager,
):
    port = SQLiteStorySessionOpenPort(database)
    original_command = command()
    first = await port.open_session(original_command)
    current_session = session(story_revision=1, turn=1)
    operation = CommitRequest(
        worldline_id="line-1",
        world_time="1349-06-12T21:45:00",
        expected_revision=1,
        idempotency_key="test-first-turn",
        request_id="turn-request",
        trace_id="turn-trace",
        operation={"kind": "test.story.turn"},
        events=(StoredEvent("test-first-turn-event", "session-1", "story.turn.committed", {}),),
    )

    def commit_turn_one(tx):
        state_json = json.dumps(
            current_session.story_state.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        tx.execute(
            "UPDATE story_sessions SET story_revision=1,story_state_json=?,"
            "committed_world_revision=? WHERE id=?",
            (state_json, tx.revision, "session-1"),
        )
        return {"session_id": "session-1"}

    await database.commit_resolved(operation, commit_turn_one)

    replay = await port.open_session(
        replace(original_command, request_id="retry-request", trace_id="retry-trace")
    )

    assert replay.replayed is True
    assert replay.opened_store_revision == first.opened_store_revision == 1
    assert replay.snapshot.observed_store_revision == 2
    assert replay.snapshot.session.story_state.revision == 1
    assert replay.snapshot.session.story_state.turn == 1
    assert await row_count(database, "domain_events") == 2
    assert await row_count(database, "projection_outbox") == 2


@pytest.mark.parametrize("change", ["seed", "secret", "base", "world_time", "expected"])
@pytest.mark.asyncio
async def test_database_open_same_key_with_different_initial_semantics_conflicts(
    database: DatabaseManager, change: str
):
    port = SQLiteStorySessionOpenPort(database)
    original = command()
    await port.open_session(original)

    altered_session = original.initial_session
    altered_command = original
    if change == "seed":
        altered_session = altered_session.model_copy(update={"story_seed_id": "seed-2"})
    elif change == "secret":
        changed_state = altered_session.story_state.model_dump(
            mode="json", exclude_none=True
        )
        changed_state["secret_states"]["secret-1"] = "revealed"
        altered_state = StoryState.model_validate(changed_state)
        altered_session = altered_session.model_copy(update={"story_state": altered_state})
    elif change == "base":
        altered_base = altered_session.base_revisions.model_copy(update={"world": 104})
        altered_session = altered_session.model_copy(update={"base_revisions": altered_base})
    elif change == "world_time":
        altered_state = altered_session.story_state.model_copy(
            update={"world_time": "1349-06-13T21:45:00"}
        )
        altered_session = altered_session.model_copy(update={"story_state": altered_state})
    if change != "expected":
        altered_command = replace(original, initial_session=altered_session)
    else:
        altered_command = replace(original, store_expected_revision=1)

    with pytest.raises(StorySessionOpenError) as raised:
        await port.open_session(altered_command)

    assert raised.value.code == "session_open_identity_conflict"
    assert await counts(database) == (1, 0, 0, 1, 1)


@pytest.mark.asyncio
async def test_database_open_does_not_overwrite_a_terminal_session_id(
    database: DatabaseManager,
):
    port = SQLiteStorySessionOpenPort(database)
    first = await port.open_session(command())
    await commit_status(
        database,
        session_id="session-1",
        worldline_id="line-1",
        world_time="1349-06-12T21:45:00",
        expected_revision=first.opened_store_revision,
        status="finalized",
    )

    with pytest.raises(StorySessionOpenError) as raised:
        await port.open_session(
            command(expected_revision=2, open_request_id="new-open")
        )

    assert raised.value.code == "story_session_exists"
    rows = await database.read_world("SELECT id,status FROM story_sessions")
    assert rows == [{"id": "session-1", "status": "finalized"}]


@pytest.mark.parametrize(
    "status",
    ["active", "suspended", "closing", "recovery_required"],
)
@pytest.mark.asyncio
async def test_database_open_rejects_second_session_on_worldline_with_live_session(
    database: DatabaseManager, status: str
):
    port = SQLiteStorySessionOpenPort(database)
    first = await port.open_session(command())
    expected_revision = first.opened_store_revision
    if status != "active":
        expected_revision = await commit_status(
            database,
            session_id="session-1",
            worldline_id="line-1",
            world_time="1349-06-12T21:45:00",
            expected_revision=expected_revision,
            status=status,
        )

    with pytest.raises(StorySessionOpenError) as raised:
        await port.open_session(
            command(
                session(session_id="session-2"),
                expected_revision=expected_revision,
                open_request_id="open-2",
            )
        )

    assert raised.value.code == "worldline_has_open_session"
    assert await row_count(database, "story_sessions") == 1


@pytest.mark.parametrize("status", ["finalized", "cancelled"])
@pytest.mark.asyncio
async def test_database_open_allows_new_session_after_terminal_status(
    database: DatabaseManager, status: str
):
    port = SQLiteStorySessionOpenPort(database)
    first = await port.open_session(command())
    expected_revision = await commit_status(
        database,
        session_id="session-1",
        worldline_id="line-1",
        world_time="1349-06-12T21:45:00",
        expected_revision=first.opened_store_revision,
        status=status,
    )

    second = await port.open_session(
        command(
            session(session_id="session-2"),
            expected_revision=expected_revision,
            open_request_id="open-2",
        )
    )

    assert second.snapshot.session.id == "session-2"
    assert second.opened_store_revision == expected_revision + 1
    assert await row_count(database, "story_sessions") == 2


@pytest.mark.asyncio
async def test_database_open_maps_stale_expected_revision_to_stable_error(
    database: DatabaseManager,
):
    request = CommitRequest(
        worldline_id="line-1",
        world_time="1349-06-12T21:45:00",
        expected_revision=0,
        idempotency_key="prior-commit",
        request_id="prior-request",
        trace_id="prior-trace",
        operation={"kind": "test.prior"},
        events=(StoredEvent("prior-event", "world-1", "test.prior", {}),),
    )
    await database.commit_resolved(request)

    with pytest.raises(StorySessionOpenError) as raised:
        await SQLiteStorySessionOpenPort(database).open_session(
            command(expected_revision=0)
        )

    assert raised.value.code == "revision_conflict"
    assert await counts(database) == (0, 0, 0, 1, 1)


@pytest.mark.parametrize(
    "stage", ["before_apply", "after_apply", "after_events", "before_commit"]
)
@pytest.mark.asyncio
async def test_database_open_fault_before_commit_rolls_back_all_rows(
    database: DatabaseManager, stage: str
):
    def fail_at(point: str) -> None:
        if point == stage:
            raise RuntimeError("injected failure")

    database._fault_hook = fail_at
    with pytest.raises(RuntimeError, match="injected failure"):
        await SQLiteStorySessionOpenPort(database).open_session(command())

    assert await counts(database) == (0, 0, 0, 0, 0)


@pytest.mark.asyncio
async def test_database_open_after_commit_lost_ack_retries_without_duplicate_effects(
    database: DatabaseManager,
):
    port = SQLiteStorySessionOpenPort(database)

    def lose_ack(stage: str) -> None:
        if stage == "after_commit":
            raise RuntimeError("lost acknowledgement")

    database._fault_hook = lose_ack
    with pytest.raises(RuntimeError, match="lost acknowledgement"):
        await port.open_session(command())
    assert await counts(database) == (1, 0, 0, 1, 1)

    database._fault_hook = None
    replay = await port.open_session(command())

    assert replay.replayed is True
    assert replay.opened_store_revision == 1
    assert replay.snapshot.observed_store_revision == 1
    assert await counts(database) == (1, 0, 0, 1, 1)


@pytest.mark.asyncio
async def test_database_open_freezes_nested_initial_state_before_waiting_in_writer_queue(
    database: DatabaseManager,
):
    entered, release = threading.Event(), threading.Event()

    def block_writer() -> None:
        entered.set()
        assert release.wait(5)

    blocker = asyncio.create_task(database._submit(block_writer))
    try:
        async with asyncio.timeout(5):
            while not entered.is_set():
                await asyncio.sleep(0.001)

        initial = session()
        pending = asyncio.create_task(
            SQLiteStorySessionOpenPort(database).open_session(command(initial))
        )
        await asyncio.sleep(0)
        initial.story_state.scene.id = "mutated-after-admission"
        initial.story_state.secret_states["secret-1"] = "revealed"
    finally:
        release.set()

    await blocker
    await pending
    persisted = (
        await database.read_world(
            "SELECT story_state_json FROM story_sessions WHERE id=?",
            ("session-1",),
        )
    )[0]
    state = json.loads(persisted["story_state_json"])
    assert state["scene"]["id"] == "scene-1"
    assert state["secret_states"]["secret-1"] == "hidden"


@pytest.mark.asyncio
async def test_database_load_snapshot_uses_one_query_for_session_and_current_revision(
    database: DatabaseManager, monkeypatch
):
    port = SQLiteStorySessionOpenPort(database)
    await port.open_session(command())
    original_read_world = database.read_world
    queries: list[str] = []

    async def track_read_world(sql: str, parameters: tuple = ()):
        queries.append(sql)
        return await original_read_world(sql, parameters)

    monkeypatch.setattr(database, "read_world", track_read_world)
    snapshot = await port.load_snapshot("session-1")

    assert snapshot.session.id == "session-1"
    assert snapshot.observed_store_revision == 1
    assert len(queries) == 1
    assert "CROSS JOIN world_meta" in queries[0]
    assert "observed_store_revision" in queries[0]


@pytest.mark.asyncio
async def test_database_load_snapshot_maps_missing_and_corrupt_sessions(
    database: DatabaseManager,
):
    port = SQLiteStorySessionOpenPort(database)
    with pytest.raises(StorySessionOpenError) as missing:
        await port.load_snapshot("unknown-session")
    assert missing.value.code == "story_session_not_found"

    await port.open_session(command())
    with sqlite3.connect(database.paths.world) as connection:
        connection.execute(
            "UPDATE story_sessions SET story_state_json='{}' WHERE id='session-1'"
        )

    with pytest.raises(StorySessionOpenError) as corrupt:
        await port.load_snapshot("session-1")
    assert corrupt.value.code == "story_session_corrupt"


@pytest.mark.asyncio
async def test_database_load_snapshot_recovers_after_database_reopen(
    paths: DatabasePaths,
):
    database = await open_database(paths)
    await SQLiteStorySessionOpenPort(database).open_session(command())
    await database.close()

    reopened = await open_database(paths)
    try:
        snapshot = await SQLiteStorySessionOpenPort(reopened).load_snapshot("session-1")
        assert snapshot.session.story_state.turn == 0
        assert snapshot.session.status.value == "active"
        assert snapshot.observed_store_revision == 1
    finally:
        await reopened.close()
