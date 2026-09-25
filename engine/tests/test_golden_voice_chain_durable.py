"""W-V09 golden durable voice chain: explicit open -> turn 1 -> COMMIT.

Chain under test (all real durable adapters over one ``world.db``):

    StorySessionOpenService -> story.session.opened
    FinalizedStoryInput -> turn_intake_commands (RECEIVED)
    PlayerAdviceInterpretationService -> turn_advice_interpretations
    AdviceActionIntentService -> bounded ActionIntent proposal (no persistence)
    DeterministicOutcomeResolver -> StateDelta
    AdviceCommitService -> StoryTurnCommitService -> COMMIT + intake promotion
"""
from __future__ import annotations

import sqlite3 as stdlib_sqlite3
from pathlib import Path

import pytest

from application.advice_action import ActionIntentCandidate, AdviceActionIntentService
from application.advice_commit import AdviceCommitError, AdviceCommitService
from application.advice_interpretation import (
    AdviceInterpretationCandidate,
    AdviceInterpretationError,
    PlayerAdviceInterpretationService,
)
from application.story_session_open import OpenStorySessionCommand, StorySessionOpenService
from application.turn_control import TurnCancellationOutcome, TurnControlService
from application.turn_input import (
    FinalizedStoryInput,
    StoryTurnInputService,
)
from application.turn_input import TurnInputStatus as ApplicationTurnInputStatus
from contracts import (
    AdherenceType,
    InputMode,
    StorySession,
    StoryState,
    TurnStatus,
)
from contracts.models import IntentAction
from domain.resolution_policy import ResolutionPolicy, ResolutionRule, StoryEffect
from domain.resolver import DeterministicOutcomeResolver
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.player_advice_repository import SQLitePlayerAdviceRepository
from infrastructure.sqlite_runtime import sqlite3
from infrastructure.story_session_open_repository import SQLiteStorySessionOpenPort
from infrastructure.story_session_repository import SQLiteStorySessionCommitPort
from infrastructure.turn_intake_repository import (
    SQLitePendingTurnControlPort,
    SQLiteTurnInputCommandPort,
    SQLiteTurnIntakeRepository,
    TurnIntakeStatus,
)

SESSION_ID = "session_voice_chain"
WORLD_REVISION = 103
CHARACTER_REVISION = 27
INPUT_TURN_1 = "input.turn.001"


class _RecordingInterpreter:
    def __init__(self) -> None:
        self.calls = 0

    async def interpret(self, value):
        self.calls += 1
        return AdviceInterpretationCandidate(
            interpreter_revision="advice-interpreter.v1",
            primary_intent="advance_into_room",
            secondary_intents=(),
            proposed_actions=("knock_on_door",),
            risk_preference=None,
            confidence=0.72,
        )


class _RecordingProposer:
    def __init__(self) -> None:
        self.calls = 0

    async def propose(self, *, frozen, advice, scope):
        self.calls += 1
        return ActionIntentCandidate(
            proposer_revision="character-reasoner.v1",
            intent="advance_into_room",
            adherence=AdherenceType.FULL,
            actions=(IntentAction(type="knock_on_door"),),
            reason_summary="先确认屋内反应再决定下一步。",
        )


def base_revisions() -> dict[str, int]:
    return {"world": WORLD_REVISION, "character": CHARACTER_REVISION, "story": 0}


def initial_session() -> StorySession:
    state = StoryState.model_validate(
        {
            "schema_version": "1.0",
            "story_session_id": SESSION_ID,
            "revision": 0,
            "turn": 0,
            "phase": "discovery",
            "scene": {
                "id": "consultation_room",
                "location_id": "location.consultation",
                "active_character_ids": ["char.evelyn", "char.morris"],
            },
            "world_time": "1889-05-01T09:00:00+00:00",
            "protagonist_goal": "确认医生的态度",
            "active_conflicts": [],
            "discovered_clue_ids": [],
            "secret_states": {},
            "commitments": {"hard_ids": [], "soft_ids": []},
            "local_state": {},
            "pressure": {},
            "last_state_delta_id": None,
        }
    )
    return StorySession.model_validate(
        {
            "schema_version": "1.0",
            "id": SESSION_ID,
            "world_id": "world.001",
            "worldline_id": "worldline.001",
            "protagonist_id": "char.evelyn",
            "story_seed_id": "seed.001",
            "base_revisions": base_revisions(),
            "story_state": state.model_dump(mode="json", exclude_none=True),
            "status": "active",
        }
    )


def voice_policy() -> ResolutionPolicy:
    return ResolutionPolicy.from_story_seed(
        {"clues": [{"id": "clue_voice_chain_door"}], "secrets": []},
        [
            ResolutionRule(
                rule_id="knock-on-door",
                intent="advance_into_room",
                action_types=("knock_on_door",),
                effect=StoryEffect(
                    outcome="partial_success",
                    clue_ids_add=("clue_voice_chain_door",),
                    world_time_delta_minutes=5,
                ),
            )
        ],
        policy_id="voice-chain-policy",
    )


