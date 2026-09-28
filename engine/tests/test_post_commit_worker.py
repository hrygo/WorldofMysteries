"""Crash recovery and bounded execution tests for post-COMMIT work."""

from __future__ import annotations

import asyncio
import sqlite3 as stdlib_sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from engine.infrastructure.database_manager import (
    DatabaseManager,
    DatabasePaths,
    StorageError,
)
from engine.infrastructure.post_commit_job_repository import (
    PostCommitJobSpec,
    PostCommitLeaseConflict,
    SQLitePostCommitJobRepository,
)
from engine.infrastructure.post_commit_worker import (
    MAX_WORKER_CONCURRENCY,
    PostCommitHandlerError,
    PostCommitJobLeaseConflict,
    PostCommitWorker,
)
from engine.infrastructure.sqlite_runtime import sqlite3

from application.post_commit_work import (
    PostCommitErrorKind,
    PostCommitKind,
    PostCommitResult,
    PostCommitResultState,
)


class _SimulatedProcessCrash(BaseException):
    """Leave a durable artifact and running lease as a dead process would."""


class _ArtifactHandler:
    def __init__(
        self,
        *,
        kind: PostCommitKind,
        artifacts: dict[tuple[PostCommitKind, str], str] | None = None,
        started: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
        failures: list[BaseException] | None = None,
        crash_after_first_write: bool = False,
    ) -> None:
        self.kind = kind
        self.artifacts = artifacts if artifacts is not None else {}
        self.started = started
        self.release = release
        self.failures = failures if failures is not None else []
        self.crash_after_first_write = crash_after_first_write
        self.write_count = 0
        self.calls: list[str] = []
        self.finished = asyncio.Event()

    async def execute(self, source) -> PostCommitResult:
        self.calls.append(source.turn_id)
        key = (self.kind, source.turn_id)
        existing = self.artifacts.get(key)
        if existing is not None:
            self.finished.set()
            return PostCommitResult(
                state=PostCommitResultState.SUCCEEDED,
                result_ref=existing,
            )

        if self.failures:
            raise self.failures.pop(0)

        if self.started is not None:
            self.started.set()
        if self.release is not None:
            await self.release.wait()

        result_ref = f"{self.kind.value}:{source.turn_id}"
        self.artifacts[key] = result_ref
        self.write_count += 1
        if self.crash_after_first_write:
            self.crash_after_first_write = False
            raise _SimulatedProcessCrash
        self.finished.set()
        return PostCommitResult(
            state=PostCommitResultState.SUCCEEDED,
            result_ref=result_ref,
        )


class _ConcurrentArtifactHandler(_ArtifactHandler):
    def __init__(self, *, kind: PostCommitKind, target: int) -> None:
        super().__init__(kind=kind)
        self.target = target
        self.active = 0
        self.peak_active = 0
        self.all_started = asyncio.Event()
        self.release_all = asyncio.Event()

    async def execute(self, source) -> PostCommitResult:
        self.calls.append(source.turn_id)
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)
        if self.active >= self.target:
            self.all_started.set()
        await self.release_all.wait()
        self.active -= 1
        result_ref = f"{self.kind.value}:{source.turn_id}"
        self.artifacts[(self.kind, source.turn_id)] = result_ref
        self.write_count += 1
        return PostCommitResult(
            state=PostCommitResultState.SUCCEEDED,
            result_ref=result_ref,
        )


def _job(
    *,
    job_id: str,
    turn_id: str = "turn-1",
    session_id: str = "session-1",
    kind: PostCommitKind = PostCommitKind.NARRATIVE_PUBLISH,
    source_story_revision: int = 1,
    source_world_revision: int = 1,
) -> PostCommitJobSpec:
    return PostCommitJobSpec(
        job_id=job_id,
        turn_id=turn_id,
        session_id=session_id,
        kind=kind.value,
        recipe_revision=f"{kind.value}-test-v1",
        source_story_revision=source_story_revision,
        source_world_revision=source_world_revision,
        input_digest="a" * 64,
    )


async def _open_database(tmp_path: Path) -> DatabaseManager:
    paths = DatabasePaths.for_world(tmp_path / "app-support", "post-commit-worker")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    return await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )


