"""Post-COMMIT job schema and scoped writer boundary tests."""
from __future__ import annotations

import sqlite3 as stdlib_sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from engine.contracts import StateDelta, StorySession, StoryState, TurnTransaction
from engine.infrastructure import (
    database_manager,
    database_schema,
)
from engine.infrastructure.database_manager import DatabaseManager, DatabasePaths
from engine.infrastructure.database_schema import (
    APPLICATION_IDS,
    StorageError,
    connect,
    initialize,
    integrity,
    statements,
)
from engine.infrastructure.post_commit_job_repository import (
    PostCommitJobConflict,
    PostCommitJobRegistration,
    PostCommitJobSpec,
    PostCommitLeaseConflict,
    SQLitePostCommitJobRepository,
)
from engine.infrastructure.sqlite_runtime import sqlite3
from engine.infrastructure.story_session_repository import (
    PlannedPostCommitJob,
    SQLiteStorySessionCommitPort,
)

from application.post_commit_work import PostCommitJobState, PostCommitKind

_JOB_COLUMNS = (
    "job_id",
    "turn_id",
    "session_id",
    "kind",
    "recipe_revision",
    "source_story_revision",
    "source_world_revision",
    "input_digest",
    "state",
    "attempt",
    "lease_owner",
    "lease_generation",
    "next_attempt_at",
    "last_error_code",
    "result_ref",
)
_IMMUTABLE_JOB_COLUMNS = {
    "job_id": "job-changed",
    "turn_id": "turn-changed",
    "session_id": "session-changed",
    "kind": "audio_prepare",
    "recipe_revision": "recipe-changed",
    "source_story_revision": 2,
    "source_world_revision": 2,
    "input_digest": "sha256:changed",
}
_SCHEDULING_COLUMNS = {
    "state": "running",
    "attempt": 1,
    "lease_owner": "worker-test",
    "lease_generation": 1,
    "next_attempt_at": "2026-09-28T12:00:00Z",
    "last_error_code": "temporary_failure",
    "result_ref": "result-test",
}


def _job_values(
    *,
    job_id: str = "job-1",
    turn_id: str = "turn-1",
    session_id: str = "session-1",
    kind: str = "narrative_publish",
    recipe_revision: str = "recipe-v1",
) -> tuple:
    return (
        job_id,
        turn_id,
        session_id,
        kind,
        recipe_revision,
        1,
        1,
        "sha256:" + "a" * 64,
        "pending",
        0,
        None,
        0,
        None,
        None,
        None,
    )


def _insert_job(tx, values: tuple) -> None:
    placeholders = ",".join("?" for _ in _JOB_COLUMNS)
    tx.execute(
        f"INSERT INTO post_commit_jobs({','.join(_JOB_COLUMNS)}) VALUES ({placeholders})",
        values,
    )


def _seed_committed_turn(connection, *, turn_id: str = "turn-1") -> None:
    """Create only the committed source rows needed by schema/writer tests."""
    connection.execute("BEGIN IMMEDIATE")
    if connection.execute(
        "SELECT 1 FROM domain_commits WHERE revision=1"
    ).fetchone() is None:
        connection.execute(
            "INSERT INTO domain_commits("
            "revision,worldline_id,idempotency_key,request_digest,request_id,trace_id,"
            "world_time,commit_time,operation_json,result_json"
            ") VALUES (1,?,?,?,?,?,?,?,?,?)",
            (
                "line-test",
                "idempotency-test",
                "digest-test",
                "request-test",
                "trace-test",
                "1349-01-01T00:00:00Z",
                "2026-09-28T00:00:00Z",
                "{}",
                "{}",
            ),
        )
        connection.execute(
            "INSERT INTO projection_outbox(revision,processed) VALUES (1,0)"
        )
        connection.execute("UPDATE world_meta SET revision=1 WHERE singleton=1")
        connection.execute(
            "INSERT INTO story_sessions("
            "id,world_id,worldline_id,protagonist_id,story_seed_id,"
            "base_world_revision,base_character_revision,base_story_revision,"
            "story_revision,status,story_state_json,committed_world_revision"
            ") VALUES ('session-1','world-test','line-test','player-test','seed-test',"
            "0,0,0,1,'active','{}',1)"
        )
    if connection.execute(
        "SELECT 1 FROM turn_transactions WHERE id=?", (turn_id,)
    ).fetchone() is None:
        connection.execute(
            "INSERT INTO turn_transactions("
            "id,session_id,idempotency_key,status,base_world_revision,"
            "base_character_revision,base_story_revision,transaction_json,"
            "committed_world_revision"
            ") VALUES (?, 'session-1', ?, 'committed', 0, 0, 0, '{}', 1)",
            (turn_id, f"idempotency-{turn_id}"),
        )
    connection.execute("COMMIT")


async def _open_database(tmp_path: Path) -> DatabaseManager:
    paths = DatabasePaths.for_world(tmp_path / "app-support", "post-commit-jobs")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    return await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )


async def _seed_job_rows(database: DatabaseManager) -> None:
    await database._submit(
        lambda: _seed_committed_turn(database._connection)
    )

    def insert_rows(tx):
        _insert_job(tx, _job_values())
        tx.execute(
            "INSERT INTO post_commit_retry_requests(request_id,job_id) VALUES (?,?)",
            ("retry-1", "job-1"),
        )
        tx.execute(
            "INSERT INTO post_commit_job_results("
            "job_id,format_version,payload_json,payload_digest"
            ") VALUES (?,?,?,?)",
            ("job-1", "1.0", "{}", "sha256:" + "b" * 64),
        )

    await database.post_commit_job_write(insert_rows)


def _build_v12_world(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        directory = Path(database_schema.__file__).with_name("migrations")
        for version in range(1, 13):
            script = next(directory.glob(f"{version:03}_world*.sql"))
            for statement in statements(script.read_text(encoding="utf-8")):
                connection.execute(statement)
        connection.execute(f"PRAGMA application_id={APPLICATION_IDS['world']}")
        connection.execute("PRAGMA user_version=12")
        connection.execute("INSERT INTO world_meta VALUES (1, 'store-v12', 0)")
        connection.execute("COMMIT")
        integrity(connection)


def _tables(path: Path) -> set[str]:
    with closing(connect(path, readonly=True)) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        }


def _columns(connection, table: str) -> list[tuple[str, str]]:
    return [
        (row["name"], row["type"])
        for row in connection.execute(f"PRAGMA table_info({table})")
    ]


