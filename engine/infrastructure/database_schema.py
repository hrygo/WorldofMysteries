"""Private storage bootstrap. Existing unknown schemas are rejected, never reset."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
from .sqlite_runtime import sqlite3
import os
import stat
import tempfile

SQLITE_VERSION = '3.53.4'
SCHEMA_VERSIONS = {'world': 10, 'retrieval': 1, 'runtime': 1}
SCHEMA_VERSION = SCHEMA_VERSIONS['world']
APPLICATION_IDS = {'world': 0x574F4D57, 'retrieval': 0x574F4D50, 'runtime': 0x574F4D52}


class StorageError(RuntimeError):
    """Storage boundary failure. Diagnostics do not echo payloads or user paths."""


def check_file(path: Path, *, required: bool = False) -> None:
    """Fail closed on symlinks, special files and multiply-linked database aliases."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        if required:
            raise StorageError('Required database is missing') from None
        return
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise StorageError('Database path must be an independent regular file')


def connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    check_file(path, required=readonly)
    # as_uri escapes ?, #, percent and non-ASCII names before appending parameters.
    conn = sqlite3.connect(path.absolute().as_uri() + ('?mode=ro' if readonly else '?mode=rwc'),
                           uri=True, isolation_level=None, timeout=5)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA trusted_schema=OFF')
        conn.execute('PRAGMA busy_timeout=5000')
        if readonly:
            conn.execute('PRAGMA query_only=ON')
        conn.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
        return conn
    except BaseException:
        conn.close()
        raise


def integrity(conn: sqlite3.Connection) -> None:
    if [row[0] for row in conn.execute('PRAGMA quick_check')] != ['ok']:
        raise StorageError('Database integrity check failed')
    if list(conn.execute('PRAGMA foreign_key_check')):
        raise StorageError('Database foreign key check failed')


def statements(text: str):
    """Split owned migration files with SQLite's parser, not a semicolon split."""
    statement = ''
    for line in text.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            yield statement
            statement = ''
    if statement.strip():
        raise StorageError('Incomplete migration statement')


def _migration_script(role: str, version: int) -> Path:
    directory = Path(__file__).with_name('migrations')
    candidates = sorted(directory.glob(f'{version:03}_{role}*.sql'))
    if len(candidates) != 1:
        raise StorageError('Migration registry is incomplete or ambiguous')
    return candidates[0]


def _apply_migration(conn: sqlite3.Connection, role: str, version: int) -> None:
    script = _migration_script(role, version)
    for statement in statements(script.read_text(encoding='utf-8')):
        conn.execute(statement)


def _validate_migration_backup(source: sqlite3.Connection, backup: Path, expected_id: int,
                               version: int) -> None:
    check_file(backup, required=True)
    with closing(connect(backup, readonly=True)) as snapshot:
        if snapshot.execute('PRAGMA application_id').fetchone()[0] != expected_id:
            raise StorageError('Migration backup belongs to another database role')
        if snapshot.execute('PRAGMA user_version').fetchone()[0] != version:
            raise StorageError('Migration backup has an unexpected schema version')
        source_meta = source.execute("SELECT store_id FROM world_meta WHERE singleton=1").fetchone()
        backup_meta = snapshot.execute("SELECT store_id FROM world_meta WHERE singleton=1").fetchone()
        if source_meta is None or backup_meta is None or source_meta[0] != backup_meta[0]:
            raise StorageError('Migration backup belongs to another world')
        integrity(snapshot)


def _ensure_world_migration_backup(conn: sqlite3.Connection, path: Path, version: int,
                                   target_version: int) -> Path:
    check_file(path, required=True)
    backup = path.with_name(f'{path.name}.pre-migration-v{version}-to-v{target_version}.bak')
    if backup.exists() or backup.is_symlink():
        _validate_migration_backup(conn, backup, APPLICATION_IDS['world'], version)
        return backup

    fd, name = tempfile.mkstemp(prefix='.wom-pre-migration-', dir=path.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        with closing(sqlite3.connect(temporary, isolation_level=None)) as destination:
            conn.backup(destination)
            integrity(destination)
        with closing(sqlite3.connect(temporary, isolation_level=None)) as snapshot:
            if snapshot.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_IDS['world']:
                raise StorageError('Migration backup identity mismatch')
            if snapshot.execute('PRAGMA user_version').fetchone()[0] != version:
                raise StorageError('Migration backup version mismatch')
        os.link(temporary, backup)
        with backup.open('rb') as stream:
            os.fsync(stream.fileno())
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return backup
    finally:
        temporary.unlink(missing_ok=True)


def initialize(conn: sqlite3.Connection, role: str, *, path: Path | None = None) -> None:
    expected_id = APPLICATION_IDS[role]
    expected_version = SCHEMA_VERSIONS[role]

    # A world upgrade is never attempted until a durable Online Backup snapshot
    # exists. New databases and non-world roles do not need a pre-migration copy.
    if role == 'world':
        identity = conn.execute('PRAGMA application_id').fetchone()[0]
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if identity == expected_id and 0 < version < expected_version:
            if path is None:
                raise StorageError('World migration requires its owned database path')
            _ensure_world_migration_backup(conn, path, version, expected_version)

    # Inspect AND initialize/migrate under the same write lock. runtime.db is
    # shared by distinct worlds; an earlier observation can otherwise become stale.
    conn.execute('BEGIN IMMEDIATE')
    try:
        identity = conn.execute('PRAGMA application_id').fetchone()[0]
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        existing = conn.execute("SELECT count(*) FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'").fetchone()[0]

        if identity == 0 and version == 0 and existing == 0:
            for migration in range(1, expected_version + 1):
                _apply_migration(conn, role, migration)
            conn.execute(f'PRAGMA application_id={expected_id}')
            conn.execute(f'PRAGMA user_version={expected_version}')
        elif identity != expected_id or version <= 0 or version > expected_version:
            raise StorageError('Unrecognized database schema; migration is required')
        elif version < expected_version:
            if role != 'world' or path is None:
                raise StorageError('Database migration is not available for this role')
            for migration in range(version + 1, expected_version + 1):
                _apply_migration(conn, role, migration)
            conn.execute(f'PRAGMA user_version={expected_version}')

        conn.execute('COMMIT')
    except BaseException:
        if conn.in_transaction:
            conn.execute('ROLLBACK')
        raise
    if conn.execute('PRAGMA journal_mode=WAL').fetchone()[0] != 'wal':
        raise StorageError('WAL mode is required')
    conn.execute('PRAGMA synchronous=FULL')
    if conn.execute('PRAGMA synchronous').fetchone()[0] != 2:
        raise StorageError('FULL durability is required')
    integrity(conn)


def read_rows(path: Path, sql: str, parameters: tuple = ()) -> list[dict]:
    """Internal repository query, not an IPC/AI SQL endpoint."""
    with closing(connect(path, readonly=True)) as conn:
        # query_only alone can be switched off by PRAGMA; the authorizer closes it.
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                   sqlite3.SQLITE_RECURSIVE}
        conn.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
        return [dict(row) for row in conn.execute(sql, parameters)]
