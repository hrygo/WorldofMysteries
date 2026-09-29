"""Voice Foundry worker orchestration and crash recovery (VF-03C).

The worker is the only component allowed to drive a supply task forward.
These tests pin the reliability contract: every external side effect is
bracketed by a durable intent, an unknown outcome is reconciled rather than
re-executed, retries are bounded and reuse one operation identity, waiting
for a human never holds a slot, and cancellation stops before binding.
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

from application.voice_foundry import (
    FoundryRetryPolicy,
    VoiceFoundryWorker,
)
from application.voice_foundry_ports import (
    AssetRequest,
    AssetResult,
    CandidateState,
    CreateRequest,
    EvidenceBundle,
    FoundryOperation,
    PreviewRequest,
    PreviewResult,
    ProviderLocaleMap,
    ValidationResult,
    VoiceFoundryCapabilities,
    VoiceFoundryPortError,
)
from domain.voice_identity import VoiceBindingScope
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.voice_foundry_repository import (
    SQLiteVoiceFoundryRepository,
    VoiceFoundryStage,
    VoiceFoundryTaskSpec,
)


@pytest.fixture
def paths(tmp_path):
    layout = DatabasePaths.for_world(tmp_path, "foundry-world")
    layout.canon.parent.mkdir(parents=True)
    with sqlite3.connect(layout.canon) as conn:
        conn.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    return layout


@pytest.fixture
async def repository(paths):
    db = await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )
    try:
        yield SQLiteVoiceFoundryRepository(db)
    finally:
        await db.close()


def scope() -> VoiceBindingScope:
    return VoiceBindingScope(
        owner_id="player",
        world_id="foundry-world",
        worldline_id="line-1",
        presentation_identity="klein-visible",
        phase="narrative",
        locale="zh-CN",
    )


def task_spec(**overrides) -> VoiceFoundryTaskSpec:
    base = {
        "task_id": "task-1",
        "request_id": "request-1",
        "request_digest": "a" * 64,
        "authorization_ref": "authz-1",
        "scope": scope(),
        "persona_revision": "persona-1",
        "usage": "dialogue",
        "provider_instance": "speechrail-local",
        "public_traits": ("低沉", "克制"),
        "voice_description": "克制而警觉的年轻男性声音。",
        "reference_text": "这是用于确认音色的完整句子，必须足够长以通过校验。",
        "validation_text": "这是用于跨文本复验的另一句完整文本，不能与参考文本相同。",
        "origin_kind": "content",
        "origin_ref": "npc:klein",
        "origin_revision": 1,
    }
    base.update(overrides)
    return VoiceFoundryTaskSpec(**base)


class RecordingPort:
    """A port double that records how many times each side effect ran."""

    def __init__(self, *, preview_error: Exception | None = None):
        self.calls: list[str] = []
        self.preview_error = preview_error
        self.create_error: Exception | None = None
        self.create_keys: list[str] = []
        self.created_identities: list[str] = []
        self.capabilities = VoiceFoundryCapabilities(
            operations=frozenset(FoundryOperation),
            accepted_game_locales=frozenset({"zh-CN"}),
            max_reference_chars=240,
            max_validation_chars=240,
            max_audio_bytes=1024 * 1024,
            max_audio_seconds=60,
            strict_rendering=True,
            evidence_fields=frozenset(
                {"execution", "reference", "output", "human", "publication", "rights"}
            ),
            remote_cancel=True,
        )
        self.locale_map = ProviderLocaleMap({"zh-CN": "zh"})

    async def preview(self, request: PreviewRequest) -> PreviewResult:
        self.calls.append("preview")
        if self.preview_error is not None:
            raise self.preview_error
        return PreviewResult(
            preview_id="pv_1",
            audio_digest="b" * 64,
            audio_bytes=16,
            duration_seconds=1.0,
            recipe={"seed": request.seed},
            recipe_digest="c" * 64,
        )

    async def create(self, request: CreateRequest) -> CandidateState:
        self.calls.append("create")
        self.create_keys.append(request.idempotency_key)
        if self.create_error is not None:
            raise self.create_error
        # A stable key always yields the same candidate, exactly like an
        # idempotent provider replaying the original instead of minting anew.
        self.created_identities.append(request.voice_id)
        return CandidateState(
            candidate_id=CANDIDATE_ID,
            candidate_revision=REVISION,
            state="created",
            reference_confirmed=False,
        )

    async def query(self, candidate_id: str) -> CandidateState:
        self.calls.append("query")
        return CandidateState(
            candidate_id=candidate_id,
            candidate_revision=REVISION,
            state="created",
            reference_confirmed=True,
        )

    async def confirm(self, candidate_id, request) -> CandidateState:
        self.calls.append("confirm")
        return CandidateState(
            candidate_id=candidate_id,
            candidate_revision="vr_" + "c" * 32,
            state="confirmed",
            reference_confirmed=True,
        )

    async def validate(self, candidate_id, *, test_text, capability_key):
        self.calls.append("validate")
        return ValidationResult(
            validation_id="vv_" + "e" * 24,
            candidate_id=candidate_id,
            candidate_revision=REVISION,
            capability_key=capability_key,
            audio_digest="d" * 64,
            text_digest="e" * 64,
            passed=True,
        )

    async def review(self, candidate_id, **kwargs) -> EvidenceBundle:
        self.calls.append("review")
        raise NotImplementedError

    async def publish(self, candidate_id, *, expected_candidate_revision):
        self.calls.append("publish")
        raise NotImplementedError

    async def read_asset(self, request: AssetRequest) -> AssetResult:
        self.calls.append("read_asset")
        raise NotImplementedError


CANDIDATE_ID = "vd_" + "a" * 24
REVISION = "vr_" + "b" * 32


def make_worker(repository, port, **kwargs):
    slept: list[float] = []
    clock = {"now": 0.0}

    async def sleeper(seconds):
        slept.append(seconds)
        clock["now"] += seconds

    policy = kwargs.pop("policy", FoundryRetryPolicy(backoff_seconds=(0.0, 0.0, 0.0)))
    worker = VoiceFoundryWorker(
        repository,
        port,
        policy=policy,
        sleeper=sleeper,
        clock=lambda: clock["now"],
        **kwargs,
    )
    return worker, slept, clock


async def test_advance_records_an_intent_before_touching_the_provider(repository):
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    task = await repository.register_task(task_spec())

    step = await worker.advance(task.task_id)

    operation = await repository.load_operation("preview:task-1:0")
    assert operation.status == "confirmed"
    assert port.calls == ["preview"]
    assert step.record.stage is VoiceFoundryStage.AWAITING_SELECTION


async def test_a_task_awaiting_a_human_holds_no_worker_slot(repository):
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    task = await repository.register_task(task_spec())

    # The first advance really does provider work, so it earns its slot...
    first = await worker.advance(task.task_id)
    assert first.slot_consumed is True
    assert first.record.stage is VoiceFoundryStage.AWAITING_SELECTION

    # ...but once parked on a human, a further advance must neither reach the
    # provider nor consume a slot, because that would starve real work.
    second = await worker.advance(task.task_id)
    assert second.slot_consumed is False
    assert port.calls == ["preview"]


async def test_transient_failure_retries_bounded_and_leaves_the_record_unknown(
    repository,
):
    port = RecordingPort(preview_error=VoiceFoundryPortError("foundry_transient"))
    worker, slept, _ = make_worker(repository, port)
    task = await repository.register_task(task_spec())

    with pytest.raises(VoiceFoundryPortError):
        await worker.advance(task.task_id)

    operation = await repository.load_operation("preview:task-1:0")
    # Never confirmed, so the durable record stays honest about the unknown.
    assert operation.status == "unknown"
    assert port.calls == ["preview", "preview", "preview"]
    assert len(slept) == 2


async def test_a_terminal_rejection_is_not_retried(repository):
    port = RecordingPort(preview_error=VoiceFoundryPortError("foundry_rejected"))
    worker, slept, _ = make_worker(repository, port)
    task = await repository.register_task(task_spec())

    with pytest.raises(VoiceFoundryPortError):
        await worker.advance(task.task_id)

    assert port.calls == ["preview"]
    assert slept == []


async def test_retry_budget_is_bounded_by_the_deadline(repository):
    port = RecordingPort(preview_error=VoiceFoundryPortError("foundry_transient"))
    policy = FoundryRetryPolicy(
        max_attempts=5, backoff_seconds=(1.0, 2.0, 4.0, 8.0), deadline_seconds=3.0
    )
    worker, slept, clock = make_worker(repository, port, policy=policy)
    task = await repository.register_task(task_spec())

    with pytest.raises(VoiceFoundryPortError):
        await worker.advance(task.task_id)

    # Sleeping 4s more would cross the 3s deadline, so it is never slept and
    # the worker stops instead of running unbounded.
    assert port.calls == ["preview", "preview", "preview"]
    assert slept == [1.0, 2.0]
    assert clock["now"] == pytest.approx(3.0)


async def test_an_unknown_create_is_reconciled_by_querying_not_recreating(
    repository,
):
    """After a crash between the call and the confirmation, resuming must ask
    the provider what happened to the same candidate — never mint a second one."""
    port = RecordingPort()
    # One attempt only, so the crash window is reached immediately.
    worker, _, _ = make_worker(
        repository, port, policy=FoundryRetryPolicy(max_attempts=1)
    )
    task = await repository.register_task(task_spec())

    await worker.advance(task.task_id)
    task = await repository.load_task(task.task_id)
    # A client command moves the task on once the human picked a candidate.
    await repository.set_stage(
        task.task_id,
        expected_revision=task.task_revision,
        stage="provisioning",
        operation_status="confirmed",
        required_actions=(),
    )

    port.create_error = VoiceFoundryPortError("foundry_transient")
    with pytest.raises(VoiceFoundryPortError):
        await worker.advance(task.task_id)

    # The create was attempted exactly once before the crash.
    assert port.calls.count("create") == 1
    port.create_error = None  # the provider is reachable again
    await worker.reconcile(task.task_id)

    # Reconciliation replays the original request under the original key. That
    # is what keeps it idempotent: the provider returns the original candidate
    # rather than minting a second voice for the same identity.
    assert port.create_keys == [port.create_keys[0], port.create_keys[0]]
    assert port.created_identities == [port.created_identities[0]]
    settled = await repository.load_operation("create:task-1:0")
    assert settled.status == "confirmed"


async def test_cancellation_stops_before_any_further_side_effect(repository):
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    task = await repository.register_task(task_spec())
    await worker.advance(task.task_id)

    current = await repository.load_task(task.task_id)
    await repository.request_cancel(
        task.task_id, expected_revision=current.task_revision
    )
    before = list(port.calls)

    step = await worker.advance(task.task_id)
    assert port.calls == before

    # The task reports itself cancelled rather than raising, so a scheduler
    # can retire it cleanly, and it consumed no slot doing so.
    assert step.record.stage is VoiceFoundryStage.CANCELLED
    assert step.slot_consumed is False