def test_v12_upgrade_creates_empty_post_commit_tables_with_constraints_and_backup(
    tmp_path,
):
    path = tmp_path / "Worlds" / "v12" / "world.db"
    _build_v12_world(path)

    with closing(connect(path)) as connection:
        initialize(connection, "world", path=path)

        assert connection.execute("PRAGMA user_version").fetchone()[0] == 14
        assert {
            "post_commit_jobs",
            "post_commit_retry_requests",
            "post_commit_job_results",
        } <= _tables(path)
        assert _columns(connection, "post_commit_jobs") == [
            ("job_id", "TEXT"),
            ("turn_id", "TEXT"),
            ("session_id", "TEXT"),
            ("kind", "TEXT"),
            ("recipe_revision", "TEXT"),
            ("source_story_revision", "INTEGER"),
            ("source_world_revision", "INTEGER"),
            ("input_digest", "TEXT"),
            ("state", "TEXT"),
            ("attempt", "INTEGER"),
            ("lease_owner", "TEXT"),
            ("lease_generation", "INTEGER"),
            ("next_attempt_at", "TEXT"),
            ("last_error_code", "TEXT"),
            ("result_ref", "TEXT"),
        ]
        assert _columns(connection, "post_commit_retry_requests") == [
            ("request_id", "TEXT"),
            ("job_id", "TEXT"),
        ]
        assert _columns(connection, "post_commit_job_results") == [
            ("job_id", "TEXT"),
            ("format_version", "TEXT"),
            ("payload_json", "TEXT"),
            ("payload_digest", "TEXT"),
        ]
        assert {
            (row["table"], row["from"], row["to"])
            for row in connection.execute("PRAGMA foreign_key_list(post_commit_jobs)")
        } >= {("turn_transactions", "turn_id", "id")}
        for table in (
            "post_commit_jobs",
            "post_commit_retry_requests",
            "post_commit_job_results",
        ):
            assert connection.execute(
                f"SELECT count(*) FROM {table}"
            ).fetchone()[0] == 0

        _seed_committed_turn(connection)
        _seed_committed_turn(connection, turn_id="turn-2")
        _insert_job(
            connection,
            _job_values(),
        )
        with pytest.raises(sqlite3.IntegrityError):
            _insert_job(connection, _job_values(job_id="job-duplicate"))

        with pytest.raises(sqlite3.IntegrityError):
            _insert_job(connection, _job_values(job_id="job-no-turn", turn_id="missing-turn"))

        _insert_job(
            connection,
            _job_values(
                job_id="job-2",
                turn_id="turn-2",
                kind="audio_prepare",
            ),
        )
        connection.execute(
            "INSERT INTO post_commit_retry_requests(request_id,job_id) VALUES ('retry-same','job-1')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO post_commit_retry_requests(request_id,job_id) "
                "VALUES ('retry-same','job-2')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO post_commit_retry_requests(request_id,job_id) "
                "VALUES ('retry-missing','missing-job')"
            )
        connection.execute(
            "INSERT INTO post_commit_job_results("
            "job_id,format_version,payload_json,payload_digest"
            ") VALUES ('job-1','1.0','{}','sha256:" + "c" * 64 + "')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO post_commit_job_results("
                "job_id,format_version,payload_json,payload_digest"
                ") VALUES ('job-1','1.0','{\"changed\":true}','sha256:"
                + "d" * 64
                + "')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO post_commit_job_results("
                "job_id,format_version,payload_json,payload_digest"
                ") VALUES ('missing-job','1.0','{}','sha256:" + "d" * 64 + "')"
            )
        integrity(connection)

    backup = path.with_name("world.db.pre-migration-v12-to-v14.bak")
    assert backup.is_file()
    with closing(connect(backup, readonly=True)) as snapshot:
        assert snapshot.execute("PRAGMA user_version").fetchone()[0] == 12
        assert snapshot.execute(
            "SELECT store_id FROM world_meta WHERE singleton=1"
        ).fetchone()[0] == "store-v12"
        assert not {
            "post_commit_jobs",
            "post_commit_retry_requests",
            "post_commit_job_results",
        } & _tables(backup)
        integrity(snapshot)


@pytest.mark.asyncio
async def test_post_commit_job_writer_allows_job_retry_and_result_inserts(tmp_path):
    database = await _open_database(tmp_path)
    try:
        await _seed_job_rows(database)

        assert await database.read_world("SELECT job_id FROM post_commit_jobs") == [
            {"job_id": "job-1"}
        ]
        assert await database.read_world(
            "SELECT request_id,job_id FROM post_commit_retry_requests"
        ) == [{"request_id": "retry-1", "job_id": "job-1"}]
        assert await database.read_world(
            "SELECT job_id,format_version FROM post_commit_job_results"
        ) == [{"job_id": "job-1", "format_version": "1.0"}]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_post_commit_job_writer_rejects_updates_to_immutable_source_columns(
    tmp_path,
):
    database = await _open_database(tmp_path)
    try:
        await _seed_job_rows(database)
        for column, value in _IMMUTABLE_JOB_COLUMNS.items():
            with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
                await database.post_commit_job_write(
                    lambda tx, column=column, value=value: tx.execute(
                        f"UPDATE post_commit_jobs SET {column}=? WHERE job_id=?",
                        (value, "job-1"),
                    )
                )

        job = (await database.read_world("SELECT * FROM post_commit_jobs"))[0]
        assert job["job_id"] == "job-1"
        assert job["turn_id"] == "turn-1"
        assert job["session_id"] == "session-1"
        assert job["kind"] == "narrative_publish"
        assert job["recipe_revision"] == "recipe-v1"
        assert job["source_story_revision"] == 1
        assert job["source_world_revision"] == 1
        assert job["input_digest"] == "sha256:" + "a" * 64
        await database.post_commit_job_write(
            lambda tx: tx.execute(
                "UPDATE post_commit_jobs SET state='running' WHERE job_id='job-1'"
            )
        )
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_post_commit_job_writer_allows_only_scheduling_column_updates(tmp_path):
    database = await _open_database(tmp_path)
    try:
        await _seed_job_rows(database)
        assignments = ",".join(f"{column}=?" for column in _SCHEDULING_COLUMNS)
        values = tuple(_SCHEDULING_COLUMNS.values()) + ("job-1",)
        await database.post_commit_job_write(
            lambda tx: tx.execute(
                f"UPDATE post_commit_jobs SET {assignments} WHERE job_id=?",
                values,
            )
        )

        job = (await database.read_world("SELECT * FROM post_commit_jobs"))[0]
        assert {key: job[key] for key in _SCHEDULING_COLUMNS} == _SCHEDULING_COLUMNS
    finally:
        await database.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO turn_transactions(id) VALUES ('unauthorized')",
        "UPDATE turn_transactions SET status=status",
        "INSERT INTO story_state_deltas(id) VALUES ('unauthorized')",
        "UPDATE story_state_deltas SET payload_json=payload_json",
        "INSERT INTO narrative_blocks(id) VALUES ('unauthorized')",
        "UPDATE narrative_blocks SET payload_json=payload_json",
        "INSERT INTO projection_outbox(revision) VALUES (99)",
        "UPDATE projection_outbox SET processed=1",
        "UPDATE post_commit_retry_requests SET job_id=job_id",
        "UPDATE post_commit_job_results SET payload_json=payload_json",
        "UPDATE world_meta SET revision=99",
    ],
)
async def test_post_commit_job_writer_rejects_world_and_projection_writes(
    tmp_path, sql
):
    database = await _open_database(tmp_path)
    try:
        with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
            await database.post_commit_job_write(lambda tx: tx.execute(sql))
    finally:
        await database.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "table",
    [
        "post_commit_jobs",
        "post_commit_retry_requests",
        "post_commit_job_results",
    ],
)
async def test_post_commit_job_writer_rejects_delete_from_all_job_tables(
    tmp_path, table
):
    database = await _open_database(tmp_path)
    try:
        await _seed_job_rows(database)
        with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
            await database.post_commit_job_write(
                lambda tx: tx.execute(f"DELETE FROM {table}")
            )
        assert (
            await database.read_world(f"SELECT count(*) AS count FROM {table}")
        )[0]["count"] == 1
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_job_result_conflict_cannot_update_the_immutable_result(tmp_path):
    database = await _open_database(tmp_path)
    try:
        await _seed_job_rows(database)
        with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
            await database.post_commit_job_write(
                lambda tx: tx.execute(
                    "INSERT INTO post_commit_job_results("
                    "job_id,format_version,payload_json,payload_digest"
                    ") VALUES ('job-1','1.0','{\"changed\":true}','sha256:"
                    + "c" * 64
                    + "') ON CONFLICT(job_id) DO UPDATE SET "
                    "payload_json=excluded.payload_json"
                )
            )

        result = (
            await database.read_world("SELECT * FROM post_commit_job_results")
        )[0]
        assert result["payload_json"] == "{}"
        assert result["payload_digest"] == "sha256:" + "b" * 64
    finally:
        await database.close()


