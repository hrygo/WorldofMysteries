"""Private storage bootstrap. Existing unknown schemas are rejected, never reset."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
from .sqlite_runtime import sqlite3
import stat

SQLITE_VERSION = '3.53.4'
SCHEMA_VERSION = 1
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


def initialize(conn: sqlite3.Connection, role: str) -> None:
    expected_id = APPLICATION_IDS[role]
    # Inspect AND initialize under the same write lock. runtime.db is shared
    # by distinct worlds; an earlier empty-schema observation can become stale.
    conn.execute('BEGIN IMMEDIATE')
    try:
        identity = conn.execute('PRAGMA application_id').fetchone()[0]
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        existing = conn.execute("SELECT count(*) FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'").fetchone()[0]
        if (identity, version) != (expected_id, SCHEMA_VERSION):
            if identity != 0 or version != 0 or existing:
                raise StorageError('Unrecognized database schema; migration is required')
            # Only brand-new files are initialized. No existing world upgrade is implied.
            script = Path(__file__).with_name('migrations') / f'001_{role}.sql'
            for statement in statements(script.read_text(encoding='utf-8')):
                conn.execute(statement)
            conn.execute(f'PRAGMA application_id={expected_id}')
            conn.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
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
