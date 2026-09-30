"""Driving one supply task: choose, review, bind — each at most once."""
from __future__ import annotations

import sqlite3

import pytest
import pytest_asyncio

from application.voice_foundry_commands import (
    VoiceFoundryCommandError,
    VoiceFoundryCommandService,
)
from application.voice_foundry import WorkerStep
from application.voice_foundry_service import (
    VoiceSupplyOutcome,
    VoiceSupplyService,
)
from domain.voice_identity import VoiceBindingScope, VoiceBindingStatus

# Imported without the ``engine.`` prefix on purpose. Both spellings resolve
# here — the repo root and ``engine/`` are both on sys.path — and they load the
# same files as *different* module objects. The application layer under test
# imports ``infrastructure.voice_foundry_repository``; spelling it ``engine.``
# here would hand the repository a ``VoiceCommandAck`` from a second copy of
# the module, and its type guard would (correctly) refuse it.
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.voice_binding_repository import (
    SQLiteVoiceBindingRepository,
)
from infrastructure.voice_foundry_repository import (
    SQLiteVoiceFoundryRepository,
    VoiceCandidateRecord,
    VoiceEvidenceSnapshot,
    VoiceFoundryStage,
    VoiceFoundryTaskSpec,
)


@pytest.fixture
def paths(tmp_path):
    layout = DatabasePaths.for_world(tmp_path, "voice-foundry-world")
    layout.canon.parent.mkdir(parents=True)
    with sqlite3.connect(layout.canon) as conn:
        conn.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    return layout


@pytest_asyncio.fixture
async def database(paths):
    db = await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )
    try:
        yield db
    finally:
        await db.close()


@pytest.fixture
def repository(database):
    return SQLiteVoiceFoundryRepository(database)


class _Bindings:
    def __init__(self):
        self.binding = None

    async def load_scope(self, _scope):
        return self.binding


class _Driver:
    """A stand-in for the worker that records what it was asked to do."""

    def __init__(self, *, settled: int = 0, slot_consumed: bool = True):
        self.settled = settled
        self.slot_consumed = slot_consumed
        self.calls: list[str] = []

    async def reconcile(self, task_id):
        self.calls.append(f"reconcile:{task_id}")
        return self.settled

    async def advance(self, task_id):
        self.calls.append(f"advance:{task_id}")
        return WorkerStep(record=None, slot_consumed=self.slot_consumed)


@pytest.fixture
def commands(repository):
    supply = VoiceSupplyService(repository=repository, bindings=_Bindings())
    driver = _Driver()
    return (
        VoiceFoundryCommandService(
            repository=repository, supply=supply, driver=driver
        ),
        supply,
        driver,
    )


def scope() -> VoiceBindingScope:
    return VoiceBindingScope(
        owner_id="player",
        world_id="voice-foundry-world",
        worldline_id="line-1",
        presentation_identity="klein-visible",
        phase="narrative",
        locale="zh-CN",
    )


def task_spec() -> VoiceFoundryTaskSpec:
    return VoiceFoundryTaskSpec(
        task_id="task-1",
        request_id="request-1",
        request_digest="a" * 64,
        authorization_ref="authz-1",
        scope=scope(),
        persona_revision="persona-1",
        usage="dialogue",
        provider_instance="speechrail-local",
        public_traits=("低沉", "克制"),
        voice_description="克制而警觉的年轻男性声音。",
        reference_text="这是用于确认音色参考的完整句子，必须足够长以通过校验。",
        validation_text="这是用于跨文本复验的另一句完整文本，不能与参考文本相同。",
        origin_kind="content",
        origin_ref="content:main-cast",
        origin_revision=1,
    )


def candidate(slot: int = 1, state: str = "ready") -> VoiceCandidateRecord:
    return VoiceCandidateRecord(
        candidate_id=f"candidate-{slot}",
        slot=slot,
        seed=100 + slot,
        state=state,
        preview_audio_digest="e" * 64,
        recipe={"seed": 100 + slot},
        recipe_digest="f" * 64,
        provider_candidate_id=f"provider-{slot}",
        provider_candidate_revision=f"provider-revision-{slot}",
    )


