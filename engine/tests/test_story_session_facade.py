"""Trusted first-turn facade integration on the real durable chain."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3 as stdlib_sqlite3

import pytest

from ai.golden_first_turn import GoldenFirstTurnFactory
from application.story_initialization import (
    GOLDEN_SCENARIO_ID,
    SUPPORTED_ADVICE,
    StoryInitializationService,
    TrustedScenarioBundle,
)
from application.story_session_facade import (
    StoredInputRecord,
    StoryEntrySnapshot,
    StorySessionFacade,
    StorySessionSnapshotRecord,
    SubmitAdviceCommand,
)
from application.story_session_open import StorySessionOpenService
from application.turn_input import TurnInputStatus
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.player_advice_repository import SQLitePlayerAdviceRepository
from infrastructure.sqlite_runtime import sqlite3
from infrastructure.story_bootstrap_repository import SQLiteStoryBootstrapRepository
from infrastructure.story_session_open_repository import SQLiteStorySessionOpenPort
from infrastructure.story_session_repository import SQLiteStorySessionCommitPort
from infrastructure.turn_intake_repository import SQLiteTurnInputCommandPort

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


class Source:
    def __init__(self) -> None:
        self.bundle = TrustedScenarioBundle.model_validate(_bundle_payload())

    async def load(self, scenario_id: str) -> TrustedScenarioBundle:
        assert scenario_id == GOLDEN_SCENARIO_ID
        return self.bundle


class CountingFirstTurn(GoldenFirstTurnFactory):
    def __init__(self) -> None:
        self.interpreter_calls = 0
        self.proposer_calls = 0

    def interpreter_for(self, bootstrap):
        self.interpreter_calls += 1
        return super().interpreter_for(bootstrap)

    def proposer_for(self, bootstrap):
        self.proposer_calls += 1
        return super().proposer_for(bootstrap)


class Query:
    def __init__(self, database: DatabaseManager, source: Source) -> None:
        self._database = database
        self._source = source
        self._bootstraps = SQLiteStoryBootstrapRepository(database)
        self._story = SQLiteStorySessionCommitPort(database)
        self._inputs = SQLiteTurnInputCommandPort(database)

    async def entry(self, scenario_id: str) -> StoryEntrySnapshot:
        rows = await self._database.read_world(
            "SELECT session_id FROM story_session_bootstraps "
            "WHERE scenario_id=? ORDER BY opened_store_revision DESC LIMIT 2",
            (scenario_id,),
        )
        observed = (
            await self._database.read_world(
                "SELECT revision FROM world_meta WHERE singleton=1"
            )
        )[0]["revision"]
        supported = self._source.bundle.advice_template.raw_input
        if not rows:
            return StoryEntrySnapshot(
                supported_advice=(supported,),
                observed_store_revision=observed,
            )
        if len(rows) != 1:
            raise AssertionError("ambiguous entry scenario")
        return StoryEntrySnapshot(
            supported_advice=(supported,),
            observed_store_revision=observed,
            session=await self.session(rows[0]["session_id"]),
        )

    async def session(self, session_id: str) -> StorySessionSnapshotRecord:
        session = await self._story.load_session(session_id)
        bootstrap = await self._bootstraps.require(session_id)
        observed = (
            await self._database.read_world(
                "SELECT revision FROM world_meta WHERE singleton=1"
            )
        )[0]["revision"]
        pending = await self._database.read_world(
            "SELECT input_turn_id FROM turn_intake_commands "
            "WHERE session_id=? AND status='received'",
            (session_id,),
        )
        if len(pending) > 1:
            raise AssertionError("multiple pending inputs")
        return StorySessionSnapshotRecord(
            session=session,
            bootstrap=bootstrap,
            observed_store_revision=observed,
            pending_input_turn_id=(
                None if not pending else pending[0]["input_turn_id"]
            ),
        )

    async def input(
        self, session_id: str, input_turn_id: str
    ) -> StoredInputRecord | None:
        receipt = await self._inputs.load(input_turn_id)
        if receipt is None or receipt.session_id != session_id:
            return None
        committed_story_revision = None
        if receipt.status is TurnInputStatus.COMMITTED:
            turn = await self._story.load_turn(receipt.turn_id)
            committed_story_revision = turn.committed_story_revision
        return StoredInputRecord(
            receipt=receipt,
            committed_story_revision=committed_story_revision,
        )


async def _database(tmp_path: Path):
    paths = DatabasePaths.for_world(tmp_path / "app-support", "world-facade")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    return (
        await DatabaseManager.open(
            paths,
            expected_sqlite_version=sqlite3.sqlite_version,
        ),
        paths,
    )


def _facade(database: DatabaseManager, source: Source, first_turn: CountingFirstTurn):
    return StorySessionFacade(
        initialization=StoryInitializationService(source),
        open_sessions=StorySessionOpenService(SQLiteStorySessionOpenPort(database)),
        query=Query(database, source),
        intake=SQLiteTurnInputCommandPort(database),
        advice=SQLitePlayerAdviceRepository(database),
        story=SQLiteStorySessionCommitPort(database),
        first_turn=first_turn,
    )


@pytest.mark.asyncio
async def test_facade_open_submit_and_get_advice_use_real_durable_chain(tmp_path):
    database, _ = await _database(tmp_path)
    source = Source()
    first_turn = CountingFirstTurn()
    facade = _facade(database, source, first_turn)
    try:
        opened = await facade.open(
            scenario_id=GOLDEN_SCENARIO_ID,
            open_request_id="open_first_001",
            expected_store_revision=0,
            request_id="request_open",
            trace_id="trace_open",
        )
        assert opened.session.turn == 0
        assert opened.session.can_submit
        assert opened.opened_store_revision == 1

        command = SubmitAdviceCommand(
            session_id=opened.session.session_id,
            input_turn_id="input_turn_first_001",
            raw_input=SUPPORTED_ADVICE,
            expected_story_revision=0,
            expected_store_revision=1,
            request_id="request_submit",
            trace_id="trace_submit",
        )
        submitted = await facade.submit(command)
        assert submitted.receipt.status == "committed"
        assert submitted.receipt.committed_store_revision == 2
        assert submitted.receipt.committed_story_revision == 1
        assert submitted.session.turn == 1
        assert submitted.session.story_revision == 1
        assert not submitted.session.can_submit
        assert [
            clue.model_dump() for clue in submitted.session.discovered_clues
        ] == [{"id": "clue_doctor_pause", "display_name": "医生的停顿"}]
        assert first_turn.interpreter_calls == 1
        assert first_turn.proposer_calls == 1

        loaded = await facade.get_advice(
            opened.session.session_id,
            "input_turn_first_001",
        )
        assert loaded.found
        assert loaded.receipt == submitted.receipt
        assert loaded.session == submitted.session

        replayed = await facade.submit(command)
        assert replayed.replayed
        assert replayed.receipt == submitted.receipt
        assert first_turn.interpreter_calls == 1
        assert first_turn.proposer_calls == 1

        counts = await database.read_world(
            "SELECT "
            "(SELECT count(*) FROM domain_commits),"
            "(SELECT count(*) FROM story_state_deltas),"
            "(SELECT count(*) FROM turn_transactions)"
        )
        assert counts == [{"(SELECT count(*) FROM domain_commits)": 2,
                           "(SELECT count(*) FROM story_state_deltas)": 1,
                           "(SELECT count(*) FROM turn_transactions)": 1}]
        serialized = submitted.session.model_dump_json()
        assert "secret_" not in serialized
        assert "hidden_truth" not in serialized
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_facade_rejects_unsupported_text_before_intake(tmp_path):
    database, _ = await _database(tmp_path)
    source = Source()
    first_turn = CountingFirstTurn()
    facade = _facade(database, source, first_turn)
    try:
        opened = await facade.open(
            scenario_id=GOLDEN_SCENARIO_ID,
            open_request_id="open_first_001",
            expected_store_revision=0,
            request_id="request_open",
            trace_id="trace_open",
        )
        with pytest.raises(Exception, match="deterministic_input_unsupported"):
            await facade.submit(
                SubmitAdviceCommand(
                    session_id=opened.session.session_id,
                    input_turn_id="input_turn_other",
                    raw_input="试试另一种输入",
                    expected_story_revision=0,
                    expected_store_revision=1,
                    request_id="request_other",
                    trace_id="trace_other",
                )
            )
        assert await database.read_world(
            "SELECT count(*) AS count FROM turn_intake_commands"
        ) == [{"count": 0}]
        assert first_turn.interpreter_calls == 0
        assert first_turn.proposer_calls == 0
    finally:
        await database.close()
