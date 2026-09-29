"""What a presentation identity still needs before it can be heard."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest
import pytest_asyncio
from jsonschema import Draft202012Validator

from application.voice_foundry_service import (
    VoiceSupplyOutcome,
    VoiceSupplyService,
)
from domain.voice_identity import (
    ProviderVoiceRevision,
    VoiceBinding,
    VoiceBindingScope,
    VoiceEvidenceReference,
    VoiceIdentityAssurance,
    VoicePersonaRevision,
)
from engine.infrastructure.database_manager import DatabaseManager, DatabasePaths
from engine.infrastructure.voice_foundry_repository import (
    SQLiteVoiceFoundryRepository,
    VoiceCandidateRecord,
    VoiceFoundryStage,
    VoiceFoundryTaskSpec,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FOUNDRY_STATE_SCHEMA = json.loads(
    (REPO_ROOT / "contracts" / "schemas" / "voice_foundry_state.schema.json").read_text(
        encoding="utf-8"
    )
)


@pytest.fixture
def paths(tmp_path):
    layout = DatabasePaths.for_world(tmp_path, "voice-foundry-world")
    layout.canon.parent.mkdir(parents=True)
    with sqlite3.connect(layout.canon) as conn:
        conn.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    return layout


async def open_database(paths):
    return await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )


@pytest_asyncio.fixture
async def repository(paths):
    database = await open_database(paths)
    try:
        yield SQLiteVoiceFoundryRepository(database)
    finally:
        await database.close()


def scope(identity: str = "klein-visible") -> VoiceBindingScope:
    return VoiceBindingScope(
        owner_id="player",
        world_id="voice-foundry-world",
        worldline_id="line-1",
        presentation_identity=identity,
        phase="narrative",
        locale="zh-CN",
    )


def task_spec(
    *,
    task_id: str = "task-1",
    request_id: str = "request-1",
    request_digest: str = "a" * 64,
    persona_revision: str = "persona-1",
    identity: str = "klein-visible",
) -> VoiceFoundryTaskSpec:
    return VoiceFoundryTaskSpec(
        task_id=task_id,
        request_id=request_id,
        request_digest=request_digest,
        authorization_ref="authz-1",
        scope=scope(identity),
        persona_revision=persona_revision,
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


def _evidence() -> VoiceEvidenceReference:
    return VoiceEvidenceReference(
        evidence_id="ev_klein_1",
        evidence_digest="d" * 64,
        model_artifact_revision="qwen3-tts-2026-09-29",
    )


def _reservation(persona_revision: str = "persona-1") -> VoiceBinding:
    return VoiceBinding.reserve(
        binding_id="vb_klein",
        scope=scope(),
        persona=VoicePersonaRevision("voice-klein", persona_revision),
        provider=ProviderVoiceRevision(
            provider_instance="speechrail-local",
            voice_id="klein-approved",
            assurance=VoiceIdentityAssurance.CONTENT_ADDRESSED,
            voice_revision="voice-" + "a" * 40,
            model_catalog_revision="b" * 40,
            revoked=False,
        ),
        world_revision=3,
    )


def _reviewed_binding(persona_revision: str = "persona-1") -> VoiceBinding:
    """A voice a human listened to and approved, and that went live."""
    reserved = _reservation(persona_revision)
    return replace(reserved, evidence=_evidence()).activate(
        expected_binding_revision=reserved.binding_revision
    )


class _Bindings:
    def __init__(self, binding: VoiceBinding | None = None):
        self.binding = binding
        self.asked = []

    async def load_scope(self, queried: VoiceBindingScope) -> VoiceBinding | None:
        self.asked.append(queried)
        if self.binding is None or self.binding.scope != queried:
            return None
        return self.binding


def _service(repository, binding: VoiceBinding | None = None):
    bindings = _Bindings(binding)
    return VoiceSupplyService(repository=repository, bindings=bindings), bindings


def _candidate(slot: int, state: str = "ready") -> VoiceCandidateRecord:
    return VoiceCandidateRecord(
        candidate_id=f"candidate-{slot}",
        slot=slot,
        seed=100 + slot,
        state=state,
        preview_audio_digest="e" * 64,
        recipe={"seed": 100 + slot},
        recipe_digest="f" * 64,
    )


def assert_matches_contract(projection) -> None:
    Draft202012Validator(FOUNDRY_STATE_SCHEMA).validate(projection.to_contract())


@pytest.mark.asyncio
async def test_a_scope_with_no_voice_is_told_supply_is_required(repository):
    service, _ = _service(repository)

    result = await service.request(task_spec())

    assert result.outcome is VoiceSupplyOutcome.SUPPLY_REQUIRED
    assert result.binding_id is None
    assert result.state is not None
    assert result.state.stage == VoiceFoundryStage.REQUESTED.value
    assert_matches_contract(result.state)


@pytest.mark.asyncio
async def test_an_already_reviewed_voice_is_reused_rather_than_recast(repository):
    """A second cast for the same identity is not a free retry.

    It spends provider budget, and it would put a second candidate in front of
    the same listener to compete with a voice they already approved. Reuse is
    also the only way "reduce manual configuration and repeated casting" can be
    true rather than aspirational.
    """
    service, _ = _service(repository, _reviewed_binding())

    result = await service.request(task_spec())

    assert result.outcome is VoiceSupplyOutcome.READY
    assert result.binding_id == "vb_klein"
    assert result.state is None
    # No task at all: nothing was minted, nothing was asked of the provider.
    assert await repository.load_scope_tasks(scope()) == ()


@pytest.mark.asyncio
async def test_a_voice_nobody_listened_to_does_not_count_as_supplied(repository):
    """A reservation is a claim, not a voice.

    If an unreviewed binding satisfied the request, the scope would be reported
    ready while its only binding is unactivatable — and no supply task would
    ever be opened to fix that.
    """
    service, _ = _service(repository, _reservation())

    result = await service.request(task_spec())

    assert result.outcome is VoiceSupplyOutcome.SUPPLY_REQUIRED
    assert result.binding_id is None
    assert [item.task_id for item in await repository.load_scope_tasks(scope())] == [
        "task-1"
    ]


@pytest.mark.asyncio
async def test_the_same_voice_under_a_new_persona_is_a_new_casting_decision(repository):
    service, _ = _service(repository, _reviewed_binding("persona-1"))

    result = await service.request(task_spec(persona_revision="persona-2"))

    assert result.outcome is VoiceSupplyOutcome.SUPPLY_REQUIRED
    assert [item.task_id for item in await repository.load_scope_tasks(scope())] == [
        "task-1"
    ]


@pytest.mark.asyncio
async def test_asking_twice_resumes_the_same_task_instead_of_casting_again(repository):
    service, _ = _service(repository)

    first = await service.request(task_spec())
    second = await service.request(task_spec())

    assert first.state.task_id == second.state.task_id
    assert len(await repository.load_scope_tasks(scope())) == 1


@pytest.mark.asyncio
async def test_a_precheck_never_starts_what_it_only_asked_about(repository):
    """Pre-warming asks what is ready for every identity in a scene.

    If asking minted a cast, walking a scene into view would spend provider
    budget for voices the scene may never use.
    """
    service, _ = _service(repository)

    result = await service.precheck(scope())

    assert result.outcome is VoiceSupplyOutcome.SUPPLY_REQUIRED
    assert result.reason_code == "voice_never_requested"
    assert result.state is None
    assert await repository.load_scope_tasks(scope()) == ()


@pytest.mark.asyncio
async def test_a_precheck_reports_the_live_task_for_a_scope(repository):
    service, _ = _service(repository)
    await service.request(task_spec())

    result = await service.precheck(scope())

    assert result.state is not None
    assert result.state.task_id == "task-1"
    assert result.outcome is VoiceSupplyOutcome.SUPPLY_REQUIRED


@pytest.mark.asyncio
async def test_a_precheck_reports_how_a_scope_ended_when_nothing_is_live(repository):
    """Asked-and-abandoned is not the same as never-asked.

    The two call for different reactions — one retries, the other requests —
    so a pre-check that collapsed them would send pre-warming down the wrong
    path for an identity that already failed once.
    """
    service, _ = _service(repository)
    first = await repository.register_task(task_spec())
    cancelled = await repository.request_cancel(
        first.task_id,
        expected_revision=first.task_revision,
        reason_code="operator_withdrew",
    )
    await repository.register_task(
        task_spec(task_id="task-2", request_id="request-2", request_digest="b" * 64)
    )
    abandoned = await repository.request_cancel(
        "task-2", expected_revision=1, reason_code="operator_withdrew"
    )
    assert abandoned.stage is VoiceFoundryStage.CANCELLED

    result = await service.precheck(scope())

    assert result.outcome is VoiceSupplyOutcome.CANCELLED
    assert result.state.task_id == "task-2"
    assert cancelled.stage is VoiceFoundryStage.CANCELLED


@pytest.mark.asyncio
async def test_the_projection_carries_every_candidate_the_worker_minted(repository):
    service, _ = _service(repository)
    task = await repository.register_task(task_spec())
    revision = task.task_revision
    for slot in (2, 1):
        task = await repository.add_candidate(
            task.task_id,
            expected_revision=revision,
            candidate=_candidate(slot),
        )
        revision = task.task_revision

    result = await service.get("task-1")

    assert [item.slot for item in result.state.candidates] == [1, 2]
    assert_matches_contract(result.state)


@pytest.mark.asyncio
async def test_the_projection_publishes_the_actions_the_record_committed(repository):
    """The durable record decides what a person owes next.

    Whoever moved the task last is the only party that knows what that move
    means. A projection that re-derived the buttons could disagree with the
    record about exactly what it is asking the player to do.
    """
    service, _ = _service(repository)
    task = await repository.register_task(task_spec())
    task = await repository.add_candidate(
        task.task_id,
        expected_revision=task.task_revision,
        candidate=_candidate(1),
    )
    await repository.set_stage(
        task.task_id,
        expected_revision=task.task_revision,
        stage=VoiceFoundryStage.AWAITING_SELECTION,
        operation_status="confirmed",
        required_actions=("select_candidate",),
    )

    result = await service.get("task-1")

    assert result.outcome is VoiceSupplyOutcome.PENDING_REVIEW
    assert result.state.required_actions == ("select_candidate",)
    assert_matches_contract(result.state)


@pytest.mark.asyncio
async def test_the_projection_carries_no_action_the_record_does_not_claim(repository):
    service, _ = _service(repository)
    task = await repository.register_task(task_spec())
    await repository.set_stage(
        task.task_id,
        expected_revision=task.task_revision,
        stage=VoiceFoundryStage.AWAITING_SELECTION,
        operation_status="confirmed",
        required_actions=(),
    )

    result = await service.get("task-1")

    assert result.state.required_actions == ()
    assert_matches_contract(result.state)