def evidence() -> VoiceEvidenceSnapshot:
    return VoiceEvidenceSnapshot(
        provider_instance="speechrail-local",
        evidence_id="evidence-1",
        evidence_digest="d" * 64,
        voice_id="voice-klein-01",
        voice_revision="voice-revision-1",
        snapshot={
            "execution": {
                "model_id": "qwen3-tts",
                "model_artifact_revision": "model-revision-1",
                "model_catalog_revision": "catalog-revision-1",
            },
            "human": {"identity_status": "pass"},
        },
    )


async def _at_selection(repository, *, candidate_state: str = "ready"):
    task = await repository.register_task(task_spec())
    task = await repository.set_stage(
        task.task_id,
        expected_revision=task.task_revision,
        stage=VoiceFoundryStage.AWAITING_SELECTION,
        operation_status="confirmed",
        required_actions=("select_candidate",),
    )
    task = await repository.add_candidate(
        task.task_id,
        expected_revision=task.task_revision,
        candidate=candidate(1, candidate_state),
    )
    return task


async def _at_review(repository, *, candidate_state: str = "reviewing"):
    task = await repository.register_task(task_spec())
    task = await repository.set_stage(
        task.task_id,
        expected_revision=task.task_revision,
        stage=VoiceFoundryStage.AWAITING_REVIEW,
        operation_status="confirmed",
        required_actions=("listen_reference", "listen_validation", "review"),
    )
    task = await repository.add_candidate(
        task.task_id,
        expected_revision=task.task_revision,
        candidate=candidate(1, candidate_state),
    )
    return task


async def _at_published(repository):
    task = await repository.register_task(task_spec())
    task = await repository.set_stage(
        task.task_id,
        expected_revision=task.task_revision,
        stage=VoiceFoundryStage.PUBLISHED,
        operation_status="confirmed",
        required_actions=(),
    )
    return task


async def _world_revision(database) -> int:
    rows = await database.read_world(
        "SELECT revision FROM world_meta WHERE singleton=1"
    )
    return rows[0]["revision"]


@pytest.mark.asyncio
async def test_selecting_a_candidate_starts_provisioning(repository, commands):
    service, _, _ = commands
    await _at_selection(repository)

    result = await service.select_candidate(
        command_id="command-1", task_id="task-1", candidate_id="candidate-1"
    )

    assert result.state.stage == VoiceFoundryStage.PROVISIONING.value
    assert result.outcome is VoiceSupplyOutcome.SUPPLY_REQUIRED
    chosen = await repository.load_candidate("task-1", "candidate-1")
    assert chosen.state == "selected"


@pytest.mark.asyncio
async def test_a_failed_candidate_cannot_be_selected(repository, commands):
    service, _, _ = commands
    await _at_selection(repository, candidate_state="failed")

    with pytest.raises(VoiceFoundryCommandError) as caught:
        await service.select_candidate(
            command_id="command-1", task_id="task-1", candidate_id="candidate-1"
        )

    assert caught.value.code == "candidate_not_selectable"


@pytest.mark.asyncio
async def test_selecting_before_the_task_asks_for_it_is_refused(repository, commands):
    service, _, _ = commands
    await repository.register_task(task_spec())

    with pytest.raises(VoiceFoundryCommandError) as caught:
        await service.select_candidate(
            command_id="command-1", task_id="task-1", candidate_id="candidate-1"
        )

    assert caught.value.code == "task_not_awaiting_selection"


