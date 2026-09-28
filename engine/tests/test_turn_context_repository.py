"""Durable, minimal bindings for dynamically authorized turn context."""
from __future__ import annotations

import hashlib
import json
import sqlite3 as stdlib_sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from application.turn_input import TurnInputCommand, TurnInputStatus
from contracts import BaseRevisions, InputMode, PlayerAdvice
from infrastructure import database_schema
from infrastructure.database_manager import (
    CommitRequest,
    DatabaseManager,
    DatabasePaths,
    StorageError,
    StoredEvent,
)
from infrastructure.database_schema import (
    APPLICATION_IDS,
    SCHEMA_VERSIONS,
    connect,
    initialize,
    statements,
)
from infrastructure.player_advice_repository import SQLitePlayerAdviceRepository
from infrastructure.sqlite_runtime import sqlite3
from infrastructure.turn_context_repository import (
    SQLiteTurnContextRepository,
    TurnContextBinding,
    TurnContextSource,
    TurnContextStorageConflict,
)
from infrastructure.turn_intake_repository import SQLiteTurnInputCommandPort


async def open_database(tmp_path: Path):
    paths = DatabasePaths.for_world(tmp_path / "app-support", "world-context-bindings")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    database = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    return database, paths


def command(
    *,
    input_turn_id: str = "input-binding-1",
    turn_id: str = "turn-binding-1",
) -> TurnInputCommand:
    raw_input = "我想先观察现场。"
    return TurnInputCommand(
        input_turn_id=input_turn_id,
        session_id="session-binding-1",
        turn_id=turn_id,
        idempotency_key=f"turn-input:{input_turn_id}",
        input_mode=InputMode.TEXT,
        raw_input=raw_input,
        input_sha256=hashlib.sha256(raw_input.encode("utf-8")).hexdigest(),
        base_revisions=BaseRevisions(world=0, character=0, story=0),
        public_expected_store_revision=0,
    )


def advice(
    *,
    turn_id: str = "turn-binding-1",
    raw_input: str | None = None,
    advice_id: str = "advice-binding-1",
) -> PlayerAdvice:
    return PlayerAdvice.model_validate(
        {
            "schema_version": "1.0",
            "id": advice_id,
            "turn_id": turn_id,
            "raw_input": raw_input or command(turn_id=turn_id).raw_input,
            "input_mode": "text",
            "primary_intent": "observe",
            "proposed_actions": ["observe_scene"],
            "confidence": 0.9,
        }
    )


def binding(
    *,
    turn_id: str = "turn-binding-1",
    input_turn_id: str = "input-binding-1",
    stage: str = "interpretation",
    source_revision: int = 7,
) -> TurnContextBinding:
    return TurnContextBinding.from_manifest(
        turn_id=turn_id,
        stage=stage,
        input_turn_id=input_turn_id,
        source_store_revision=11,
        source_story_revision=4,
        policy_revision="visibility-v1",
        content_digest="content-pack-sha256",
        lineage_digest="lineage-sha256",
        manifest=(
            TurnContextSource(
                source_id="knowledge:character-a:proposition-p",
                source_revision=source_revision,
                fingerprint="a" * 64,
            ),
            TurnContextSource(
                source_id="world-event:event-7",
                source_revision=source_revision + 1,
                fingerprint="b" * 64,
            ),
        ),
    )


async def receive_input(database: DatabaseManager) -> None:
    await SQLiteTurnInputCommandPort(database).receive(command())


async def test_interpretation_and_canonical_binding_are_saved_together(tmp_path):
    database, _ = await open_database(tmp_path)
    try:
        await receive_input(database)
        stored = await SQLitePlayerAdviceRepository(database).publish(
            "input-binding-1",
            advice(),
            interpreter_revision="authorized-interpreter-v1",
            context_binding=binding(),
        )

        repository = SQLiteTurnContextRepository(database)
        saved = await repository.load(
            turn_id="turn-binding-1",
            stage="interpretation",
            context_revision=binding().context_revision,
        )
        assert saved == binding()
        assert not stored.replayed
        assert saved is not None
        assert saved.context_revision == binding().context_revision
        assert saved.manifest_digest == hashlib.sha256(
            saved.manifest_json.encode("utf-8")
        ).hexdigest()
        assert json.loads(saved.manifest_json) == [
            {
                "source_id": "knowledge:character-a:proposition-p",
                "source_revision": 7,
                "fingerprint": "a" * 64,
            },
            {
                "source_id": "world-event:event-7",
                "source_revision": 8,
                "fingerprint": "b" * 64,
            },
        ]
        assert (await database.read_world(
            "SELECT count(*) AS n FROM turn_advice_interpretations"
        ))[0]["n"] == 1
        assert (await database.read_world(
            "SELECT count(*) AS n FROM turn_context_bindings"
        ))[0]["n"] == 1
        assert (await database.read_world(
            "SELECT revision FROM world_meta WHERE singleton=1"
        ))[0]["revision"] == 0
    finally:
        await database.close()