async def open_database(tmp_path: Path) -> tuple[DatabaseManager, DatabasePaths]:
    paths = DatabasePaths.for_world(tmp_path / "app-support", "world-voice-chain")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    database = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    return database, paths


async def world_revision(database: DatabaseManager) -> int:
    rows = await database.read_world(
        "SELECT revision FROM world_meta WHERE singleton=1"
    )
    return rows[0]["revision"]


async def rows(database: DatabaseManager, table: str) -> list[dict]:
    return await database.read_world(f"SELECT * FROM {table}")


class Chain:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database
        self.opening = StorySessionOpenService(
            SQLiteStorySessionOpenPort(database)
        )
        self.story = SQLiteStorySessionCommitPort(database)
        self.advice = SQLitePlayerAdviceRepository(database)
        self.intake = SQLiteTurnInputCommandPort(database)
        self.interpreter = _RecordingInterpreter()
        self.proposer = _RecordingProposer()
        self.intake_service = StoryTurnInputService(
            sessions=self.story,
            intake=self.intake,
        )
        self.interpretation = PlayerAdviceInterpretationService(
            durable=self.advice,
            interpreter=self.interpreter,
        )
        self.proposal = AdviceActionIntentService(
            durable=self.advice,
            sessions=self.story,
            proposer=self.proposer,
        )
        self.commit = AdviceCommitService(
            durable=self.advice,
            proposal=self.proposal,
            story=self.story,
            resolver=DeterministicOutcomeResolver(),
        )

    async def open_session(self):
        return await self.opening.open(
            OpenStorySessionCommand(
                initial_session=initial_session(),
                open_request_id="open.voice-chain",
                store_expected_revision=0,
                request_id="request.open.voice-chain",
                trace_id="trace.open.voice-chain",
            )
        )

    async def receive(self, input_turn_id: str, raw_input: str):
        return await self.intake_service.receive(
            FinalizedStoryInput(
                input_turn_id=input_turn_id,
                session_id=SESSION_ID,
                input_mode=InputMode.VOICE,
                raw_input=raw_input,
            )
        )

    async def commit_turn(self, input_turn_id: str, *, expected_revision: int, suffix: str):
        return await self.commit.commit(
            input_turn_id,
            policy=voice_policy(),
            store_expected_revision=expected_revision,
            request_id=f"request.{suffix}",
            trace_id=f"trace.{suffix}",
        )

    async def cancel_pending(self, turn_id: str, *, expected_revision: int, suffix: str):
        return await TurnControlService(
            turns=SQLitePendingTurnControlPort(self.database)
        ).cancel_pending(
            turn_id,
            expected_revision=expected_revision,
            request_id=f"request.cancel.{suffix}",
            trace_id=f"trace.cancel.{suffix}",
        )


