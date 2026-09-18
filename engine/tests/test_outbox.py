"""Outbox crash windows are tested with separate real SQLite files and processes."""
import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading

import pytest

from engine.infrastructure.outbox import OutboxProjector
from engine.infrastructure.database_manager import StorageError
from test_database_manager import paths, database, request, increment, open_database, ROOT


def rows(path, sql):
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(sql)]


async def pending(database):
    return (await database.read_world('SELECT count(*) AS n FROM projection_outbox WHERE processed=0'))[0]['n']


async def test_outbox_projection_commits_before_ack_and_replays_idempotently(database):
    await database.commit_resolved(request(), increment)
    projector = OutboxProjector(database)
    first = await projector.run_once()
    assert (first.indexed_revision, first.applied_events, first.observed_world_revision) == (1,1,1)
    assert await pending(database) == 0
    second = await projector.run_once()
    assert second.applied_events == 0 and second.indexed_revision == 1
    projected = rows(database.paths.retrieval, 'SELECT * FROM projected_events')
    assert len(projected) == 1 and projected[0]['source_revision'] == 1
    assert projected[0]['worldline_id'] == 'line.one'
    assert json.loads(projected[0]['payload_json']) == {'delta':1}


@pytest.mark.parametrize('stage', ['after_project_event','before_projection_commit'])
async def test_outbox_projection_failure_never_rolls_back_world(database, stage):
    await database.commit_resolved(request(), increment)
    def fail(at):
        if at == stage:
            raise RuntimeError('projection failure')
    projector = OutboxProjector(database, fault_hook=fail)
    with pytest.raises(RuntimeError):
        await projector.run_once()
    assert await pending(database) == 1
    assert rows(database.paths.retrieval, 'SELECT * FROM projected_events') == []
    assert await database.read_world('SELECT value FROM test_character') == [{'value':1}]
    projector._fault_hook = None
    assert (await projector.run_once()).applied_events == 1


@pytest.mark.parametrize('stage', ['after_projection_commit','before_acknowledge'])
async def test_outbox_commit_ack_gap_is_recovered_without_duplicate_projection(database, stage):
    await database.commit_resolved(request(), increment)
    def fail(at):
        if at == stage:
            raise RuntimeError('lost acknowledgement')
    projector = OutboxProjector(database, fault_hook=fail)
    with pytest.raises(RuntimeError):
        await projector.run_once()
    assert await pending(database) == 1
    assert len(rows(database.paths.retrieval, 'SELECT * FROM projected_events')) == 1
    projector._fault_hook = None
    recovered = await projector.run_once()
    assert recovered.applied_events == 0 and recovered.indexed_revision == 1
    assert await pending(database) == 0


async def test_outbox_deleted_projection_rebuilds_already_acknowledged_history(database):
    for number in range(1,5):
        await database.commit_resolved(request(number), increment)
    projector = OutboxProjector(database)
    assert (await projector.run_once(limit=2)).indexed_revision == 2
    assert await pending(database) == 2
    assert (await projector.run_once()).indexed_revision == 4
    expected = rows(database.paths.retrieval, 'SELECT * FROM projected_events ORDER BY event_id')
    # No live connection holds this file: every projection pass closes its readers/writers.
    database.paths.retrieval.unlink()
    assert await pending(database) == 0
    rebuilt = await projector.rebuild()
    assert rebuilt.rebuilt and rebuilt.applied_events == 4
    assert rows(database.paths.retrieval, 'SELECT * FROM projected_events ORDER BY event_id') == expected
    await projector.rebuild()
    assert rows(database.paths.retrieval, 'SELECT * FROM projected_events ORDER BY event_id') == expected


async def test_outbox_rebuild_empty_world_is_valid(database):
    result = await OutboxProjector(database).rebuild()
    assert result.indexed_revision == 0 and result.applied_events == 0
    assert await pending(database) == 0


async def test_outbox_corruption_cannot_block_authoritative_reads_or_commits(database):
    database.paths.retrieval.write_bytes(b'not a SQLite database')
    await database.commit_resolved(request(), increment)
    with pytest.raises(sqlite3.DatabaseError):
        await OutboxProjector(database).run_once()
    assert await pending(database) == 1
    assert await database.read_world('SELECT value FROM test_character') == [{'value':1}]
    assert (await database.commit_resolved(request(2), increment)).revision == 2


async def test_outbox_rejects_projection_belonging_to_another_world(database):
    await database.commit_resolved(request(), increment)
    projector = OutboxProjector(database)
    await projector.run_once()
    with sqlite3.connect(database.paths.retrieval) as conn:
        conn.execute("UPDATE projection_meta SET store_id='different-world'")
    expected = rows(database.paths.retrieval, 'SELECT * FROM projected_events')
    with pytest.raises(StorageError, match='another world'):
        await projector.rebuild()
    assert rows(database.paths.retrieval, 'SELECT * FROM projected_events') == expected


async def test_outbox_rebuild_after_restore_does_not_trust_future_checkpoint(database):
    await database.commit_resolved(request(), increment)
    projector = OutboxProjector(database)
    await projector.run_once()
    with sqlite3.connect(database.paths.retrieval) as conn:
        conn.execute('UPDATE projection_meta SET last_indexed_revision=500')
    with pytest.raises(StorageError, match='ahead'):
        await projector.run_once()
    result = await projector.rebuild()
    assert result.indexed_revision == 1