async def test_binding_failure_rolls_back_new_interpretation(tmp_path, monkeypatch):
    database, _ = await open_database(tmp_path)
    try:
        await receive_input(database)
        contexts = SQLiteTurnContextRepository(database)
        save_in_transaction = contexts.save_in_transaction

        def fail_after_binding_insert(tx, value):
            save_in_transaction(tx, value)
            raise RuntimeError("injected binding persistence failure")

        monkeypatch.setattr(contexts, "save_in_transaction", fail_after_binding_insert)
        advice_repository = SQLitePlayerAdviceRepository(
            database,
            context_repository=contexts,
        )
        with pytest.raises(RuntimeError, match="injected binding persistence failure"):
            await advice_repository.publish(
                "input-binding-1",
                advice(),
                interpreter_revision="authorized-interpreter-v1",
                context_binding=binding(),
            )

        assert (await database.read_world(
            "SELECT count(*) AS n FROM turn_advice_interpretations"
        ))[0]["n"] == 0
        assert (await database.read_world(
            "SELECT count(*) AS n FROM turn_context_bindings"
        ))[0]["n"] == 0
        frozen = await SQLitePlayerAdviceRepository(database).load_input(
            "input-binding-1"
        )
        assert frozen is not None and frozen.status is TurnInputStatus.RECEIVED
    finally:
        await database.close()


async def test_stale_context_revision_is_rejected_without_rebinding_or_cancelling_input(
    tmp_path,
):
    database, _ = await open_database(tmp_path)
    try:
        await receive_input(database)
        advice_repository = SQLitePlayerAdviceRepository(database)
        await advice_repository.publish(
            "input-binding-1",
            advice(),
            interpreter_revision="authorized-interpreter-v1",
            context_binding=binding(),
        )

        contexts = SQLiteTurnContextRepository(database)
        with pytest.raises(TurnContextStorageConflict) as raised:
            await contexts.save(binding(source_revision=70))
        assert raised.value.code in {"revision_conflict", "context_stale"}

        with pytest.raises(TurnContextStorageConflict) as replay_error:
            await advice_repository.publish(
                "input-binding-1",
                advice(advice_id="stale-replay"),
                interpreter_revision="authorized-interpreter-v2",
                context_binding=binding(source_revision=70),
            )
        assert replay_error.value.code == "context_stale"
        persisted = await contexts.load(
            turn_id="turn-binding-1",
            stage="interpretation",
        )
        assert persisted == binding()
        frozen = await advice_repository.load_input("input-binding-1")
        assert frozen is not None and frozen.status is TurnInputStatus.RECEIVED
    finally:
        await database.close()


async def test_legacy_interpretation_is_not_rebound_to_a_new_context(tmp_path):
    database, _ = await open_database(tmp_path)
    try:
        await receive_input(database)
        advice_repository = SQLitePlayerAdviceRepository(database)
        original = await advice_repository.publish(
            "input-binding-1",
            advice(),
            interpreter_revision="legacy-interpreter-v1",
        )

        with pytest.raises(TurnContextStorageConflict) as raised:
            await advice_repository.publish(
                "input-binding-1",
                advice(advice_id="attempted-rebind"),
                interpreter_revision="authorized-interpreter-v2",
                context_binding=binding(),
            )
        assert raised.value.code == "legacy_context_unbound"
        assert (await advice_repository.load_advice("input-binding-1")).advice == original.advice
        assert (await database.read_world(
            "SELECT count(*) AS n FROM turn_context_bindings"
        ))[0]["n"] == 0
        frozen = await advice_repository.load_input("input-binding-1")
        assert frozen is not None and frozen.status is TurnInputStatus.RECEIVED
    finally:
        await database.close()


