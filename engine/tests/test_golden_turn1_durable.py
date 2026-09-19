"""Golden 001 Turn 1 durable vertical slice on a real world.db."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3 as stdlib_sqlite3

import pytest

from application.story_turn_commit import StoryTurnCommitService, StoryTurnValidationError
from contracts import ActionIntent, StateDelta, StorySession, StoryState, TurnTransaction
from domain.resolution_policy import ResolutionPolicy, ResolutionRule, StoryEffect
from domain.resolver import DeterministicOutcomeResolver
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.sqlite_runtime import sqlite3 as runtime_sqlite3
from infrastructure.story_session_repository import SQLiteStorySessionCommitPort


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "golden_001"
RUNTIME = ROOT / "docs" / "07_工程启动" / "golden_001_runtime"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _initial_session() -> StorySession:
    seed = _read(FIXTURES / "seed.json")
    world = _read(FIXTURES / "world.json")
    character = _read(FIXTURES / "character.json")
    secret_states = {item["id"]: item["initial_state"] for item in seed["secrets"]}
    pressure = {item["id"]: item["initial_value"] for item in seed["pressures"]}
    state = StoryState.model_validate(
        {
            "schema_version": "1.0",
            "story_session_id": "session_golden_001",
            "revision": 0,
            "turn": 0,
            "phase": "discovery",
            "scene": {
                "id": "consultation_room",
                "location_id": world["location"]["id"],
                "active_character_ids": [character["id"], "npc_doctor_morris"],
            },
            "world_time": seed["setting"]["start_world_time"],
            "protagonist_goal": character["state"]["goals"]["immediate"],
            "active_conflicts": [seed["surface_problem"]],
            "discovered_clue_ids": [],
            "secret_states": secret_states,
            "commitments": {"hard_ids": [], "soft_ids": []},
            "local_state": {},
            "pressure": pressure,
            "last_state_delta_id": None,
        }
    )
    return StorySession.model_validate(
        {
            "schema_version": "1.0",
            "id": "session_golden_001",
            "world_id": world["world_id"],
            "worldline_id": world["worldline_id"],
            "protagonist_id": character["id"],
            "story_seed_id": seed["id"],
            "base_revisions": {
                "world": world["revision"],
                "character": character["revision"],
                "story": 0,
            },
            "story_state": state.model_dump(mode="json", exclude_none=True),
            "status": "active",
        }
    )


def _turn1_delta() -> StateDelta:
    seed = _read(FIXTURES / "seed.json")
    intent = ActionIntent.model_validate(
        _read(RUNTIME / "mock" / "01_action_intent.json")
    )
    policy = ResolutionPolicy.from_story_seed(
        seed,
        [
            ResolutionRule(
                rule_id="observe-morris-reaction",
                intent="observe_subject",
                action_types=("continue_conversation",),
                effect=StoryEffect(
                    outcome="partial_success",
                    clue_ids_add=("clue_doctor_pause",),
                    pressure_delta=(("doctor_suspicion", 0),),
                ),
                evidence_ids=("policy.golden001.opening",),
            )
        ],
        policy_id="golden001-opening-policy",
    )
    return DeterministicOutcomeResolver().resolve(
        intent, policy, delta_id="delta_g001_t01"
    )


def _validated_turn(delta: StateDelta) -> TurnTransaction:
    return TurnTransaction.model_validate(
        {
            "schema_version": "1.0",
            "id": "turn_g001_01",
            "session_id": "session_golden_001",
            "idempotency_key": "golden001.turn.01",
            "status": "validated",
            "base_revisions": {"world": 103, "character": 27, "story": 0},
            "player_advice_id": "advice_g001_t01",
            "action_intent_id": "intent_g001_t01",
            "state_delta_id": delta.id,
            "committed_story_revision": None,
            "narrative_block_id": None,
        }
    )


async def _open_database(tmp_path: Path) -> tuple[DatabaseManager, DatabasePaths]:
    paths = DatabasePaths.for_world(tmp_path / "app-support", "world_001")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute(
            "CREATE TABLE canon_fixture(id TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT"
        )
        canon.execute("INSERT INTO canon_fixture VALUES ('canon','immutable')")
    database = await DatabaseManager.open(
        paths, expected_sqlite_version=runtime_sqlite3.sqlite_version
    )
    return database, paths


async def _rows(database: DatabaseManager, table: str) -> list[dict]:
    return await database.read_world(f"SELECT * FROM {table}")


@pytest.mark.asyncio
async def test_golden_turn1_commit_survives_close_reopen_and_replay(tmp_path):
    database, paths = await _open_database(tmp_path)
    initial = _initial_session()
    delta = _turn1_delta()
    turn = _validated_turn(delta)
    expected = _read(RUNTIME / "expected" / "01_committed_state.json")

    port = SQLiteStorySessionCommitPort(database)
    service = StoryTurnCommitService(port)
    result = await service.commit_validated(
        initial,
        delta,
        turn,
        store_expected_revision=0,
        request_id="request.g001.01",
        trace_id="trace.g001.01",
    )

    assert result.store_revision == 1
    assert not result.replayed
    assert result.session.base_revisions.world == 103
    assert result.session.story_state.revision == expected["story_revision"] == 1
    assert result.session.story_state.turn == expected["turn"] == 1
    assert result.session.story_state.discovered_clue_ids == expected["clues"]
    assert {
        key: value.value for key, value in result.session.story_state.secret_states.items()
    } == expected["secrets"]
    assert result.session.story_state.pressure["doctor_suspicion"] == expected["doctor_suspicion"]
    assert result.turn.status.value == "committed"
    assert result.turn.committed_story_revision == 1

    session_row = (await _rows(database, "story_sessions"))[0]
    assert session_row["base_world_revision"] == 103
    assert session_row["committed_world_revision"] == 1
    assert len(await _rows(database, "story_state_deltas")) == 1
    assert len(await _rows(database, "turn_transactions")) == 1
    assert len(await _rows(database, "domain_commits")) == 1
    assert len(await _rows(database, "domain_events")) == 1
    assert len(await _rows(database, "projection_outbox")) == 1

    await database.close()

    reopened = await DatabaseManager.open(
        paths, expected_sqlite_version=runtime_sqlite3.sqlite_version
    )
    try:
        reopened_port = SQLiteStorySessionCommitPort(reopened)
        persisted_session = await reopened_port.load_session(initial.id)
        persisted_delta = await reopened_port.load_delta(delta.id)
        persisted_turn = await reopened_port.load_turn(turn.id)

        assert persisted_session == result.session
        assert persisted_delta == result.delta
        assert persisted_turn == result.turn

        replay = await StoryTurnCommitService(reopened_port).commit_validated(
            initial,
            delta,
            turn,
            store_expected_revision=0,
            request_id="request.g001.01.retry",
            trace_id="trace.g001.01.retry",
        )
        assert replay.replayed
        assert replay.store_revision == 1
        assert replay.session == persisted_session
        assert len(await _rows(reopened, "domain_commits")) == 1
        assert len(await _rows(reopened, "story_state_deltas")) == 1
        assert len(await _rows(reopened, "turn_transactions")) == 1
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_unsupported_session_overlay_fails_before_any_commit(tmp_path):
    database, _ = await _open_database(tmp_path)
    try:
        initial = _initial_session()
        delta = _turn1_delta()
        payload = delta.model_dump(mode="json", exclude_none=True)
        payload["world_event_candidates"] = [
            {
                "event_type": "unsupported-in-first-slice",
                "actors": [],
                "targets": [],
                "payload": {},
                "visibility": {"public": False},
            }
        ]
        unsupported = StateDelta.model_validate(payload)
        turn = _validated_turn(unsupported)
        service = StoryTurnCommitService(SQLiteStorySessionCommitPort(database))
        with pytest.raises(StoryTurnValidationError, match="does not yet persist"):
            await service.commit_validated(
                initial,
                unsupported,
                turn,
                store_expected_revision=0,
                request_id="request.unsupported",
                trace_id="trace.unsupported",
            )
        assert await _rows(database, "domain_commits") == []
        assert await _rows(database, "story_sessions") == []
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_failure_before_sqlite_commit_leaves_no_partial_story_rows(tmp_path):
    database, _ = await _open_database(tmp_path)
    initial = _initial_session()
    delta = _turn1_delta()
    turn = _validated_turn(delta)

    def fail(stage: str) -> None:
        if stage == "before_commit":
            raise RuntimeError("injected pre-commit failure")

    database._fault_hook = fail
    service = StoryTurnCommitService(SQLiteStorySessionCommitPort(database))
    try:
        with pytest.raises(RuntimeError, match="pre-commit"):
            await service.commit_validated(
                initial,
                delta,
                turn,
                store_expected_revision=0,
                request_id="request.failure",
                trace_id="trace.failure",
            )
        for table in (
            "story_sessions",
            "story_state_deltas",
            "turn_transactions",
            "domain_commits",
            "domain_events",
            "projection_outbox",
        ):
            assert await _rows(database, table) == []
    finally:
        await database.close()