async def test_outbox_projection_uses_consistent_snapshot_while_world_advances(database):
    await database.commit_resolved(request(), increment)
    entered, release = threading.Event(), threading.Event()
    def pause(at):
        if at == 'after_project_event':
            entered.set()
            assert release.wait(5)
    projector = OutboxProjector(database, fault_hook=pause)
    projection = asyncio.create_task(projector.run_once())
    try:
        async with asyncio.timeout(5):
            while not entered.is_set():
                await asyncio.sleep(0.001)
        assert (await asyncio.wait_for(database.commit_resolved(request(2), increment), 2)).revision == 2
    finally:
        release.set()
    first = await projection
    assert first.observed_world_revision == 1 and first.indexed_revision == 1
    assert await pending(database) == 1
    projector._fault_hook = None
    assert (await projector.run_once()).indexed_revision == 2


async def test_outbox_concurrent_calls_are_serial_and_cancel_does_not_drop_ack(database):
    await database.commit_resolved(request(), increment)
    entered, release = threading.Event(), threading.Event()
    def pause(at):
        if at == 'after_project_event':
            entered.set()
            assert release.wait(5)
    projector = OutboxProjector(database, fault_hook=pause)
    first = asyncio.create_task(projector.run_once())
    try:
        async with asyncio.timeout(5):
            while not entered.is_set():
                await asyncio.sleep(0.001)
        first.cancel()
        second = asyncio.create_task(projector.run_once())
        await asyncio.sleep(0)
        assert not first.done() and not second.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert (await second).applied_events == 0
    assert await pending(database) == 0


@pytest.mark.parametrize('stage', ['before_projection_commit','after_projection_commit'])
async def test_outbox_real_process_crash_does_not_lose_commits(database, paths, stage):
    await database.commit_resolved(request(), increment)
    await database.close()
    script = '''
import asyncio,os,sqlite3,sys
from pathlib import Path
from engine.infrastructure.database_manager import DatabaseManager,DatabasePaths
from engine.infrastructure.outbox import OutboxProjector
async def main():
    db=await DatabaseManager.open(DatabasePaths(*(Path(p) for p in sys.argv[1:5])),expected_sqlite_version=sqlite3.sqlite_version)
    def fault(at):
        if at==sys.argv[5]: os._exit(78)
    await OutboxProjector(db,fault_hook=fault).run_once()
asyncio.run(main())
'''
    result = await asyncio.to_thread(subprocess.run, [sys.executable,'-c',script,
            *[str(getattr(paths,r)) for r in ('canon','world','retrieval','runtime')], stage],
            cwd=ROOT, capture_output=True, timeout=15)
    assert result.returncode == 78, result.stderr
    reopened = await open_database(paths)
    try:
        assert await pending(reopened) == 1
        assert await reopened.read_world('SELECT value FROM test_character') == [{'value':1}]
        recovery = await OutboxProjector(reopened).run_once()
        assert recovery.applied_events == int(stage == 'before_projection_commit')
        assert recovery.indexed_revision == 1 and await pending(reopened) == 0
    finally:
        await reopened.close()


@pytest.mark.parametrize('limit', [0, -1, True, 129, 1.5])
async def test_outbox_invalid_batch_limits_fail_closed(database, limit):
    with pytest.raises(StorageError):
        await OutboxProjector(database).run_once(limit=limit)


async def test_outbox_index_cannot_alias_authority_after_open(database):
    os.link(database.paths.world, database.paths.retrieval)
    with pytest.raises(StorageError, match='independent'):
        await OutboxProjector(database).run_once()
    # A hardlink aliases both paths; remove only the fixture-created alias before reading.
    database.paths.retrieval.unlink()
    assert await database.read_world('SELECT revision FROM world_meta') == [{'revision':0}]


async def test_outbox_acknowledgement_checks_store_and_revision(database):
    await database.commit_resolved(request(), increment)
    for store, rev in [('other-world',1), (database.store_id,2), (database.store_id,True)]:
        with pytest.raises(StorageError):
            await database.mark_projected(store, rev)
    assert await pending(database) == 1


async def test_outbox_independent_workers_cannot_race_rebuild(database):
    await database.commit_resolved(request(), increment)
    entered, release = threading.Event(), threading.Event()
    def pause(at):
        if at == 'after_project_event':
            entered.set()
            assert release.wait(5)
    first = asyncio.create_task(OutboxProjector(database, fault_hook=pause).run_once())
    try:
        async with asyncio.timeout(5):
            while not entered.is_set():
                await asyncio.sleep(0.001)
        with pytest.raises(StorageError, match='Another projection worker'):
            await OutboxProjector(database).rebuild()
    finally:
        release.set()
    assert (await first).indexed_revision == 1


async def test_outbox_missing_identity_is_not_silently_adopted(database):
    await database.commit_resolved(request(), increment)
    await OutboxProjector(database).run_once()
    with sqlite3.connect(database.paths.retrieval) as conn:
        conn.execute('DELETE FROM projection_meta')
    with pytest.raises(StorageError, match='identity is missing'):
        await OutboxProjector(database).run_once()
