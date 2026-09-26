"""W-V09 durable pre-COMMIT turn intake and cancel-vs-commit tests."""
from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3 as stdlib_sqlite3

import pytest

from application.story_turn_commit import StoryTurnCommitService
from contracts import (
    BaseRevisions,
    InputMode,
    StateDelta,
    StorySession,
    StoryState,
    TurnStatus,
    TurnTransaction,
)
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.database_schema import StorageError
from infrastructure.sqlite_runtime import sqlite3
from infrastructure.story_session_repository import SQLiteStorySessionCommitPort
from application.turn_control import (
    TurnCancellationOutcome,
    TurnControlService,
)
from infrastructure.turn_intake_repository import (
    SQLitePendingTurnControlPort,
    SQLiteTurnIntakeRepository,
    TurnIntakeConflict,
    TurnIntakeRequest,
    TurnIntakeStatus,
)


async def open_database(tmp_path: Path):
    paths = DatabasePaths.for_world(tmp_path / "app-support", "world-intake")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    database = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    return database, paths


def base_revisions() -> BaseRevisions:
    return BaseRevisions(world=0, character=0, story=0)


def request(
    *,
    raw_input: str = "请调查那扇门。",
    public_expected_store_revision: int | None = None,
) -> TurnIntakeRequest:
    return TurnIntakeRequest(
        input_turn_id="input-turn-1",
        session_id="session-intake",
        turn_id="turn-intake-1",
        idempotency_key="input-turn:session-intake:input-turn-1",
        input_mode=InputMode.VOICE,
        raw_input=raw_input,
        base_revisions=base_revisions(),
        public_expected_store_revision=public_expected_store_revision,
    )


def session() -> StorySession:
    state = StoryState.model_validate(
        {
            "schema_version": "1.0",
            "story_session_id": "session-intake",
            "revision": 0,
            "turn": 0,
            "phase": "discovery",
            "scene": {
                "id": "scene-intake",
                "location_id": "room-intake",
                "active_character_ids": ["npc-1"],
            },
            "world_time": "1349-06-12T21:45:00",
            "protagonist_goal": "investigate",
            "active_conflicts": [],
            "discovered_clue_ids": [],
            "secret_states": {},
            "commitments": {"hard_ids": [], "soft_ids": []},
            "local_state": {},
            "pressure": {},
            "last_state_delta_id": None,
        }
    )
    return StorySession.model_validate(
        {
            "schema_version": "1.0",
            "id": "session-intake",
            "world_id": "world-intake",
            "worldline_id": "line-main",
            "protagonist_id": "player",
            "story_seed_id": "seed-intake",
            "base_revisions": base_revisions().model_dump(mode="json"),
            "story_state": state.model_dump(mode="json", exclude_none=True),
            "status": "active",
        }
    )


def delta() -> StateDelta:
    return StateDelta.model_validate(
        {
            "schema_version": "1.0",
            "id": "delta-intake-1",
            "turn_id": "turn-intake-1",
            "outcome": "clean_success",
            "story_delta": {},
            "character_deltas": [],
            "relationship_deltas": [],
            "knowledge_candidates": [],
            "world_event_candidates": [],
            "evidence_ids": [],
        }
    )


def validated_turn(value: StateDelta) -> TurnTransaction:
    return TurnTransaction.model_validate(
        {
            "schema_version": "1.0",
            "id": "turn-intake-1",
            "session_id": "session-intake",
            "idempotency_key": "input-turn:session-intake:input-turn-1",
            "status": "validated",
            "base_revisions": base_revisions().model_dump(mode="json"),
            "state_delta_id": value.id,
            "committed_story_revision": None,
            "narrative_block_id": None,
        }
    )


async def world_revision(database: DatabaseManager) -> int:
    return (
        await database.read_world(
            "SELECT revision FROM world_meta WHERE singleton=1"
        )
    )[0]["revision"]


