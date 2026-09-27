"""T5 durable post-COMMIT BeatPlan publication tests."""
from __future__ import annotations

import pytest
from test_narrative_block_repository import (
    _commit_turn,
    _narrative,
    _open_database,
)

from contracts import BeatPlan, TurnStatus
from infrastructure.beat_plan_repository import SQLiteBeatPlanRepository
from infrastructure.database_manager import DatabaseManager, StorageError
from infrastructure.narrative_block_repository import SQLiteNarrativeBlockRepository
from infrastructure.sqlite_runtime import sqlite3


def _beat(*, beat_id: str = "beat-voice-1", revision: int = 1,
          session_id: str = "session-voice") -> BeatPlan:
    return BeatPlan.model_validate(
        {
            "schema_version": "1.0",
            "id": beat_id,
            "story_session_id": session_id,
            "source_story_revision": revision,
            "beat_type": "revelation",
            "dramatic_goal": "reveal the hidden sign",
            "tension_delta": 1,
            "intervention_required": False,
        }
    )


@pytest.mark.asyncio
async def test_publish_beat_is_durable_idempotent_and_advances_to_beat_ready(tmp_path):
    database, paths = await _open_database(tmp_path)
    try:
        committed = await _commit_turn(database)
        repo = SQLiteBeatPlanRepository(database)
        before_commits = await database.read_world("SELECT count(*) AS n FROM domain_commits")

        published = await repo.publish(turn_id=committed.id, beat_plan=_beat())
        assert not published.replayed
        assert published.turn.status is TurnStatus.BEAT_READY
        assert published.beat_plan == _beat()
        # Beat publication must not create a new authoritative world revision.
        assert await database.read_world("SELECT count(*) AS n FROM domain_commits") == before_commits

        # Replay is idempotent and does not duplicate the row.
        replay = await repo.publish(turn_id=committed.id, beat_plan=_beat())
        assert replay.replayed is True
        assert replay.beat_plan.id == "beat-voice-1"
        assert (await database.read_world("SELECT count(*) AS n FROM beat_plans"))[0]["n"] == 1

        # Durable across restart: reopen the same world.db and read back.
        await database.close()
        reopened = await DatabaseManager.open(paths, expected_sqlite_version=sqlite3.sqlite_version)
        try:
            assert (await SQLiteBeatPlanRepository(reopened).load_turn_beat_plan(committed.id)) == _beat()
            assert (await SQLiteBeatPlanRepository(reopened).load_turn(committed.id)).status is TurnStatus.BEAT_READY
        finally:
            await reopened.close()
    finally:
        pass


@pytest.mark.asyncio
async def test_publish_beat_then_narrative_advances_status_in_order(tmp_path):
    database, _paths = await _open_database(tmp_path)
    try:
        committed = await _commit_turn(database)
        beats = SQLiteBeatPlanRepository(database)
        narratives = SQLiteNarrativeBlockRepository(database)

        assert (await beats.publish(turn_id=committed.id, beat_plan=_beat())).turn.status is TurnStatus.BEAT_READY
        # Narrative accepts a BEAT_READY turn and advances it to NARRATIVE_READY.
        published = await narratives.publish(turn_id=committed.id, narrative=_narrative())
        assert published.turn.status is TurnStatus.NARRATIVE_READY
        # Both expression artifacts remain readable together.
        assert (await beats.load_turn_beat_plan(committed.id)) is not None
        assert (await narratives.load_narrative_block("narrative-voice-1")) is not None
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_publish_beat_rejects_mismatched_identity_and_conflicting_replay(tmp_path):
    database, _paths = await _open_database(tmp_path)
    try:
        committed = await _commit_turn(database)
        repo = SQLiteBeatPlanRepository(database)

        # Wrong session must be rejected.
        with pytest.raises(StorageError, match="another StorySession"):
            await repo.publish(turn_id=committed.id, beat_plan=_beat(session_id="other-session"))
        # Wrong story revision must be rejected.
        with pytest.raises(StorageError, match="does not match committed turn"):
            await repo.publish(turn_id=committed.id, beat_plan=_beat(revision=99))
        assert (await repo.load_turn(committed.id)).status is TurnStatus.COMMITTED

        # After a successful publish, a different beat for the same turn is rejected.
        await repo.publish(turn_id=committed.id, beat_plan=_beat())
        with pytest.raises(StorageError, match="different BeatPlan"):
            await repo.publish(turn_id=committed.id, beat_plan=_beat(beat_id="beat-voice-2"))
    finally:
        await database.close()
