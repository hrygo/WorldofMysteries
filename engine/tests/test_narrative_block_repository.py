"""W-V05 durable post-COMMIT NarrativeBlock publication tests."""
from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3 as stdlib_sqlite3
import threading

import pytest

from application.story_turn_commit import StoryTurnCommitService
from contracts import NarrativeBlock, StateDelta, StorySession, StoryState, TurnStatus, TurnTransaction
from infrastructure.database_manager import DatabaseManager, DatabasePaths, StorageError
from infrastructure.narrative_block_repository import SQLiteNarrativeBlockRepository
from infrastructure.sqlite_runtime import sqlite3
from infrastructure.story_session_repository import SQLiteStorySessionCommitPort


async def _open_database(tmp_path: Path) -> tuple[DatabaseManager, DatabasePaths]:
    paths = DatabasePaths.for_world(tmp_path / "app-support", "world-voice")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    database = await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )
    return database, paths


def _initial_session() -> StorySession:
    state = StoryState.model_validate(
        {
            "schema_version": "1.0",
            "story_session_id": "session-voice",
            "revision": 0,
            "turn": 0,
            "phase": "discovery",
            "scene": {"id": "scene-1", "location_id": "room-1", "active_character_ids": ["npc-1"]},
            "world_time": "1349-06-12T21:45:00",
            "protagonist_goal": "listen",
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
            "id": "session-voice",
            "world_id": "world-voice",
            "worldline_id": "line-main",
            "protagonist_id": "player",
            "story_seed_id": "seed-voice",
            "base_revisions": {"world": 0, "character": 0, "story": 0},
            "story_state": state.model_dump(mode="json", exclude_none=True),
            "status": "active",
        }
    )


def _delta() -> StateDelta:
    return StateDelta.model_validate(
        {
            "schema_version": "1.0",
            "id": "delta-voice-1",
            "turn_id": "turn-voice-1",
            "outcome": "clean_success",
            "story_delta": {},
            "character_deltas": [],
            "world_event_candidates": [],
            "evidence_ids": [],
        }
    )


def _validated_turn(delta: StateDelta) -> TurnTransaction:
    return TurnTransaction.model_validate(
        {
            "schema_version": "1.0",
            "id": "turn-voice-1",
            "session_id": "session-voice",
            "idempotency_key": "voice.turn.1",
            "status": "validated",
            "base_revisions": {"world": 0, "character": 0, "story": 0},
            "state_delta_id": delta.id,
            "committed_story_revision": None,
            "narrative_block_id": None,
        }
    )


def _narrative(*, block_id: str = "narrative-voice-1", revision: int = 1,
               session_id: str = "session-voice", delta_id: str = "delta-voice-1") -> NarrativeBlock:
    return NarrativeBlock.model_validate(
        {
            "schema_version": "1.0",
            "id": block_id,
            "story_session_id": session_id,
            "source_story_revision": revision,
            "scene_id": "scene-1",
            "segments": [
                {
                    "type": "character",
                    "speaker_id": "npc-1",
                    "text": "不要打开那扇门。",
                    "speech_intent": "warning",
                }
            ],
            "source_state_delta_id": delta_id,
        }
    )


async def _commit_turn(database: DatabaseManager) -> TurnTransaction:
    delta = _delta()
    result = await StoryTurnCommitService(SQLiteStorySessionCommitPort(database)).commit_validated(
        _initial_session(),
        delta,
        _validated_turn(delta),
        store_expected_revision=0,
        request_id="request.voice.1",
        trace_id="trace.voice.1",
    )
    assert result.turn.status is TurnStatus.COMMITTED
    return result.turn


async def _world_revision(database: DatabaseManager) -> int:
    return (await database.read_world("SELECT revision FROM world_meta WHERE singleton=1"))[0]["revision"]


