"""Disk-backed infrastructure boundary, not a Domain reducer or an IPC SQL API.

Only trusted Application/repository code receives this object. A resolved operation
and its repository writes are committed once; model proposals must be validated
before crossing this boundary. Cancellation of an admitted operation waits for its
outcome and never means that a completed COMMIT was undone.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
from .sqlite_runtime import sqlite3
import tempfile
import threading
from typing import Callable, Protocol
import uuid

from .database_schema import SQLITE_VERSION, StorageError, check_file, connect, initialize, integrity, read_rows
from .sqlite_runtime import BUNDLED_DATA_SQLITE


class DatabaseManagerProtocol(Protocol):
    """Interface retained for existing imports; concrete behavior is below."""
    async def close(self) -> None: ...


class RevisionConflict(StorageError):
    pass


class IdempotencyConflict(StorageError):
    pass


def _text(value: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or not value or len(value) > 256 or '\x00' in value:
        raise StorageError('Invalid storage identifier')


def _json(value) -> str:
    def validate_keys(item, depth=0):
        if depth > 64:
            raise StorageError('Storage JSON nesting exceeds limit')
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise StorageError('Storage JSON keys must be strings')
            for child in item.values():
                validate_keys(child, depth + 1)
        elif isinstance(item, (list, tuple)):
            for child in item:
                validate_keys(child, depth + 1)
    try:
        validate_keys(value)
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if len(encoded.encode('utf-8')) > 1024 * 1024:
            raise StorageError('Storage payload exceeds limit')
        return encoded
    except (TypeError, ValueError, RecursionError, UnicodeError):
        raise StorageError('Storage payload must be bounded finite JSON') from None


@dataclass(frozen=True)
class DatabasePaths:
    canon: Path
    world: Path
    retrieval: Path
    runtime: Path

    @classmethod
    def for_world(cls, root: Path, world_id: str) -> DatabasePaths:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', world_id):
            raise StorageError('Invalid world directory identifier')
        directory = root / 'Worlds' / world_id
        return cls(root/'Canon/canon.db', directory/'world.db', directory/'retrieval.db',
                   root/'Runtime/runtime.db')

    def normalized(self) -> DatabasePaths:
        paths = [self.canon, self.world, self.retrieval, self.runtime]
        for index, path in enumerate(paths):
            check_file(path, required=index == 0)
            for suffix in ('-wal', '-shm', '-journal'):
                check_file(Path(str(path)+suffix))
        resolved = [path.resolve() for path in paths]
        if len(set(resolved)) != 4:
            raise StorageError('Database roles must use separate files')
        return DatabasePaths(*resolved)


@dataclass(frozen=True)
class StoredEvent:
    """Internal journal header; not a replacement for canonical Domain DTOs."""
    event_id: str
    aggregate_id: str
    event_type: str
    payload: dict
    cause_id: str | None = None
    episode_id: str | None = None
    turn_id: str | None = None


@dataclass(frozen=True)
class CommitRequest:
    worldline_id: str
    world_time: str
    expected_revision: int
    idempotency_key: str
    request_id: str
    trace_id: str
    operation: dict
    events: tuple[StoredEvent, ...]

    def freeze(self) -> dict:
        for value in (self.worldline_id, self.world_time, self.idempotency_key, self.request_id, self.trace_id):
            _text(value)
        if type(self.expected_revision) is not int or not 0 <= self.expected_revision < 2**63-1:
            raise StorageError('Invalid expected revision')
        if not isinstance(self.operation, dict) or not 1 <= len(self.events) <= 1000:
            raise StorageError('A commit requires an operation and bounded events')
        events = []
        for event in self.events:
            for value in (event.event_id, event.aggregate_id, event.event_type):
                _text(value)
            for value in (event.cause_id, event.episode_id, event.turn_id):
                _text(value, optional=True)
            if not isinstance(event.payload, dict):
                raise StorageError('Event payload must be an object')
            events.append(vars(event))
        if len({event['event_id'] for event in events}) != len(events):
            raise StorageError('Duplicate event identifiers in commit')
        # Copy caller-owned containers BEFORE an await or queue admission.
        return json.loads(_json({**vars(self), 'events': events}))


@dataclass(frozen=True)
class CommitResult:
    revision: int
    value: object
    replayed: bool


_PROTECTED = frozenset({'world_meta', 'domain_commits', 'domain_events', 'projection_outbox',
                        'sqlite_master', 'sqlite_schema', 'sqlite_sequence'})


class PresentationTransaction:
    """Synchronous presentation-state transaction with no world revision authority."""

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection
        self._active = True
        self._thread = threading.get_ident()

    def execute(self, sql: str, parameters: tuple = ()) -> list[dict]:
        if not self._active or threading.get_ident() != self._thread:
            raise StorageError('Transaction is no longer active on its writer')
        with closing(self._connection.execute(sql, parameters)) as cursor:
            return [dict(row) for row in cursor] if cursor.description else []


_PRESENTATION_TABLES = frozenset({'voice_bindings', 'delivery_cursors'})


class AudioAssetTransaction:
    """Insert-only complete AudioTake transaction with no world-fact authority."""

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection
        self._active = True
        self._thread = threading.get_ident()

    def execute(self, sql: str, parameters: tuple = ()) -> list[dict]:
        if not self._active or threading.get_ident() != self._thread:
            raise StorageError('Transaction is no longer active on its writer')
        with closing(self._connection.execute(sql, parameters)) as cursor:
            return [dict(row) for row in cursor] if cursor.description else []


_AUDIO_ASSET_INSERT_TABLES = frozenset({'audio_takes'})


def _audio_asset_authorizer(action, table, _column, database, _trigger):
    if database not in (None, 'main'):
        return sqlite3.SQLITE_DENY
    table_name = table.lower() if isinstance(table, str) else ''
    if action == sqlite3.SQLITE_INSERT:
        return sqlite3.SQLITE_OK if table_name in _AUDIO_ASSET_INSERT_TABLES else sqlite3.SQLITE_DENY
    if action in (sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
        return sqlite3.SQLITE_DENY
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


class PostCommitTransaction:
    """Scoped post-COMMIT expression transaction with no world-fact authority."""

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection
        self._active = True
        self._thread = threading.get_ident()

    def execute(self, sql: str, parameters: tuple = ()) -> list[dict]:
        if not self._active or threading.get_ident() != self._thread:
            raise StorageError('Transaction is no longer active on its writer')
        with closing(self._connection.execute(sql, parameters)) as cursor:
            return [dict(row) for row in cursor] if cursor.description else []


_POST_COMMIT_INSERT_TABLES = frozenset({'narrative_blocks'})
_POST_COMMIT_UPDATE_COLUMNS = {
    'turn_transactions': frozenset({'status', 'narrative_block_id', 'transaction_json'}),
}


def _post_commit_authorizer(action, table, column, database, _trigger):
    if database not in (None, 'main'):
        return sqlite3.SQLITE_DENY
    table_name = table.lower() if isinstance(table, str) else ''
    if action == sqlite3.SQLITE_INSERT:
        return sqlite3.SQLITE_OK if table_name in _POST_COMMIT_INSERT_TABLES else sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_UPDATE:
        allowed = _POST_COMMIT_UPDATE_COLUMNS.get(table_name, frozenset())
        return sqlite3.SQLITE_OK if column in allowed else sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_DELETE:
        return sqlite3.SQLITE_DENY
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def _presentation_authorizer(action, table, _column, database, _trigger):
    if database not in (None, 'main'):
        return sqlite3.SQLITE_DENY
    if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
        return sqlite3.SQLITE_OK if table.lower() in _PRESENTATION_TABLES else sqlite3.SQLITE_DENY
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


class DomainTransaction:
    """Synchronous, scoped SQL facade for trusted repositories; never given to AI.

    No commit/rollback/connection escapes. Specialized domain tables are supplied
    by future repository migrations, not replaced with a generic fact dictionary.
    """
    def __init__(self, connection: sqlite3.Connection, revision: int):
        self._connection = connection
        self.revision = revision
        self._active = True
        self._thread = threading.get_ident()

    def execute(self, sql: str, parameters: tuple = ()) -> list[dict]:
        if not self._active or threading.get_ident() != self._thread:
            raise StorageError('Transaction is no longer active on its writer')
        with closing(self._connection.execute(sql, parameters)) as cursor:
            return [dict(row) for row in cursor] if cursor.description else []


def _repository_authorizer(action, table, _column, database, _trigger):
    if database not in (None, 'main'):
        return sqlite3.SQLITE_DENY
    if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
        return sqlite3.SQLITE_DENY if table.lower() in _PROTECTED else sqlite3.SQLITE_OK
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


class DatabaseManager:
    """One bounded writer per world; read queries run on a separate small pool."""
    def __init__(self, paths: DatabasePaths, *, fault_hook: Callable[[str], None] | None):
        self.paths = paths
        self._fault_hook = fault_hook
        self._writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix='wom-domain-writer')
        self._readers = ThreadPoolExecutor(max_workers=2, thread_name_prefix='wom-domain-reader')
        self._capacity = asyncio.Semaphore(64)
        self._closing = False
        self._close_task = None
        self._connection = None
        self._lock_fd = None
        self.store_id = ''
        self._world_identity = None

    @classmethod
    async def open(cls, paths: DatabasePaths, *, expected_sqlite_version: str | None = None,
                   fault_hook: Callable[[str], None] | None = None) -> DatabaseManager:
        # None is the production path: exact approved version AND the private bundled
        # driver are mandatory. An explicit version is compatibility-test injection,
        # never an environment-driven production fallback.
        production = expected_sqlite_version is None
        expected = SQLITE_VERSION if production else expected_sqlite_version
        if (sqlite3.sqlite_version != expected or sqlite3.sqlite_version_info < (3, 37, 0)
                or (production and not BUNDLED_DATA_SQLITE)):
            raise StorageError('SQLite runtime does not match the required baseline')
        self = cls(paths.normalized(), fault_hook=fault_hook)
        try:
            await self._submit(self._open)
            return self
        except BaseException:
            await self.close()
            raise

    def _open(self):
        with closing(connect(self.paths.canon, readonly=True)) as canon:
            integrity(canon)
        self.paths.world.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = Path(str(self.paths.world) + '.writer.lock')
        self._lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        info = os.fstat(self._lock_fd)
        import stat
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
            raise StorageError('Invalid writer lease')
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise StorageError('Another Domain Writer owns this world') from None
        self._connection = connect(self.paths.world)
        initialize(self._connection, 'world', path=self.paths.world)
        meta = self._connection.execute('SELECT * FROM world_meta').fetchone()
        journal = self._connection.execute('SELECT count(*),coalesce(max(revision),0) FROM domain_commits').fetchone()
        outbox_count = self._connection.execute('SELECT count(*) FROM projection_outbox').fetchone()[0]
        if meta is None:
            if journal[0] or outbox_count:
                raise StorageError('World identity missing from existing history')
            self._connection.execute('INSERT INTO world_meta VALUES (1, ?, 0)', (str(uuid.uuid4()),))
            meta = self._connection.execute('SELECT * FROM world_meta').fetchone()
        if journal[0] != meta['revision'] or journal[1] != meta['revision'] or outbox_count != meta['revision']:
            raise StorageError('World revision and commit journal are inconsistent')
        self.store_id = meta['store_id']
        identity = self.paths.world.stat()
        self._world_identity = (identity.st_dev, identity.st_ino)
        self.paths.runtime.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with closing(connect(self.paths.runtime)) as runtime:
            initialize(runtime, 'runtime')
        # retrieval.db is deliberately lazy: corruption/rebuild does not block facts.

    async def _submit(self, operation, *, read: bool = False):
        if self._closing:
            raise StorageError('Database manager is closing')
        async with self._capacity:
            if self._closing:
                raise StorageError('Database manager is closing')
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(self._readers if read else self._writer, operation)
            cancelled = False
            while True:
                try:
                    result = await asyncio.shield(future)
                    break
                except asyncio.CancelledError:
                    cancelled = True
                    # Await the known operation, never enqueue it again.
                    if future.done():
                        result = future.result()
                        break
            if cancelled:
                raise asyncio.CancelledError
            return result

    async def close(self) -> None:
        if self._close_task is None:
            self._closing = True
            async def finish():
                def close_writer():
                    if self._connection is not None:
                        self._connection.close()
                        self._connection = None
                    if self._lock_fd is not None:
                        os.close(self._lock_fd)
                        self._lock_fd = None
                    # Never unlink the lease file: waiters may hold its inode.
                await asyncio.get_running_loop().run_in_executor(self._writer, close_writer)
                await asyncio.to_thread(self._writer.shutdown, wait=True)
                await asyncio.to_thread(self._readers.shutdown, wait=True)
            self._close_task = asyncio.create_task(finish())
        await asyncio.shield(self._close_task)

    async def read_world(self, sql: str, parameters: tuple = ()) -> list[dict]:
        def query():
            self._check_world_identity()
            return read_rows(self.paths.world, sql, tuple(parameters))
        return await self._submit(query, read=True)

    async def read_canon(self, sql: str, parameters: tuple = ()) -> list[dict]:
        return await self._submit(lambda: read_rows(self.paths.canon, sql, tuple(parameters)), read=True)

    async def post_commit_write(self, apply: Callable[[PostCommitTransaction], object]) -> object:
        """Persist post-COMMIT expression state without advancing world facts."""
        if not callable(apply):
            raise StorageError('Post-COMMIT write requires a synchronous repository operation')
        return await self._submit(lambda: self._post_commit_write(apply))

    def _post_commit_write(self, apply):
        self._check_world_identity()
        conn = self._connection
        conn.execute('BEGIN IMMEDIATE')
        tx = PostCommitTransaction(conn)
        conn.set_authorizer(_post_commit_authorizer)
        try:
            try:
                value = apply(tx)
                if inspect.isawaitable(value):
                    if inspect.iscoroutine(value):
                        value.close()
                    raise StorageError('Post-COMMIT repository transaction must not suspend')
            finally:
                tx._active = False
                conn.set_authorizer(None)
            conn.execute('COMMIT')
            return value
        except BaseException:
            conn.set_authorizer(None)
            if conn.in_transaction:
                conn.execute('ROLLBACK')
            raise

    async def audio_asset_write(self, apply: Callable[[AudioAssetTransaction], object]) -> object:
        """Insert a complete immutable media asset row without advancing world facts."""
        if not callable(apply):
            raise StorageError('Audio asset write requires a synchronous repository operation')
        return await self._submit(lambda: self._audio_asset_write(apply))

    def _audio_asset_write(self, apply):
        self._check_world_identity()
        conn = self._connection
        conn.execute('BEGIN IMMEDIATE')
        tx = AudioAssetTransaction(conn)
        conn.set_authorizer(_audio_asset_authorizer)
        try:
            try:
                value = apply(tx)
                if inspect.isawaitable(value):
                    if inspect.iscoroutine(value):
                        value.close()
                    raise StorageError('Audio asset repository transaction must not suspend')
            finally:
                tx._active = False
                conn.set_authorizer(None)
            conn.execute('COMMIT')
            return value
        except BaseException:
            conn.set_authorizer(None)
            if conn.in_transaction:
                conn.execute('ROLLBACK')
            raise

    async def presentation_write(self, apply: Callable[[PresentationTransaction], object]) -> object:
        """Persist presentation-only state without advancing Domain world revision."""
        if not callable(apply):
            raise StorageError('Presentation write requires a synchronous repository operation')
        return await self._submit(lambda: self._presentation_write(apply))

    def _presentation_write(self, apply):
        self._check_world_identity()
        conn = self._connection
        conn.execute('BEGIN IMMEDIATE')
        tx = PresentationTransaction(conn)
        conn.set_authorizer(_presentation_authorizer)
        try:
            try:
                value = apply(tx)
                if inspect.isawaitable(value):
                    if inspect.iscoroutine(value):
                        value.close()
                    raise StorageError('Presentation repository transaction must not suspend')
            finally:
                tx._active = False
                conn.set_authorizer(None)
            conn.execute('COMMIT')
            return value
        except BaseException:
            conn.set_authorizer(None)
            if conn.in_transaction:
                conn.execute('ROLLBACK')
            raise

    async def commit_resolved(self, request: CommitRequest,
                              apply: Callable[[DomainTransaction], object] | None = None) -> CommitResult:
        record = request.freeze()
        return await self._submit(lambda: self._commit(record, apply))

    def _hit(self, stage: str) -> None:
        if self._fault_hook is not None:
            self._fault_hook(stage)

    def _check_world_identity(self):
        check_file(self.paths.world, required=True)
        info = self.paths.world.stat()
        if (info.st_dev, info.st_ino) != self._world_identity:
            raise StorageError('World database replaced while writer was active')

    def _commit(self, record, apply):
        self._check_world_identity()
        conn = self._connection
        semantic = {key: value for key, value in record.items() if key not in {'trace_id', 'request_id', 'idempotency_key'}}
        digest = hashlib.sha256(_json(semantic).encode()).hexdigest()
        conn.execute('BEGIN IMMEDIATE')
        try:
            previous = conn.execute('SELECT * FROM domain_commits WHERE idempotency_key=?',
                                    (record['idempotency_key'],)).fetchone()
            if previous:
                if previous['request_digest'] != digest:
                    raise IdempotencyConflict('Idempotency key is already bound to a different operation')
                conn.execute('ROLLBACK')
                return CommitResult(previous['revision'], json.loads(previous['result_json']), True)
            current = conn.execute('SELECT revision FROM world_meta WHERE singleton=1').fetchone()[0]
            if current != record['expected_revision']:
                raise RevisionConflict('Expected world revision does not match')
            revision = current + 1
            self._hit('before_apply')
            tx = DomainTransaction(conn, revision)
            conn.set_authorizer(_repository_authorizer)
            try:
                value = apply(tx) if apply is not None else None
                if inspect.isawaitable(value):
                    if inspect.iscoroutine(value):
                        value.close()
                    raise StorageError('Repository transaction must not suspend')
                result_json = _json(value)
            finally:
                tx._active = False
                conn.set_authorizer(None)
            self._hit('after_apply')
            conn.execute('INSERT INTO domain_commits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                         (revision, record['worldline_id'], record['idempotency_key'], digest,
                          record['request_id'], record['trace_id'], record['world_time'],
                          datetime.now(timezone.utc).isoformat(), _json(record['operation']), result_json))
            for event in record['events']:
                conn.execute('INSERT INTO domain_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                             (event['event_id'], revision, record['worldline_id'], record['world_time'],
                              event['aggregate_id'], event['event_type'], event['cause_id'],
                              event['episode_id'], event['turn_id'], _json(event['payload'])))
            self._hit('after_events')
            conn.execute('INSERT INTO projection_outbox(revision) VALUES (?)', (revision,))
            conn.execute('UPDATE world_meta SET revision=? WHERE singleton=1', (revision,))
            self._hit('before_commit')
            conn.execute('COMMIT')
        except BaseException:
            conn.set_authorizer(None)
            if conn.in_transaction:
                conn.execute('ROLLBACK')
            raise
        self._hit('after_commit')
        return CommitResult(revision, json.loads(result_json), False)

    async def mark_projected(self, store_id: str, revision: int) -> None:
        """Internal projector acknowledgement, never a domain mutation or IPC API."""
        def acknowledge():
            self._check_world_identity()
            if store_id != self.store_id or type(revision) is not int or revision < 0:
                raise StorageError('Projection acknowledgement does not belong to this store')
            conn = self._connection
            conn.execute('BEGIN IMMEDIATE')
            try:
                current = conn.execute('SELECT revision FROM world_meta').fetchone()[0]
                if revision > current:
                    raise StorageError('Projection acknowledgement exceeds world revision')
                conn.execute('UPDATE projection_outbox SET processed=1 WHERE revision<=?', (revision,))
                conn.execute('COMMIT')
            except BaseException:
                if conn.in_transaction:
                    conn.execute('ROLLBACK')
                raise
        await self._submit(acknowledge)

    async def backup_world(self, target: Path) -> str:
        """Consistent database-only snapshot; assets/pack manifests are not yet covered."""
        def backup():
            self._check_world_identity()
            if target.exists() or target.is_symlink():
                raise StorageError('Backup destination already exists')
            fd, name = tempfile.mkstemp(prefix='.wom-backup-', dir=target.parent)
            os.close(fd)
            temporary = Path(name)
            try:
                with closing(sqlite3.connect(temporary, isolation_level=None)) as destination:
                    self._connection.backup(destination)
                    destination.execute('PRAGMA journal_mode=DELETE')
                    integrity(destination)
                with temporary.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                    os.fsync(stream.fileno())
                os.link(temporary, target)  # atomic, no overwrite on publication race
                directory_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                return digest
            finally:
                temporary.unlink(missing_ok=True)
        return await self._submit(backup)
