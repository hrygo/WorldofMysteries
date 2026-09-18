"""Real disk/child-process tests; compatibility injection never relaxes production pin."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading

import pytest
import pytest_asyncio

from engine.infrastructure.database_manager import (
    CommitRequest, DatabaseManager, DatabasePaths, IdempotencyConflict,
    RevisionConflict, StorageError, StoredEvent,
)
from engine.infrastructure.database_schema import SQLITE_VERSION

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def paths(tmp_path):
    layout = DatabasePaths.for_world(tmp_path/'世界 空格 ?#%', 'world.test')
    layout.canon.parent.mkdir(parents=True)
    with sqlite3.connect(layout.canon) as conn:
        conn.execute('CREATE TABLE canon_fixture(id TEXT PRIMARY KEY, value TEXT) STRICT')
        conn.execute("INSERT INTO canon_fixture VALUES ('fact', 'immutable')")
    return layout


async def open_database(paths, **kwargs):
    # Developer/CI compatibility suite records its actual SQLite. The production
    # constructor still fails closed unless that runtime is exactly 3.53.4.
    return await DatabaseManager.open(paths, expected_sqlite_version=sqlite3.sqlite_version, **kwargs)


@pytest_asyncio.fixture
async def database(paths):
    store = await open_database(paths)
    # This is a fixture repository, not a substitute generic production fact table.
    with sqlite3.connect(paths.world) as conn:
        conn.execute('CREATE TABLE test_character(id TEXT PRIMARY KEY, value INTEGER NOT NULL CHECK(value>=0)) STRICT')
        conn.execute("INSERT INTO test_character VALUES ('hero', 0)")
    try:
        yield store
    finally:
        await store.close()


def request(number=1, **kwargs):
    base = CommitRequest('line.one', '1349-07-03T10:00:00', number-1, f'key.{number}',
                         f'request.{number}', f'trace.{number}', {'delta': 1},
                         (StoredEvent(f'event.{number}', 'hero', 'test.changed', {'delta': 1}),))
    return replace(base, **kwargs)


def increment(tx):
    tx.execute("UPDATE test_character SET value=value+1 WHERE id='hero'")
    return {'value': tx.execute("SELECT value FROM test_character WHERE id='hero'")[0]['value']}


async def counts(database):
    return [(await database.read_world(f'SELECT count(*) AS n FROM {table}'))[0]['n']
            for table in ('domain_commits', 'domain_events', 'projection_outbox')]


async def test_database_production_version_is_not_silently_downgraded(paths):
    if sqlite3.sqlite_version == SQLITE_VERSION:
        db = await DatabaseManager.open(paths)
        await db.close()
    else:
        with pytest.raises(StorageError, match='baseline'):
            await DatabaseManager.open(paths)
        assert not paths.world.exists()
    print('SQLite test runtime:', sqlite3.sqlite_version, '; required production:', SQLITE_VERSION)


async def test_database_physical_roles_and_pragmas(database, paths):
    assert paths.world.exists() and paths.runtime.exists()
    assert not paths.retrieval.exists()  # lazy, never blocks authoritative world open
    actual = await database._submit(lambda: {key: database._connection.execute('PRAGMA '+key).fetchone()[0]
                    for key in ('journal_mode','synchronous','foreign_keys','trusted_schema')})
    assert actual == {'journal_mode':'wal','synchronous':2,'foreign_keys':1,'trusted_schema':0}
    with sqlite3.connect(paths.world) as conn:
        tables = list(conn.execute('PRAGMA table_list'))
        assert all(row[5] == 1 for row in tables if row[1] in {'world_meta','domain_commits','domain_events','projection_outbox'})
    assert await database.read_canon('SELECT value FROM canon_fixture') == [{'value':'immutable'}]


@pytest.mark.parametrize('sql', ["UPDATE canon_fixture SET value='changed'", 'PRAGMA query_only=OFF',
                                "ATTACH DATABASE ':memory:' AS external", 'DROP TABLE canon_fixture'])
async def test_database_canon_connection_cannot_write_or_attach(database, paths, sql):
    before = paths.canon.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):
        await database.read_canon(sql)
    assert paths.canon.read_bytes() == before


async def test_database_unknown_canon_not_created(tmp_path):
    paths = DatabasePaths.for_world(tmp_path, 'missing')
    with pytest.raises(StorageError, match='missing'):
        await open_database(paths)
    assert not paths.world.parent.exists()


@pytest.mark.parametrize('role', ['world', 'retrieval', 'runtime'])
async def test_database_aliases_cannot_write_canon(paths, role):
    with pytest.raises(StorageError, match='separate'):
        await open_database(replace(paths, **{role: paths.canon}))
    target = getattr(paths, role)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.link(paths.canon, target)
    with pytest.raises(StorageError, match='independent'):
        await open_database(paths)


@pytest.mark.parametrize('sidecar', ['', '-wal', '-shm', '-journal', '.writer.lock'])
async def test_database_rejects_symlinks(paths, tmp_path, sidecar):
    paths.world.parent.mkdir(parents=True, exist_ok=True)
    Path(str(paths.world)+sidecar).symlink_to(tmp_path/'not-owned')
    with pytest.raises((StorageError, OSError)):
        await open_database(paths)
    assert not (tmp_path/'not-owned').exists()


async def test_database_unknown_schema_is_not_overwritten(paths):
    paths.world.parent.mkdir(parents=True)
    with sqlite3.connect(paths.world) as conn:
        conn.execute('CREATE TABLE older_user_data(id INTEGER)')
        conn.execute('INSERT INTO older_user_data VALUES (99)')
    before = paths.world.read_bytes()
    with pytest.raises(StorageError, match='migration'):
        await open_database(paths)
    assert paths.world.read_bytes() == before


async def test_database_exclusive_writer_and_lease_release(database, paths):
    lock = Path(str(paths.world)+'.writer.lock')
    inode = lock.stat().st_ino
    with pytest.raises(StorageError, match='Another Domain Writer'):
        await open_database(paths)
    assert (await database.commit_resolved(request(), increment)).revision == 1
    await database.close()
    reopened = await open_database(paths)
    try:
        assert lock.stat().st_ino == inode
        assert await counts(reopened) == [1, 1, 1]
    finally:
        await reopened.close()


async def test_database_commit_replay_survives_reopen(database, paths):
    before = paths.canon.read_bytes()
    result = await database.commit_resolved(request(), increment)
    assert result.revision == 1 and result.value == {'value':1} and not result.replayed
    await database.close()
    reopened = await open_database(paths)
    try:
        replay = await reopened.commit_resolved(replace(request(), trace_id='new-trace', request_id='retry'),
                                               lambda _: pytest.fail('Replay executed repository writes'))
        assert replay.replayed and replay.revision == 1 and replay.value == result.value
        assert await counts(reopened) == [1,1,1]
        assert await reopened.read_world('SELECT value FROM test_character') == [{'value':1}]
    finally:
        await reopened.close()
    assert paths.canon.read_bytes() == before


@pytest.mark.parametrize('change', [{'operation':{'delta':2}}, {'worldline_id':'other.line'},
                                    {'expected_revision':1}, {'world_time':'other-time'}])
async def test_database_same_key_different_operation_conflicts(database, change):
    await database.commit_resolved(request(), increment)
    with pytest.raises(IdempotencyConflict):
        await database.commit_resolved(replace(request(), **change), increment)
    assert await counts(database) == [1,1,1]


async def test_database_concurrent_same_key_writes_once(database):
    results = await asyncio.gather(*[database.commit_resolved(request(), increment) for _ in range(30)])
    assert sum(not item.replayed for item in results) == 1
    assert {item.revision for item in results} == {1}
    assert await counts(database) == [1,1,1]


async def test_database_revision_cas_serializes_competing_commands(database):
    requests = [replace(request(n), expected_revision=0) for n in range(1,11)]
    results = await asyncio.gather(*[database.commit_resolved(r, increment) for r in requests], return_exceptions=True)
    assert sum(isinstance(item, RevisionConflict) for item in results) == 9
    assert await counts(database) == [1,1,1]


@pytest.mark.parametrize('stage', ['before_apply','after_apply','after_events','before_commit'])
async def test_database_failed_commit_rolls_back_everything(database, stage):
    def fail(at):
        if at == stage:
            raise RuntimeError('injected transaction failure')
    database._fault_hook = fail
    with pytest.raises(RuntimeError):
        await database.commit_resolved(request(), increment)
    assert await counts(database) == [0,0,0]
    assert await database.read_world('SELECT value FROM test_character') == [{'value':0}]
    database._fault_hook = None
    assert (await database.commit_resolved(request(), increment)).revision == 1


async def test_database_failure_after_commit_has_replayable_outcome(database):
    def fail(at):
        if at == 'after_commit':
            raise RuntimeError('lost response')
    database._fault_hook = fail
    with pytest.raises(RuntimeError, match='lost response'):
        await database.commit_resolved(request(), increment)
    assert await counts(database) == [1,1,1]
    database._fault_hook = None
    assert (await database.commit_resolved(request(), increment)).replayed


@pytest.mark.parametrize('sql', ['COMMIT','ROLLBACK','PRAGMA synchronous=OFF',
    "ATTACH DATABASE ':memory:' AS other", 'UPDATE world_meta SET revision=100',
    'DELETE FROM projection_outbox', 'DROP TABLE test_character', 'DELETE FROM domain_commits'])
async def test_database_repository_cannot_control_boundary(database, sql):
    def unsafe(tx):
        increment(tx)
        tx.execute(sql)
    with pytest.raises(sqlite3.DatabaseError):
        await database.commit_resolved(request(), unsafe)
    assert await counts(database) == [0,0,0]
    assert await database.read_world('SELECT value FROM test_character') == [{'value':0}]


async def test_database_transaction_cannot_escape(database):
    held = []
    def apply(tx):
        held.append(tx)
        return increment(tx)
    await database.commit_resolved(request(), apply)
    with pytest.raises(StorageError, match='no longer active'):
        held[0].execute('SELECT 1')


async def test_database_foreign_key_failure_rolls_back(database, paths):
    with sqlite3.connect(paths.world) as conn:
        conn.execute('CREATE TABLE test_knowledge(id TEXT PRIMARY KEY, hero TEXT REFERENCES test_character(id)) STRICT')
    def apply(tx):
        increment(tx)
        tx.execute("INSERT INTO test_knowledge VALUES ('k','missing')")
    with pytest.raises(sqlite3.IntegrityError):
        await database.commit_resolved(request(), apply)
    assert await counts(database) == [0,0,0]
    assert await database.read_world('SELECT value FROM test_character') == [{'value':0}]


@pytest.mark.parametrize('value', [float('nan'), float('inf'), {'bad':object()}])
async def test_database_non_json_result_rolls_back(database, value):
    def apply(tx):
        increment(tx)
        return value
    with pytest.raises(StorageError):
        await database.commit_resolved(request(), apply)
    assert await counts(database) == [0,0,0]


async def test_database_async_repository_is_rejected(database):
    async def suspended(tx):
        return None
    with pytest.raises(StorageError, match='must not suspend'):
        await database.commit_resolved(request(), suspended)
    assert await counts(database) == [0,0,0]


async def test_database_reader_does_not_block_on_writer_and_cancel_does_not_undo_commit(database):
    entered, release = threading.Event(), threading.Event()
    def apply(tx):
        result = increment(tx)
        entered.set()
        assert release.wait(5)
        return result
    pending = asyncio.create_task(database.commit_resolved(request(), apply))
    try:
        async with asyncio.timeout(5):
            while not entered.is_set():
                await asyncio.sleep(0.001)
        assert await asyncio.wait_for(database.read_world('SELECT value FROM test_character'), 1) == [{'value':0}]
        pending.cancel()
        await asyncio.sleep(0)
        assert not pending.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert (await database.commit_resolved(request(), increment)).replayed
    assert await database.read_world('SELECT value FROM test_character') == [{'value':1}]


async def test_database_shutdown_drains_accepted_writes(database):
    entered, release = threading.Event(), threading.Event()
    def apply(tx):
        entered.set()
        assert release.wait(5)
        return increment(tx)
    pending = asyncio.create_task(database.commit_resolved(request(), apply))
    async with asyncio.timeout(5):
        while not entered.is_set():
            await asyncio.sleep(0.001)
    closing = asyncio.create_task(database.close())
    await asyncio.sleep(0)
    try:
        with pytest.raises(StorageError, match='closing'):
            await database.commit_resolved(request(2), increment)
        assert not closing.done()
    finally:
        release.set()
    assert (await pending).revision == 1
    await closing


async def test_database_payload_is_frozen_before_queue_wait(database):
    entered, release = threading.Event(), threading.Event()
    def blocking():
        entered.set()
        assert release.wait(5)
    blocker = asyncio.create_task(database._submit(blocking))
    async with asyncio.timeout(5):
        while not entered.is_set():
            await asyncio.sleep(0.001)
    payload = {'delta':1}
    command = request(operation=payload)
    pending = asyncio.create_task(database.commit_resolved(command, increment))
    await asyncio.sleep(0)
    payload['delta'] = 999
    release.set()
    await blocker
    await pending
    rows = await database.read_world('SELECT operation_json FROM domain_commits')
    assert json.loads(rows[0]['operation_json']) == {'delta':1}


@pytest.mark.parametrize('stage', ['after_apply','after_events','before_commit','after_commit'])
async def test_database_real_process_crash_is_atomic(database, paths, stage):
    await database.close()
    script = '''
import asyncio,os,sqlite3,sys
from pathlib import Path
from engine.infrastructure.database_manager import DatabaseManager,DatabasePaths,CommitRequest,StoredEvent
async def main():
    paths=DatabasePaths(*(Path(p) for p in sys.argv[1:5]))
    def fault(at):
        if at==sys.argv[5]: os._exit(77)
    db=await DatabaseManager.open(paths,expected_sqlite_version=sqlite3.sqlite_version,fault_hook=fault)
    command=CommitRequest('line.one','1349-07-03T10:00:00',0,'key.1','request.1','trace.1',{'delta':1},
        (StoredEvent('event.1','hero','test.changed',{'delta':1}),))
    def apply(tx):
        tx.execute("UPDATE test_character SET value=value+1 WHERE id='hero'")
        return {'value':1}
    await db.commit_resolved(command,apply)
asyncio.run(main())
'''
    result = await asyncio.to_thread(subprocess.run, [sys.executable,'-c',script,
            *[str(getattr(paths,r)) for r in ('canon','world','retrieval','runtime')],stage],
            cwd=ROOT, capture_output=True, timeout=15)
    assert result.returncode == 77, result.stderr
    reopened = await open_database(paths)
    try:
        committed = int(stage == 'after_commit')
        assert await counts(reopened) == [committed]*3
        assert await reopened.read_world('SELECT value FROM test_character') == [{'value':committed}]
        recovery = await reopened.commit_resolved(request(), increment)
        assert recovery.revision == 1 and recovery.replayed == bool(committed)
    finally:
        await reopened.close()


async def test_database_backup_reads_live_wal_and_never_overwrites(database, paths, tmp_path):
    await database.commit_resolved(request(), increment)
    assert Path(str(paths.world)+'-wal').stat().st_size > 0
    target = tmp_path/'snapshot.db'
    digest = await database.backup_world(target)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    with sqlite3.connect(target) as conn:
        assert conn.execute('SELECT revision FROM world_meta').fetchone()[0] == 1
        assert conn.execute('SELECT value FROM test_character').fetchone()[0] == 1
        assert conn.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    await database.commit_resolved(request(2), increment)
    with pytest.raises(StorageError, match='already exists'):
        await database.backup_world(target)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    alias = tmp_path/'alias.db'; alias.symlink_to('missing')
    with pytest.raises(StorageError):
        await database.backup_world(alias)
    assert not (tmp_path/'missing').exists()


@pytest.mark.parametrize('value', [-1, True, 2**63, 1.2, '0'])
async def test_database_invalid_revision_rejected(database, value):
    with pytest.raises(StorageError):
        await database.commit_resolved(request(expected_revision=value), increment)
    assert await counts(database) == [0,0,0]


async def test_database_duplicate_event_rolls_back_domain_write(database):
    await database.commit_resolved(request(), increment)
    command = replace(request(2), events=request().events)
    with pytest.raises(sqlite3.IntegrityError):
        await database.commit_resolved(command, increment)
    assert await counts(database) == [1,1,1]
    assert await database.read_world('SELECT value FROM test_character') == [{'value':1}]


async def test_database_rejects_mismatched_journal_without_resetting(database, paths):
    await database.commit_resolved(request(), increment)
    await database.close()
    with sqlite3.connect(paths.world) as conn:
        conn.execute('UPDATE world_meta SET revision=0')
    with pytest.raises(StorageError, match='inconsistent'):
        await open_database(paths)
    with sqlite3.connect(paths.world) as conn:
        assert conn.execute('SELECT count(*) FROM domain_events').fetchone()[0] == 1


async def test_database_cannot_recreate_missing_world_identity(database, paths):
    await database.commit_resolved(request(), increment)
    await database.close()
    with sqlite3.connect(paths.world) as conn:
        conn.execute('DELETE FROM world_meta')
    with pytest.raises(StorageError, match='identity missing'):
        await open_database(paths)


async def test_database_rejects_active_world_file_replacement(database, paths):
    # Offline restore must never be mistaken for the currently opened writer file.
    moved = paths.world.with_name('old.db')
    paths.world.rename(moved)
    paths.world.write_bytes(b'not the opened world')
    try:
        with pytest.raises(StorageError, match='replaced'):
            await database.commit_resolved(request(), increment)
    finally:
        paths.world.unlink()
        moved.rename(paths.world)
    assert await counts(database) == [0,0,0]


async def test_database_non_string_json_keys_are_not_coerced(database):
    with pytest.raises(StorageError, match='keys'):
        await database.commit_resolved(request(operation={1:'coerced'}))
    assert await counts(database) == [0,0,0]


def test_database_shared_runtime_initializes_once_under_concurrent_open(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import closing
    from engine.infrastructure.database_schema import connect, initialize, APPLICATION_IDS

    path = tmp_path/'shared-runtime.db'
    both_ready = threading.Barrier(2)

    def initialize_one():
        with closing(connect(path)) as conn:
            # The old implementation read an empty schema before this barrier,
            # then its second caller blindly attempted the same CREATE TABLE.
            conn.set_trace_callback(lambda sql: both_ready.wait(timeout=5)
                                    if sql == 'BEGIN IMMEDIATE' else None)
            initialize(conn, 'runtime')
            return conn.execute('PRAGMA application_id').fetchone()[0]

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(initialize_one) for _ in range(2)]
        assert [future.result(timeout=10) for future in futures] == [APPLICATION_IDS['runtime']]*2
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute("SELECT count(*) FROM sqlite_schema WHERE name='runtime_metadata'").fetchone()[0] == 1
