"""Atomic Story Session bootstrap persistence and migration tests."""
from __future__ import annotations

import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3 as stdlib_sqlite3

import pytest

from application.story_initialization import (
    GOLDEN_SCENARIO_ID,
    SUPPORTED_ADVICE,
    StoryInitializationService,
    TrustedScenarioBundle,
)
from application.story_session_open import (
    OpenStorySessionCommand,
    StorySessionOpenError,
    StorySessionOpenService,
)
from contracts import StorySession
from engine.infrastructure import database_schema
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.database_schema import (
    APPLICATION_IDS,
    StorageError,
    connect,
    initialize,
    statements,
)
from infrastructure.sqlite_runtime import sqlite3
from infrastructure.story_bootstrap_repository import (
    SQLiteStoryBootstrapRepository,
    StoryBootstrapError,
)
from infrastructure.story_session_open_repository import SQLiteStorySessionOpenPort

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "golden_001"
RUNTIME = ROOT / "docs" / "07_工程启动" / "golden_001_runtime"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_digest(payload: dict) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "content_digest"}
    return hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _bundle_payload() -> dict:
    advice = _read(FIXTURES / "turns" / "01_advice.json")
    advice["input_mode"] = "text"
    advice["raw_input"] = SUPPORTED_ADVICE
    payload = {
        "scenario_id": GOLDEN_SCENARIO_ID,
        "content_version": "1",
        "policy_version": "golden001-opening-policy",
        "seed": _read(FIXTURES / "seed.json"),
        "world": _read(FIXTURES / "world.json"),
        "character": _read(FIXTURES / "character.json"),
        "knowledge": [
            _read(path)
            for path in sorted((FIXTURES / "knowledge").glob("*.json"))
        ],
        "presentation": {
            "scenario_title": "不存在的预约",
            "scene_display_name": "哈维诊所 · 诊室",
            "clue_display_names": {"clue_doctor_pause": "医生的停顿"},
        },
        "advice_template": advice,
        "action_intent_template": _read(
            RUNTIME / "mock" / "01_action_intent.json"
        ),
    }
    payload["content_digest"] = _canonical_digest(payload)
    return payload


def _bundle() -> TrustedScenarioBundle:
    return TrustedScenarioBundle.model_validate(_bundle_payload())


class Source:
    def __init__(self, bundle: TrustedScenarioBundle | None = None) -> None:
        self.bundle = bundle or _bundle()

    async def load(self, scenario_id: str) -> TrustedScenarioBundle:
        return self.bundle


async def _open_database(tmp_path: Path) -> tuple[DatabaseManager, DatabasePaths]:
    paths = DatabasePaths.for_world(tmp_path / "app-support", "world-bootstrap")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    database = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    return database, paths


async def _rows(database: DatabaseManager, table: str) -> list[dict]:
    return await database.read_world(f"SELECT * FROM {table}")


async def _initialized(source: Source | None = None):
    return await StoryInitializationService(source or Source()).initialize(
        scenario_id=GOLDEN_SCENARIO_ID,
        open_request_id="open_first_001",
    )


async def _open_with_bootstrap(database: DatabaseManager, initialized):
    return await StorySessionOpenService(SQLiteStorySessionOpenPort(database)).open(
        OpenStorySessionCommand(
            initial_session=initialized.initial_session,
            open_request_id="open_first_001",
            store_expected_revision=0,
            request_id="request_open_first_001",
            trace_id="trace_open_first_001",
            bootstrap=initialized.bootstrap,
        )
    )