async def commit_turn(database: DatabaseManager):
    value = delta()
    return await StoryTurnCommitService(
        SQLiteStorySessionCommitPort(database)
    ).commit_validated(
        session(),
        value,
        validated_turn(value),
        store_expected_revision=0,
        request_id="request-intake-commit",
        trace_id="trace-intake-commit",
    )


async def test_receive_is_durable_idempotent_and_does_not_advance_world(tmp_path):
    database, paths = await open_database(tmp_path)
    try:
        repo = SQLiteTurnIntakeRepository(database)
        first = await repo.receive(request())
        second = await repo.receive(request())

        assert not first.replayed
        assert second.replayed
        assert first.record == second.record
        assert first.record.status is TurnIntakeStatus.RECEIVED
        assert await world_revision(database) == 0
    finally:
        await database.close()

    reopened = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    try:
        recovered = await SQLiteTurnIntakeRepository(reopened).load("input-turn-1")
        assert recovered.status is TurnIntakeStatus.RECEIVED
        assert recovered.raw_input == "请调查那扇门。"
        assert await world_revision(reopened) == 0
    finally:
        await reopened.close()


async def test_same_input_turn_id_with_different_text_fails_closed(tmp_path):
    database, _ = await open_database(tmp_path)
    try:
        repo = SQLiteTurnIntakeRepository(database)
        await repo.receive(request())
        with pytest.raises(TurnIntakeConflict, match="different input"):
            await repo.receive(request(raw_input="篡改后的输入"))
        assert (await repo.load("input-turn-1")).raw_input == "请调查那扇门。"
    finally:
        await database.close()


async def test_public_expected_store_revision_survives_restart_and_identity_conflict(
    tmp_path,
):
    database, paths = await open_database(tmp_path)
    try:
        repo = SQLiteTurnIntakeRepository(database)
        first = await repo.receive(
            request(public_expected_store_revision=7)
        )
        assert first.record.public_expected_store_revision == 7
        with pytest.raises(TurnIntakeConflict, match="different input"):
            await repo.receive(
                request(public_expected_store_revision=8)
            )
    finally:
        await database.close()

    reopened = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    try:
        recovered = await SQLiteTurnIntakeRepository(reopened).load("input-turn-1")
        assert recovered.public_expected_store_revision == 7
    finally:
        await reopened.close()


async def test_cancel_before_commit_wins_without_world_revision(tmp_path):
    database, _ = await open_database(tmp_path)
    try:
        repo = SQLiteTurnIntakeRepository(database)
        await repo.receive(request())
        cancelled = await repo.cancel("input-turn-1")
        assert cancelled.status is TurnIntakeStatus.CANCELLED
        assert await world_revision(database) == 0

        with pytest.raises(StorageError, match="cancelled before COMMIT"):
            await commit_turn(database)
        assert await world_revision(database) == 0
        assert (await repo.load("input-turn-1")).status is TurnIntakeStatus.CANCELLED
    finally:
        await database.close()


async def test_commit_promotes_intake_atomically_and_lost_ack_is_queryable(tmp_path):
    database, paths = await open_database(tmp_path)
    try:
        repo = SQLiteTurnIntakeRepository(database)
        await repo.receive(request())
        committed = await commit_turn(database)

        intake = await repo.load("input-turn-1")
        assert committed.turn.status is TurnStatus.COMMITTED
        assert intake.status is TurnIntakeStatus.COMMITTED
        assert intake.committed_world_revision == committed.store_revision == 1
        assert await world_revision(database) == 1
        with pytest.raises(TurnIntakeConflict, match="cannot be cancelled"):
            await repo.cancel("input-turn-1")
    finally:
        await database.close()

    reopened = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    try:
        intake = await SQLiteTurnIntakeRepository(reopened).load("input-turn-1")
        turn = await SQLiteStorySessionCommitPort(reopened).load_turn(intake.turn_id)
        assert intake.status is TurnIntakeStatus.COMMITTED
        assert turn.status is TurnStatus.COMMITTED
        assert turn.idempotency_key == intake.idempotency_key
    finally:
        await reopened.close()


