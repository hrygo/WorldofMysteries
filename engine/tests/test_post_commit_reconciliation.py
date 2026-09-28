"""Historical post-COMMIT reconciliation tests backed by a real SQLite file."""
from __future__ import annotations

import hashlib
import sqlite3 as stdlib_sqlite3
from pathlib import Path

import pytest
from engine.infrastructure.database_manager import DatabaseManager, DatabasePaths
from engine.infrastructure.database_schema import StorageError
from engine.infrastructure.post_commit_job_repository import (
    PostCommitJobRegistration,
    PostCommitJobSpec,
    SQLitePostCommitJobRepository,
)
from engine.infrastructure.post_commit_reconciliation import (
    PostCommitReconciler,
)
from engine.infrastructure.sqlite_runtime import sqlite3

_COMMITTED = (
    "committed",
    "beat_ready",
    "narrative_ready",
    "audio_ready",
    "delivered",
)


async def _open_database(tmp_path: Path) -> DatabaseManager:
    paths = DatabasePaths.for_world(tmp_path / "app-support", "reconciliation")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    return await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )


def _domain_commit(revision: int, worldline_id: str) -> tuple:
    return (
        revision,
        worldline_id,
        f"idempotency-{revision}",
        f"digest-{revision}",
        f"request-{revision}",
        f"trace-{revision}",
        f"1349-01-0{revision}T00:00:00Z",
        f"2026-09-28T00:00:0{revision}Z",
        "{}",
        "{}",
    )


