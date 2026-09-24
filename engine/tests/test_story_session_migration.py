"""Safe ordered world.db v1→v5 migration and Story/Narrative/Delivery schema tests."""
from __future__ import annotations

from contextlib import closing
import hashlib
from pathlib import Path

import pytest

from engine.infrastructure import database_schema
from engine.infrastructure.database_schema import (
    APPLICATION_IDS,
    SCHEMA_VERSION,
    SCHEMA_VERSIONS,
    StorageError,
    connect,
    initialize,
    integrity,
    statements,
)


def _build_v1_world(path: Path, *, store_id: str = "store-v1") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        script = Path(database_schema.__file__).with_name("migrations") / "001_world.sql"
        for statement in statements(script.read_text(encoding="utf-8")):
            conn.execute(statement)
        conn.execute(f"PRAGMA application_id={APPLICATION_IDS['world']}")
        conn.execute("PRAGMA user_version=1")
        conn.execute("INSERT INTO world_meta VALUES (1, ?, 0)", (store_id,))
        # Represents pre-existing specialized user data; migration must preserve it.
        conn.execute("CREATE TABLE legacy_story_marker(id TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT")
        conn.execute("INSERT INTO legacy_story_marker VALUES ('existing', 'preserve-me')")
        conn.execute("COMMIT")
        integrity(conn)


def _version(path: Path) -> int:
    with closing(connect(path, readonly=True)) as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def _tables(path: Path) -> set[str]:
    with closing(connect(path, readonly=True)) as conn:
        return {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        }


def test_fresh_world_initializes_directly_to_v5_without_migration_backup(tmp_path):
    path = tmp_path / "Worlds" / "fresh" / "world.db"
    path.parent.mkdir(parents=True)
    with closing(connect(path)) as conn:
        initialize(conn, "world", path=path)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 5
        integrity(conn)
    assert {"story_sessions", "story_state_deltas", "turn_transactions", "voice_bindings", "narrative_blocks", "delivery_cursors"} <= _tables(path)
    assert not list(path.parent.glob("*.pre-migration-*.bak"))


def test_existing_v1_world_is_backed_up_then_migrated_without_data_loss(tmp_path):
    path = tmp_path / "Worlds" / "existing" / "world.db"
    _build_v1_world(path)

    with closing(connect(path)) as conn:
        initialize(conn, "world", path=path)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        assert conn.execute(
            "SELECT value FROM legacy_story_marker WHERE id='existing'"
        ).fetchone()[0] == "preserve-me"
        integrity(conn)

    backup = path.with_name("world.db.pre-migration-v1-to-v5.bak")
    assert backup.is_file() and _version(backup) == 1
    assert "story_sessions" not in _tables(backup)
    with closing(connect(backup, readonly=True)) as snapshot:
        assert snapshot.execute("SELECT store_id FROM world_meta").fetchone()[0] == "store-v1"
        assert snapshot.execute("SELECT value FROM legacy_story_marker").fetchone()[0] == "preserve-me"
        integrity(snapshot)


def test_migration_failure_rolls_back_source_and_leaves_recoverable_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "Worlds" / "failure" / "world.db"
    _build_v1_world(path, store_id="store-failure")
    original = database_schema._apply_migration

    def fail_after_partial_ddl(conn, role, version):
        if role == "world" and version == 2:
            conn.execute("CREATE TABLE must_rollback(id INTEGER) STRICT")
            raise RuntimeError("injected migration failure")
        return original(conn, role, version)

    monkeypatch.setattr(database_schema, "_apply_migration", fail_after_partial_ddl)
    with closing(connect(path)) as conn:
        with pytest.raises(RuntimeError, match="injected migration failure"):
            initialize(conn, "world", path=path)

    assert _version(path) == 1
    assert "must_rollback" not in _tables(path)
    assert "story_sessions" not in _tables(path)
    backup = path.with_name("world.db.pre-migration-v1-to-v5.bak")
    assert backup.is_file() and _version(backup) == 1

    monkeypatch.setattr(database_schema, "_apply_migration", original)
    with closing(connect(path)) as conn:
        initialize(conn, "world", path=path)
    assert _version(path) == 5


def test_repeated_open_does_not_replace_migration_backup(tmp_path):
    path = tmp_path / "Worlds" / "repeat" / "world.db"
    _build_v1_world(path)
    with closing(connect(path)) as conn:
        initialize(conn, "world", path=path)
    backup = path.with_name("world.db.pre-migration-v1-to-v5.bak")
    before = hashlib.sha256(backup.read_bytes()).hexdigest()

    with closing(connect(path)) as conn:
        initialize(conn, "world", path=path)

    assert hashlib.sha256(backup.read_bytes()).hexdigest() == before
    assert _version(path) == 5