def test_post_commit_job_authorizer_rejects_non_main_database():
    authorizer = getattr(database_manager, "_post_commit_job_authorizer")
    assert authorizer(
        sqlite3.SQLITE_INSERT,
        "post_commit_jobs",
        "job_id",
        "attached",
        None,
    ) == sqlite3.SQLITE_DENY


# Repository tests. These use the existing schema/authorizer fixture above and
# intentionally keep job registration in the caller's transaction callback.
def _repository_job(
    *,
    job_id: str = "repo-job-1",
    turn_id: str = "turn-1",
    session_id: str = "session-1",
    kind: str = "narrative_publish",
    recipe_revision: str = "recipe-v1",
    source_story_revision: int = 1,
    source_world_revision: int = 1,
    input_digest: str = "sha256:" + "e" * 64,
) -> PostCommitJobSpec:
    return PostCommitJobSpec(
        job_id=job_id,
        turn_id=turn_id,
        session_id=session_id,
        kind=kind,
        recipe_revision=recipe_revision,
        source_story_revision=source_story_revision,
        source_world_revision=source_world_revision,
        input_digest=input_digest,
    )


def _domain_commit_request(*, turn_id: str, expected_revision: int = 0):
    return database_manager.CommitRequest(
        worldline_id="line-test",
        world_time="1349-01-01T00:00:00Z",
        expected_revision=expected_revision,
        idempotency_key=f"job-commit-{turn_id}",
        request_id=f"job-request-{turn_id}",
        trace_id=f"job-trace-{turn_id}",
        operation={"turn_id": turn_id},
        events=(
            database_manager.StoredEvent(
                event_id=f"job-event-{turn_id}",
                aggregate_id="world-test",
                event_type="PostCommitJobTestTurn",
                payload={"turn_id": turn_id},
                turn_id=turn_id,
            ),
        ),
    )


def _insert_domain_turn(tx, *, turn_id: str, session_id: str) -> None:
    revision = tx.revision
    delta_id = f"delta-{turn_id}"
    tx.execute(
        "INSERT INTO story_sessions("
        "id,world_id,worldline_id,protagonist_id,story_seed_id,"
        "base_world_revision,base_character_revision,base_story_revision,"
        "story_revision,status,story_state_json,committed_world_revision"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            session_id,
            "world-test",
            "line-test",
            "player-test",
            "seed-test",
            revision - 1,
            revision - 1,
            0,
            1,
            "active",
            "{}",
            revision,
        ),
    )
    tx.execute(
        "INSERT INTO story_state_deltas("
        "id,session_id,turn_id,story_revision,payload_json,committed_world_revision"
        ") VALUES (?,?,?,?,?,?)",
        (delta_id, session_id, turn_id, 1, "{}", revision),
    )
    tx.execute(
        "INSERT INTO turn_transactions("
        "id,session_id,idempotency_key,status,base_world_revision,"
        "base_character_revision,base_story_revision,state_delta_id,"
        "committed_story_revision,transaction_json,committed_world_revision"
        ") VALUES (?,?,?,'committed',?,?,?,?,?,'{}',?)",
        (
            turn_id,
            session_id,
            f"turn-idem-{turn_id}",
            revision - 1,
            revision - 1,
            0,
            delta_id,
            1,
            revision,
        ),
    )


async def _seed_repository_turn(
    database: DatabaseManager,
    *,
    turn_id: str = "turn-1",
    session_id: str = "session-1",
) -> None:
    await database._submit(
        lambda: _seed_committed_turn(database._connection, turn_id=turn_id)
    )

    def seed_delta():
        connection = database._connection
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO story_state_deltas("
            "id,session_id,turn_id,story_revision,payload_json,committed_world_revision"
            ") VALUES (?,?,?,?,?,?)",
            (f"delta-{turn_id}", session_id, turn_id, 1, "{}", 1),
        )
        connection.execute(
            "UPDATE turn_transactions SET state_delta_id=?,committed_story_revision=1 "
            "WHERE id=?",
            (f"delta-{turn_id}", turn_id),
        )
        connection.execute("COMMIT")

    await database._submit(seed_delta)


async def _world_revision(database: DatabaseManager) -> int:
    rows = await database.read_world(
        "SELECT revision FROM world_meta WHERE singleton=1"
    )
    return rows[0]["revision"]