async def test_publish_narrative_is_durable_atomic_and_does_not_advance_world_revision(tmp_path):
    database, paths = await _open_database(tmp_path)
    try:
        committed = await _commit_turn(database)
        assert await _world_revision(database) == 1
        before_commits = await database.read_world("SELECT count(*) AS n FROM domain_commits")

        repo = SQLiteNarrativeBlockRepository(database)
        published = await repo.publish(turn_id=committed.id, narrative=_narrative())

        assert not published.replayed
        assert published.turn.status is TurnStatus.NARRATIVE_READY
        assert published.turn.narrative_block_id == "narrative-voice-1"
        assert published.narrative == _narrative()
        assert await _world_revision(database) == 1
        assert await database.read_world("SELECT count(*) AS n FROM domain_commits") == before_commits
        narrative_rows = await database.read_world(
            "SELECT source_world_revision,source_story_revision FROM narrative_blocks"
        )
        assert narrative_rows == [{"source_world_revision": 1, "source_story_revision": 1}]
    finally:
        await database.close()

    reopened = await DatabaseManager.open(paths, expected_sqlite_version=sqlite3.sqlite_version)
    try:
        repo = SQLiteNarrativeBlockRepository(reopened)
        assert (await repo.load_turn("turn-voice-1")).status is TurnStatus.NARRATIVE_READY
        assert await repo.load_narrative_block("narrative-voice-1") == _narrative()
        replay = await repo.publish(turn_id="turn-voice-1", narrative=_narrative())
        assert replay.replayed
        assert await _world_revision(reopened) == 1
        assert (await reopened.read_world("SELECT count(*) AS n FROM domain_commits"))[0]["n"] == 1
    finally:
        await reopened.close()


@pytest.mark.parametrize(
    "narrative,match",
    [
        (_narrative(revision=2), "story revision"),
        (_narrative(session_id="other-session"), "another StorySession"),
        (_narrative(delta_id="other-delta"), "StateDelta"),
    ],
)
async def test_publish_narrative_rejects_mismatched_committed_identity(tmp_path, narrative, match):
    database, _ = await _open_database(tmp_path)
    try:
        await _commit_turn(database)
        repo = SQLiteNarrativeBlockRepository(database)
        with pytest.raises(StorageError, match=match):
            await repo.publish(turn_id="turn-voice-1", narrative=narrative)
        assert await database.read_world("SELECT * FROM narrative_blocks") == []
        assert (await repo.load_turn("turn-voice-1")).status is TurnStatus.COMMITTED
        assert await _world_revision(database) == 1
    finally:
        await database.close()


async def test_publish_narrative_rejects_conflicting_second_block(tmp_path):
    database, _ = await _open_database(tmp_path)
    try:
        await _commit_turn(database)
        repo = SQLiteNarrativeBlockRepository(database)
        await repo.publish(turn_id="turn-voice-1", narrative=_narrative())
        with pytest.raises(StorageError, match="different NarrativeBlock"):
            await repo.publish(
                turn_id="turn-voice-1",
                narrative=_narrative(block_id="narrative-other"),
            )
        assert (await database.read_world("SELECT count(*) AS n FROM narrative_blocks"))[0]["n"] == 1
        assert await _world_revision(database) == 1
    finally:
        await database.close()


async def test_post_commit_transaction_cannot_mutate_world_facts_or_other_presentation_state(tmp_path):
    database, _ = await _open_database(tmp_path)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            await database.post_commit_write(
                lambda tx: tx.execute("UPDATE world_meta SET revision=99 WHERE singleton=1")
            )
        with pytest.raises(sqlite3.DatabaseError):
            await database.post_commit_write(
                lambda tx: tx.execute("DELETE FROM domain_commits")
            )
        assert await _world_revision(database) == 0
    finally:
        await database.close()


async def test_publish_freezes_narrative_before_writer_queue_wait(tmp_path):
    database, _ = await _open_database(tmp_path)
    entered, release = threading.Event(), threading.Event()

    def blocking_writer():
        entered.set()
        assert release.wait(5)

    try:
        await _commit_turn(database)
        blocker = asyncio.create_task(database._submit(blocking_writer))
        async with asyncio.timeout(5):
            while not entered.is_set():
                await asyncio.sleep(0.001)

        caller_owned = _narrative()
        publish = asyncio.create_task(
            SQLiteNarrativeBlockRepository(database).publish(
                turn_id="turn-voice-1", narrative=caller_owned
            )
        )
        await asyncio.sleep(0)
        caller_owned.segments[0].text = "调用方排队后篡改文本。"
        release.set()
        await blocker

        result = await publish
        assert result.narrative.segments[0].text == "不要打开那扇门。"
        persisted = await SQLiteNarrativeBlockRepository(database).load_narrative_block(
            "narrative-voice-1"
        )
        assert persisted.segments[0].text == "不要打开那扇门。"
    finally:
        release.set()
        await database.close()
