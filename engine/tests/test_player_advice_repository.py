"""world.db integration for immutable W-V09 PlayerAdvice interpretations."""
from __future__ import annotations

from pathlib import Path
import hashlib
import sqlite3 as stdlib_sqlite3

import pytest

from application.advice_interpretation import (
    AdviceInterpretationCandidate,
    PlayerAdviceInterpretationService,
)
from application.turn_input import TurnInputCommand, TurnInputStatus
from contracts import BaseRevisions, InputMode
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.player_advice_repository import (
    PlayerAdviceStorageConflict,
    SQLitePlayerAdviceRepository,
)
from infrastructure.sqlite_runtime import sqlite3
from infrastructure.turn_intake_repository import SQLiteTurnInputCommandPort


async def open_database(tmp_path: Path):
    paths = DatabasePaths.for_world(tmp_path / "app-support", "world-advice")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    database = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    return database, paths


def command():
    text = "先别问医生病人的事，我想看看他的反应。"
    return TurnInputCommand(
        input_turn_id="input-advice-1",
        session_id="session-1",
        turn_id="turn-advice-1",
        idempotency_key="turn-input:advice-1",
        input_mode=InputMode.VOICE,
        raw_input=text,
        input_sha256=hashlib.sha256(text.encode()).hexdigest(),
        base_revisions=BaseRevisions(world=0, character=0, story=0),
        public_expected_store_revision=7,
    )


class Interpreter:
    def __init__(self, primary="observe"):
        self.primary = primary
        self.calls = 0

    async def interpret(self, value):
        self.calls += 1
        return AdviceInterpretationCandidate(
            interpreter_revision="advice-profile-v1",
            primary_intent=self.primary,
            secondary_intents=("delay_confrontation",),
            proposed_actions=("observe_morris",),
            risk_preference="cautious",
            confidence=0.97,
        )


async def test_player_advice_survives_restart_and_lost_ack_without_second_model_call(tmp_path):
    database, paths = await open_database(tmp_path)
    intake = SQLiteTurnInputCommandPort(database)
    await intake.receive(command())
    model = Interpreter()
    service = PlayerAdviceInterpretationService(
        durable=SQLitePlayerAdviceRepository(database),
        interpreter=model,
    )
    try:
        first = await service.interpret("input-advice-1")
        assert not first.replayed
        assert model.calls == 1
        frozen = await SQLitePlayerAdviceRepository(database).load_input(
            "input-advice-1"
        )
        assert frozen is not None
        assert frozen.public_expected_store_revision == 7
        meta = await database.read_world("SELECT revision FROM world_meta")
        assert meta[0]["revision"] == 0
    finally:
        await database.close()

    reopened = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    second_model = Interpreter(primary="different")
    try:
        recovered = await PlayerAdviceInterpretationService(
            durable=SQLitePlayerAdviceRepository(reopened),
            interpreter=second_model,
        ).interpret("input-advice-1")
        assert recovered.replayed
        assert recovered.advice == first.advice
        assert recovered.advice.raw_input == command().raw_input
        assert second_model.calls == 0
    finally:
        await reopened.close()


async def test_first_durable_interpretation_wins_if_second_candidate_differs(tmp_path):
    database, _ = await open_database(tmp_path)
    try:
        await SQLiteTurnInputCommandPort(database).receive(command())
        repo = SQLitePlayerAdviceRepository(database)
        first = await PlayerAdviceInterpretationService(
            durable=repo,
            interpreter=Interpreter(primary="observe"),
        ).interpret("input-advice-1")

        second = await repo.publish(
            "input-advice-1",
            first.advice.model_copy(update={"primary_intent": "confront"}),
            interpreter_revision="advice-profile-v2",
        )
        assert second.replayed
        assert second.advice.primary_intent == "observe"
        assert second.interpreter_revision == "advice-profile-v1"
    finally:
        await database.close()


async def test_cancelled_input_cannot_publish_first_player_advice(tmp_path):
    database, _ = await open_database(tmp_path)
    try:
        intake = SQLiteTurnInputCommandPort(database)
        await intake.receive(command())
        await intake.cancel("input-advice-1")
        repo = SQLitePlayerAdviceRepository(database)
        frozen = await repo.load_input("input-advice-1")
        assert frozen is not None and frozen.status is TurnInputStatus.CANCELLED

        from contracts import PlayerAdvice
        advice = PlayerAdvice.model_validate({
            "schema_version":"1.0",
            "id":"advice-cancelled",
            "turn_id":"turn-advice-1",
            "raw_input":command().raw_input,
            "input_mode":"voice",
            "primary_intent":"observe",
            "proposed_actions":["observe_morris"],
            "confidence":0.9,
        })
        with pytest.raises(
            PlayerAdviceStorageConflict,
            match="Cancelled input",
        ):
            await repo.publish(
                "input-advice-1",
                advice,
                interpreter_revision="advice-profile-v1",
            )
    finally:
        await database.close()