async def test_cancel_and_commit_are_serialized_by_one_writer(tmp_path):
    database, _ = await open_database(tmp_path)
    try:
        repo = SQLiteTurnIntakeRepository(database)
        await repo.receive(request())

        async def cancel():
            try:
                return ("cancel", await repo.cancel("input-turn-1"))
            except Exception as exc:
                return ("cancel_error", exc)

        async def commit():
            try:
                return ("commit", await commit_turn(database))
            except Exception as exc:
                return ("commit_error", exc)

        results = await asyncio.gather(cancel(), commit())
        intake = await repo.load("input-turn-1")
        revision = await world_revision(database)

        if intake.status is TurnIntakeStatus.CANCELLED:
            assert revision == 0
            assert any(name == "cancel" for name, _ in results)
            assert any(
                name == "commit_error" and "cancelled before COMMIT" in str(value)
                for name, value in results
            )
        else:
            assert intake.status is TurnIntakeStatus.COMMITTED
            assert revision == 1
            assert any(name == "commit" for name, _ in results)
            assert any(
                name == "cancel_error" and isinstance(value, TurnIntakeConflict)
                for name, value in results
            )
    finally:
        await database.close()


async def test_turn_command_transaction_has_no_world_fact_authority(tmp_path):
    database, _ = await open_database(tmp_path)
    try:
        with pytest.raises(Exception):
            await database.turn_command_write(
                lambda tx: tx.execute("UPDATE world_meta SET revision=99")
            )
        with pytest.raises(Exception):
            await database.turn_command_write(
                lambda tx: tx.execute(
                    "INSERT INTO domain_events(event_id,revision,worldline_id,world_time,"
                    "aggregate_id,event_type,cause_id,episode_id,turn_id,payload_json) "
                    "VALUES ('e',1,'l','t','a','x',NULL,NULL,NULL,'{}')"
                )
            )
        assert await world_revision(database) == 0
    finally:
        await database.close()


async def test_cancel_pending_wins_before_commit_without_world_revision(tmp_path):
    database, _ = await open_database(tmp_path)
    try:
        repo = SQLiteTurnIntakeRepository(database)
        await repo.receive(request())

        cancellation = await repo.cancel_pending("turn-intake-1", 0)

        assert cancellation.outcome is TurnCancellationOutcome.CANCELLED_BEFORE_COMMIT
        assert cancellation.replayed is False
        assert cancellation.record is not None
        assert cancellation.record.status is TurnIntakeStatus.CANCELLED
        assert cancellation.record.committed_world_revision is None
        assert await world_revision(database) == 0
        with pytest.raises(StorageError, match="cancelled before COMMIT"):
            await commit_turn(database)
        assert await world_revision(database) == 0

        # 取消的 lost ACK 重放必须幂等：不重复释放，也不推进世界
        replayed = await repo.cancel_pending("turn-intake-1", 0)
        assert replayed.outcome is TurnCancellationOutcome.CANCELLED_BEFORE_COMMIT
        assert replayed.replayed is True
        assert await world_revision(database) == 0
    finally:
        await database.close()


async def test_cancel_pending_after_commit_reports_revision_and_keeps_commit(tmp_path):
    database, _ = await open_database(tmp_path)
    try:
        repo = SQLiteTurnIntakeRepository(database)
        await repo.receive(request())
        committed = await commit_turn(database)

        cancellation = await repo.cancel_pending("turn-intake-1", 0)

        assert cancellation.outcome is TurnCancellationOutcome.ALREADY_COMMITTED
        assert cancellation.record is not None
        assert cancellation.record.status is TurnIntakeStatus.COMMITTED
        assert (
            cancellation.record.committed_world_revision
            == committed.store_revision
            == 1
        )
        assert cancellation.record.input_turn_id == "input-turn-1"
        assert await world_revision(database) == 1
        assert (await repo.load("input-turn-1")).status is TurnIntakeStatus.COMMITTED
    finally:
        await database.close()