@pytest.mark.asyncio
async def test_replaying_a_selection_does_not_advance_the_task_twice(
    repository, commands, database
):
    """A client that retries after a timeout must not provision twice."""
    service, _, _ = commands
    await _at_selection(repository)

    first = await service.select_candidate(
        command_id="command-1", task_id="task-1", candidate_id="candidate-1"
    )
    second = await service.select_candidate(
        command_id="command-1", task_id="task-1", candidate_id="candidate-1"
    )

    assert second.state.task_revision == first.state.task_revision
    assert second.state.stage == VoiceFoundryStage.PROVISIONING.value
    assert await _world_revision(database) == 0


@pytest.mark.asyncio
async def test_one_command_id_cannot_be_reused_for_another_decision(
    repository, commands
):
    """A command id is an idempotency key, not a label."""
    service, _, _ = commands
    task = await _at_selection(repository)
    await repository.add_candidate(
        task.task_id,
        expected_revision=task.task_revision,
        candidate=candidate(2, "ready"),
    )
    await service.select_candidate(
        command_id="command-1", task_id="task-1", candidate_id="candidate-1"
    )

    with pytest.raises(VoiceFoundryCommandError) as caught:
        await service.select_candidate(
            command_id="command-1", task_id="task-1", candidate_id="candidate-2"
        )

    assert caught.value.code == "command_id_rebound_to_different_input"
    assert (
        await repository.load_candidate("task-1", "candidate-2")
    ).state == "ready"


@pytest.mark.asyncio
async def test_binding_a_published_voice_yields_one_renderable_binding(
    repository, commands, database
):
    service, _, _ = commands
    task = await _at_published(repository)
    binding_id = task.scope.binding_identity

    result = await service.bind(
        command_id="command-1",
        task_id="task-1",
        evidence=evidence(),
        binding_id=binding_id,
    )

    assert result.outcome is VoiceSupplyOutcome.READY
    bound = await SQLiteVoiceBindingRepository(database).load(binding_id)
    assert bound.status is VoiceBindingStatus.ACTIVE
    assert bound.permits_new_render
    assert bound.evidence.model_artifact_revision == "model-revision-1"
    assert await _world_revision(database) == 0


@pytest.mark.asyncio
async def test_replaying_a_bind_does_not_mint_a_second_binding(
    repository, commands, database
):
    service, _, _ = commands
    task = await _at_published(repository)
    binding_id = task.scope.binding_identity

    await service.bind(
        command_id="command-1",
        task_id="task-1",
        evidence=evidence(),
        binding_id=binding_id,
    )
    await service.bind(
        command_id="command-1",
        task_id="task-1",
        evidence=evidence(),
        binding_id=binding_id,
    )

    rows = await database.read_world("SELECT binding_id FROM voice_bindings")
    assert rows == [{"binding_id": binding_id}]


@pytest.mark.asyncio
async def test_binding_a_voice_nobody_reviewed_is_refused(repository, commands, database):
    """The command layer does not get a shortcut past the review.

    Binding is the step that makes a voice audible, so it is exactly where a
    convenient call site would reach around the audition and publish whatever
    the provider last returned. The task has to have been published first.
    """
    service, _, _ = commands
    task = await _at_review(repository)

    with pytest.raises(VoiceFoundryCommandError) as caught:
        await service.bind(
            command_id="command-1", task_id="task-1", evidence=evidence(), binding_id="b"
        )

    assert caught.value.code == "task_not_published"
    assert (await repository.load_task("task-1")).stage is VoiceFoundryStage.AWAITING_REVIEW
    assert await _world_revision(database) == 0
    assert (await repository.load_task("task-1")).task_revision == task.task_revision
    assert await database.read_world("SELECT binding_id FROM voice_bindings") == []


@pytest.mark.asyncio
async def test_cancelling_withdraws_the_task_and_stops_the_worker(
    repository, commands, database
):
    service, _, driver = commands
    await _at_selection(repository)

    result = await service.cancel(
        command_id="command-cancel", task_id="task-1", reason_code="user_withdrew"
    )

    task = await repository.load_task("task-1")
    assert task.cancel_requested is True
    assert task.stage is VoiceFoundryStage.CANCELLED
    assert task.reason_code == "user_withdrew"
    assert result.outcome is VoiceSupplyOutcome.CANCELLED
    assert driver.calls == []
    # Withdrawing a cast is presentation bookkeeping; it must not read as a
    # world fact having happened.
    assert await _world_revision(database) == 0


