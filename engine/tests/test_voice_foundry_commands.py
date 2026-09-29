"""Driving one supply task: choose, review, bind — each at most once."""
from __future__ import annotations

import sqlite3

import pytest
import pytest_asyncio

from application.voice_foundry_commands import (
    VoiceFoundryCommandError,
    VoiceFoundryCommandService,
)
from application.voice_foundry_ports import FoundryReviewVerdict
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


@pytest.fixture
def commands(repository):
    supply = VoiceSupplyService(repository=repository, bindings=_Bindings())
    return VoiceFoundryCommandService(repository=repository, supply=supply), supply


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
    service, _ = commands
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
    service, _ = commands
    await _at_selection(repository, candidate_state="failed")

    with pytest.raises(VoiceFoundryCommandError) as caught:
        await service.select_candidate(
            command_id="command-1", task_id="task-1", candidate_id="candidate-1"
        )

    assert caught.value.code == "candidate_not_selectable"


@pytest.mark.asyncio
async def test_selecting_before_the_task_asks_for_it_is_refused(repository, commands):
    service, _ = commands
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
    service, _ = commands
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
    service, _ = commands
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
async def test_an_accepted_review_publishes_the_candidate(repository, commands):
    service, _ = commands
    await _at_review(repository)

    result = await service.submit_review(
        command_id="command-1",
        task_id="task-1",
        candidate_id="candidate-1",
        verdict=FoundryReviewVerdict.PASS,
    )

    assert result.state.stage == VoiceFoundryStage.PUBLISHED.value
    assert (
        await repository.load_candidate("task-1", "candidate-1")
    ).state == "published"


@pytest.mark.asyncio
async def test_a_rejected_review_ends_the_task_and_says_why(repository, commands):
    service, _ = commands
    await _at_review(repository)

    result = await service.submit_review(
        command_id="command-1",
        task_id="task-1",
        candidate_id="candidate-1",
        verdict=FoundryReviewVerdict.REJECT,
    )

    assert result.outcome is VoiceSupplyOutcome.FAILED
    assert result.state.stage == VoiceFoundryStage.FAILED.value
    assert result.state.reason_code == "human_review_rejected"
    assert (
        await repository.load_candidate("task-1", "candidate-1")
    ).state == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "verdict,expected",
    [
        (FoundryReviewVerdict.WARN, "review_verdict_requires_explicit_handling"),
        (FoundryReviewVerdict.NOT_REVIEWED, "review_verdict_absent"),
    ],
)
async def test_a_verdict_that_is_not_a_decision_changes_nothing(
    repository, commands, verdict, expected
):
    """A warning is not a pass, and an absent review is not a pass.

    Both are refused outright rather than mapped onto an outcome, because the
    only thing worse than publishing unreviewed audio is publishing it by
    accident through a lenient default.
    """
    service, _ = commands
    task = await _at_review(repository)

    with pytest.raises(VoiceFoundryCommandError) as caught:
        await service.submit_review(
            command_id="command-1",
            task_id="task-1",
            candidate_id="candidate-1",
            verdict=verdict,
        )

    assert caught.value.code == expected
    assert (await repository.load_task("task-1")).stage is (
        VoiceFoundryStage.AWAITING_REVIEW
    )
    assert (await repository.load_task("task-1")).task_revision == task.task_revision


@pytest.mark.asyncio
async def test_binding_a_published_voice_yields_one_renderable_binding(
    repository, commands, database
):
    service, _ = commands
    await _at_published(repository)

    result = await service.bind(
        command_id="command-1",
        task_id="task-1",
        evidence=evidence(),
        binding_id="binding-1",
    )

    assert result.outcome is VoiceSupplyOutcome.READY
    bound = await SQLiteVoiceBindingRepository(database).load("binding-1")
    assert bound.status is VoiceBindingStatus.ACTIVE
    assert bound.permits_new_render
    assert bound.evidence.model_artifact_revision == "model-revision-1"
    assert await _world_revision(database) == 0


@pytest.mark.asyncio
async def test_replaying_a_bind_does_not_mint_a_second_binding(
    repository, commands, database
):
    service, _ = commands
    await _at_published(repository)

    await service.bind(
        command_id="command-1",
        task_id="task-1",
        evidence=evidence(),
        binding_id="binding-1",
    )
    await service.bind(
        command_id="command-1",
        task_id="task-1",
        evidence=evidence(),
        binding_id="binding-1",
    )

    rows = await database.read_world("SELECT binding_id FROM voice_bindings")
    assert rows == [{"binding_id": "binding-1"}]


@pytest.mark.asyncio
async def test_binding_a_voice_nobody_reviewed_is_refused(repository, commands, database):
    """The command layer does not get a shortcut past the review.

    Binding is the step that makes a voice audible, so it is exactly where a
    convenient call site would reach around the audition and publish whatever
    the provider last returned. The task has to have been published first.
    """
    service, _ = commands
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