def _story_commit_inputs(
    *,
    session_id: str = "planned-session",
    turn_id: str = "planned-turn",
) -> tuple[StorySession, StateDelta, TurnTransaction]:
    delta_id = f"delta-{turn_id}"
    state = StoryState.model_validate(
        {
            "schema_version": "1.0",
            "story_session_id": session_id,
            "revision": 1,
            "turn": 1,
            "phase": "discovery",
            "scene": {
                "id": "scene-1",
                "location_id": "room-1",
                "active_character_ids": ["player-1"],
            },
            "world_time": "1349-06-12T21:40:00",
            "protagonist_goal": "investigate",
            "active_conflicts": [],
            "discovered_clue_ids": [],
            "secret_states": {},
            "commitments": {"hard_ids": [], "soft_ids": []},
            "local_state": {},
            "pressure": {},
            "last_state_delta_id": delta_id,
        }
    )
    session = StorySession.model_validate(
        {
            "schema_version": "1.0",
            "id": session_id,
            "world_id": "world-test",
            "worldline_id": "line-test",
            "protagonist_id": "player-1",
            "story_seed_id": "seed-test",
            "base_revisions": {"world": 0, "character": 0, "story": 0},
            "story_state": state.model_dump(mode="json", exclude_none=True),
            "status": "active",
        }
    )
    delta = StateDelta.model_validate(
        {
            "schema_version": "1.0",
            "id": delta_id,
            "turn_id": turn_id,
            "outcome": "clean_success",
            "story_delta": {},
            "character_deltas": [],
            "world_event_candidates": [],
            "evidence_ids": [],
        }
    )
    turn = TurnTransaction.model_validate(
        {
            "schema_version": "1.0",
            "id": turn_id,
            "session_id": session_id,
            "idempotency_key": f"idempotency-{turn_id}",
            "status": "committed",
            "base_revisions": {"world": 0, "character": 0, "story": 0},
            "state_delta_id": delta_id,
            "committed_story_revision": 1,
            "narrative_block_id": None,
        }
    )
    return session, delta, turn


def _planned_job(
    *,
    job_id: str = "planned-job",
    kind: PostCommitKind | str = PostCommitKind.NARRATIVE_PUBLISH,
    recipe_revision: str = "narrative-v1",
    input_digest: str = "a" * 64,
    initial_state: PostCommitJobState | str = PostCommitJobState.PENDING,
    initial_reason_code: str | None = None,
) -> PlannedPostCommitJob:
    return PlannedPostCommitJob(
        job_id=job_id,
        kind=kind,
        recipe_revision=recipe_revision,
        input_digest=input_digest,
        initial_state=initial_state,
        initial_reason_code=initial_reason_code,
    )


class _FixedPostCommitPlanner:
    def __init__(self, jobs):
        self.jobs = tuple(jobs)
        self.calls = 0

    def plan_jobs(self, *, session, delta, turn):
        self.calls += 1
        assert session.id == turn.session_id
        assert delta.id == turn.state_delta_id
        return self.jobs


async def _commit_planned_story_turn(
    database: DatabaseManager,
    *,
    planner=None,
    turn_id: str = "planned-turn",
    session_id: str = "planned-session",
):
    session, delta, turn = _story_commit_inputs(
        session_id=session_id,
        turn_id=turn_id,
    )
    return await SQLiteStorySessionCommitPort(
        database, planner=planner
    ).commit_turn(
        session,
        delta,
        turn,
        store_expected_revision=0,
        request_id=f"request-{turn_id}",
        trace_id=f"trace-{turn_id}",
    )


async def _assert_story_commit_absent(
    database: DatabaseManager,
    turn_id: str,
) -> None:
    assert await _world_revision(database) == 0
    for table in (
        "story_sessions",
        "story_state_deltas",
        "turn_transactions",
        "domain_commits",
        "domain_events",
        "post_commit_jobs",
    ):
        assert await database.read_world(
            f"SELECT count(*) AS count FROM {table}"
        ) == [{"count": 0}]
    assert await database.read_world(
        "SELECT count(*) AS count FROM post_commit_jobs AS j "
        "LEFT JOIN turn_transactions AS t ON t.id=j.turn_id "
        "WHERE t.id IS NULL OR j.turn_id=?",
        (turn_id,),
    ) == [{"count": 0}]