@pytest.mark.asyncio
async def test_open_writes_bootstrap_in_the_same_commit_and_reloads_it(tmp_path):
    database, paths = await _open_database(tmp_path)
    initialized = await _initialized()
    try:
        result = await _open_with_bootstrap(database, initialized)

        assert result.opened_store_revision == 1
        assert result.snapshot.session.id == initialized.initial_session.id
        assert len(await _rows(database, "story_session_bootstraps")) == 1
        row = (await _rows(database, "story_session_bootstraps"))[0]
        assert row["session_id"] == initialized.initial_session.id
        assert row["scenario_id"] == GOLDEN_SCENARIO_ID
        assert row["content_digest"] == initialized.bootstrap.content_digest
        assert row["opened_store_revision"] == 1
        assert await _rows(database, "domain_commits")
    finally:
        await database.close()

    reopened = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    try:
        loaded = await SQLiteStoryBootstrapRepository(reopened).load(
            initialized.initial_session.id
        )
        assert loaded == initialized.bootstrap
        assert loaded.initial_session == initialized.initial_session
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_bootstrap_write_failure_rolls_back_session_and_commit(tmp_path):
    database, _ = await _open_database(tmp_path)
    initialized = await _initialized()

    def fail(stage: str) -> None:
        if stage == "before_commit":
            raise RuntimeError("injected bootstrap failure")

    database._fault_hook = fail
    try:
        with pytest.raises(RuntimeError, match="bootstrap"):
            await _open_with_bootstrap(database, initialized)

        assert await _rows(database, "story_sessions") == []
        assert await _rows(database, "story_session_bootstraps") == []
        assert await _rows(database, "domain_commits") == []
        assert await _rows(database, "domain_events") == []
        assert await _rows(database, "projection_outbox") == []
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_same_open_key_with_different_bootstrap_is_rejected_after_commit(tmp_path):
    database, _ = await _open_database(tmp_path)
    first = await _initialized()
    try:
        await _open_with_bootstrap(database, first)

        changed_payload = _bundle_payload()
        changed_payload["seed"]["premise"] = "另一份仍然合法的可信内容"
        changed_payload["content_digest"] = _canonical_digest(changed_payload)
        changed = await _initialized(Source(TrustedScenarioBundle.model_validate(changed_payload)))

        with pytest.raises(StorySessionOpenError, match="session_open_identity_conflict"):
            await _open_with_bootstrap(database, changed)

        assert len(await _rows(database, "story_sessions")) == 1
        assert len(await _rows(database, "story_session_bootstraps")) == 1
        assert len(await _rows(database, "domain_commits")) == 1
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_legacy_session_without_bootstrap_fails_closed_on_required_read(tmp_path):
    database, _ = await _open_database(tmp_path)
    initialized = await _initialized()
    try:
        # Internal opener compatibility path intentionally writes no bootstrap.
        await StorySessionOpenService(SQLiteStorySessionOpenPort(database)).open(
            OpenStorySessionCommand(
                initial_session=initialized.initial_session,
                open_request_id="legacy_open_001",
                store_expected_revision=0,
                request_id="legacy_request",
                trace_id="legacy_trace",
            )
        )

        repository = SQLiteStoryBootstrapRepository(database)
        assert await repository.load(initialized.initial_session.id) is None
        with pytest.raises(StoryBootstrapError, match="recovery_required"):
            await repository.require(initialized.initial_session.id)
    finally:
        await database.close()


def _build_v9_world(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        directory = Path(database_schema.__file__).with_name("migrations")
        for version in range(1, 10):
            script = next(directory.glob(f"{version:03}_world*.sql"))
            for statement in statements(script.read_text(encoding="utf-8")):
                connection.execute(statement)
        connection.execute(f"PRAGMA application_id={APPLICATION_IDS['world']}")
        connection.execute("PRAGMA user_version=9")
        connection.execute("INSERT INTO world_meta VALUES (1, ?, 0)", ("store-v9",))
        connection.execute(
            "CREATE TABLE legacy_bootstrap_marker("
            "id TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT"
        )
        connection.execute(
            "INSERT INTO legacy_bootstrap_marker VALUES ('preserve-me','preserve-me')"
        )
        connection.execute("COMMIT")


def test_v9_world_migrates_to_v10_with_backup_and_preserves_legacy_data(tmp_path):
    path = tmp_path / "Worlds" / "v9" / "world.db"
    _build_v9_world(path)

    with connect(path) as connection:
        initialize(connection, "world", path=path)
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 10
        assert connection.execute(
            "SELECT value FROM legacy_bootstrap_marker WHERE id='preserve-me'"
        ).fetchone()[0] == "preserve-me"

    backup = path.with_name("world.db.pre-migration-v9-to-v10.bak")
    assert backup.is_file()
    assert backup.exists()
    with connect(backup, readonly=True) as snapshot:
        assert snapshot.execute("PRAGMA user_version").fetchone()[0] == 9
        assert "story_session_bootstraps" not in {
            row[0] for row in snapshot.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        }