def _seed_source_rows(connection, sources: tuple[tuple[str, str, int], ...]) -> None:
    """Create committed source turns at the existing fixture world revision."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        for session_id, turn_id, story_revision in sources:
            if session_id != "session-1":
                connection.execute(
                    "INSERT OR IGNORE INTO story_sessions("
                    "id,world_id,worldline_id,protagonist_id,story_seed_id,"
                    "base_world_revision,base_character_revision,base_story_revision,"
                    "story_revision,status,story_state_json,committed_world_revision"
                    ") VALUES (?, 'world-test',?,'player-test','seed-test',"
                    "0,0,0,?,'active','{}',1)",
                    (session_id, f"line-{session_id}", story_revision),
                )
            delta_id = f"delta-{turn_id}"
            connection.execute(
                "INSERT INTO story_state_deltas("
                "id,session_id,turn_id,story_revision,payload_json,"
                "committed_world_revision"
                ") VALUES (?,?,?,?,?,1)",
                (delta_id, session_id, turn_id, story_revision, "{}"),
            )
            existing_turn = connection.execute(
                "SELECT id FROM turn_transactions WHERE id=?", (turn_id,)
            ).fetchone()
            if existing_turn is None:
                connection.execute(
                    "INSERT INTO turn_transactions("
                    "id,session_id,idempotency_key,status,base_world_revision,"
                    "base_character_revision,base_story_revision,state_delta_id,"
                    "committed_story_revision,transaction_json,committed_world_revision"
                    ") VALUES (?,?,?,'committed',0,0,0,?,?,'{}',1)",
                    (
                        turn_id,
                        session_id,
                        f"idempotency-{turn_id}",
                        delta_id,
                        story_revision,
                    ),
                )
            else:
                connection.execute(
                    "UPDATE turn_transactions SET state_delta_id=?,"
                    "committed_story_revision=? WHERE id=?",
                    (delta_id, story_revision, turn_id),
                )
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")


async def _seed_database(
    database: DatabaseManager,
    sources: tuple[tuple[str, str, int], ...] = (("session-1", "turn-1", 1),),
) -> None:
    await database._submit(lambda: _seed_committed_world(database._connection))
    await database._submit(lambda: _seed_source_rows(database._connection, sources))


def _seed_committed_world(connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    if connection.execute("SELECT 1 FROM domain_commits WHERE revision=1").fetchone() is None:
        connection.execute(
            "INSERT INTO domain_commits("
            "revision,worldline_id,idempotency_key,request_digest,request_id,"
            "trace_id,world_time,commit_time,operation_json,result_json"
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
        connection.execute("INSERT INTO projection_outbox(revision,processed) VALUES (1,0)")
        connection.execute("UPDATE world_meta SET revision=1 WHERE singleton=1")
        connection.execute(
            "INSERT INTO story_sessions("
            "id,world_id,worldline_id,protagonist_id,story_seed_id,"
            "base_world_revision,base_character_revision,base_story_revision,"
            "story_revision,status,story_state_json,committed_world_revision"
            ") VALUES ('session-1','world-test','line-test','player-test','seed-test',"
            "0,0,0,1,'active','{}',1)"
        )
        connection.execute(
            "INSERT INTO turn_transactions("
            "id,session_id,idempotency_key,status,base_world_revision,"
            "base_character_revision,base_story_revision,transaction_json,"
            "committed_world_revision"
            ") VALUES ('turn-1','session-1','idempotency-turn-1','committed',"
            "0,0,0,'{}',1)"
        )
    connection.execute("COMMIT")


async def _register(
    repository: SQLitePostCommitJobRepository,
    database: DatabaseManager,
    *jobs: PostCommitJobSpec,
) -> None:
    await database.post_commit_job_write(lambda tx: repository.register(tx, jobs))


def _worker(
    database: DatabaseManager,
    repository: SQLitePostCommitJobRepository,
    *,
    narrative_handler: _ArtifactHandler | None = None,
    episode_handler: _ArtifactHandler | None = None,
    audio_handler: _ArtifactHandler | None = None,
    max_concurrency: int = 1,
) -> PostCommitWorker:
    return PostCommitWorker(
        database=database,
        repository=repository,
        narrative_handler=narrative_handler
        or _ArtifactHandler(kind=PostCommitKind.NARRATIVE_PUBLISH),
        episode_finalize_handler=episode_handler
        or _ArtifactHandler(kind=PostCommitKind.EPISODE_FINALIZE),
        audio_prepare_handler=audio_handler or _ArtifactHandler(kind=PostCommitKind.AUDIO_PREPARE),
        supported_recipes={
            PostCommitKind.NARRATIVE_PUBLISH.value: {"narrative_publish-test-v1"},
            PostCommitKind.EPISODE_FINALIZE.value: {"episode_finalize-test-v1"},
            PostCommitKind.AUDIO_PREPARE.value: {"audio_prepare-test-v1"},
        },
        max_concurrency=max_concurrency,
        lease_owner="worker-test",
    )


async def _job_row(database: DatabaseManager, job_id: str) -> dict:
    rows = await database.read_world(
        "SELECT state,attempt,lease_owner,lease_generation,next_attempt_at,"
        "last_error_code,result_ref FROM post_commit_jobs WHERE job_id=?",
        (job_id,),
    )
    assert len(rows) == 1
    return rows[0]


@pytest.mark.parametrize(
    "kind",
    (
        PostCommitKind.NARRATIVE_PUBLISH,
        PostCommitKind.EPISODE_FINALIZE,
    ),
)
async def test_worker_recovers_existing_artifact_without_duplicate_publication_or_settlement(
    tmp_path: Path,
    kind: PostCommitKind,
) -> None:
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    artifacts: dict[tuple[PostCommitKind, str], str] = {}
    handler = _ArtifactHandler(
        kind=kind,
        artifacts=artifacts,
        crash_after_first_write=True,
    )
    try:
        await _seed_database(database)
        job_id = f"crash-{kind.value}"
        await _register(
            repository,
            database,
            _job(job_id=job_id, kind=kind),
        )
        handlers = (
            {"narrative_handler": handler}
            if kind is PostCommitKind.NARRATIVE_PUBLISH
            else {"episode_handler": handler}
        )
        worker = _worker(database, repository, **handlers)
        with pytest.raises(_SimulatedProcessCrash):
            await worker.run_once(now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC))
        assert (await _job_row(database, job_id))["state"] == "running"
        assert handler.write_count == 1
        paths = database.paths
    finally:
        await database.close()

    reopened = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    try:
        resumed_repository = SQLitePostCommitJobRepository(reopened)
        resumed_worker = _worker(reopened, resumed_repository, **handlers)
        await resumed_worker.run_once(now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC))
        assert handler.calls == ["turn-1", "turn-1"]
        assert handler.write_count == 1
        result_ref = f"{kind.value}:turn-1"
        assert artifacts[(kind, "turn-1")] == result_ref
        assert await _job_row(reopened, job_id) == {
            "state": "succeeded",
            "attempt": 2,
            "lease_owner": None,
            "lease_generation": 2,
            "next_attempt_at": None,
            "last_error_code": None,
            "result_ref": result_ref,
        }
    finally:
        await reopened.close()


async def test_worker_claims_in_source_order_and_world_writer_lease_is_exclusive(
    tmp_path: Path,
) -> None:
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    handler = _ArtifactHandler(kind=PostCommitKind.NARRATIVE_PUBLISH)
    try:
        await _seed_database(
            database,
            (
                ("session-1", "turn-1", 1),
                ("session-1", "turn-2", 2),
            ),
        )
        await _register(
            repository,
            database,
            _job(job_id="later", turn_id="turn-2", source_story_revision=2),
            _job(job_id="earlier", turn_id="turn-1", source_story_revision=1),
        )
        with pytest.raises(StorageError, match="Another Domain Writer"):
            await DatabaseManager.open(
                database.paths,
                expected_sqlite_version=sqlite3.sqlite_version,
            )

        assert (
            await _worker(
                database,
                repository,
                narrative_handler=handler,
            ).run_once(now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC))
            == 2
        )
        assert handler.calls == ["turn-1", "turn-2"]
    finally:
        await database.close()


async def test_worker_ack_failure_and_completion_require_current_owner_generation(
    tmp_path: Path,
) -> None:
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        await _seed_database(database)
        await _register(
            repository,
            database,
            _job(job_id="lease-narrative"),
            _job(
                job_id="lease-episode",
                kind=PostCommitKind.EPISODE_FINALIZE,
            ),
        )
        first = await repository.claim(
            session_id="session-1",
            lease_owner="worker-1",
            supported_recipes={
                PostCommitKind.NARRATIVE_PUBLISH.value: {"narrative_publish-test-v1"},
                PostCommitKind.EPISODE_FINALIZE.value: {"episode_finalize-test-v1"},
            },
            now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
        second = await repository.claim(
            session_id="session-1",
            lease_owner="worker-1",
            supported_recipes={
                PostCommitKind.NARRATIVE_PUBLISH.value: {"narrative_publish-test-v1"},
                PostCommitKind.EPISODE_FINALIZE.value: {"episode_finalize-test-v1"},
            },
            now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
        assert first is not None and second is not None

        with pytest.raises(PostCommitJobLeaseConflict):
            await repository.complete(
                first.job_id,
                lease_owner="other-owner",
                lease_generation=first.lease_generation,
                result_ref="wrong-owner",
            )
        with pytest.raises(PostCommitJobLeaseConflict):
            await repository.complete(
                first.job_id,
                lease_owner=first.lease_owner,
                lease_generation=first.lease_generation + 1,
                result_ref="wrong-generation",
            )
        with pytest.raises(PostCommitJobLeaseConflict):
            await repository.fail(
                second.job_id,
                lease_owner="other-owner",
                lease_generation=second.lease_generation,
                error_code="temporary_network_failure",
                retryable=True,
            )
        with pytest.raises(PostCommitJobLeaseConflict):
            await repository.fail(
                second.job_id,
                lease_owner=second.lease_owner,
                lease_generation=second.lease_generation + 1,
                error_code="temporary_network_failure",
                retryable=True,
            )
        assert PostCommitLeaseConflict is PostCommitJobLeaseConflict
    finally:
        await database.close()


async def test_worker_applies_bounded_transient_retry_delays_and_blocks_after_three(
    tmp_path: Path,
) -> None:
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    handler = _ArtifactHandler(
        kind=PostCommitKind.NARRATIVE_PUBLISH,
        failures=[
            ConnectionError("temporary provider outage"),
            TimeoutError("temporary provider timeout"),
            ConnectionError("temporary provider outage"),
            TimeoutError("temporary provider timeout"),
        ],
    )
    try:
        await _seed_database(database)
        await _register(repository, database, _job(job_id="retry-job"))
        worker = _worker(database, repository, narrative_handler=handler)
        now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
        for attempt, delay in enumerate((1, 5, 30), start=1):
            assert await worker.run_once(now=now) == 1
            record = await _job_row(database, "retry-job")
            expected_next = now + timedelta(seconds=delay)
            assert record["state"] == "retry_wait"
            assert record["attempt"] == attempt
            assert record["next_attempt_at"] == (
                expected_next.isoformat(timespec="microseconds").replace("+00:00", "Z")
            )
            now = expected_next

        assert await worker.run_once(now=now) == 1
        blocked = await _job_row(database, "retry-job")
        assert blocked["state"] == "blocked"
        assert blocked["attempt"] == 4
        assert blocked["next_attempt_at"] is None
    finally:
        await database.close()


@pytest.mark.parametrize(
    "kind",
    (
        PostCommitErrorKind.CONFIGURATION,
        PostCommitErrorKind.PERMISSION,
        PostCommitErrorKind.IDENTITY,
    ),
)
async def test_worker_blocks_configuration_permission_and_identity_errors(
    tmp_path: Path,
    kind: PostCommitErrorKind,
) -> None:
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    handler = _ArtifactHandler(
        kind=PostCommitKind.NARRATIVE_PUBLISH,
        failures=[
            PostCommitHandlerError(
                kind=kind,
                reason_code=f"{kind.value}_failed",
            )
        ],
    )
    try:
        await _seed_database(database)
        await _register(repository, database, _job(job_id="blocked-job"))
        assert (
            await _worker(
                database,
                repository,
                narrative_handler=handler,
            ).run_once(now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC))
            == 1
        )
        row = await _job_row(database, "blocked-job")
        assert row["state"] == "blocked"
        assert row["attempt"] == 1
        assert row["next_attempt_at"] is None
        assert row["last_error_code"] == f"{kind.value}_failed"
    finally:
        await database.close()


async def test_audio_is_not_claimed_until_its_matching_narrative_exists(
    tmp_path: Path,
) -> None:
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    audio = _ArtifactHandler(kind=PostCommitKind.AUDIO_PREPARE)
    try:
        await _seed_database(database)
        await _register(
            repository,
            database,
            _job(
                job_id="audio-waits",
                kind=PostCommitKind.AUDIO_PREPARE,
            ),
        )
        worker = _worker(database, repository, audio_handler=audio)
        now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
        assert await worker.run_once(now=now) == 0
        assert audio.calls == []
        assert (await _job_row(database, "audio-waits"))["state"] == "pending"

        await database.post_commit_write(
            lambda tx: tx.execute(
                "INSERT INTO narrative_blocks("
                "id,turn_id,session_id,source_story_revision,source_world_revision,"
                "source_state_delta_id,payload_json"
                ") VALUES (?,?,?,?,?,?,?)",
                (
                    "narrative-ready",
                    "turn-1",
                    "session-1",
                    1,
                    1,
                    "delta-turn-1",
                    "{}",
                ),
            )
        )
        assert await worker.run_once(now=now) == 1
        assert audio.calls == ["turn-1"]
        assert (await _job_row(database, "audio-waits"))["state"] == "succeeded"
    finally:
        await database.close()


async def test_handler_await_occurs_after_sqlite_claim_transaction_commits(
    tmp_path: Path,
) -> None:
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    started = asyncio.Event()
    release = asyncio.Event()
    handler = _ArtifactHandler(
        kind=PostCommitKind.NARRATIVE_PUBLISH,
        started=started,
        release=release,
    )
    try:
        await _seed_database(database)
        await _register(repository, database, _job(job_id="barrier-job"))
        worker_task = asyncio.create_task(
            _worker(
                database,
                repository,
                narrative_handler=handler,
            ).run_once(now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC))
        )
        await started.wait()
        callback_entered = asyncio.Event()
        loop = asyncio.get_running_loop()

        def independent_job_write(tx) -> None:
            tx.execute(
                "UPDATE post_commit_jobs SET last_error_code='barrier_probe' "
                "WHERE job_id='barrier-job'"
            )
            loop.call_soon_threadsafe(callback_entered.set)

        write_task = asyncio.create_task(database.post_commit_job_write(independent_job_write))
        await callback_entered.wait()
        await write_task
        release.set()
        assert await worker_task == 1
        assert (await _job_row(database, "barrier-job"))["state"] == "succeeded"
    finally:
        release.set()
        await database.close()


async def test_stop_stops_claiming_then_drains_inflight_before_database_close(
    tmp_path: Path,
) -> None:
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    started = asyncio.Event()
    release = asyncio.Event()
    handler = _ArtifactHandler(
        kind=PostCommitKind.NARRATIVE_PUBLISH,
        started=started,
        release=release,
    )
    try:
        await _seed_database(
            database,
            (
                ("session-1", "turn-1", 1),
                ("session-1", "turn-2", 2),
            ),
        )
        await _register(
            repository,
            database,
            _job(job_id="inflight", turn_id="turn-1"),
            _job(
                job_id="must-remain-pending",
                turn_id="turn-2",
                source_story_revision=2,
            ),
        )
        worker = _worker(
            database,
            repository,
            narrative_handler=handler,
        )
        await worker.start()
        await started.wait()

        async def release_after_shutdown_begins() -> None:
            await worker._stop_event.wait()
            assert not handler.finished.is_set()
            release.set()

        release_task = asyncio.create_task(release_after_shutdown_begins())
        await worker.stop()
        await release_task
        assert handler.calls == ["turn-1"]
        assert (await _job_row(database, "inflight"))["state"] == "succeeded"
        assert (await _job_row(database, "must-remain-pending"))["state"] == ("pending")
    finally:
        release.set()
        await database.close()


async def test_worker_ack_does_not_advance_world_revision(tmp_path: Path) -> None:
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    try:
        await _seed_database(database)
        await _register(repository, database, _job(job_id="revision-job"))
        before = await database.read_world("SELECT revision FROM world_meta WHERE singleton=1")
        await _worker(database, repository).run_once(now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC))
        after = await database.read_world("SELECT revision FROM world_meta WHERE singleton=1")
        assert before == after == [{"revision": 1}]
    finally:
        await database.close()


async def test_worker_defaults_to_one_concurrent_job_and_caps_configuration(
    tmp_path: Path,
) -> None:
    database = await _open_database(tmp_path)
    repository = SQLitePostCommitJobRepository(database)
    handler = _ConcurrentArtifactHandler(
        kind=PostCommitKind.NARRATIVE_PUBLISH,
        target=2,
    )
    try:
        await _seed_database(
            database,
            (
                ("session-1", "turn-1", 1),
                ("session-2", "turn-2", 1),
            ),
        )
        await _register(
            repository,
            database,
            _job(job_id="session-1-job", turn_id="turn-1"),
            _job(
                job_id="session-2-job",
                turn_id="turn-2",
                session_id="session-2",
            ),
        )
        default_worker = _worker(database, repository, narrative_handler=handler)
        assert default_worker.max_concurrency == 1
        configured = _worker(
            database,
            repository,
            narrative_handler=handler,
            max_concurrency=2,
        )
        run_task = asyncio.create_task(
            configured.run_once(now=datetime(2026, 9, 28, 12, 0, tzinfo=UTC))
        )
        await handler.all_started.wait()
        assert handler.peak_active == 2
        handler.release_all.set()
        assert await run_task == 2
        assert MAX_WORKER_CONCURRENCY >= 2
        with pytest.raises(ValueError, match="max_concurrency"):
            _worker(
                database,
                repository,
                max_concurrency=MAX_WORKER_CONCURRENCY + 1,
            )
    finally:
        handler.release_all.set()
        await database.close()