@pytest.mark.asyncio
async def test_cancelling_a_withdrawn_task_converges_instead_of_erroring(
    repository, commands
):
    service, _, _ = commands
    await _at_selection(repository)
    await service.cancel(command_id="command-cancel", task_id="task-1")

    # A second, differently-identified withdrawal of the same task is the
    # client retrying a call it never saw the answer to.
    result = await service.cancel(command_id="command-cancel-2", task_id="task-1")

    assert result.outcome is VoiceSupplyOutcome.CANCELLED


@pytest.mark.asyncio
async def test_a_published_voice_cannot_be_cancelled_as_if_it_never_existed(
    repository, commands
):
    service, _, _ = commands
    await _at_published(repository)

    with pytest.raises(VoiceFoundryCommandError) as excinfo:
        await service.cancel(command_id="command-cancel", task_id="task-1")

    assert excinfo.value.code == "published_voice_cannot_be_cancelled"
    task = await repository.load_task("task-1")
    assert task.stage is VoiceFoundryStage.PUBLISHED
    assert task.cancel_requested is False


@pytest.mark.asyncio
async def test_retry_settles_the_unknown_outcome_before_advancing(
    repository, commands
):
    service, _, driver = commands
    driver.settled = 2
    task = await repository.register_task(task_spec())

    await service.retry(command_id="command-retry", task_id="task-1")

    # Reconcile first: resuming before the unknown outcome is settled is
    # exactly how a second voice gets minted for one identity.
    assert driver.calls == ["reconcile:task-1", "advance:task-1"]


@pytest.mark.asyncio
async def test_retry_replays_under_the_same_command_id_without_re_driving(
    repository, commands
):
    service, _, driver = commands
    await repository.register_task(task_spec())
    await service.retry(command_id="command-retry", task_id="task-1")

    await service.retry(command_id="command-retry", task_id="task-1")

    assert driver.calls == ["reconcile:task-1", "advance:task-1"]


@pytest.mark.asyncio
async def test_retry_refuses_to_race_a_decision_a_person_owes(repository, commands):
    service, _, driver = commands
    await _at_selection(repository)

    with pytest.raises(VoiceFoundryCommandError) as excinfo:
        await service.retry(command_id="command-retry", task_id="task-1")

    assert excinfo.value.code == "task_awaits_a_human_decision"
    assert driver.calls == []


@pytest.mark.asyncio
async def test_retry_refuses_a_task_the_machine_half_has_nothing_left_to_drive(
    repository, commands
):
    service, _, driver = commands
    await _at_published(repository)

    with pytest.raises(VoiceFoundryCommandError) as excinfo:
        await service.retry(command_id="command-retry", task_id="task-1")

    assert excinfo.value.code == "task_is_not_retryable"
    assert driver.calls == []


@pytest.mark.asyncio
async def test_retry_refuses_a_withdrawn_task(repository, commands):
    service, _, driver = commands
    await _at_selection(repository)
    await service.cancel(command_id="command-cancel", task_id="task-1")

    with pytest.raises(VoiceFoundryCommandError) as excinfo:
        await service.retry(command_id="command-retry", task_id="task-1")

    assert excinfo.value.code == "cancelled_task_cannot_be_retried"
    assert driver.calls == []


@pytest.mark.asyncio
async def test_a_command_id_rebound_to_a_different_task_is_refused(
    repository, commands
):
    service, _, _ = commands
    await _at_selection(repository)
    await service.cancel(command_id="command-cancel", task_id="task-1")

    with pytest.raises(VoiceFoundryCommandError) as excinfo:
        await service.cancel(
            command_id="command-cancel", task_id="task-1", reason_code="different"
        )

    assert excinfo.value.code == "command_id_rebound_to_different_input"