async def test_turn_context_table_is_writable_only_inside_dedicated_turn_command_port(
    tmp_path,
):
    database, _ = await open_database(tmp_path)
    try:
        await receive_input(database)
        repository = SQLitePlayerAdviceRepository(database)
        await repository.publish(
            "input-binding-1",
            advice(),
            interpreter_revision="authorized-interpreter-v1",
            context_binding=binding(),
        )
        before = await database.read_world(
            "SELECT count(*) AS n FROM turn_context_bindings"
        )
        assert before[0]["n"] == 1

        request = CommitRequest(
            worldline_id="line.one",
            world_time="1349-07-03T10:00:00",
            expected_revision=0,
            idempotency_key="context-write-denied",
            request_id="context-write-denied",
            trace_id="context-write-denied",
            operation={"kind": "unauthorized-context-write"},
            events=(
                StoredEvent(
                    "event-context-write-denied",
                    "hero",
                    "test.denied",
                    {},
                ),
            ),
        )

        def domain_writer(tx):
            tx.execute(
                "INSERT INTO turn_context_bindings("
                "turn_id,stage,context_revision,input_turn_id,"
                "source_store_revision,source_story_revision,policy_revision,"
                "content_digest,lineage_digest,manifest_json,manifest_digest"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "turn-binding-1",
                    "action",
                    "0" * 64,
                    "input-binding-1",
                    11,
                    4,
                    "visibility-v1",
                    "content-pack-sha256",
                    "lineage-sha256",
                    "[]",
                    "0" * 64,
                ),
            )

        with pytest.raises(stdlib_sqlite3.DatabaseError):
            await database.commit_resolved(request, domain_writer)

        assert (await database.read_world(
            "SELECT count(*) AS n FROM turn_context_bindings"
        ))[0]["n"] == 1
        assert (await database.read_world(
            "SELECT revision FROM world_meta WHERE singleton=1"
        ))[0]["revision"] == 0
    finally:
        await database.close()


def test_binding_revision_is_server_derived_and_manifest_rejects_payload_or_credentials():
    manifest_source = {
        "source_id": "knowledge:character-a:proposition-p",
        "source_revision": 7,
        "fingerprint": "a" * 64,
        "content": "raw evidence body",
        "api_key": "must-not-be-stored",
    }
    with pytest.raises(StorageError, match="manifest"):
        TurnContextBinding.from_manifest(
            turn_id="turn-binding-1",
            stage="interpretation",
            input_turn_id="input-binding-1",
            source_store_revision=11,
            source_story_revision=4,
            policy_revision="visibility-v1",
            content_digest="content-pack-sha256",
            lineage_digest="lineage-sha256",
            manifest=(manifest_source,),
        )

    derived = binding()
    assert len(derived.context_revision) == 64
    assert derived.context_revision != derived.manifest_digest
    assert "raw evidence body" not in derived.manifest_json
    assert "must-not-be-stored" not in derived.manifest_json


def _build_v13_world(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        for version in range(1, 14):
            script = database_schema._migration_script("world", version)
            for statement in statements(script.read_text(encoding="utf-8")):
                connection.execute(statement)
        connection.execute(f"PRAGMA application_id={APPLICATION_IDS['world']}")
        connection.execute("PRAGMA user_version=13")
        connection.execute("INSERT INTO world_meta VALUES (1, 'store-v13', 0)")
        connection.execute(
            "CREATE TABLE legacy_context_marker("
            "id TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT"
        )
        connection.execute(
            "INSERT INTO legacy_context_marker VALUES ('existing', 'preserve-me')"
        )
        connection.execute("COMMIT")


def _version(path: Path) -> int:
    with closing(connect(path, readonly=True)) as connection:
        return connection.execute("PRAGMA user_version").fetchone()[0]


def _table_names(path: Path) -> set[str]:
    with closing(connect(path, readonly=True)) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        }


def test_v13_to_v14_migration_failure_rolls_back_and_recovers_from_backup(
    tmp_path, monkeypatch
):
    path = tmp_path / "world" / "world.db"
    _build_v13_world(path)
    original = database_schema._apply_migration

    def fail_after_partial_v14_ddl(connection, role, version):
        if role == "world" and version == 14:
            connection.execute(
                "CREATE TABLE must_rollback_v14(id INTEGER) STRICT"
            )
            raise RuntimeError("injected v14 migration failure")
        return original(connection, role, version)

    monkeypatch.setattr(
        database_schema, "_apply_migration", fail_after_partial_v14_ddl
    )
    with closing(connect(path)) as connection, pytest.raises(
        RuntimeError, match="injected v14 migration failure"
    ):
        initialize(connection, "world", path=path)

    assert _version(path) == 13
    assert "must_rollback_v14" not in _table_names(path)
    backup = path.with_name("world.db.pre-migration-v13-to-v14.bak")
    assert backup.is_file() and _version(backup) == 13

    monkeypatch.setattr(database_schema, "_apply_migration", original)
    with closing(connect(path)) as connection:
        initialize(connection, "world", path=path)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 14
        assert connection.execute(
            "SELECT value FROM legacy_context_marker WHERE id='existing'"
        ).fetchone()[0] == "preserve-me"
    assert SCHEMA_VERSIONS["world"] == 14
    assert "turn_context_bindings" in _table_names(path)