@pytest.mark.asyncio
async def test_voice_chain_commits_first_turn_and_replays_without_new_model_call(tmp_path):
    database, paths = await open_database(tmp_path)
    try:
        chain = Chain(database)
        opened = await chain.open_session()
        assert opened.opened_store_revision == 1
        assert opened.snapshot.observed_store_revision == 1
        assert opened.snapshot.session.story_state.revision == 0
        assert opened.snapshot.session.story_state.turn == 0
        assert opened.snapshot.session.base_revisions.model_dump(mode="json") == (
            base_revisions()
        )
        assert opened.snapshot.session.story_state.world_time == "1889-05-01T09:00:00+00:00"
        assert await world_revision(database) == 1

        receipt = await chain.receive(INPUT_TURN_1, "我上前敲门。")
        assert receipt.status is ApplicationTurnInputStatus.RECEIVED
        assert receipt.base_revisions.story == 0
        assert await world_revision(database) == 1

        stored = await chain.interpretation.interpret(INPUT_TURN_1)
        assert chain.interpreter.calls == 1
        assert stored.replayed is False
        # 解读是 insert-only：不推进世界、不制造回合结果
        assert await world_revision(database) == 1

        result = await chain.commit_turn(
            INPUT_TURN_1,
            expected_revision=1,
            suffix="001",
        )
        assert chain.proposer.calls == 1
        assert result.replayed is False
        assert result.store_revision == 2
        assert result.session.story_state.revision == 1
        assert result.session.story_state.turn == 1
        assert result.turn.status is TurnStatus.COMMITTED
        assert result.delta.evidence_ids
        intake = await SQLiteTurnIntakeRepository(database).load(INPUT_TURN_1)
        assert intake.status is TurnIntakeStatus.COMMITTED
        assert intake.committed_world_revision == 2
        assert len(await rows(database, "turn_transactions")) == 1
        assert len(await rows(database, "domain_commits")) == 2
        assert len(await rows(database, "domain_events")) == 2
        assert len(await rows(database, "projection_outbox")) == 2

        # Lost ACK: replaying turn 1 neither advances the world nor calls either model again.
        replay = await chain.commit_turn(
            INPUT_TURN_1,
            expected_revision=1,
            suffix="001.retry",
        )
        assert replay.replayed is True
        assert replay.store_revision == 2
        assert chain.interpreter.calls == 1
        assert chain.proposer.calls == 1
        assert await world_revision(database) == 2
        assert len(await rows(database, "turn_transactions")) == 1
        assert len(await rows(database, "domain_commits")) == 2
        assert len(await rows(database, "domain_events")) == 2
        assert len(await rows(database, "projection_outbox")) == 2
    finally:
        await database.close()

    reopened = await DatabaseManager.open(
        paths,
        expected_sqlite_version=sqlite3.sqlite_version,
    )
    try:
        restart = Chain(reopened)
        assert await world_revision(reopened) == 2

        # After restart, interpretation replays persisted PlayerAdvice without a model call.
        recovered = await restart.interpretation.interpret(INPUT_TURN_1)
        assert recovered.replayed is True
        assert restart.interpreter.calls == 0

        recovered_intake = await SQLiteTurnIntakeRepository(reopened).load(
            INPUT_TURN_1
        )
        assert recovered_intake.committed_world_revision == 2
        session = await restart.story.load_session(SESSION_ID)
        assert session.story_state.revision == 1
        assert session.story_state.turn == 1

        restarted_replay = await restart.commit_turn(
            INPUT_TURN_1,
            expected_revision=1,
            suffix="001.restart",
        )
        assert restarted_replay.replayed is True
        assert restarted_replay.store_revision == 2
        assert restart.proposer.calls == 0
        assert await world_revision(reopened) == 2
        assert len(await rows(reopened, "turn_transactions")) == 1
        assert len(await rows(reopened, "domain_commits")) == 2
        assert len(await rows(reopened, "domain_events")) == 2
        assert len(await rows(reopened, "projection_outbox")) == 2
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_pending_turn_cancel_wins_before_commit_in_the_durable_chain(tmp_path):
    database, _ = await open_database(tmp_path)
    try:
        chain = Chain(database)
        opened = await chain.open_session()
        assert opened.opened_store_revision == 1
        assert await world_revision(database) == 1

        receipt = await chain.receive(INPUT_TURN_1, "算了，我还是等着。")
        cancellation = await chain.cancel_pending(
            receipt.turn_id,
            expected_revision=WORLD_REVISION,
            suffix="003",
        )

        assert cancellation.outcome is TurnCancellationOutcome.CANCELLED_BEFORE_COMMIT
        assert cancellation.committed_world_revision is None
        assert await world_revision(database) == 1

        # 取消先赢后 COMMIT 必须被拒绝，且世界不被推进
        with pytest.raises(AdviceCommitError, match="input_turn_cancelled"):
            await chain.commit_turn(INPUT_TURN_1, expected_revision=1, suffix="001")
        assert await world_revision(database) == 1

        # 已取消的回合不进入解读，也不产生建议
        with pytest.raises(AdviceInterpretationError, match="input_turn_cancelled"):
            await chain.interpretation.interpret(INPUT_TURN_1)
        assert chain.interpreter.calls == 0
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_committed_turn_reports_revision_to_a_late_cancellation(tmp_path):
    database, _ = await open_database(tmp_path)
    try:
        chain = Chain(database)
        opened = await chain.open_session()
        assert opened.opened_store_revision == 1
        assert await world_revision(database) == 1

        receipt = await chain.receive(INPUT_TURN_1, "我敲门并退后半步。")
        await chain.interpretation.interpret(INPUT_TURN_1)
        committed = await chain.commit_turn(
            INPUT_TURN_1,
            expected_revision=1,
            suffix="001",
        )
        assert committed.store_revision == 2
        assert committed.session.story_state.revision == 1
        assert committed.session.story_state.turn == 1
        assert await world_revision(database) == 2

        late = await chain.cancel_pending(
            receipt.turn_id,
            expected_revision=WORLD_REVISION,
            suffix="001",
        )

        assert late.outcome is TurnCancellationOutcome.ALREADY_COMMITTED
        assert late.committed_world_revision == committed.store_revision == 2
        assert late.replayed is False
        assert await world_revision(database) == 2
        assert (await SQLiteTurnIntakeRepository(database).load(
            INPUT_TURN_1
        )).status is TurnIntakeStatus.COMMITTED
    finally:
        await database.close()
