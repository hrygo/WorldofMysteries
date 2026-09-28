"""T4 application orchestration across the fixed Golden 001 five-turn run."""
from __future__ import annotations

import hashlib
import json
import sqlite3 as stdlib_sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from ai.golden_five_turn import GoldenFiveTurnCatalog, GoldenFiveTurnFactory
from application.episode_finalization import (
    EpisodeFinalizationArtifacts,
    EpisodeFinalizationCommand,
    EpisodeFinalizationService,
)
from application.post_commit_expression import (
    CommittedExpressionInput,
    ExpressionError,
    PostCommitExpressionService,
)
from application.scenario_policy import (
    ActionSignature,
    FinalizationRecipe,
    ScenarioIdentity,
    TurnPolicyDecision,
)
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
from application.story_turn_commit import (
    DomainValidationContext,
    StoryTurnCommitResult,
)
from application.turn_input import TurnInputStatus
from contracts import StorySession, StorySessionStatus, TurnStatus
from infrastructure.database_manager import (
    CommitRequest,
    DatabaseManager,
    DatabasePaths,
    RevisionConflict,
    StoredEvent,
)
from infrastructure.episode_finalization_repository import (
    EpisodeFinalizationArtifacts as InfrastructureArtifacts,
)
from infrastructure.episode_finalization_repository import (
    EpisodeFinalizationRequest as InfrastructureRequest,
)
from infrastructure.episode_finalization_repository import (
    SQLiteEpisodeFinalizationRepository,
)
from infrastructure.narrative_block_repository import SQLiteNarrativeBlockRepository
from infrastructure.player_advice_repository import SQLitePlayerAdviceRepository
from infrastructure.sqlite_runtime import sqlite3
from infrastructure.story_bootstrap_repository import SQLiteStoryBootstrapRepository
from infrastructure.story_session_open_repository import SQLiteStorySessionOpenPort
from infrastructure.story_session_repository import SQLiteStorySessionCommitPort
from infrastructure.turn_intake_repository import SQLiteTurnInputCommandPort
from infrastructure.episode_settlement import ScenarioSettlement

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
            "clue_display_names": {
                "clue_doctor_pause": "医生的停顿",
                "clue_appointment_book": "异常的预约记录",
                "clue_removed_page": "被撕去的预约页",
                "clue_basement_powder": "门框黑粉",
                "clue_jonathan_note": "Jonathan 的纸片",
            },
        },
        "advice_template": advice,
        "action_intent_template": _read(RUNTIME / "mock" / "01_action_intent.json"),
    }
    payload["content_digest"] = _canonical_digest(payload)
    return payload


def _catalog() -> GoldenFiveTurnCatalog:
    return GoldenFiveTurnCatalog.from_directory(
        FIXTURES / "turns",
        RUNTIME / "mock",
        seed=_read(FIXTURES / "seed.json"),
    )


