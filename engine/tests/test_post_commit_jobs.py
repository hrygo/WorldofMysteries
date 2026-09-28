"""Post-COMMIT job schema and scoped writer boundary tests."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3 as stdlib_sqlite3

import pytest

from engine.infrastructure import database_manager, database_schema
from engine.infrastructure.database_manager import DatabaseManager, DatabasePaths
from engine.infrastructure.database_schema import (
    APPLICATION_IDS,
    connect,
    initialize,
    integrity,
    statements,
)
from engine.infrastructure.sqlite_runtime import sqlite3


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

        assert connection.execute("PRAGMA user_version").fetchone()[0] == 13
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

    backup = path.with_name("world.db.pre-migration-v12-to-v13.bak")
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