@pytest.mark.asyncio
async def test_commit_turn_registers_jobs_atomically_and_persists_blocked_voice_state(
    tmp_path,
):
    database = await _open_database(tmp_path)
    planner = _FixedPostCommitPlanner(
        (
            _planned_job(
                job_id="planned-narrative",
                recipe_revision="narrative-v1",
                input_digest="b" * 64,
            ),
            _planned_job(
                job_id="planned-audio",
                kind=PostCommitKind.AUDIO_PREPARE,
                recipe_revision="audio-v1",
                input_digest="c" * 64,
                initial_state=PostCommitJobState.BLOCKED,
                initial_reason_code="voice_not_configured",
            ),
        )
    )
    observations: dict[str, tuple[int, ...]] = {}

    def counts(connection):
        return tuple(
            connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "turn_transactions",
                "story_state_deltas",
                "domain_events",
                "post_commit_jobs",
            )
        )

    def observe_transaction_visibility(stage: str):
        if stage != "before_commit":
            return
        observations["inside"] = counts(database._connection)
        with stdlib_sqlite3.connect(database.paths.world) as external:
            observations["outside"] = counts(external)

    database._fault_hook = observe_transaction_visibility
    try:
        committed = await _commit_planned_story_turn(database, planner=planner)
        assert committed.store_revision == 1
        assert planner.calls == 1
        assert observations == {
            "inside": (1, 1, 1, 2),
            "outside": (0, 0, 0, 0),
        }
        assert await database.read_world(
            "SELECT kind,state,last_error_code FROM post_commit_jobs "
            "ORDER BY kind"
        ) == [
            {
                "kind": "audio_prepare",
                "state": "blocked",
                "last_error_code": "voice_not_configured",
            },
            {
                "kind": "narrative_publish",
                "state": "pending",
                "last_error_code": None,
            },
        ]
        assert await _world_revision(database) == 1
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_commit_turn_without_planner_preserves_no_job_behavior(tmp_path):
    database = await _open_database(tmp_path)
    try:
        result = await _commit_planned_story_turn(database)
        assert result.store_revision == 1
        assert await _world_revision(database) == 1
        assert await database.read_world(
            "SELECT count(*) AS count FROM post_commit_jobs"
        ) == [{"count": 0}]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_commit_turn_rollback_leaves_no_jobs_or_orphan_turn(tmp_path):
    database = await _open_database(tmp_path)
    planner = _FixedPostCommitPlanner(
        (
            _planned_job(
                job_id="rollback-job",
                input_digest="d" * 64,
            ),
        )
    )

    def fail_before_commit(stage: str):
        if stage == "before_commit":
            raise RuntimeError("injected domain rollback")

    database._fault_hook = fail_before_commit
    try:
        with pytest.raises(RuntimeError, match="injected domain rollback"):
            await _commit_planned_story_turn(database, planner=planner)
        await _assert_story_commit_absent(database, "planned-turn")
        assert planner.calls == 1
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_commit_turn_planner_error_rolls_back_the_domain_transaction(tmp_path):
    database = await _open_database(tmp_path)

    class RaisingPlanner:
        def plan_jobs(self, *, session, delta, turn):
            raise RuntimeError("planner failed")

    try:
        with pytest.raises(RuntimeError, match="planner failed"):
            await _commit_planned_story_turn(database, planner=RaisingPlanner())
        await _assert_story_commit_absent(database, "planned-turn")
    finally:
        await database.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "job",
    [
        _planned_job(kind="unknown_kind"),
        _planned_job(recipe_revision=""),
        _planned_job(input_digest="sha256:" + "e" * 64),
        _planned_job(initial_state="running"),
        _planned_job(initial_state="succeeded"),
        _planned_job(initial_state="pending", initial_reason_code="unavailable"),
    ],
)
async def test_commit_turn_rejects_invalid_planned_job_and_rolls_back(tmp_path, job):
    database = await _open_database(tmp_path)
    try:
        with pytest.raises(StorageError):
            await _commit_planned_story_turn(
                database,
                planner=_FixedPostCommitPlanner((job,)),
            )
        await _assert_story_commit_absent(database, "planned-turn")
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_commit_turn_reuses_duplicate_planner_identity_without_duplicate_rows(
    tmp_path,
):
    database = await _open_database(tmp_path)
    planned = _planned_job(
        job_id="duplicate-job",
        recipe_revision="narrative-v1",
        input_digest="f" * 64,
    )
    try:
        await _commit_planned_story_turn(
            database,
            planner=_FixedPostCommitPlanner((planned, planned)),
        )
        assert await database.read_world(
            "SELECT count(*) AS count FROM post_commit_jobs"
        ) == [{"count": 1}]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_commit_turn_rejects_duplicate_identity_with_conflicting_digest(tmp_path):
    database = await _open_database(tmp_path)
    first = _planned_job(
        job_id="conflicting-job",
        recipe_revision="narrative-v1",
        input_digest="1" * 64,
    )
    second = _planned_job(
        job_id="conflicting-job",
        recipe_revision="narrative-v1",
        input_digest="2" * 64,
    )
    try:
        with pytest.raises(PostCommitJobConflict):
            await _commit_planned_story_turn(
                database,
                planner=_FixedPostCommitPlanner((first, second)),
            )
        await _assert_story_commit_absent(database, "planned-turn")
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_commit_turn_rejects_duplicate_job_id_across_identities(tmp_path):
    database = await _open_database(tmp_path)
    first = _planned_job(
        job_id="shared-job-id",
        kind=PostCommitKind.NARRATIVE_PUBLISH,
        recipe_revision="narrative-v1",
        input_digest="3" * 64,
    )
    second = _planned_job(
        job_id="shared-job-id",
        kind=PostCommitKind.AUDIO_PREPARE,
        recipe_revision="audio-v1",
        input_digest="4" * 64,
    )
    try:
        with pytest.raises(PostCommitJobConflict):
            await _commit_planned_story_turn(
                database,
                planner=_FixedPostCommitPlanner((first, second)),
            )
        await _assert_story_commit_absent(database, "planned-turn")
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_registration_preserves_initial_state_and_never_resets_existing_state(
    tmp_path,
):
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        await _seed_repository_turn(database)
        spec = _repository_job()
        blocked = PostCommitJobRegistration(
            spec=spec,
            initial_state="blocked",
            initial_reason_code="voice_not_configured",
        )
        first = await database.post_commit_job_write(
            lambda tx: repository.register(tx, (blocked,))
        )
        assert first[0].state == "blocked"
        assert first[0].last_error_code == "voice_not_configured"

        await database.post_commit_job_write(
            lambda tx: tx.execute(
                "UPDATE post_commit_jobs SET state='succeeded',"
                "last_error_code=NULL WHERE job_id='repo-job-1'"
            )
        )
        retry_registration = PostCommitJobRegistration(
            spec=spec,
            initial_state="pending",
            initial_reason_code=None,
        )
        second = await database.post_commit_job_write(
            lambda tx: repository.register(tx, (retry_registration,))
        )
        assert second[0].state == "succeeded"
        assert second[0].last_error_code is None
        assert await database.read_world(
            "SELECT state,last_error_code FROM post_commit_jobs "
            "WHERE job_id='repo-job-1'"
        ) == [{"state": "succeeded", "last_error_code": None}]
    finally:
        await database.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "initial_state,initial_reason_code",
    [
        ("running", None),
        ("succeeded", None),
        ("pending", "voice_not_configured"),
        ("blocked", None),
        ("blocked", "Uppercase"),
        ("blocked", "x" * 129),
    ],
)
async def test_registration_rejects_invalid_initial_state_or_reason(
    tmp_path,
    initial_state,
    initial_reason_code,
):
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        await _seed_repository_turn(database)
        registration = PostCommitJobRegistration(
            spec=_repository_job(),
            initial_state=initial_state,
            initial_reason_code=initial_reason_code,
        )
        with pytest.raises(StorageError):
            await database.post_commit_job_write(
                lambda tx: repository.register(tx, (registration,))
            )
        assert await database.read_world(
            "SELECT count(*) AS count FROM post_commit_jobs"
        ) == [{"count": 0}]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_registration_rejects_source_pointer_mismatch(tmp_path):
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        await _seed_repository_turn(database)
        mismatched = _repository_job(source_world_revision=2)
        with pytest.raises(PostCommitJobConflict):
            await database.post_commit_job_write(
                lambda tx: repository.register(tx, (mismatched,))
            )
        assert await database.read_world(
            "SELECT count(*) AS count FROM post_commit_jobs"
        ) == [{"count": 0}]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_registration_is_atomic_with_turn_and_rolls_back_with_domain_transaction(
    tmp_path,
):
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        spec = _repository_job(
            job_id="atomic-job",
            turn_id="atomic-turn",
            session_id="atomic-session",
            source_world_revision=1,
        )

        def apply(tx, *, fail: bool):
            _insert_domain_turn(
                tx, turn_id="atomic-turn", session_id="atomic-session"
            )
            registered = repository.register(tx, (spec,))
            assert len(registered) == 1
            assert registered[0].job_id == "atomic-job"
            if fail:
                raise RuntimeError("injected domain rollback")

        with pytest.raises(RuntimeError, match="injected domain rollback"):
            await database.commit_resolved(
                _domain_commit_request(turn_id="atomic-turn"),
                lambda tx: apply(tx, fail=True),
            )
        assert await _world_revision(database) == 0
        assert await database.read_world(
            "SELECT count(*) AS count FROM turn_transactions"
        ) == [{"count": 0}]
        assert await database.read_world(
            "SELECT count(*) AS count FROM post_commit_jobs"
        ) == [{"count": 0}]

        committed = await database.commit_resolved(
            _domain_commit_request(turn_id="atomic-turn"),
            lambda tx: apply(tx, fail=False),
        )
        assert committed.revision == 1
        assert await database.read_world(
            "SELECT turn_id,session_id,state FROM post_commit_jobs"
        ) == [
            {
                "turn_id": "atomic-turn",
                "session_id": "atomic-session",
                "state": "pending",
            }
        ]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_domain_job_registration_scope_is_insert_only_and_restores_after_error(
    tmp_path,
):
    database = await _open_database(tmp_path)
    try:
        await _seed_repository_turn(database)

        def apply(tx):
            with tx._post_commit_job_registration_scope() as scoped:
                _insert_job(scoped, _job_values(job_id="scope-job"))
                scoped.execute(
                    "INSERT INTO post_commit_retry_requests(request_id,job_id) "
                    "VALUES ('scope-retry','scope-job')"
                )
                scoped.execute(
                    "INSERT INTO post_commit_job_results("
                    "job_id,format_version,payload_json,payload_digest"
                    ") VALUES ('scope-job','1.0','{}','sha256:"
                    + "f" * 64
                    + "')"
                )
                for sql in (
                    "UPDATE post_commit_jobs SET state='running' WHERE job_id='scope-job'",
                    "DELETE FROM post_commit_jobs WHERE job_id='scope-job'",
                    "UPDATE post_commit_retry_requests SET job_id=job_id",
                    "DELETE FROM post_commit_retry_requests",
                    "UPDATE post_commit_job_results SET payload_json=payload_json",
                    "DELETE FROM post_commit_job_results",
                    "UPDATE turn_transactions SET status=status",
                    "UPDATE story_state_deltas SET payload_json=payload_json",
                    "UPDATE narrative_blocks SET id=id",
                    "UPDATE projection_outbox SET processed=processed",
                    "UPDATE world_meta SET revision=revision",
                ):
                    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
                        scoped.execute(sql)

            # A no-op UPDATE still passes through the original domain
            # authorizer, proving the insert-only scope was restored.
            tx.execute(
                "UPDATE story_sessions SET status=status WHERE id='session-1'"
            )
            with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
                tx.execute(
                    "UPDATE post_commit_jobs SET state='running' "
                    "WHERE job_id='scope-job'"
                )
            with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
                tx.execute(
                    "INSERT INTO post_commit_retry_requests(request_id,job_id) "
                    "VALUES ('bypass-retry','scope-job')"
                )

        committed = await database.commit_resolved(
            _domain_commit_request(turn_id="scope-domain-commit", expected_revision=1),
            apply,
        )
        assert committed.revision == 2
        assert await database.read_world(
            "SELECT job_id FROM post_commit_jobs WHERE job_id='scope-job'"
        ) == [{"job_id": "scope-job"}]
        assert await database.read_world(
            "SELECT request_id FROM post_commit_retry_requests"
        ) == [{"request_id": "scope-retry"}]
        assert await database.read_world(
            "SELECT job_id FROM post_commit_job_results"
        ) == [{"job_id": "scope-job"}]
        assert await database.read_world(
            "SELECT revision FROM world_meta WHERE singleton=1"
        ) == [{"revision": 2}]

        def apply_after_scope_exception(tx):
            with pytest.raises(RuntimeError, match="scope callback failure"):
                with tx._post_commit_job_registration_scope():
                    raise RuntimeError("scope callback failure")
            tx.execute(
                "UPDATE story_sessions SET status=status WHERE id='session-1'"
            )

        committed_after_error = await database.commit_resolved(
            _domain_commit_request(
                turn_id="scope-domain-commit-after-error", expected_revision=2
            ),
            apply_after_scope_exception,
        )
        assert committed_after_error.revision == 3
        assert await database.read_world(
            "SELECT revision FROM world_meta WHERE singleton=1"
        ) == [{"revision": 3}]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_repository_register_reuses_identical_identity_and_rejects_digest_conflict(
    tmp_path,
):
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        await _seed_repository_turn(database)
        spec = _repository_job()
        first = await database.post_commit_job_write(
            lambda tx: repository.register(tx, (spec,))
        )
        second = await database.post_commit_job_write(
            lambda tx: repository.register(tx, (spec,))
        )
        assert first == second
        assert await database.read_world(
            "SELECT count(*) AS count FROM post_commit_jobs"
        ) == [{"count": 1}]

        conflict = _repository_job(input_digest="sha256:" + "0" * 64)
        with pytest.raises(PostCommitJobConflict):
            await database.post_commit_job_write(
                lambda tx: repository.register(tx, (conflict,))
            )
        assert await database.read_world(
            "SELECT input_digest FROM post_commit_jobs WHERE job_id='repo-job-1'"
        ) == [{"input_digest": "sha256:" + "e" * 64}]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_claim_is_ordered_and_second_claim_cannot_reclaim_running_job(tmp_path):
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        await _seed_repository_turn(database)

        def add_later_turn(tx):
            tx.execute(
                "UPDATE story_sessions SET story_revision=2,committed_world_revision=? "
                "WHERE id='session-1'",
                (tx.revision,),
            )
            tx.execute(
                "INSERT INTO story_state_deltas("
                "id,session_id,turn_id,story_revision,payload_json,"
                "committed_world_revision"
                ") VALUES ('delta-turn-2','session-1','turn-2',2,'{}',?)",
                (tx.revision,),
            )
            tx.execute(
                "INSERT INTO turn_transactions("
                "id,session_id,idempotency_key,status,base_world_revision,"
                "base_character_revision,base_story_revision,state_delta_id,"
                "committed_story_revision,transaction_json,committed_world_revision"
                ") VALUES ('turn-2','session-1','turn-idem-2','committed',"
                "1,1,1,'delta-turn-2',2,'{}',?)",
                (tx.revision,),
            )

        await database.commit_resolved(
            _domain_commit_request(turn_id="turn-2", expected_revision=1),
            add_later_turn,
        )
        specs = (
            _repository_job(job_id="claim-turn-2", turn_id="turn-2",
                            source_story_revision=2, source_world_revision=2),
            _repository_job(job_id="claim-turn-1"),
        )
        await database.post_commit_job_write(
            lambda tx: repository.register(tx, specs)
        )

        claimed = await repository.claim(
            session_id="session-1",
            lease_owner="worker-private-owner",
            supported_recipes={
                "narrative_publish": {"recipe-v1"},
            },
            now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
        assert claimed is not None
        assert claimed.job_id == "claim-turn-1"
        assert claimed.lease_generation == 1

        second = await repository.claim(
            session_id="session-1",
            lease_owner="worker-private-owner",
            supported_recipes={"narrative_publish": {"recipe-v1"}},
            now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
        assert second is not None
        assert second.job_id == "claim-turn-2"
        third = await repository.claim(
            session_id="session-1",
            lease_owner="worker-private-owner",
            supported_recipes={"narrative_publish": {"recipe-v1"}},
            now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
        assert third is None
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_completion_requires_matching_lease_owner_and_generation(tmp_path):
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        await _seed_repository_turn(database)
        await database.post_commit_job_write(
            lambda tx: repository.register(tx, (_repository_job(),))
        )
        claimed = await repository.claim(
            session_id="session-1",
            lease_owner="worker-1",
            supported_recipes={"narrative_publish": {"recipe-v1"}},
            now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
        assert claimed is not None
        with pytest.raises(PostCommitLeaseConflict):
            await repository.complete(
                claimed.job_id,
                lease_owner="worker-1",
                lease_generation=claimed.lease_generation + 1,
                result_ref="narrative-result",
            )
        with pytest.raises(PostCommitLeaseConflict):
            await repository.complete(
                claimed.job_id,
                lease_owner="worker-other",
                lease_generation=claimed.lease_generation,
                result_ref="narrative-result",
            )

        completed = await repository.complete(
            claimed.job_id,
            lease_owner="worker-1",
            lease_generation=claimed.lease_generation,
            result_ref="narrative-result",
        )
        assert completed.state == "succeeded"
        assert completed.lease_owner is None
        assert completed.lease_generation == claimed.lease_generation
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_retry_request_is_idempotent_and_cannot_be_rebound_to_another_job(
    tmp_path,
):
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        await _seed_repository_turn(database)
        first_job = _repository_job(job_id="retry-job-1")
        second_job = _repository_job(
            job_id="retry-job-2",
            kind="episode_finalize",
            recipe_revision="episode-v1",
        )
        await database.post_commit_job_write(
            lambda tx: repository.register(tx, (first_job, second_job))
        )
        claimed = await repository.claim(
            session_id="session-1",
            lease_owner="worker-1",
            supported_recipes={
                "narrative_publish": {"recipe-v1"},
                "episode_finalize": {"episode-v1"},
            },
            now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
        assert claimed is not None
        await database.post_commit_job_write(
            lambda tx: tx.execute(
                "INSERT INTO post_commit_job_results("
                "job_id,format_version,payload_json,payload_digest"
                ") VALUES (?,?,?,?)",
                (
                    claimed.job_id,
                    "1.0",
                    '{"sealed":"unchanged"}',
                    "sha256:" + "9" * 64,
                ),
            )
        )
        with pytest.raises(PostCommitLeaseConflict):
            await repository.fail(
                claimed.job_id,
                lease_owner="worker-1",
                lease_generation=claimed.lease_generation + 1,
                error_code="temporary_network_failure",
                retryable=True,
                now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
            )
        with pytest.raises(PostCommitLeaseConflict):
            await repository.fail(
                claimed.job_id,
                lease_owner="worker-other",
                lease_generation=claimed.lease_generation,
                error_code="temporary_network_failure",
                retryable=True,
                now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
            )
        await repository.fail(
            claimed.job_id,
            lease_owner=claimed.lease_owner,
            lease_generation=claimed.lease_generation,
            error_code="temporary_network_failure",
            retryable=True,
            now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )

        first = await repository.retry("retry-job-1", request_id="retry-request-1")
        replay = await repository.retry("retry-job-1", request_id="retry-request-1")
        assert first.accepted is True
        assert first.replayed is False
        assert replay.accepted is True
        assert replay.replayed is True
        assert await database.read_world(
            "SELECT state,attempt,last_error_code,next_attempt_at,lease_owner,"
            "lease_generation FROM post_commit_jobs WHERE job_id='retry-job-1'"
        ) == [
            {
                "state": "pending",
                "attempt": 0,
                "last_error_code": None,
                "next_attempt_at": None,
                "lease_owner": None,
                "lease_generation": 1,
            }
        ]
        assert await database.read_world(
            "SELECT payload_json FROM post_commit_job_results WHERE job_id=?",
            ("retry-job-1",),
        ) == [{"payload_json": '{"sealed":"unchanged"}'}]
        with pytest.raises(PostCommitJobConflict):
            await repository.retry("retry-job-2", request_id="retry-request-1")
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_automatic_retry_uses_bounded_one_five_thirty_second_schedule(tmp_path):
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        await _seed_repository_turn(database)
        await database.post_commit_job_write(
            lambda tx: repository.register(tx, (_repository_job(),))
        )
        clock = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
        for attempt, delay_seconds in enumerate((1, 5, 30), start=1):
            claimed = await repository.claim(
                session_id="session-1",
                lease_owner="retry-worker",
                supported_recipes={"narrative_publish": {"recipe-v1"}},
                now=clock,
            )
            assert claimed is not None
            assert claimed.attempt == attempt
            await repository.fail(
                claimed.job_id,
                lease_owner=claimed.lease_owner,
                lease_generation=claimed.lease_generation,
                error_code="temporary_network_failure",
                retryable=True,
                now=clock,
            )
            scheduled = (
                await database.read_world(
                    "SELECT state,next_attempt_at FROM post_commit_jobs "
                    "WHERE job_id='repo-job-1'"
                )
            )[0]
            clock += timedelta(seconds=delay_seconds)
            assert scheduled == {
                "state": "retry_wait",
                "next_attempt_at": clock.isoformat(timespec="microseconds").replace(
                    "+00:00", "Z"
                ),
            }
            clock -= timedelta(seconds=delay_seconds)
            assert (
                await repository.claim(
                    session_id="session-1",
                    lease_owner="retry-worker",
                    supported_recipes={"narrative_publish": {"recipe-v1"}},
                    now=clock,
                )
                is None
            )
            clock += timedelta(seconds=delay_seconds)

        final_claim = await repository.claim(
            session_id="session-1",
            lease_owner="retry-worker",
            supported_recipes={"narrative_publish": {"recipe-v1"}},
            now=clock,
        )
        assert final_claim is not None
        assert final_claim.attempt == 4
        final = await repository.fail(
            final_claim.job_id,
            lease_owner=final_claim.lease_owner,
            lease_generation=final_claim.lease_generation,
            error_code="temporary_network_failure",
            retryable=True,
            now=clock,
        )
        assert final.state == "blocked"
        assert final.next_attempt_at is None
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_audio_job_waits_for_matching_narrative_dependency(tmp_path):
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        await _seed_repository_turn(database)
        await database.post_commit_job_write(
            lambda tx: repository.register(
                tx,
                (
                    _repository_job(
                        job_id="audio-job",
                        kind="audio_prepare",
                        recipe_revision="audio-v1",
                    ),
                ),
            )
        )
        claim_args = {
            "session_id": "session-1",
            "lease_owner": "worker-audio",
            "supported_recipes": {"audio_prepare": {"audio-v1"}},
            "now": datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        }
        assert await repository.claim(**claim_args) is None
        assert await database.read_world(
            "SELECT state FROM post_commit_jobs WHERE job_id='audio-job'"
        ) == [{"state": "pending"}]

        await database.post_commit_write(
            lambda tx: tx.execute(
                "INSERT INTO narrative_blocks("
                "id,turn_id,session_id,source_story_revision,source_world_revision,"
                "source_state_delta_id,payload_json"
                ") VALUES (?,?,?,?,?,?,?)",
                (
                    "narrative-1",
                    "turn-1",
                    "session-1",
                    1,
                    1,
                    "delta-turn-1",
                    "{}",
                ),
            )
        )
        claimed = await repository.claim(**claim_args)
        assert claimed is not None
        assert claimed.job_id == "audio-job"
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_audio_job_blocks_when_narrative_dependency_source_mismatches(tmp_path):
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        await _seed_repository_turn(database)
        await database.post_commit_job_write(
            lambda tx: repository.register(
                tx,
                (
                    _repository_job(
                        job_id="audio-mismatch-job",
                        kind="audio_prepare",
                        recipe_revision="audio-v1",
                    ),
                ),
            )
        )
        await database.post_commit_write(
            lambda tx: tx.execute(
                "INSERT INTO narrative_blocks("
                "id,turn_id,session_id,source_story_revision,source_world_revision,"
                "source_state_delta_id,payload_json"
                ") VALUES (?,?,?,?,?,?,?)",
                (
                    "narrative-mismatch",
                    "turn-1",
                    "session-1",
                    0,
                    1,
                    "delta-turn-1",
                    "{}",
                ),
            )
        )
        claimed = await repository.claim(
            session_id="session-1",
            lease_owner="worker-audio",
            supported_recipes={"audio_prepare": {"audio-v1"}},
            now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
        assert claimed is None
        assert await database.read_world(
            "SELECT state,last_error_code FROM post_commit_jobs "
            "WHERE job_id='audio-mismatch-job'"
        ) == [
            {
                "state": "blocked",
                "last_error_code": "dependency_source_mismatch",
            }
        ]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_unknown_recipe_is_blocked_without_becoming_claimed(tmp_path):
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        await _seed_repository_turn(database)
        await database.post_commit_job_write(
            lambda tx: repository.register(
                tx, (_repository_job(recipe_revision="recipe-not-installed"),)
            )
        )
        assert (
            await repository.claim(
                session_id="session-1",
                lease_owner="worker-1",
                supported_recipes={"narrative_publish": {"recipe-v1"}},
                now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
            )
            is None
        )
        assert await database.read_world(
            "SELECT state,last_error_code FROM post_commit_jobs WHERE job_id=?",
            ("repo-job-1",),
        ) == [{"state": "blocked", "last_error_code": "recipe_unavailable"}]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_job_repository_writes_do_not_advance_world_revision(tmp_path):
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        await _seed_repository_turn(database)
        before = await _world_revision(database)
        specs = (
            _repository_job(job_id="revision-narrative"),
            _repository_job(
                job_id="revision-episode",
                kind="episode_finalize",
                recipe_revision="episode-v1",
            ),
        )
        await database.post_commit_job_write(
            lambda tx: repository.register(tx, specs)
        )
        claimed = await repository.claim(
            session_id="session-1",
            lease_owner="revision-worker",
            supported_recipes={
                "narrative_publish": {"recipe-v1"},
                "episode_finalize": {"episode-v1"},
            },
            now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
        assert claimed is not None
        await repository.complete(
            claimed.job_id,
            lease_owner=claimed.lease_owner,
            lease_generation=claimed.lease_generation,
            result_ref="revision-result",
        )
        # Claim and complete an independent retryable job to cover the explicit
        # retry path without altering the completed job's state.
        await database.post_commit_job_write(
            lambda tx: tx.execute(
                "UPDATE post_commit_jobs SET state='pending' "
                "WHERE job_id='revision-episode'"
            )
        )
        episode = await repository.claim(
            session_id="session-1",
            lease_owner="revision-worker",
            supported_recipes={"episode_finalize": {"episode-v1"}},
            now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
        assert episode is not None
        await repository.fail(
            episode.job_id,
            lease_owner=episode.lease_owner,
            lease_generation=episode.lease_generation,
            error_code="temporary_network_failure",
            retryable=True,
            now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
        await repository.retry(episode.job_id, request_id="revision-retry")
        assert await _world_revision(database) == before
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_public_work_projection_is_read_only_and_hides_lease_and_internal_error(
    tmp_path,
):
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        await _seed_repository_turn(database)
        await database.post_commit_job_write(
            lambda tx: repository.register(tx, (_repository_job(),))
        )
        claimed = await repository.claim(
            session_id="session-1",
            lease_owner="private-worker-owner",
            supported_recipes={"narrative_publish": {"recipe-v1"}},
            now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
        assert claimed is not None
        await repository.fail(
            claimed.job_id,
            lease_owner=claimed.lease_owner,
            lease_generation=claimed.lease_generation,
            error_code="private-provider-trace-secret",
            retryable=False,
            now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
        revision_before = await _world_revision(database)
        raw_count_before = await database.read_world(
            "SELECT count(*) AS count FROM post_commit_jobs"
        )
        status = await repository.get_status(
            session_id="session-1", turn_id="turn-1"
        )
        replay = await repository.get_status(
            session_id="session-1", turn_id="turn-1"
        )
        public_data = repr(status)
        assert status == replay
        assert status.settlement == "not_required"
        assert status.narrative == "blocked"
        assert status.audio == "unavailable"
        assert status.narrative_reason == "work_unavailable"
        assert "private-worker-owner" not in public_data
        assert "private-provider-trace-secret" not in public_data
        assert "lease_owner" not in public_data
        assert "lease_generation" not in public_data
        assert await _world_revision(database) == revision_before
        assert await database.read_world(
            "SELECT count(*) AS count FROM post_commit_jobs"
        ) == raw_count_before
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_durable_audio_success_stays_unavailable_without_lowering_other_work(
    tmp_path,
):
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        await _seed_repository_turn(database)
        specs = (
            _repository_job(
                job_id="projection-settlement",
                kind="episode_finalize",
                recipe_revision="episode-v1",
            ),
            _repository_job(job_id="projection-narrative"),
            _repository_job(
                job_id="projection-audio",
                kind="audio_prepare",
                recipe_revision="audio-v1",
            ),
        )
        await database.post_commit_job_write(
            lambda tx: repository.register(tx, specs)
        )

        def complete_durable_work(tx):
            tx.execute(
                "INSERT INTO post_commit_job_results("
                "job_id,format_version,payload_json,payload_digest"
                ") VALUES (?,?,?,?)",
                (
                    "projection-audio",
                    "1.0",
                    '{"sealed":"durable"}',
                    "sha256:" + "8" * 64,
                ),
            )
            tx.execute(
                "UPDATE post_commit_jobs SET state='succeeded',result_ref=? "
                "WHERE job_id IN (?,?,?)",
                (
                    "durable-result",
                    "projection-settlement",
                    "projection-narrative",
                    "projection-audio",
                ),
            )

        await database.post_commit_job_write(complete_durable_work)
        status = await repository.get_status(
            session_id="session-1", turn_id="turn-1"
        )
        assert status.settlement == "succeeded"
        assert status.narrative == "ready"
        assert status.audio == "unavailable"
        assert status.audio_reason == "handoff_unverified"
        assert "ready" != status.audio
    finally:
        await database.close()