async def _seed_turns(database: DatabaseManager, turns: tuple[dict, ...]) -> None:
    def seed(connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO domain_commits("
            "revision,worldline_id,idempotency_key,request_digest,request_id,trace_id,"
            "world_time,commit_time,operation_json,result_json"
            ") VALUES (?,?,?,?,?,?,?,?,?,?)",
            _domain_commit(1, "line-seed"),
        )
        connection.execute("INSERT INTO projection_outbox(revision,processed) VALUES (1,0)")
        connection.execute("UPDATE world_meta SET revision=1 WHERE singleton=1")
        for item in turns:
            session_id = item["session_id"]
            worldline_id = f"line-{session_id}"
            connection.execute(
                "INSERT INTO story_sessions("
                "id,world_id,worldline_id,protagonist_id,story_seed_id,"
                "base_world_revision,base_character_revision,base_story_revision,"
                "story_revision,status,story_state_json,committed_world_revision"
                ") VALUES (?, ?, ?, ?, ?, 0, 0, 0, 1, ?, '{}', 1)",
                (
                    session_id,
                    f"world-{session_id}",
                    worldline_id,
                    f"player-{session_id}",
                    f"seed-{session_id}",
                    item.get("session_status", "active"),
                ),
            )
            turn_id = item["turn_id"]
            state = item.get("status", "committed")
            delta_id = f"delta-{turn_id}" if state in _COMMITTED else None
            if delta_id is not None:
                connection.execute(
                    "INSERT INTO story_state_deltas("
                    "id,session_id,turn_id,story_revision,payload_json,"
                    "committed_world_revision"
                    ") VALUES (?, ?, ?, 1, '{}', 1)",
                    (delta_id, session_id, turn_id),
                )
            connection.execute(
                "INSERT INTO turn_transactions("
                "id,session_id,idempotency_key,status,base_world_revision,"
                "base_character_revision,base_story_revision,state_delta_id,"
                "committed_story_revision,narrative_block_id,transaction_json,"
                "committed_world_revision"
                ") VALUES (?, ?, ?, ?, 0, 0, 0, ?, ?, NULL, '{}', ?)",
                (
                    turn_id,
                    session_id,
                    f"idempotency-{turn_id}",
                    state,
                    delta_id,
                    1 if delta_id else None,
                    1 if delta_id else None,
                ),
            )
        connection.execute("COMMIT")

    await database._submit(lambda: seed(database._connection))


async def _insert_narrative(
    database: DatabaseManager,
    *,
    turn_id: str,
    session_id: str,
    source_state_delta_id: str | None = None,
    source_story_revision: int = 1,
    source_world_revision: int = 1,
    narrative_id: str | None = None,
) -> None:
    artifact_id = narrative_id or f"narrative-{turn_id}"

    def insert(connection) -> None:
        connection.execute(
            "INSERT INTO narrative_blocks("
            "id,turn_id,session_id,source_story_revision,source_world_revision,"
            "source_state_delta_id,payload_json"
            ") VALUES (?, ?, ?, ?, ?, ?, '{}')",
            (
                artifact_id,
                turn_id,
                session_id,
                source_story_revision,
                source_world_revision,
                source_state_delta_id or f"delta-{turn_id}",
            ),
        )
        connection.execute(
            "UPDATE turn_transactions SET narrative_block_id=? WHERE id=?",
            (artifact_id, turn_id),
        )

    await database._submit(lambda: insert(database._connection))


async def _insert_beat_plan(
    database: DatabaseManager, *, turn_id: str, session_id: str
) -> None:
    await database._submit(
        lambda: database._connection.execute(
            "INSERT INTO beat_plans("
            "id,turn_id,session_id,source_story_revision,source_world_revision,payload_json"
            ") VALUES (?, ?, ?, 1, 1, '{}')",
            (f"beat-{turn_id}", turn_id, session_id),
        )
    )


async def _insert_episode(
    database: DatabaseManager, *, turn_id: str, session_id: str
) -> None:
    """Persist an Episode with a matching finalization/domain commit revision."""
    def seed(connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO domain_commits("
            "revision,worldline_id,idempotency_key,request_digest,request_id,trace_id,"
            "world_time,commit_time,operation_json,result_json"
            ") VALUES (?,?,?,?,?,?,?,?,?,?)",
            _domain_commit(2, f"line-{session_id}"),
        )
        connection.execute("INSERT INTO projection_outbox(revision,processed) VALUES (2,0)")
        connection.execute("UPDATE world_meta SET revision=2 WHERE singleton=1")
        connection.execute(
            "UPDATE story_sessions SET status='finalized',committed_world_revision=2 "
            "WHERE id=?",
            (session_id,),
        )
        connection.execute(
            "INSERT INTO episodes("
            "id,world_id,worldline_id,session_id,story_seed_id,payload_json,"
            "committed_world_revision"
            ") VALUES (?, ?, ?, ?, ?, '{}', 2)",
            (
                f"episode-{turn_id}",
                f"world-{session_id}",
                f"line-{session_id}",
                session_id,
                f"seed-{session_id}",
            ),
        )
        connection.execute(
            "INSERT INTO episode_finalizations("
            "episode_id,idempotency_key,request_digest,committed_world_revision"
            ") VALUES (?, ?, ?, 2)",
            (f"episode-{turn_id}", f"finalize-{session_id}", "a" * 64),
        )
        connection.execute("COMMIT")

    await database._submit(lambda: seed(database._connection))


async def _rows(database: DatabaseManager, sql: str, parameters: tuple = ()) -> list[dict]:
    return await database.read_world(sql, parameters)


@pytest.mark.asyncio
async def test_matching_narrative_is_reconciled_as_succeeded_with_its_artifact_ref(
    tmp_path,
):
    database = await _open_database(tmp_path)
    try:
        await _seed_turns(
            database,
            ({"turn_id": "turn-narrative", "session_id": "session-narrative"},),
        )
        await _insert_narrative(
            database, turn_id="turn-narrative", session_id="session-narrative"
        )

        report = await PostCommitReconciler(database).reconcile()

        assert report.registered_jobs == 1
        assert await _rows(
            database,
            "SELECT kind,state,result_ref FROM post_commit_jobs WHERE turn_id=?",
            ("turn-narrative",),
        ) == [
            {
                "kind": "narrative_publish",
                "state": "succeeded",
                "result_ref": "narrative-turn-narrative",
            }
        ]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_missing_narrative_is_blocked_even_when_only_a_beat_plan_exists(tmp_path):
    database = await _open_database(tmp_path)
    try:
        await _seed_turns(
            database,
            ({"turn_id": "turn-beat-only", "session_id": "session-beat-only"},),
        )
        await _insert_beat_plan(
            database, turn_id="turn-beat-only", session_id="session-beat-only"
        )

        report = await PostCommitReconciler(database).reconcile()

        assert report.blocked_jobs == 1
        assert await _rows(
            database,
            "SELECT kind,state,last_error_code,result_ref FROM post_commit_jobs "
            "WHERE turn_id=?",
            ("turn-beat-only",),
        ) == [
            {
                "kind": "narrative_publish",
                "state": "blocked",
                "last_error_code": "legacy_recipe_unknown",
                "result_ref": None,
            }
        ]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_turn_without_any_post_commit_artifact_is_blocked_not_guessed_pending(
    tmp_path,
):
    database = await _open_database(tmp_path)
    try:
        await _seed_turns(
            database,
            ({"turn_id": "turn-empty", "session_id": "session-empty"},),
        )

        await PostCommitReconciler(database).reconcile()

        assert await _rows(
            database,
            "SELECT kind,state,last_error_code FROM post_commit_jobs WHERE turn_id=?",
            ("turn-empty",),
        ) == [
            {
                "kind": "narrative_publish",
                "state": "blocked",
                "last_error_code": "legacy_recipe_unknown",
            }
        ]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_non_committed_turn_is_unverifiable_and_never_registered(tmp_path):
    database = await _open_database(tmp_path)
    try:
        await _seed_turns(
            database,
            (
                {
                    "turn_id": "turn-reconcile-required",
                    "session_id": "session-reconcile-required",
                    "status": "reconcile_required",
                },
            ),
        )

        report = await PostCommitReconciler(database).reconcile()

        assert report.unverifiable_turns == 1
        assert await _rows(
            database, "SELECT * FROM post_commit_jobs WHERE turn_id=?",
            ("turn-reconcile-required",),
        ) == []
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_mismatched_turn_delta_is_unverifiable_and_never_registered(tmp_path):
    database = await _open_database(tmp_path)
    try:
        await _seed_turns(
            database,
            (
                {"turn_id": "turn-source-a", "session_id": "session-source-a"},
                {"turn_id": "turn-source-b", "session_id": "session-source-b"},
            ),
        )
        await database._submit(
            lambda: database._connection.execute(
                "UPDATE turn_transactions SET state_delta_id=? WHERE id=?",
                ("delta-turn-source-b", "turn-source-a"),
            )
        )

        report = await PostCommitReconciler(database).reconcile()

        assert report.unverifiable_turns == 1
        assert await _rows(
            database, "SELECT * FROM post_commit_jobs WHERE turn_id=?",
            ("turn-source-a",),
        ) == []
        assert await _rows(
            database, "SELECT state FROM post_commit_jobs WHERE turn_id=?",
            ("turn-source-b",),
        ) == [{"state": "blocked"}]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_narrative_artifact_with_wrong_source_delta_is_not_succeeded(tmp_path):
    database = await _open_database(tmp_path)
    try:
        await _seed_turns(
            database,
            (
                {"turn_id": "turn-narrative-a", "session_id": "session-narrative-a"},
                {"turn_id": "turn-narrative-b", "session_id": "session-narrative-b"},
            ),
        )
        await _insert_narrative(
            database,
            turn_id="turn-narrative-a",
            session_id="session-narrative-a",
            source_state_delta_id="delta-turn-narrative-b",
        )

        await PostCommitReconciler(database).reconcile()

        assert await _rows(
            database,
            "SELECT state,last_error_code,result_ref FROM post_commit_jobs "
            "WHERE turn_id='turn-narrative-a'",
        ) == [
            {
                "state": "blocked",
                "last_error_code": "legacy_recipe_unknown",
                "result_ref": None,
            }
        ]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_episode_result_is_registered_only_for_the_finalized_terminal_turn(
    tmp_path,
):
    database = await _open_database(tmp_path)
    try:
        await _seed_turns(
            database,
            (
                {
                    "turn_id": "turn-closing",
                    "session_id": "session-closing",
                    "session_status": "closing",
                },
                {
                    "turn_id": "turn-finalized",
                    "session_id": "session-finalized",
                    "session_status": "finalized",
                },
                {"turn_id": "turn-active", "session_id": "session-active"},
            ),
        )
        await _insert_episode(
            database, turn_id="turn-finalized", session_id="session-finalized"
        )

        report = await PostCommitReconciler(database).reconcile()

        assert report.registered_jobs == 5
        assert await _rows(
            database,
            "SELECT kind,state,last_error_code,result_ref FROM post_commit_jobs "
            "WHERE turn_id IN (?, ?) ORDER BY turn_id,kind",
            ("turn-closing", "turn-finalized"),
        ) == [
            {
                "kind": "episode_finalize",
                "state": "blocked",
                "last_error_code": "legacy_recipe_unknown",
                "result_ref": None,
            },
            {
                "kind": "narrative_publish",
                "state": "blocked",
                "last_error_code": "legacy_recipe_unknown",
                "result_ref": None,
            },
            {
                "kind": "episode_finalize",
                "state": "succeeded",
                "last_error_code": None,
                "result_ref": "episode-turn-finalized",
            },
            {
                "kind": "narrative_publish",
                "state": "blocked",
                "last_error_code": "legacy_recipe_unknown",
                "result_ref": None,
            },
        ]
        assert await _rows(
            database, "SELECT kind FROM post_commit_jobs WHERE turn_id='turn-active'",
        ) == [{"kind": "narrative_publish"}]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_existing_jobs_and_sealed_audio_result_are_not_replaced_on_replay(
    tmp_path,
):
    database = await _open_database(tmp_path)
    try:
        await _seed_turns(
            database,
            (
                {"turn_id": "turn-existing", "session_id": "session-existing"},
                {"turn_id": "turn-missing", "session_id": "session-missing"},
            ),
        )
        await _insert_narrative(
            database, turn_id="turn-existing", session_id="session-existing"
        )

        def insert_existing(connection) -> None:
            connection.execute(
                "INSERT INTO post_commit_jobs("
                "job_id,turn_id,session_id,kind,recipe_revision,source_story_revision,"
                "source_world_revision,input_digest,state,attempt,lease_owner,"
                "lease_generation,next_attempt_at,last_error_code,result_ref"
                ") VALUES ('existing-audio','turn-existing','session-existing',"
                "'audio_prepare','audio-v1',1,1,?,'succeeded',1,NULL,1,NULL,NULL,"
                "'sealed-unit-v1')",
                ("b" * 64,),
            )
            connection.execute(
                "INSERT INTO post_commit_job_results("
                "job_id,format_version,payload_json,payload_digest"
                ") VALUES ('existing-audio','1.0','{\"unit\":\"sealed-v1\"}',?)",
                (hashlib.sha256(b'{"unit":"sealed-v1"}').hexdigest(),),
            )
            connection.execute(
                "INSERT INTO post_commit_jobs("
                "job_id,turn_id,session_id,kind,recipe_revision,source_story_revision,"
                "source_world_revision,input_digest,state,attempt,lease_owner,"
                "lease_generation,next_attempt_at,last_error_code,result_ref"
                ") VALUES ('existing-narrative','turn-missing','session-missing',"
                "'narrative_publish','legacy-old-v2',1,1,?,'blocked',0,NULL,0,NULL,"
                "'prior_block','prior-result')",
                ("c" * 64,),
            )

        await database._submit(lambda: insert_existing(database._connection))
        before_audio_job = await _rows(
            database,
            "SELECT * FROM post_commit_jobs WHERE job_id='existing-audio'",
        )
        before_audio_result = await _rows(
            database,
            "SELECT * FROM post_commit_job_results WHERE job_id='existing-audio'",
        )
        world_revision_before = await _rows(
            database, "SELECT revision FROM world_meta WHERE singleton=1"
        )

        first = await PostCommitReconciler(database).reconcile()
        second = await PostCommitReconciler(database).reconcile()

        assert first.registered_jobs == 1
        assert first.preserved_jobs == 2
        assert second.registered_jobs == 0
        assert second.preserved_jobs == 3
        assert await _rows(
            database, "SELECT revision FROM world_meta WHERE singleton=1"
        ) == world_revision_before
        assert await _rows(
            database, "SELECT * FROM post_commit_jobs WHERE job_id='existing-audio'"
        ) == before_audio_job
        assert await _rows(
            database,
            "SELECT * FROM post_commit_job_results WHERE job_id='existing-audio'",
        ) == before_audio_result
        assert await _rows(
            database,
            "SELECT state,last_error_code,result_ref FROM post_commit_jobs "
            "WHERE job_id='existing-narrative'",
        ) == [
            {
                "state": "blocked",
                "last_error_code": "prior_block",
                "result_ref": "prior-result",
            }
        ]
        assert await _rows(
            database,
            "SELECT turn_id,kind FROM post_commit_jobs WHERE turn_id='turn-existing' "
            "ORDER BY kind",
        ) == [
            {"turn_id": "turn-existing", "kind": "audio_prepare"},
            {"turn_id": "turn-existing", "kind": "narrative_publish"},
        ]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_job_registration_requires_result_ref_for_succeeded_and_rejects_it_otherwise(
    tmp_path,
):
    database = await _open_database(tmp_path)
    try:
        await _seed_turns(
            database,
            ({"turn_id": "turn-registration", "session_id": "session-registration"},),
        )
        repository = SQLitePostCommitJobRepository(database)
        spec = PostCommitJobSpec(
            job_id="registration-job",
            turn_id="turn-registration",
            session_id="session-registration",
            kind="narrative_publish",
            recipe_revision="legacy_recipe_unknown",
            source_story_revision=1,
            source_world_revision=1,
            input_digest="d" * 64,
        )

        with pytest.raises(StorageError, match="result ref"):
            await database.post_commit_job_write(
                lambda tx: repository.register(
                    tx, (PostCommitJobRegistration(spec, initial_state="succeeded"),)
                )
            )
        with pytest.raises(StorageError, match="Pending"):
            await database.post_commit_job_write(
                lambda tx: repository.register(
                    tx,
                    (
                        PostCommitJobRegistration(
                            spec,
                            initial_state="pending",
                            initial_result_ref="unexpected-result",
                        ),
                    ),
                )
            )
        with pytest.raises(StorageError, match="result ref"):
            await database.post_commit_job_write(
                lambda tx: repository.register(
                    tx,
                    (
                        PostCommitJobRegistration(
                            spec,
                            initial_state="succeeded",
                            initial_result_ref="invalid\x00result",
                        ),
                    ),
                )
            )
        records = await database.post_commit_job_write(
            lambda tx: repository.register(
                tx,
                (
                    PostCommitJobRegistration(
                        spec,
                        initial_state="succeeded",
                        initial_result_ref="narrative-turn-registration",
                    ),
                ),
            )
        )
        assert records[0].result_ref == "narrative-turn-registration"
    finally:
        await database.close()
