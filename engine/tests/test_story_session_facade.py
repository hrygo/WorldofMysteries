"""Trusted first-turn facade integration on the real durable chain."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3 as stdlib_sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai.golden_first_turn import GoldenFirstTurnFactory
from application.advice_interpretation import (
    AdviceInterpretationCandidate,
    AdviceInterpretationError,
    FrozenTurnInput,
)
from application.scenario_policy import (
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
    SegmentDeliveryView,
    StoredInputRecord,
    StoryEntrySnapshot,
    StoryFacadeError,
    StorySessionFacade,
    StorySessionSnapshotRecord,
    SubmitAdviceCommand,
    TurnDeliveryView,
)
from application.story_session_open import StorySessionOpenService
from application.story_turn_commit import DomainValidationContext
from application.turn_context_binding import AuthorizedTurnContextBinding
from application.turn_input import (
    TurnInputReceipt,
    TurnInputStatus,
)
from application.turn_orchestrator import TurnOrchestrator
from domain.resolution_policy import ResolutionPolicy
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.player_advice_repository import SQLitePlayerAdviceRepository
from infrastructure.scenarios.golden_policy import GoldenScenarioPolicy
from infrastructure.sqlite_runtime import sqlite3
from infrastructure.story_bootstrap_repository import SQLiteStoryBootstrapRepository
from infrastructure.story_control import story_control_handlers
from infrastructure.story_runtime import (
    _BoundSQLitePlayerAdviceRepository,
    _SQLiteTurnContextBindingPort,
)
from infrastructure.story_session_open_repository import SQLiteStorySessionOpenPort
from infrastructure.story_session_repository import SQLiteStorySessionCommitPort
from infrastructure.turn_context_repository import SQLiteTurnContextRepository
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


class GoldenTestScenarioPolicy:
    """Test-only policy wrapper for the frozen single-turn fixture."""

    def __init__(self) -> None:
        self._golden = GoldenFirstTurnFactory()

    def identity(self, bootstrap):
        return ScenarioIdentity(
            scenario_id=bootstrap.scenario_id,
            content_digest=bootstrap.content_digest,
            rules_revision=bootstrap.policy_version,
        )

    def decision(self, session, committed_evidence):
        del committed_evidence
        terminal = session.story_state.turn >= self._golden.max_turn
        return TurnPolicyDecision(
            allowed_to_submit=(session.status.value == "active" and not terminal),
            terminal=terminal,
            reason="iteration_limit_reached" if terminal else None,
        )

    def expected_input(self, bootstrap, session):
        next_turn = session.story_state.turn + 1
        if next_turn > self._golden.max_turn:
            return None
        return self._golden.expected_input(bootstrap, next_turn)

    def resolution_policy(self, bootstrap, session) -> ResolutionPolicy:
        return self._golden.policy_for_turn(
            bootstrap, session.story_state.turn + 1
        )

    def validation_context(
        self, bootstrap, session
    ) -> DomainValidationContext:
        return self._golden.domain_validation_for(
            bootstrap, session.story_state.turn + 1
        )

    def finalization_recipe(self, bootstrap, committed_session):
        del bootstrap, committed_session


class MissingFixedInputScenario(GoldenTestScenarioPolicy):
    def expected_input(self, bootstrap, session):
        del bootstrap, session


class CountingWorkers:
    def __init__(self) -> None:
        self.interpreter_calls = 0
        self.proposer_calls = 0
        self.supports_live_input = False
        self._golden = GoldenFirstTurnFactory()
        self.allowed_signatures = ()

    def interpreter_for(self, bootstrap, turn_number=1):
        self.interpreter_calls += 1
        return self._golden.interpreter_for(bootstrap, turn_number)

    def proposer_for(self, bootstrap, turn_number, allowed_signatures):
        self.proposer_calls += 1
        self.allowed_signatures = allowed_signatures
        return self._golden.proposer_for(bootstrap, turn_number)

    def narrative_compiler(self, bootstrap):
        del bootstrap
        raise AssertionError("the Golden facade test does not compile narration")


class _FreeTextInterpreter:
    def __init__(self, workers) -> None:
        self._workers = workers

    async def interpret(self, value):
        self._workers.interpreted_inputs.append(value.raw_input)
        return AdviceInterpretationCandidate(
            interpreter_revision="test-live-interpreter-v1",
            primary_intent="observe_subject",
            secondary_intents=(),
            proposed_actions=("continue_conversation",),
            risk_preference=None,
            confidence=0.9,
        )


class LiveCapableTestWorkers(CountingWorkers):
    def __init__(self) -> None:
        super().__init__()
        self.supports_live_input = True
        self.interpreted_inputs: list[str] = []

    def interpreter_for(self, bootstrap, turn_number=1):
        del bootstrap, turn_number
        self.interpreter_calls += 1
        return _FreeTextInterpreter(self)


class _BlockingFreeTextInterpreter:
    def __init__(self, workers) -> None:
        self._workers = workers

    async def interpret(self, value):
        self._workers.interpreted_inputs.append(value.raw_input)
        self._workers.interpreter_started.set()
        await self._workers.release_interpreter.wait()
        return AdviceInterpretationCandidate(
            interpreter_revision="test-live-interpreter-v1",
            primary_intent="observe_subject",
            secondary_intents=(),
            proposed_actions=("continue_conversation",),
            risk_preference=None,
            confidence=0.9,
        )


class BlockingLiveWorkers(LiveCapableTestWorkers):
    def __init__(self) -> None:
        super().__init__()
        self.interpreter_started = asyncio.Event()
        self.release_interpreter = asyncio.Event()

    def interpreter_for(self, bootstrap, turn_number=1):
        del bootstrap, turn_number
        self.interpreter_calls += 1
        return _BlockingFreeTextInterpreter(self)


class _ConcurrentAdmissionInterpreter:
    def __init__(self, workers) -> None:
        self._workers = workers

    async def interpret(self, value):
        self._workers.started[value.input_turn_id].set()
        await self._workers.release[value.input_turn_id].wait()
        raise AdviceInterpretationError("controlled_model_failure")


class _ConcurrentAdmissionWorkers:
    supports_live_input = True

    def __init__(self, input_turn_ids: tuple[str, ...]) -> None:
        self.started = {value: asyncio.Event() for value in input_turn_ids}
        self.release = {value: asyncio.Event() for value in input_turn_ids}

    def interpreter_for(self, bootstrap, turn_number=1):
        del bootstrap, turn_number
        return _ConcurrentAdmissionInterpreter(self)

    def proposer_for(self, bootstrap, turn_number, allowed_signatures):
        del bootstrap, turn_number, allowed_signatures
        return object()

    def narrative_compiler(self, bootstrap):
        del bootstrap

    async def aclose(self):
        return None


class _ContextBoundFreeTextInterpreter:
    def __init__(self, bootstrap) -> None:
        self._bootstrap = bootstrap

    async def interpret(self, value):
        binding = AuthorizedTurnContextBinding(
            turn_id=value.turn_id,
            stage="interpretation",
            input_turn_id=value.input_turn_id,
            source_store_revision=value.public_expected_store_revision,
            source_story_revision=value.base_revisions.story,
            policy_revision=self._bootstrap.policy_version,
            content_digest=self._bootstrap.content_digest,
            lineage_digest="test-lineage",
            manifest=(),
        )
        return AdviceInterpretationCandidate(
            interpreter_revision="test-bound-interpreter-v1",
            primary_intent="observe_subject",
            secondary_intents=(),
            proposed_actions=("continue_conversation",),
            risk_preference=None,
            confidence=0.9,
            context_binding=binding,
        )


class _StaleActionBindingProposer:
    def __init__(self, delegate) -> None:
        self._delegate = delegate

    async def propose(self, **kwargs):
        expected = kwargs.pop("expected_context_binding")
        assert isinstance(expected, AuthorizedTurnContextBinding)
        candidate = await self._delegate.propose(**kwargs)
        stale_action_binding = replace(
            expected,
            stage="action",
            source_store_revision=expected.source_store_revision + 1,
        )
        return replace(candidate, context_binding=stale_action_binding)


class StaleContextLiveWorkers(LiveCapableTestWorkers):
    def interpreter_for(self, bootstrap, turn_number=1):
        del turn_number
        self.interpreter_calls += 1
        return _ContextBoundFreeTextInterpreter(bootstrap)

    def proposer_for(self, bootstrap, turn_number, allowed_signatures):
        self.proposer_calls += 1
        self.allowed_signatures = allowed_signatures
        return _StaleActionBindingProposer(
            self._golden.proposer_for(bootstrap, turn_number)
        )


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


def _facade(
    database: DatabaseManager,
    source: Source,
    scenario: GoldenTestScenarioPolicy,
    workers: CountingWorkers,
    *,
    advice=None,
    context_bindings=None,
    after_commit=None,
):
    query = Query(database, source)
    advice_port = (
        SQLitePlayerAdviceRepository(database)
        if advice is None
        else advice
    )
    return StorySessionFacade(
        initialization=StoryInitializationService(source),
        open_sessions=StorySessionOpenService(SQLiteStorySessionOpenPort(database)),
        query=query,
        scenario=scenario,
        turns=TurnOrchestrator(
            sessions=query,
            intake=SQLiteTurnInputCommandPort(database),
            advice=advice_port,
            story=SQLiteStorySessionCommitPort(database),
            scenario=scenario,
            workers=workers,
            context=context_bindings,
            work=after_commit,
        ),
    )


@pytest.mark.asyncio
async def test_facade_open_submit_and_get_advice_use_real_durable_chain(tmp_path):
    database, _ = await _database(tmp_path)
    source = Source()
    scenario = GoldenTestScenarioPolicy()
    workers = CountingWorkers()
    delivery_calls = []

    async def after_commit(command, result, session):
        delivery_calls.append((command.input_turn_id, result.turn.id, session))
        return TurnDeliveryView(
            state="ready",
            narrative_block_id="narrative-01",
            speech_units=(_ready_unit(1),),
        )

    facade = _facade(
        database,
        source,
        scenario,
        workers,
        after_commit=after_commit,
    )
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
        initial_snapshot = await facade._query.session(
            opened.session.session_id
        )
        expected_signatures = tuple(
            rule.signature
            for rule in scenario.resolution_policy(
                initial_snapshot.bootstrap, initial_snapshot.session
            ).rules
        )

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
        assert workers.interpreter_calls == 1
        assert workers.proposer_calls == 1
        assert workers.allowed_signatures == expected_signatures
        assert submitted.delivery is not None
        assert submitted.delivery.state == "ready"
        assert len(delivery_calls) == 1

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
        assert replayed.delivery is None
        assert len(delivery_calls) == 1
        assert workers.interpreter_calls == 1
        assert workers.proposer_calls == 1

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
async def test_same_session_submission_admission_stays_serial_during_model_work(
    tmp_path,
):
    database, _ = await _database(tmp_path)
    source = Source()
    scenario = GoldenTestScenarioPolicy()
    workers = BlockingLiveWorkers()
    facade = _facade(database, source, scenario, workers)
    assert not hasattr(facade, "_locks")
    assert isinstance(facade._turns, TurnOrchestrator)
    try:
        opened = await facade.open(
            scenario_id=GOLDEN_SCENARIO_ID,
            open_request_id="open_serial_admission_001",
            expected_store_revision=0,
            request_id="request_open_serial_admission",
            trace_id="trace_open_serial_admission",
        )
        first_command = SubmitAdviceCommand(
            session_id=opened.session.session_id,
            input_turn_id="input_serial_first_001",
            raw_input="先观察医生的反应。",
            expected_story_revision=0,
            expected_store_revision=1,
            request_id="request_serial_first",
            trace_id="trace_serial_first",
        )
        second_command = SubmitAdviceCommand(
            session_id=opened.session.session_id,
            input_turn_id="input_serial_second_001",
            raw_input="然后再记录医生的反应。",
            expected_story_revision=0,
            expected_store_revision=1,
            request_id="request_serial_second",
            trace_id="trace_serial_second",
        )

        first = asyncio.create_task(facade.submit_live(first_command))
        await asyncio.wait_for(workers.interpreter_started.wait(), timeout=2)
        second = asyncio.create_task(facade.submit_live(second_command))
        await asyncio.sleep(0)

        assert not second.done()
        assert workers.interpreter_calls == 1

        workers.release_interpreter.set()
        committed = await first
        with pytest.raises(StoryFacadeError, match="revision_conflict"):
            await second

        assert committed.receipt.status == "committed"
        assert workers.interpreter_calls == 1
        assert workers.interpreted_inputs == ["先观察医生的反应。"]
        assert await database.read_world(
            "SELECT count(*) AS count FROM turn_intake_commands"
        ) == [{"count": 1}]
    finally:
        workers.release_interpreter.set()
        await database.close()


@pytest.mark.asyncio
async def test_different_sessions_do_not_block_each_other_during_model_work():
    source = Source()
    first_bootstrap = (
        await StoryInitializationService(source).initialize(
            scenario_id=GOLDEN_SCENARIO_ID,
            open_request_id="open_cross_session_first",
        )
    ).bootstrap
    second_bootstrap = (
        await StoryInitializationService(source).initialize(
            scenario_id=GOLDEN_SCENARIO_ID,
            open_request_id="open_cross_session_second",
        )
    ).bootstrap
    input_ids = ("input_cross_session_first", "input_cross_session_second")
    workers = _ConcurrentAdmissionWorkers(input_ids)
    records: dict[str, TurnInputReceipt] = {}
    snapshots = {
        bootstrap.initial_session.id: StorySessionSnapshotRecord(
            session=bootstrap.initial_session,
            bootstrap=bootstrap,
            observed_store_revision=4,
        )
        for bootstrap in (first_bootstrap, second_bootstrap)
    }

    class Sessions:
        async def session(self, session_id):
            return snapshots[session_id]

        async def input(self, _session_id, input_turn_id):
            receipt = records.get(input_turn_id)
            if receipt is None:
                return None
            return StoredInputRecord(
                receipt=receipt,
                committed_story_revision=None,
            )

    class Intake:
        async def load(self, input_turn_id):
            return records.get(input_turn_id)

        async def receive(self, command):
            receipt = TurnInputReceipt(
                input_turn_id=command.input_turn_id,
                session_id=command.session_id,
                turn_id=command.turn_id,
                idempotency_key=command.idempotency_key,
                input_mode=command.input_mode,
                input_sha256=command.input_sha256,
                base_revisions=command.base_revisions,
                status=TurnInputStatus.RECEIVED,
                committed_world_revision=None,
                public_expected_store_revision=(
                    command.public_expected_store_revision
                ),
            )
            records[receipt.input_turn_id] = receipt
            return receipt

        async def cancel(self, input_turn_id):
            return records[input_turn_id]

    intake = Intake()

    class Advice:
        async def load_advice(self, _input_turn_id):
            return None

        async def load_input(self, input_turn_id):
            receipt = records[input_turn_id]
            return FrozenTurnInput(
                input_turn_id=receipt.input_turn_id,
                session_id=receipt.session_id,
                turn_id=receipt.turn_id,
                idempotency_key=receipt.idempotency_key,
                input_mode=receipt.input_mode,
                raw_input=raw_inputs[input_turn_id],
                input_sha256=receipt.input_sha256,
                base_revisions=receipt.base_revisions,
                status=receipt.status,
                committed_world_revision=receipt.committed_world_revision,
                public_expected_store_revision=(
                    receipt.public_expected_store_revision
                ),
            )

        async def publish(self, *args, **kwargs):
            del args, kwargs
            raise AssertionError("controlled interpreter failure must not publish")

    raw_inputs = {
        input_ids[0]: "先观察医生的反应。",
        input_ids[1]: "记录病历里的日期。",
    }
    query = Sessions()
    scenario = GoldenTestScenarioPolicy()
    turns = TurnOrchestrator(
        sessions=query,
        intake=intake,
        advice=Advice(),
        story=None,
        scenario=scenario,
        workers=workers,
    )
    facade = StorySessionFacade(
        initialization=None,
        open_sessions=None,
        query=query,
        scenario=scenario,
        turns=turns,
    )

    async def submit(session_id: str, input_turn_id: str, index: int):
        return await facade.submit_live(
            SubmitAdviceCommand(
                session_id=session_id,
                input_turn_id=input_turn_id,
                raw_input=raw_inputs[input_turn_id],
                expected_story_revision=0,
                expected_store_revision=4,
                request_id=f"request_cross_session_{index}",
                trace_id=f"trace_cross_session_{index}",
            )
        )

    first = asyncio.create_task(
        submit(first_bootstrap.initial_session.id, input_ids[0], 1)
    )
    second = None
    try:
        try:
            await asyncio.wait_for(
                workers.started[input_ids[0]].wait(),
                timeout=2,
            )
        except TimeoutError:
            if first.done():
                first.result()
            raise
        second = asyncio.create_task(
            submit(second_bootstrap.initial_session.id, input_ids[1], 2)
        )
        await asyncio.wait_for(workers.started[input_ids[1]].wait(), timeout=2)
        assert not first.done()
        assert not second.done()
    finally:
        for release in workers.release.values():
            release.set()
        tasks = [first]
        if second is not None:
            tasks.append(second)
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    assert len(outcomes) == 2
    assert all(
        isinstance(outcome, AdviceInterpretationError)
        and outcome.code == "controlled_model_failure"
        for outcome in outcomes
    )


@pytest.mark.asyncio
async def test_same_session_admission_is_not_held_by_post_commit_delivery(tmp_path):
    database, _ = await _database(tmp_path)
    source = Source()
    scenario = GoldenTestScenarioPolicy()
    workers = CountingWorkers()
    delivery_started = asyncio.Event()
    release_delivery = asyncio.Event()

    async def after_commit(command, result, session):
        del command, result, session
        delivery_started.set()
        await release_delivery.wait()
        return TurnDeliveryView(
            state="ready",
            narrative_block_id="narrative-01",
            speech_units=(_ready_unit(1),),
        )

    facade = _facade(
        database,
        source,
        scenario,
        workers,
        after_commit=after_commit,
    )
    try:
        opened = await facade.open(
            scenario_id=GOLDEN_SCENARIO_ID,
            open_request_id="open_post_commit_lock_001",
            expected_store_revision=0,
            request_id="request_open_post_commit_lock",
            trace_id="trace_open_post_commit_lock",
        )
        first = asyncio.create_task(
            facade.submit(
                SubmitAdviceCommand(
                    session_id=opened.session.session_id,
                    input_turn_id="input_post_commit_lock_001",
                    raw_input=SUPPORTED_ADVICE,
                    expected_story_revision=0,
                    expected_store_revision=1,
                    request_id="request_post_commit_lock_first",
                    trace_id="trace_post_commit_lock_first",
                )
            )
        )
        await asyncio.wait_for(delivery_started.wait(), timeout=2)
        second = asyncio.create_task(
            facade.submit(
                SubmitAdviceCommand(
                    session_id=opened.session.session_id,
                    input_turn_id="input_post_commit_lock_002",
                    raw_input=SUPPORTED_ADVICE,
                    expected_story_revision=1,
                    expected_store_revision=2,
                    request_id="request_post_commit_lock_second",
                    trace_id="trace_post_commit_lock_second",
                )
            )
        )

        try:
            with pytest.raises(StoryFacadeError, match="iteration_limit_reached"):
                await asyncio.wait_for(second, timeout=1)
        finally:
            release_delivery.set()

        submitted = await first
        assert submitted.receipt.committed_story_revision == 1
        assert submitted.delivery is not None
        assert submitted.delivery.state == "ready"
        assert workers.interpreter_calls == 1
    finally:
        release_delivery.set()
        await database.close()


@pytest.mark.asyncio
async def test_facade_rejects_unsupported_text_before_intake(tmp_path):
    database, _ = await _database(tmp_path)
    source = Source()
    scenario = GoldenTestScenarioPolicy()
    workers = CountingWorkers()
    facade = _facade(database, source, scenario, workers)
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
        assert workers.interpreter_calls == 0
        assert workers.proposer_calls == 0
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_fixed_method_rejects_when_scenario_has_no_fixed_input(tmp_path):
    database, _ = await _database(tmp_path)
    source = Source()
    scenario = MissingFixedInputScenario()
    workers = CountingWorkers()
    facade = _facade(database, source, scenario, workers)
    try:
        opened = await facade.open(
            scenario_id=GOLDEN_SCENARIO_ID,
            open_request_id="open_fixed_missing_001",
            expected_store_revision=0,
            request_id="request_open",
            trace_id="trace_open",
        )
        with pytest.raises(Exception, match="fixed_input_unsupported"):
            await facade.submit(
                SubmitAdviceCommand(
                    session_id=opened.session.session_id,
                    input_turn_id="input_fixed_missing_001",
                    raw_input=SUPPORTED_ADVICE,
                    expected_story_revision=0,
                    expected_store_revision=1,
                    request_id="request_fixed_missing",
                    trace_id="trace_fixed_missing",
                )
            )
        assert await database.read_world(
            "SELECT count(*) AS count FROM turn_intake_commands"
        ) == [{"count": 0}]
        assert workers.interpreter_calls == 0
        assert workers.proposer_calls == 0
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_live_method_requires_live_worker_before_accepting_free_input(tmp_path):
    database, _ = await _database(tmp_path)
    source = Source()
    scenario = GoldenTestScenarioPolicy()
    workers = CountingWorkers()
    facade = _facade(database, source, scenario, workers)
    try:
        opened = await facade.open(
            scenario_id=GOLDEN_SCENARIO_ID,
            open_request_id="open_live_without_worker_001",
            expected_store_revision=0,
            request_id="request_open",
            trace_id="trace_open",
        )
        with pytest.raises(Exception, match="live_worker_unavailable"):
            await facade.submit_live(
                SubmitAdviceCommand(
                    session_id=opened.session.session_id,
                    input_turn_id="input_live_without_worker_001",
                    raw_input="自由描述一个不同的行动",
                    expected_story_revision=0,
                    expected_store_revision=1,
                    request_id="request_live_without_worker",
                    trace_id="trace_live_without_worker",
                )
            )
        assert await database.read_world(
            "SELECT count(*) AS count FROM turn_intake_commands"
        ) == [{"count": 0}]
        assert workers.interpreter_calls == 0
        assert workers.proposer_calls == 0
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_live_method_accepts_free_text_with_live_worker_using_same_policy(
    tmp_path,
):
    database, _ = await _database(tmp_path)
    source = Source()
    scenario = GoldenTestScenarioPolicy()
    workers = LiveCapableTestWorkers()
    facade = _facade(database, source, scenario, workers)
    raw_input = "我希望先记录医生刚才的停顿。"
    try:
        opened = await facade.open(
            scenario_id=GOLDEN_SCENARIO_ID,
            open_request_id="open_live_worker_001",
            expected_store_revision=0,
            request_id="request_open",
            trace_id="trace_open",
        )
        snapshot = await facade._query.session(opened.session.session_id)
        policy = scenario.resolution_policy(snapshot.bootstrap, snapshot.session)

        submitted = await facade.submit_live(
            SubmitAdviceCommand(
                session_id=opened.session.session_id,
                input_turn_id="input_live_worker_001",
                raw_input=raw_input,
                expected_story_revision=0,
                expected_store_revision=1,
                request_id="request_live_worker",
                trace_id="trace_live_worker",
            )
        )

        assert submitted.receipt.status == "committed"
        assert submitted.session.turn == 1
        assert [clue.id for clue in submitted.session.discovered_clues] == [
            "clue_doctor_pause"
        ]
        assert workers.interpreted_inputs == [raw_input]
        assert workers.allowed_signatures == tuple(
            rule.signature for rule in policy.rules
        )
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_story_control_maps_stale_live_context_and_keeps_input_pending(
    tmp_path,
):
    database, _ = await _database(tmp_path)
    source = Source()
    scenario = GoldenTestScenarioPolicy()
    workers = StaleContextLiveWorkers()
    context_bindings = _SQLiteTurnContextBindingPort(
        SQLiteTurnContextRepository(database)
    )
    advice = _BoundSQLitePlayerAdviceRepository(
        SQLitePlayerAdviceRepository(database),
        context_bindings,
    )
    facade = _facade(
        database,
        source,
        scenario,
        workers,
        advice=advice,
        context_bindings=context_bindings,
    )
    handlers = story_control_handlers(facade)
    try:
        opened, error, retryable = await handlers["story.session.open"](
            {
                "request_id": "request_open_stale_context",
                "trace_id": "trace_open_stale_context",
                "idempotency_key": "open_stale_context",
            },
            {
                "schema_version": "1.0",
                "scenario_id": GOLDEN_SCENARIO_ID,
                "open_request_id": "open_stale_context",
                "expected_store_revision": 0,
            },
        )
        assert error is None
        assert not retryable
        assert opened is not None
        session_id = opened["session"]["session_id"]

        result, error, retryable = await handlers["story.turn.submit"](
            {
                "request_id": "request_submit_stale_context",
                "trace_id": "trace_submit_stale_context",
                "idempotency_key": "input_stale_context",
            },
            {
                "schema_version": "1.0",
                "session_id": session_id,
                "input_turn_id": "input_stale_context",
                "raw_input": "请先观察医生的反应。",
                "input_mode": "text",
                "expected_story_revision": 0,
                "expected_store_revision": 1,
            },
        )

        assert result is None
        assert error == "revision_conflict"
        assert not retryable
        assert await database.read_world(
            "SELECT status FROM turn_intake_commands "
            "WHERE input_turn_id=?",
            ("input_stale_context",),
        ) == [{"status": "received"}]
        turn_rows = await database.read_world(
            "SELECT turn_id FROM turn_intake_commands WHERE input_turn_id=?",
            ("input_stale_context",),
        )
        assert len(turn_rows) == 1
        assert await database.read_world(
            "SELECT stage FROM turn_context_bindings WHERE turn_id=? "
            "ORDER BY stage",
            (turn_rows[0]["turn_id"],),
        ) == [{"stage": "interpretation"}]
        assert workers.interpreter_calls == 1
        assert workers.proposer_calls == 1
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_injected_conditional_exit_policy_controls_service_public_view():
    from test_scenario_policy import ConditionalExitTestPolicy

    from application.story_session_facade import StorySessionFacade

    initialized = await StoryInitializationService(Source()).initialize(
        scenario_id=GOLDEN_SCENARIO_ID,
        open_request_id="open_conditional_exit_001",
    )
    bootstrap = initialized.bootstrap.model_copy(
        update={
            "scenario_id": "conditional_exit",
            "presentation": initialized.bootstrap.presentation.model_copy(
                update={
                    "clue_display_names": {
                        **initialized.bootstrap.presentation.clue_display_names,
                        "exit_clue": "出口线索",
                    }
                }
            ),
        }
    )
    session = initialized.initial_session.model_copy(
        update={
            "story_state": initialized.initial_session.story_state.model_copy(
                update={
                    "turn": 2,
                    "revision": 2,
                    "discovered_clue_ids": ["exit_clue"],
                }
            )
        }
    )

    class SnapshotQuery:
        async def session(self, session_id):
            assert session_id == session.id
            return StorySessionSnapshotRecord(
                session=session,
                bootstrap=bootstrap,
                observed_store_revision=3,
            )

        async def input(self, _session_id, _input_turn_id):
            return None

    query = SnapshotQuery()
    policy = ConditionalExitTestPolicy()
    facade = StorySessionFacade(
        initialization=None,
        open_sessions=None,
        query=query,
        scenario=policy,
        turns=TurnOrchestrator(
            sessions=query,
            intake=None,
            advice=None,
            story=None,
            scenario=policy,
            workers=CountingWorkers(),
        ),
    )

    view = await facade.get(session.id)

    assert view.session.scenario_id == "conditional_exit"
    assert view.session.turn == 2
    assert view.session.discovered_clues[0].display_name == "出口线索"
    assert view.session.can_submit is False
    with pytest.raises(StoryFacadeError, match="exit_clue_committed"):
        await facade.submit(
            SubmitAdviceCommand(
                session_id=session.id,
                input_turn_id="input_after_exit_clue",
                raw_input="尝试继续已结束的场景。",
                expected_story_revision=2,
                expected_store_revision=3,
                request_id="request_after_exit_clue",
                trace_id="trace_after_exit_clue",
            )
        )


@pytest.mark.asyncio
async def test_get_fails_closed_for_unknown_frozen_scenario_identity():
    initialized = await StoryInitializationService(Source()).initialize(
        scenario_id=GOLDEN_SCENARIO_ID,
        open_request_id="open_unknown_identity_001",
    )
    bootstrap = initialized.bootstrap.model_copy(
        update={"content_digest": "f" * 64}
    )
    session = initialized.initial_session

    class SnapshotQuery:
        async def session(self, session_id):
            assert session_id == session.id
            return StorySessionSnapshotRecord(
                session=session,
                bootstrap=bootstrap,
                observed_store_revision=1,
            )

    query = SnapshotQuery()
    scenario = GoldenScenarioPolicy(object())
    facade = StorySessionFacade(
        initialization=None,
        open_sessions=None,
        query=query,
        scenario=scenario,
        turns=TurnOrchestrator(
            sessions=query,
            intake=None,
            advice=None,
            story=None,
            scenario=scenario,
            workers=CountingWorkers(),
        ),
    )

    with pytest.raises(StoryFacadeError, match="unknown_scenario_identity"):
        await facade.get(session.id)


def _ready_unit(index: int) -> SegmentDeliveryView:
    return SegmentDeliveryView(
        segment_index=index,
        state="ready",
        speech_unit_id=f"speech_unit_{index}",
        spoken_text="别动那只表。",
        render_recipe={"segment_index": index},
    )


def test_a_ready_segment_must_carry_its_own_recipe():
    """A ready segment with nothing to play is a lie the App would act on."""
    with pytest.raises(ValidationError):
        SegmentDeliveryView(
            segment_index=1,
            state="ready",
            speech_unit_id="speech_unit_1",
            spoken_text="别动那只表。",
        )


def test_an_unavailable_segment_must_say_why():
    """Without a reason a gap is indistinguishable from an oversight."""
    with pytest.raises(ValidationError):
        SegmentDeliveryView(segment_index=1, state="unavailable")


def test_a_ready_segment_may_not_also_claim_a_reason():
    with pytest.raises(ValidationError):
        SegmentDeliveryView(
            segment_index=1,
            state="ready",
            speech_unit_id="speech_unit_1",
            spoken_text="别动那只表。",
            render_recipe={},
            reason="voice_binding_not_found",
        )


def test_a_turn_keeps_its_segments_in_block_order():
    """Order is the block's order. Reordering here would desync text from audio."""
    view = TurnDeliveryView(
        state="ready",
        narrative_block_id="narrative-01",
        speech_units=(
            SegmentDeliveryView(segment_index=3, state="unavailable", reason="x"),
            _ready_unit(5),
            _ready_unit(7),
        ),
    )
    assert [unit.segment_index for unit in view.speech_units] == [3, 5, 7]
    assert view.speech_units[0].state == "unavailable"


def test_a_ready_turn_with_nothing_sealed_is_refused():
    """``ready`` with no playable unit is a silence the player would blame on us.

    The single-segment mirror used to make this unrepresentable; now that it is
    gone, the batch itself has to carry the fact, and a coordinator that
    forgets to build one fails here instead of shipping a hollow ``ready``.
    """
    with pytest.raises(ValidationError):
        TurnDeliveryView(
            state="ready",
            narrative_block_id="narrative-01",
            speech_units=(
                SegmentDeliveryView(segment_index=1, state="unavailable", reason="voice_binding_not_found"),
            ),
        )
    with pytest.raises(ValidationError):
        TurnDeliveryView(state="ready", narrative_block_id="narrative-01")