async def test_cancel_pending_refuses_a_stale_expected_revision(tmp_path):
    database, _ = await open_database(tmp_path)
    try:
        repo = SQLiteTurnIntakeRepository(database)
        await repo.receive(request())

        cancellation = await repo.cancel_pending("turn-intake-1", 7)

        assert cancellation.outcome is TurnCancellationOutcome.STALE_REVISION
        assert cancellation.record is not None
        assert cancellation.record.status is TurnIntakeStatus.RECEIVED
        assert cancellation.record.committed_world_revision is None
        # 拒绝取消后该回合仍然可以正常提交
        committed = await commit_turn(database)
        assert committed.store_revision == 1
        assert await world_revision(database) == 1
    finally:
        await database.close()


async def test_cancel_pending_reports_unknown_turn_without_state_change(tmp_path):
    database, _ = await open_database(tmp_path)
    try:
        repo = SQLiteTurnIntakeRepository(database)
        await repo.receive(request())

        cancellation = await repo.cancel_pending("turn-missing", 0)

        assert cancellation.outcome is TurnCancellationOutcome.NOT_FOUND
        assert cancellation.record is None
        assert (await repo.load("input-turn-1")).status is TurnIntakeStatus.RECEIVED
        assert await world_revision(database) == 0
    finally:
        await database.close()


async def test_pending_turn_control_port_answers_through_the_control_service(tmp_path):
    database, _ = await open_database(tmp_path)
    try:
        await SQLiteTurnIntakeRepository(database).receive(request())
        port = SQLitePendingTurnControlPort(database)
        service = TurnControlService(turns=port)

        cancelled = await service.cancel_pending(
            "turn-intake-1",
            expected_revision=0,
            request_id="request-cancel",
            trace_id="trace-cancel",
        )
        assert cancelled.outcome is TurnCancellationOutcome.CANCELLED_BEFORE_COMMIT
        assert cancelled.input_turn_id == "input-turn-1"
        assert cancelled.session_id == "session-intake"
        assert cancelled.committed_world_revision is None
        assert cancelled.replayed is False

        replayed = await service.cancel_pending(
            "turn-intake-1",
            expected_revision=0,
            request_id="request-cancel",
            trace_id="trace-cancel",
        )
        assert replayed.outcome is TurnCancellationOutcome.CANCELLED_BEFORE_COMMIT
        assert replayed.replayed is True

        missing = await service.cancel_pending(
            "turn-missing",
            expected_revision=0,
            request_id="request-missing",
            trace_id="trace-missing",
        )
        assert missing.outcome is TurnCancellationOutcome.NOT_FOUND
        assert missing.input_turn_id is None
        assert missing.session_id is None
    finally:
        await database.close()


async def test_cancel_pending_race_reports_one_typed_outcome(tmp_path):
    database, _ = await open_database(tmp_path)
    try:
        repo = SQLiteTurnIntakeRepository(database)
        await repo.receive(request())

        async def cancel():
            try:
                return ("cancel", await repo.cancel_pending("turn-intake-1", 0))
            except Exception as exc:
                return ("cancel_error", exc)

        async def commit():
            try:
                return ("commit", await commit_turn(database))
            except Exception as exc:
                return ("commit_error", exc)

        results = await asyncio.gather(cancel(), commit())
        outcomes = [value.outcome for name, value in results if name == "cancel"]
        assert len(outcomes) == 1
        outcome = outcomes[0]
        revision = await world_revision(database)
        intake = await repo.load("input-turn-1")

        if outcome is TurnCancellationOutcome.CANCELLED_BEFORE_COMMIT:
            assert revision == 0
            assert intake.status is TurnIntakeStatus.CANCELLED
            assert any(name == "commit" for name, _ in results) is False
            assert any(
                name == "commit_error" and "cancelled before COMMIT" in str(value)
                for name, value in results
            )
        else:
            assert outcome is TurnCancellationOutcome.ALREADY_COMMITTED
            assert revision == 1
            assert intake.status is TurnIntakeStatus.COMMITTED
            assert intake.committed_world_revision == 1
            assert any(name == "commit" for name, _ in results)
    finally:
        await database.close()
