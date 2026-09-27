"""T5 restart read (Story Book) and retrieval projection rebuild on five-turn data."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from test_golden_five_turn_application import (
    _finalization_command_from_evidence,
    _FinalizationAdapter,
    _open_five_turn_facade,
    _submit_five_turns,
)

from application.episode_finalization import EpisodeFinalizationService
from infrastructure.database_manager import DatabaseManager
from infrastructure.episode_finalization_repository import (
    SQLiteEpisodeFinalizationRepository,
)
from infrastructure.outbox import OutboxProjector
from infrastructure.sqlite_runtime import sqlite3 as sqlite3_runtime


def _rows(path: Path, sql: str) -> list[dict]:
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(sql)]


async def _build_finalized(tmp_path: Path):
    database, paths, facade, _factory, opened = await _open_five_turn_facade(tmp_path)
    await _submit_five_turns(database, facade, opened)
    command = await _finalization_command_from_evidence(database, opened.session.session_id)
    service = EpisodeFinalizationService(port=_FinalizationAdapter(database))
    finalized = await service.finalize(command)
    return database, paths, opened, finalized


@pytest.mark.asyncio
async def test_restart_reads_finalized_episode_bundle_without_resolver(tmp_path):
    database, paths, opened, finalized = await _build_finalized(tmp_path)
    session_id = opened.session.session_id
    await database.close()

    # Restart: a fresh handle on the same world.db must read the committed bundle.
    reopened = await DatabaseManager.open(paths, expected_sqlite_version=sqlite3_runtime.sqlite_version)
    try:
        loaded = await SQLiteEpisodeFinalizationRepository(reopened).load_by_session(session_id)
        assert loaded.episode == finalized.episode
        assert loaded.store_revision == finalized.store_revision
        # Every artifact group survives the restart with identical identity/content.
        assert loaded.artifacts.character_events == finalized.artifacts.character_events
        assert loaded.artifacts.relationship_events == finalized.artifacts.relationship_events
        assert loaded.artifacts.knowledge_changes == finalized.artifacts.knowledge_changes
        assert loaded.artifacts.memories == finalized.artifacts.memories
        assert loaded.artifacts.world_events == finalized.artifacts.world_events
        # The fixed Golden memory is present and bound to the protagonist.
        assert loaded.artifacts.memories[0]["character_id"] == "char_evelyn_gray"
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_deleted_retrieval_projection_rebuilds_idempotently_from_authority(tmp_path):
    database, paths, _opened, _finalized = await _build_finalized(tmp_path)
    try:
        projector = OutboxProjector(database)
        # Drain the outbox into the disposable projection.
        result = await projector.run_once(limit=64)
        assert result.applied_events > 0
        expected = _rows(paths.retrieval, "SELECT * FROM projected_events ORDER BY event_id")
        assert expected, "finalization must project at least one event"

        # Delete the isolated retrieval projection entirely, then rebuild from world.db.
        database.paths.retrieval.unlink()
        rebuilt = await projector.rebuild()
        assert rebuilt.rebuilt is True
        assert rebuilt.applied_events == len(expected)
        assert _rows(paths.retrieval, "SELECT * FROM projected_events ORDER BY event_id") == expected

        # Rebuild is idempotent: a second pass changes nothing.
        again = await projector.rebuild()
        assert _rows(paths.retrieval, "SELECT * FROM projected_events ORDER BY event_id") == expected
        assert again.applied_events == 0 or again.indexed_revision >= rebuilt.indexed_revision
    finally:
        await database.close()