class Source:
    def __init__(self) -> None:
        self.bundle = TrustedScenarioBundle.model_validate(_bundle_payload())

    async def load(self, scenario_id: str) -> TrustedScenarioBundle:
        assert scenario_id == GOLDEN_SCENARIO_ID
        return self.bundle


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
        supported = tuple(
            item.raw_input for item in _catalog().advice_templates.values()
        )
        if not rows:
            return StoryEntrySnapshot(
                supported_advice=supported,
                observed_store_revision=observed,
            )
        return StoryEntrySnapshot(
            supported_advice=supported,
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
    paths = DatabasePaths.for_world(tmp_path / "app-support", "world-five-turn")
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


def _facade(
    database: DatabaseManager,
    source: Source,
    factory: GoldenFiveTurnFactory,
    *,
    story=None,
):
    return StorySessionFacade(
        initialization=StoryInitializationService(source),
        open_sessions=StorySessionOpenService(SQLiteStorySessionOpenPort(database)),
        query=Query(database, source),
        intake=SQLiteTurnInputCommandPort(database),
        advice=SQLitePlayerAdviceRepository(database),
        story=story or SQLiteStorySessionCommitPort(database),
        scenario=_GoldenFiveTurnScenario(factory),
        workers=_GoldenFiveTurnWorkers(factory),
    )


class _GoldenFiveTurnScenario:
    """Test-only adapter around the frozen fixture's existing rule source."""

    def __init__(self, factory: GoldenFiveTurnFactory) -> None:
        self._factory = factory

    def identity(self, bootstrap) -> ScenarioIdentity:
        return ScenarioIdentity(
            scenario_id=bootstrap.scenario_id,
            content_digest=bootstrap.content_digest,
            rules_revision=bootstrap.policy_version,
        )

    def decision(
        self, session: StorySession, committed_evidence: frozenset[str]
    ) -> TurnPolicyDecision:
        del committed_evidence
        terminal = session.story_state.turn >= self._factory.max_turn
        return TurnPolicyDecision(
            allowed_to_submit=(
                session.status is StorySessionStatus.ACTIVE and not terminal
            ),
            terminal=terminal,
            reason="iteration_limit_reached" if terminal else None,
        )

    def expected_input(self, bootstrap, session) -> str | None:
        turn_number = session.story_state.turn + 1
        if turn_number > self._factory.max_turn:
            return None
        return self._factory.expected_input(bootstrap, turn_number)

    def resolution_policy(self, bootstrap, session):
        return self._factory.policy_for_turn(
            bootstrap, session.story_state.turn + 1
        )

    def validation_context(
        self, bootstrap, session
    ) -> DomainValidationContext:
        return self._factory.domain_validation_for(
            bootstrap, session.story_state.turn + 1
        )

    def finalization_recipe(self, bootstrap, committed_session):
        del bootstrap, committed_session
        return None


class _GoldenFiveTurnWorkers:
    """Test-only worker projection; scenario rules stay in the scenario port."""

    supports_live_input = False

    def __init__(self, factory: GoldenFiveTurnFactory) -> None:
        self._factory = factory
        self.allowed_signatures: tuple[ActionSignature, ...] = ()

    def interpreter_for(self, bootstrap, turn_number):
        return self._factory.interpreter_for(bootstrap, turn_number)

    def proposer_for(self, bootstrap, turn_number, allowed_signatures):
        self.allowed_signatures = allowed_signatures
        return self._factory.proposer_for(bootstrap, turn_number)

    def narrative_compiler(self, bootstrap):
        del bootstrap
        raise AssertionError("Golden test workers do not compile live narration")


async def _open_five_turn_facade(tmp_path: Path):
    database, paths = await _database(tmp_path)
    source = Source()
    factory = GoldenFiveTurnFactory(_catalog())
    facade = _facade(database, source, factory)
    opened = await facade.open(
        scenario_id=GOLDEN_SCENARIO_ID,
        open_request_id="open_golden_five_turn",
        expected_store_revision=0,
        request_id="request_open_five_turn",
        trace_id="trace_open_five_turn",
    )
    return database, paths, facade, factory, opened


async def _submit_five_turns(
    database: DatabaseManager,
    facade: StorySessionFacade,
    opened,
    *,
    upto: int = 5,
) -> list:
    catalog = _catalog()
    submitted = []
    sessions = []
    for turn_number in range(1, upto + 1):
        advice = catalog.advice_templates[turn_number]
        command = SubmitAdviceCommand(
            session_id=opened.session.session_id,
            input_turn_id=f"input_turn_golden_{turn_number:02d}",
            raw_input=advice.raw_input,
            expected_story_revision=turn_number - 1,
            expected_store_revision=turn_number,
            request_id=f"request_turn_{turn_number:02d}",
            trace_id=f"trace_turn_{turn_number:02d}",
        )
        submitted.append(await facade.submit(command))
        sessions.append(
            await SQLiteStorySessionCommitPort(database).load_session(
                opened.session.session_id
            )
        )
    return submitted, sessions


async def _committed_session(database: DatabaseManager, session_id: str):
    return await SQLiteStorySessionCommitPort(database).load_session(session_id)


@pytest.mark.asyncio
async def test_five_turns_commit_real_durable_state_and_match_expected(tmp_path):
    database, _paths, facade, _factory, opened = await _open_five_turn_facade(tmp_path)
    try:
        submitted, sessions = await _submit_five_turns(database, facade, opened)

        assert [item.session.story_revision for item in submitted] == [1, 2, 3, 4, 5]
        for turn_number, item in enumerate(submitted, start=1):
            session = sessions[turn_number - 1]
            expected = _read(
                RUNTIME / "expected" / f"{turn_number:02d}_committed_state.json"
            )
            secrets = {
                key: value.value for key, value in session.story_state.secret_states.items()
            }
            assert session.story_state.turn == expected["turn"]
            assert session.story_state.discovered_clue_ids == expected["clues"]
            assert secrets == expected["secrets"]
            pressure = session.story_state.pressure
            assert pressure["doctor_suspicion"] == expected["doctor_suspicion"]
        assert submitted[-1].session.can_submit is False

        rows = await database.read_world(
            "SELECT "
            "(SELECT count(*) FROM turn_transactions) AS turns,"
            "(SELECT count(*) FROM turn_character_changes) AS characters,"
            "(SELECT count(*) FROM turn_relationship_changes) AS relationships,"
            "(SELECT count(*) FROM turn_knowledge_changes) AS knowledge,"
            "(SELECT count(*) FROM turn_world_events) AS world_events"
        )
        assert rows == [
            {
                "turns": 5,
                "characters": 1,
                "relationships": 1,
                "knowledge": 1,
                "world_events": 3,
            }
        ]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_character_never_identifies_morris_as_the_culprit(tmp_path):
    """G002: suspicion is not promoted to a culprit verdict by the run.

    The bundle seeds `fact.family_suspects_morris`, which is a *suspicion*
    about the doctor. Nothing the five committed turns write may turn that
    suspicion into a committed claim that Morris is the culprit.
    """
    database, _paths, facade, _factory, opened = await _open_five_turn_facade(tmp_path)
    try:
        await _submit_five_turns(database, facade, opened)

        knowledge = await database.read_world(
            "SELECT character_id, proposition_id, payload_json "
            "FROM turn_knowledge_changes"
        )
        world_events = await database.read_world(
            "SELECT id, event_type, payload_json FROM turn_world_events"
        )

        # The doctor may legitimately be a *target* of evidence gathering, but
        # no committed knowledge or world event may assert culpability.
        for row in knowledge:
            payload = json.loads(row["payload_json"])
            blob = f"{row['proposition_id']} {payload}".lower()
            assert "morris" not in blob
            assert "culprit" not in blob

        for row in world_events:
            payload = json.loads(row["payload_json"])
            blob = f"{row['event_type']} {payload}".lower()
            assert "culprit" not in blob
            # Every write-back must be evidence, never an accusation.
            assert row["event_type"] in {"evidence_observed", "evidence_recovered"}
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_closure_turn_adds_no_major_conflict(tmp_path):
    """G006: the fifth turn closes the run without inventing a major conflict."""
    database, _paths, facade, _factory, opened = await _open_five_turn_facade(tmp_path)
    try:
        seed = _read(FIXTURES / "seed.json")
        baseline = [seed["surface_problem"]]

        _submitted, sessions = await _submit_five_turns(database, facade, opened)

        # The closing turn must leave the conflict set exactly as it started:
        # closure resolves the run, it does not escalate it.
        assert sessions[-1].story_state.active_conflicts == baseline
        for session in sessions:
            assert session.story_state.active_conflicts == baseline
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_hidden_truth_never_enters_public_world_writeback(tmp_path):
    """G008: world write-back stays private to the subjects who observed it."""
    database, _paths, facade, _factory, opened = await _open_five_turn_facade(tmp_path)
    try:
        _submitted, sessions = await _submit_five_turns(database, facade, opened)

        world_events = await database.read_world(
            "SELECT id, payload_json FROM turn_world_events"
        )
        assert world_events, "the run is expected to write world evidence back"
        for row in world_events:
            visibility = json.loads(row["payload_json"])["visibility"]
            assert visibility["public"] is False
            assert visibility["known_by"], "a private event must still name its observers"

        # Secret 04 is the hidden truth the whole scenario protects.
        secrets = sessions[-1].story_state.secret_states
        assert secrets["secret_04"].value == "hidden"
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_replaying_each_key_does_not_recommit_or_re_call_models(tmp_path):
    database, _paths, facade, factory, opened = await _open_five_turn_facade(tmp_path)
    try:
        submitted, _sessions = await _submit_five_turns(database, facade, opened)
        assert factory.interpreter_calls == 5
        assert factory.proposer_calls == 5

        for turn_number, original in enumerate(submitted, start=1):
            advice = _catalog().advice_templates[turn_number]
            replay = await facade.submit(
                SubmitAdviceCommand(
                    session_id=opened.session.session_id,
                    input_turn_id=f"input_turn_golden_{turn_number:02d}",
                    raw_input=advice.raw_input,
                    expected_story_revision=turn_number - 1,
                    expected_store_revision=turn_number,
                    request_id=f"request_turn_{turn_number:02d}_retry",
                    trace_id=f"trace_turn_{turn_number:02d}_retry",
                )
            )
            assert replay.replayed is True
            assert replay.receipt == original.receipt
            assert replay.session.story_revision == 5

        assert factory.interpreter_calls == 5
        assert factory.proposer_calls == 5
        assert await database.read_world(
            "SELECT count(*) AS count FROM turn_transactions"
        ) == [{"count": 5}]
    finally:
        await database.close()


class _FailBeforeCommitPort:
    def __init__(self, delegate: SQLiteStorySessionCommitPort) -> None:
        self._delegate = delegate
        self.fail = True

    async def load_session(self, session_id):
        return await self._delegate.load_session(session_id)

    async def load_turn(self, turn_id):
        return await self._delegate.load_turn(turn_id)

    async def load_delta(self, delta_id):
        return await self._delegate.load_delta(delta_id)

    async def commit_turn(self, *args, **kwargs):
        if self.fail:
            self.fail = False
            raise RuntimeError("injected failure before commit")
        return await self._delegate.commit_turn(*args, **kwargs)


@pytest.mark.asyncio
async def test_pending_input_resumes_without_repeating_interpretation(tmp_path):
    database, _paths, facade, factory, opened = await _open_five_turn_facade(
        tmp_path
    )
    story = SQLiteStorySessionCommitPort(database)
    try:
        first = await _submit_five_turns(
            database,
            facade,
            opened,
            upto=2,
        )
        assert len(first) == 2
        failing_facade = _facade(
            database,
            Source(),
            factory,
            story=_FailBeforeCommitPort(story),
        )
        advice = _catalog().advice_templates[3]
        command = SubmitAdviceCommand(
            session_id=opened.session.session_id,
            input_turn_id="input_turn_golden_03",
            raw_input=advice.raw_input,
            expected_story_revision=2,
            expected_store_revision=3,
            request_id="request_turn_03",
            trace_id="trace_turn_03",
        )
        with pytest.raises(RuntimeError, match="injected failure before commit"):
            await failing_facade.submit(command)
        pending = await database.read_world(
            "SELECT status FROM turn_intake_commands WHERE input_turn_id=?",
            (command.input_turn_id,),
        )
        assert pending == [{"status": "received"}]
        assert factory.interpreter_calls == 3
        assert factory.proposer_calls == 3

        resumed = await failing_facade.submit(command)
        assert resumed.session.story_revision == 3
        committed = await database.read_world(
            "SELECT status FROM turn_intake_commands WHERE input_turn_id=?",
            (command.input_turn_id,),
        )
        assert committed == [{"status": "committed"}]
        assert factory.interpreter_calls == 3
        assert factory.proposer_calls == 4
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_same_key_with_changed_text_is_rejected_before_replay(tmp_path):
    database, _paths, facade, _factory, opened = await _open_five_turn_facade(tmp_path)
    try:
        advice = _catalog().advice_templates[1]
        command = SubmitAdviceCommand(
            session_id=opened.session.session_id,
            input_turn_id="input_turn_golden_01",
            raw_input=advice.raw_input,
            expected_story_revision=0,
            expected_store_revision=1,
            request_id="request_turn_01",
            trace_id="trace_turn_01",
        )
        original = await facade.submit(command)
        with pytest.raises(Exception, match="input_turn_identity_conflict"):
            await facade.submit(
                replace(command, raw_input=advice.raw_input + "并跟上去")
            )
        assert original.session.story_revision == 1
        assert await database.read_world(
            "SELECT count(*) AS count FROM turn_intake_commands"
        ) == [{"count": 1}]
    finally:
        await database.close()


class _FailOnceNarrativePort:
    def __init__(self, delegate: SQLiteNarrativeBlockRepository) -> None:
        self._delegate = delegate
        self.fail = True
        self.calls = 0

    async def publish(self, *, turn_id, narrative):
        self.calls += 1
        if self.fail:
            self.fail = False
            raise RuntimeError("injected expression failure")
        return await self._delegate.publish(turn_id=turn_id, narrative=narrative)


class _RecordingBeatPlanPort:
    def __init__(self) -> None:
        self.published: list = []

    async def publish(self, beat_plan) -> None:
        self.published.append(beat_plan)


@pytest.mark.asyncio
async def test_beat_plan_publishes_only_after_commit_and_binds_committed_revision(
    tmp_path,
):
    database, _paths, facade, factory, opened = await _open_five_turn_facade(tmp_path)
    beats = _RecordingBeatPlanPort()
    expression = PostCommitExpressionService(
        templates=factory.expression_templates,
        beats=beats,
        narratives=SQLiteNarrativeBlockRepository(database),
    )
    first, _sessions = await _submit_five_turns(database, facade, opened)
    turn = first[0].receipt.turn_id
    committed = await SQLiteStorySessionCommitPort(database).load_turn(turn)
    expression_input = CommittedExpressionInput(
        session_id=opened.session.session_id,
        turn_id=turn,
        story_revision=committed.committed_story_revision,
        state_delta_id=committed.state_delta_id,
        turn_status=committed.status,
    )

    # BeatPlan must not publish before the authoritative COMMIT.
    with pytest.raises(ExpressionError, match="expression_requires_committed_turn"):
        await expression.publish(
            turn_number=1,
            commit=replace(expression_input, turn_status=TurnStatus.RESOLVED),
        )
    assert beats.published == []

    await expression.publish(turn_number=1, commit=expression_input)
    assert len(beats.published) == 1
    beat = beats.published[0]
    assert beat.story_session_id == opened.session.session_id
    assert beat.source_story_revision == committed.committed_story_revision


@pytest.mark.asyncio
async def test_post_commit_expression_failure_never_rewrites_committed_facts(tmp_path):
    database, _paths, facade, factory, opened = await _open_five_turn_facade(tmp_path)
    narrative_port = _FailOnceNarrativePort(SQLiteNarrativeBlockRepository(database))
    expression = PostCommitExpressionService(
        templates=factory.expression_templates,
        beats=None,
        narratives=narrative_port,
    )
    try:
        first, _sessions = await _submit_five_turns(database, facade, opened)
        turn = first[0].receipt.turn_id
        committed = await SQLiteStorySessionCommitPort(database).load_turn(turn)
        expression_input = CommittedExpressionInput(
            session_id=opened.session.session_id,
            turn_id=turn,
            story_revision=committed.committed_story_revision,
            state_delta_id=committed.state_delta_id,
            turn_status=committed.status,
        )
        before = await database.read_world(
            "SELECT story_revision,status,story_state_json FROM story_sessions "
            "WHERE id=?",
            (opened.session.session_id,),
        )

        with pytest.raises(RuntimeError, match="injected expression failure"):
            await expression.publish(turn_number=1, commit=expression_input)

        assert await database.read_world(
            "SELECT story_revision,status,story_state_json FROM story_sessions "
            "WHERE id=?",
            (opened.session.session_id,),
        ) == before
        published = await expression.publish(turn_number=1, commit=expression_input)
        assert published.narrative.source_story_revision == 1
        assert published.narrative.source_state_delta_id is not None
        assert published.replayed is False
        assert (
            await expression.publish(turn_number=1, commit=expression_input)
        ).replayed is True
        assert await database.read_world(
            "SELECT story_revision,status,story_state_json FROM story_sessions "
            "WHERE id=?",
            (opened.session.session_id,),
        ) == before
        persisted_turn = await SQLiteStorySessionCommitPort(database).load_turn(turn)
        assert persisted_turn.narrative_block_id == published.narrative.id
        for turn_number in range(2, 6):
            turn_id = first[turn_number - 1].receipt.turn_id
            committed_turn = await SQLiteStorySessionCommitPort(database).load_turn(
                turn_id
            )
            result = await expression.publish(
                turn_number=turn_number,
                commit=CommittedExpressionInput(
                    session_id=opened.session.session_id,
                    turn_id=turn_id,
                    story_revision=committed_turn.committed_story_revision,
                    state_delta_id=committed_turn.state_delta_id,
                    turn_status=committed_turn.status,
                ),
            )
            assert result.narrative.source_story_revision == turn_number
        assert await database.read_world(
            "SELECT count(*) AS count FROM narrative_blocks"
        ) == [{"count": 5}]
    finally:
        await database.close()


class _FinalizationAdapter:
    def __init__(self, database: DatabaseManager) -> None:
        self._repository = SQLiteEpisodeFinalizationRepository(database)

    async def finalize(self, command: EpisodeFinalizationCommand):
        request = InfrastructureRequest(
            session_id=command.session_id,
            expected_story_revision=command.expected_story_revision,
            world_time=command.world_time,
            expected_store_revision=command.expected_store_revision,
            idempotency_key=command.idempotency_key,
            request_id=command.request_id,
            trace_id=command.trace_id,
            episode=command.episode,
            artifacts=InfrastructureArtifacts(
                character_events=command.artifacts.character_events,
                relationship_events=command.artifacts.relationship_events,
                knowledge_changes=command.artifacts.knowledge_changes,
                memories=command.artifacts.memories,
                world_events=command.artifacts.world_events,
            ),
        )
        return await self._repository.finalize(request)


@pytest.mark.asyncio
async def test_finalization_requires_five_committed_turns_and_replays_idempotently(tmp_path):
    database, _paths, facade, _factory, opened = await _open_five_turn_facade(tmp_path)
    service = EpisodeFinalizationService(port=_FinalizationAdapter(database))
    try:
        command = _finalization_command(opened.session.session_id)
        with pytest.raises(Exception, match="expected_story_revision_mismatch"):
            await service.finalize(
                replace(
                    command,
                    expected_story_revision=0,
                    expected_store_revision=1,
                )
            )

        await _submit_five_turns(database, facade, opened)
        command = await _finalization_command_from_evidence(
            database, opened.session.session_id
        )
        finalized = await service.finalize(command)
        replayed = await service.finalize(replace(command, request_id="retry", trace_id="retry"))
        assert finalized.replayed is False
        assert replayed.replayed is True
        assert replayed.store_revision == finalized.store_revision
        assert await database.read_world(
            "SELECT status FROM story_sessions WHERE id=?",
            (opened.session.session_id,),
        ) == [{"status": "finalized"}]

        # G007: settlement closes the run without resolving the mystery. The
        # durable Episode must still carry its unresolved threads.
        rows = await database.read_world(
            "SELECT payload_json FROM episodes WHERE session_id=?",
            (opened.session.session_id,),
        )
        assert len(rows) == 1
        assert json.loads(rows[0]["payload_json"])["unresolved_threads"], (
            "a closed five-turn run must not resolve every thread"
        )
    finally:
        await database.close()


def _finalization_command(session_id: str) -> EpisodeFinalizationCommand:
    expected = _read(FIXTURES / "expected_episode.json")
    episode = _episode_from_expected(session_id, expected)
    artifacts = EpisodeFinalizationArtifacts(
        character_events=(),
        relationship_events=(),
        knowledge_changes=(),
        memories=(_memory([f"preflight-{session_id}"]),),
        world_events=(),
    )
    episode = episode.model_copy(
        update={"memory_ids": [artifacts.memories[0]["id"]]}
    )
    return EpisodeFinalizationCommand(
        session_id=session_id,
        expected_story_revision=5,
        world_time=episode.end_world_time,
        expected_store_revision=6,
        idempotency_key="finalize-golden-five-turn",
        request_id="request_finalize",
        trace_id="trace_finalize",
        episode=episode,
        artifacts=artifacts,
    )


async def _finalization_command_from_evidence(
    database: DatabaseManager, session_id: str
) -> EpisodeFinalizationCommand:
    port = SQLiteStorySessionCommitPort(database)
    session = await port.load_session(session_id)
    character_rows = await database.read_world(
        "SELECT id,turn_id,payload_json FROM turn_character_changes "
        "WHERE session_id=? ORDER BY committed_world_revision,ordinal",
        (session_id,),
    )
    relationship_rows = await database.read_world(
        "SELECT id,turn_id,payload_json FROM turn_relationship_changes "
        "WHERE session_id=? ORDER BY committed_world_revision,ordinal",
        (session_id,),
    )
    knowledge_rows = await database.read_world(
        "SELECT id,turn_id,payload_json FROM turn_knowledge_changes "
        "WHERE session_id=? ORDER BY committed_world_revision,ordinal",
        (session_id,),
    )
    world_event_rows = await database.read_world(
        "SELECT id,turn_id,payload_json FROM turn_world_events "
        "WHERE session_id=? ORDER BY committed_world_revision,ordinal",
        (session_id,),
    )

    character_events = tuple(
        {"id": row["id"], "change": json.loads(row["payload_json"])}
        for row in character_rows
    )
    relationship_events = tuple(
        {"id": row["id"], "change": json.loads(row["payload_json"])}
        for row in relationship_rows
    )
    knowledge_changes = tuple(
        _knowledge_artifact(row, worldline_id=session.worldline_id)
        for row in knowledge_rows
    )
    world_events = tuple(
        _world_event_artifact(
            row,
            episode_id=f"episode_{session_id}",
            world_id=session.world_id,
            worldline_id=session.worldline_id,
        )
        for row in world_event_rows
    )
    source_ids = [row["id"] for row in character_rows]
    artifacts = EpisodeFinalizationArtifacts(
        character_events=character_events,
        relationship_events=relationship_events,
        knowledge_changes=knowledge_changes,
        memories=(_memory(source_ids),),
        world_events=world_events,
    )
    expected = _read(FIXTURES / "expected_episode.json")
    episode = _episode_from_expected(session_id, expected).model_copy(
        update={
            "end_world_time": session.story_state.world_time,
            "secret_states": session.story_state.secret_states,
            "discovered_clue_ids": session.story_state.discovered_clue_ids,
            "unresolved_threads": session.story_state.active_conflicts or [],
            "character_event_ids": [item["id"] for item in character_events],
            "relationship_event_ids": [
                item["id"] for item in relationship_events
            ],
            "knowledge_change_ids": [item["id"] for item in knowledge_changes],
            "memory_ids": [artifacts.memories[0]["id"]],
            "world_event_ids": [item["id"] for item in world_events],
        }
    )
    return EpisodeFinalizationCommand(
        session_id=session_id,
        expected_story_revision=session.story_state.revision,
        world_time=session.story_state.world_time or "",
        expected_store_revision=6,
        idempotency_key="finalize-golden-five-turn",
        request_id="request_finalize",
        trace_id="trace_finalize",
        episode=episode,
        artifacts=artifacts,
    )


def _knowledge_artifact(row: dict, *, worldline_id: str) -> dict:
    candidate = json.loads(row["payload_json"])
    return {
        "schema_version": "1.0",
        "id": row["id"],
        "character_id": candidate["character_id"],
        "worldline_id": worldline_id,
        "proposition_id": candidate["proposition_id"],
        "certainty": candidate["certainty"],
        "source": {
            "type": "investigation",
            "ref": candidate["source_ref"],
            "reliability": candidate["certainty"],
        },
        "status": candidate["status"],
        "revision": 0,
    }


def _world_event_artifact(
    row: dict,
    *,
    episode_id: str,
    world_id: str,
    worldline_id: str,
) -> dict:
    candidate = json.loads(row["payload_json"])
    return {
        "schema_version": "1.0",
        "id": row["id"],
        "world_id": world_id,
        "worldline_id": worldline_id,
        "event_type": candidate["event_type"],
        "actors": candidate["actors"],
        "targets": candidate["targets"],
        "cause": {
            "episode_id": episode_id,
            "story_turn_id": row["turn_id"],
        },
        "payload": candidate["payload"],
        "visibility": candidate["visibility"],
        "persistence": "episode",
        "importance": "world",
        "revision": 0,
    }


def _episode_from_expected(session_id: str, expected: dict):
    from contracts import Episode

    return Episode.model_validate(
        {
            "schema_version": "1.0",
            "id": f"episode_{session_id}",
            "world_id": "world_001",
            "worldline_id": "wl_main",
            "story_seed_id": "seed_golden_001",
            "protagonist_ids": ["char_evelyn_gray"],
            "title": expected["title"],
            "start_world_time": "1349-06-12T21:40:00",
            "end_world_time": expected["end_world_time"],
            "ending": expected["ending"],
            "secret_states": expected["secret_states"],
            "discovered_clue_ids": expected["discovered_clue_ids"],
            "unresolved_threads": expected["unresolved_threads"],
            "narrative_block_ids": expected["narrative_block_ids"],
            "character_event_ids": [],
            "relationship_event_ids": [],
            "knowledge_change_ids": [],
            "memory_ids": [],
            "world_event_ids": [],
        }
    )


def _memory(source_ids: list[str]) -> dict:
    return {
        "schema_version": "1.0",
        "id": "memory_golden_five_turn",
        "character_id": "char_evelyn_gray",
        "worldline_id": "wl_main",
        "memory_type": "episode",
        "summary": "在诊所调查到 Jonathan 留下的片段，但真正组织仪式的人仍未知。",
        "importance": {
            "overall": 0.7,
            "emotional": 0.2,
            "relationship": 0.3,
            "identity": 0.1,
        },
        "source_ids": source_ids,
        "retention": "long",
    }


class _EpisodeFinalizingScenario(_GoldenFiveTurnScenario):
    def finalization_recipe(self, bootstrap, committed_session):
        del bootstrap, committed_session
        return FinalizationRecipe(
            episode_filename="episode.json",
            memory_filename="episode_memory.json",
        )


async def _episode_settlement_case(tmp_path: Path):
    database, _paths, facade, factory, opened = await _open_five_turn_facade(
        tmp_path
    )
    try:
        submitted, _sessions = await _submit_five_turns(database, facade, opened)
        session_id = opened.session.session_id
        story = SQLiteStorySessionCommitPort(database)
        turn = await story.load_turn(submitted[-1].receipt.turn_id)
        delta = await story.load_delta(turn.state_delta_id)
        session = await story.load_session(session_id)
        revision_rows = await database.read_world(
            "SELECT committed_world_revision FROM turn_transactions WHERE id=?",
            (turn.id,),
        )
        result = StoryTurnCommitResult(
            store_revision=revision_rows[0]["committed_world_revision"],
            session=session,
            turn=turn,
            delta=delta,
            replayed=False,
        )

        content_dir = tmp_path / "episode-content"
        content_dir.mkdir()
        content_path = content_dir / "canon.db"
        for filename in ("episode.json", "episode_memory.json"):
            (content_dir / filename).write_text(
                (FIXTURES / filename).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        settlement = ScenarioSettlement(
            database=database,
            expression=object(),
            content_path=content_path,
            scenario=_EpisodeFinalizingScenario(factory),
            frozen_expression=False,
        )
        return database, settlement, result
    except BaseException:
        await database.close()
        raise


async def _episode_row_counts(database: DatabaseManager) -> dict[str, int]:
    rows = await database.read_world(
        "SELECT "
        "(SELECT count(*) FROM episodes) AS episodes,"
        "(SELECT count(*) FROM episode_finalizations) AS finalizations,"
        "(SELECT count(*) FROM character_episode_memories) AS memories"
    )
    return rows[0]


async def _store_revision(database: DatabaseManager) -> int:
    rows = await database.read_world(
        "SELECT revision FROM world_meta WHERE singleton=1"
    )
    return rows[0]["revision"]


async def _commit_unrelated_world_change(
    database: DatabaseManager, session: StorySession, *, advance_session: bool = False
) -> None:
    current_revision = await _store_revision(database)
    event_id = (
        "test-session-advance"
        if advance_session
        else "test-unrelated-world-commit"
    )
    request = CommitRequest(
        worldline_id=session.worldline_id,
        world_time=session.story_state.world_time or "",
        expected_revision=current_revision,
        idempotency_key=event_id,
        request_id=f"request-{event_id}",
        trace_id=f"trace-{event_id}",
        operation={"kind": "test.unrelated_world_change"},
        events=(
            StoredEvent(
                event_id=event_id,
                aggregate_id=session.id if advance_session else "unrelated-session",
                event_type="test.unrelated_world_change",
                payload={},
            ),
        ),
    )
    if advance_session:
        advanced_state = session.story_state.model_copy(
            update={
                "revision": session.story_state.revision + 1,
                "turn": session.story_state.turn + 1,
            }
        )
        advanced_json = json.dumps(
            advanced_state.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

        def apply(tx):
            tx.execute(
                "UPDATE story_sessions SET story_revision=?,story_state_json=?,"
                "committed_world_revision=? WHERE id=?",
                (
                    advanced_state.revision,
                    advanced_json,
                    tx.revision,
                    session.id,
                ),
            )
            return {"session_id": session.id, "story_revision": advanced_state.revision}

        await database.commit_resolved(request, apply)
        return
    await database.commit_resolved(request, lambda _tx: {"unrelated": True})


@pytest.mark.asyncio
async def test_episode_settlement_returns_early_for_completed_episode(tmp_path):
    database, settlement, result = await _episode_settlement_case(tmp_path)
    try:
        await settlement.settle(result)
        before = await _episode_row_counts(database)

        load_calls = 0
        finalize_calls = 0
        original_load = settlement.episodes.load_by_session
        original_finalize = settlement.episodes.finalize

        async def record_load(session_id: str):
            nonlocal load_calls
            load_calls += 1
            return await original_load(session_id)

        async def record_finalize(request):
            nonlocal finalize_calls
            finalize_calls += 1
            return await original_finalize(request)

        settlement.episodes.load_by_session = record_load
        settlement.episodes.finalize = record_finalize
        await settlement.settle(result)
        await settlement.settle(result)

        assert load_calls == 2
        assert finalize_calls == 0
        assert await _episode_row_counts(database) == before
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_episode_settlement_reads_current_revision_after_unrelated_commit(
    tmp_path,
):
    database, settlement, result = await _episode_settlement_case(tmp_path)
    try:
        old_turn_revision = result.store_revision
        await _commit_unrelated_world_change(database, result.session)
        current_revision = await _store_revision(database)
        assert current_revision == old_turn_revision + 1

        attempted_revisions = []
        conflicted_revisions = []
        original_finalize = settlement.episodes.finalize

        async def record_finalize(request):
            attempted_revisions.append(request.expected_store_revision)
            try:
                return await original_finalize(request)
            except RevisionConflict:
                conflicted_revisions.append(request.expected_store_revision)
                raise

        settlement.episodes.finalize = record_finalize
        await settlement.settle(result)
        await settlement.settle(result)

        counts = await _episode_row_counts(database)
        assert counts["finalizations"] == 1, (
            "episode did not recover after an unrelated world commit: "
            f"turn_revision={old_turn_revision}, current_revision={current_revision}, "
            f"attempted_revisions={attempted_revisions}, "
            f"revision_conflicts={conflicted_revisions}"
        )
        assert attempted_revisions == [current_revision]
        assert conflicted_revisions == []
        assert await _store_revision(database) == current_revision + 1
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_episode_settlement_reports_when_session_left_terminal_turn(tmp_path):
    database, settlement, result = await _episode_settlement_case(tmp_path)
    try:
        await _commit_unrelated_world_change(
            database, result.session, advance_session=True
        )
        current_revision = await _store_revision(database)

        with pytest.raises(RuntimeError) as failure:
            await settlement.settle(result)

        assert failure.value.stage == "episode_finalize"
        assert failure.value.code == "session_advanced"
        assert await _episode_row_counts(database) == {
            "episodes": 0,
            "finalizations": 0,
            "memories": 0,
        }
        assert await _store_revision(database) == current_revision
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_episode_settlement_surfaces_finalize_failure_without_revision_change(
    tmp_path,
):
    database, settlement, result = await _episode_settlement_case(tmp_path)
    try:
        before_revision = await _store_revision(database)
        before_counts = await _episode_row_counts(database)

        async def fail_finalize(_request):
            raise RuntimeError("injected finalization failure")

        settlement.episodes.finalize = fail_finalize
        with pytest.raises(RuntimeError) as failure:
            await settlement.settle(result)

        assert failure.value.stage == "episode_finalize"
        assert failure.value.code == "episode_finalize_failed"
        assert await _episode_row_counts(database) == before_counts
        assert await _store_revision(database) == before_revision
    finally:
        await database.close()