@pytest.mark.parametrize("role", ["runtime", "retrieval"])
def test_non_world_database_versions_remain_v1(tmp_path, role):
    path = tmp_path / f"{role}.db"
    with closing(connect(path)) as conn:
        initialize(conn, role)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSIONS[role] == 1


def test_future_world_schema_still_fails_closed(tmp_path):
    path = tmp_path / "future.db"
    with closing(connect(path)) as conn:
        conn.execute(f"PRAGMA application_id={APPLICATION_IDS['world']}")
        conn.execute("PRAGMA user_version=99")
        conn.execute("CREATE TABLE future_data(id INTEGER PRIMARY KEY) STRICT")
    before = path.read_bytes()

    with closing(connect(path)) as conn:
        with pytest.raises(StorageError, match="migration"):
            initialize(conn, "world", path=path)

    assert path.read_bytes() == before


def _build_v3_world(path: Path, *, store_id: str = "store-v3") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        directory = Path(database_schema.__file__).with_name("migrations")
        for version in (1, 2, 3):
            script = next(directory.glob(f"{version:03}_world*.sql"))
            for statement in statements(script.read_text(encoding="utf-8")):
                conn.execute(statement)
        conn.execute(f"PRAGMA application_id={APPLICATION_IDS['world']}")
        conn.execute("PRAGMA user_version=3")
        conn.execute("INSERT INTO world_meta VALUES (1, ?, 0)", (store_id,))
        conn.execute("COMMIT")
        integrity(conn)


def test_existing_v3_world_gets_narrative_table_with_recoverable_backup(tmp_path):
    path = tmp_path / "Worlds" / "v3-existing" / "world.db"
    _build_v3_world(path)

    with closing(connect(path)) as conn:
        initialize(conn, "world", path=path)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        integrity(conn)

    assert "narrative_blocks" in _tables(path)
    assert "delivery_cursors" in _tables(path)
    backup = path.with_name("world.db.pre-migration-v3-to-v5.bak")
    assert backup.is_file() and _version(backup) == 3
    assert "narrative_blocks" not in _tables(backup)



def _build_v4_world(path: Path, *, store_id: str = "store-v4") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        directory = Path(database_schema.__file__).with_name("migrations")
        for version in (1, 2, 3, 4):
            script = next(directory.glob(f"{version:03}_world*.sql"))
            for statement in statements(script.read_text(encoding="utf-8")):
                conn.execute(statement)
        conn.execute(f"PRAGMA application_id={APPLICATION_IDS['world']}")
        conn.execute("PRAGMA user_version=4")
        conn.execute("INSERT INTO world_meta VALUES (1, ?, 1)", (store_id,))
        conn.execute(
            "INSERT INTO domain_commits("
            "revision,worldline_id,idempotency_key,request_digest,request_id,"
            "trace_id,world_time,commit_time,operation_json,result_json"
            ") VALUES (1,?,?,?,?,?,?,?,?,?)",
            (
                "line-v4",
                "idem-v4",
                "digest-v4",
                "request-v4",
                "trace-v4",
                "1895-01-01T00:00:00Z",
                "2026-09-24T00:00:00Z",
                "{}",
                "{}",
            ),
        )
        conn.execute(
            "INSERT INTO story_sessions("
            "id,world_id,worldline_id,protagonist_id,story_seed_id,"
            "base_world_revision,base_character_revision,base_story_revision,"
            "story_revision,status,story_state_json,committed_world_revision"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "session-v4",
                "world-v4",
                "line-v4",
                "klein-v4",
                "seed-v4",
                1,
                0,
                0,
                0,
                "active",
                '{"schema_version":"1.0","id":"session-v4"}',
                1,
            ),
        )
        conn.execute("COMMIT")
        integrity(conn)


def test_existing_v4_world_gets_delivery_cursor_table_with_recoverable_backup(tmp_path):
    path = tmp_path / "Worlds" / "v4-existing" / "world.db"
    _build_v4_world(path)

    with closing(connect(path)) as conn:
        initialize(conn, "world", path=path)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        assert conn.execute(
            "SELECT session_id FROM story_sessions WHERE session_id='session-v4'"
        ).fetchone()[0] == "session-v4"
        integrity(conn)

    assert "delivery_cursors" in _tables(path)
    backup = path.with_name("world.db.pre-migration-v4-to-v5.bak")
    assert backup.is_file() and _version(backup) == 4
    assert "narrative_blocks" in _tables(backup)
    assert "delivery_cursors" not in _tables(backup)
