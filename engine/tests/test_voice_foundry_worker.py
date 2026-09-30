"""Voice Foundry worker orchestration and crash recovery (VF-03C).

The worker is the only component allowed to drive a supply task forward.
These tests pin the reliability contract: every external side effect is
bracketed by a durable intent, an unknown outcome is reconciled rather than
re-executed, retries are bounded and reuse one operation identity, waiting
for a human never holds a slot, and cancellation stops before binding.
"""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from dataclasses import replace

import pytest

from application.voice_foundry import (
    MAX_AUDITION_ASSET_BYTES,
    FoundryRetryPolicy,
    PRODUCTION_CAPABILITY_KEY,
    VoiceFoundryWorker,
)
from application.voice_foundry_ports import (
    AssetRequest,
    AssetResult,
    CandidateState,
    CreateRequest,
    EvidenceBundle,
    FoundryOperation,
    FoundryReviewVerdict,
    PreviewRequest,
    PreviewResult,
    ProviderLocaleMap,
    PublishResult,
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

    def __init__(
        self,
        *,
        preview_error: Exception | None = None,
        validation_passes: bool = True,
        review_error: Exception | None = None,
    ):
        self.calls: list[str] = []
        self.asset_requests: list[AssetRequest] = []
        #: What the provider serves for an asset read. Kept small and real:
        #: an audition that returns nothing must be refused, and a stub that
        #: cannot be refused proves nothing.
        self.asset_audio: bytes = b"RIFF----WAVEfake"
        #: Set to make the provider answer with audio that is not what was
        #: recorded, which is the drift an audition has to catch.
        self.asset_digest_override: str | None = None
        self.preview_error = preview_error
        self.validation_passes = validation_passes
        self.review_error = review_error
        self.create_error: Exception | None = None
        self.create_keys: list[str] = []
        self.created_identities: list[str] = []
        self.review_arguments: dict[str, object] = {}
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
            candidate_revision=CONFIRMED_REVISION,
            state="confirmed",
            reference_confirmed=True,
        )

    async def validate(self, candidate_id, *, test_text, capability_key):
        self.calls.append("validate")
        return ValidationResult(
            validation_id="vv_" + "e" * 24,
            candidate_id=candidate_id,
            # The revision the candidate is at *now*. ``confirm`` advanced it
            # upstream, and the provider answers with where the design
            # actually is — not with the revision it was created at. A double
            # that echoed the create-time revision hid the fact that the
            # engine's candidate row never followed.
            candidate_revision=CONFIRMED_REVISION,
            capability_key=capability_key,
            audio_digest="d" * 64,
            text_digest="e" * 64,
            passed=self.validation_passes,
        )

    async def review(
        self,
        candidate_id,
        *,
        validation_id,
        identity,
        naturalness,
        validation_audio_digest="",
    ) -> EvidenceBundle:
        self.calls.append("review")
        if self.review_error is not None:
            raise self.review_error
        self.review_arguments = {
            "candidate_id": candidate_id,
            "validation_id": validation_id,
            "identity": identity,
            "naturalness": naturalness,
            "validation_audio_digest": validation_audio_digest,
        }
        return EvidenceBundle(
            evidence_id="ev_review",
            evidence_digest="a" * 64,
            execution={"model_artifact_revision": "art-1"},
            reference={"audio_sha256": "9" * 64},
            output={"audio_sha256": "d" * 64},
            human={
                "identity_status": identity.value,
                "naturalness_status": naturalness.value,
            },
            publication={"published": False},
            rights={"cleared": True},
        )

    async def publish(self, candidate_id, *, expected_candidate_revision):
        self.calls.append("publish")
        self.published_revision = expected_candidate_revision
        return PublishResult(
            candidate_id=candidate_id,
            candidate_revision=expected_candidate_revision,
            voice_id="klein_visible",
            voice_revision="wvr_" + "9" * 24,
            evidence=EvidenceBundle(
                evidence_id="ev_1",
                evidence_digest="7" * 64,
                execution={
                    "model_id": "qwen3-tts",
                    "model_artifact_revision": "art-1",
                    "variant": "custom_voice",
                    "locale": "zh",
                    "validation_policy_revision": "policy-1",
                    "processing_fingerprint": "8" * 64,
                },
                reference={"audio_sha256": "c" * 64},
                output={"audio_sha256": "d" * 64},
                human={"identity_status": "pass", "naturalness_status": "pass"},
                publication={"published": True},
                rights={"cleared": True},
            ),
        )

    async def read_asset(self, request: AssetRequest) -> AssetResult:
        self.calls.append("read_asset")
        self.asset_requests.append(request)
        # Which asset is being read is decided by the validation id, exactly as
        # upstream decides it: the reference belongs to no validation.
        reported = (
            REFERENCE_AUDIO_DIGEST
            if request.validation_id is None
            else VALIDATION_AUDIO_DIGEST
        )
        return AssetResult(
            audio_digest=self.asset_digest_override or reported,
            audio_bytes=len(self.asset_audio),
            duration_seconds=1.0,
            audio=self.asset_audio,
        )


CANDIDATE_ID = "vd_" + "a" * 24
REVISION = "vr_" + "b" * 32
#: What ``confirm`` answers with. The provider moves the design to a new
#: revision when the reference text is bound, and every later call has to
#: report where the design is now.
CONFIRMED_REVISION = "vr_" + "c" * 32
#: What the recording port hands back for the cross-text pass, and the digests
#: the audition assets actually carry. A review may only speak about these.
VALIDATION_ID = "vv_" + "e" * 24
REFERENCE_AUDIO_DIGEST = "9" * 64
VALIDATION_AUDIO_DIGEST = "d" * 64


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


async def _drive_to_validating(repository, worker, port):
    """Walk a fresh task the way production would, up to the deadlock."""
    task = await repository.register_task(task_spec())
    await worker.advance(task.task_id)
    task = await repository.load_task(task.task_id)
    assert task.stage is VoiceFoundryStage.AWAITING_SELECTION

    await repository.update_candidate(
        task.task_id,
        expected_revision=task.task_revision,
        candidate_id=f"{task.task_id}:candidate:0",
        state="selected",
    )
    task = await repository.load_task(task.task_id)
    await repository.set_stage(
        task.task_id,
        expected_revision=task.task_revision,
        stage="provisioning",
        operation_status="confirmed",
        required_actions=(),
    )
    return await worker.advance(task.task_id)


class _DiesBeforeRecording:
    """A repository that dies the way a power cut does: mid-write, once.

    Only the write that would have recorded a named field is fatal, so the
    provider call it followed is already settled and the task is left exactly
    as a crash would leave it.
    """

    def __init__(self, inner, field: str):
        self._inner = inner
        self._field = field
        self._spent = False

    def __getattr__(self, name):
        return getattr(self._inner, name)

    async def update_candidate(self, task_id, **kwargs):
        if not self._spent and kwargs.get(self._field) is not None:
            self._spent = True
            raise RuntimeError("the process died before the answer was recorded")
        return await self._inner.update_candidate(task_id, **kwargs)


class _DriftingValidationPort(RecordingPort):
    """A provider that answers a replayed key with something else."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._answers = 0

    async def validate(self, candidate_id, *, test_text, capability_key):
        self._answers += 1
        result = await super().validate(
            candidate_id, test_text=test_text, capability_key=capability_key
        )
        if self._answers > 1:
            return replace(result, validation_id="vv_" + "f" * 24)
        return result


async def test_a_selected_candidate_is_proved_on_text_it_has_not_heard(repository):
    """Selection used to be a one-way door into nowhere.

    Provisioning left the task ``validating`` and nothing advanced it, so a
    chosen candidate waited there forever and no voice could ever be reviewed.
    The step confirms the reference, proves the voice on text it has not been
    read, and only then hands it to a person.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)

    parked = await _drive_to_validating(repository, worker, port)
    assert parked.record.stage is VoiceFoundryStage.VALIDATING

    step = await worker.advance("task-1")

    assert step.record.stage is VoiceFoundryStage.AWAITING_REVIEW
    assert step.slot_consumed is True
    # The actions are the record's, so the App renders exactly what the task
    # is actually waiting on.
    assert step.record.required_actions == (
        "listen_reference",
        "listen_validation",
        "review",
    )

    candidate = await repository.load_candidate("task-1", "task-1:candidate:0")
    assert candidate.state == "reviewing"
    # The audition a listener judges is hashed from the asset the provider
    # actually served, not from the call that promised it.
    assert candidate.reference_audio_digest == "9" * 64
    assert candidate.reference_text_digest == hashlib.sha256(
        task_spec().reference_text.encode("utf-8")
    ).hexdigest()
    assert candidate.validation_audio_digest == "d" * 64
    # The trailing read_asset is the cross-text audio being read back to
    # establish its digest: the provider publishes none, so the identity of
    # what a listener will hear has to come from the bytes themselves.
    assert port.calls[-4:] == [
        "confirm",
        "read_asset",
        "validate",
        "read_asset",
    ]


async def test_confirming_the_reference_moves_the_recorded_revision(repository):
    """The row has to follow the provider, not the other way round.

    The provider's contract says binding the reference text produces a new
    candidate revision and clears the old validations. The revision a caller
    may act on is therefore never the one ``create`` handed out, and holding
    that older value would make the publish step a guaranteed 409.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_validating(repository, worker, port)

    step = await worker.advance("task-1")

    assert step.record.stage is VoiceFoundryStage.AWAITING_REVIEW
    candidate = await repository.load_candidate("task-1", "task-1:candidate:0")
    assert candidate.provider_candidate_revision == CONFIRMED_REVISION


async def test_the_audition_is_read_at_the_revision_we_recorded(repository):
    """The reference a listener hears has to be the one this engine recorded.

    Reading an asset without naming the revision does not fail loudly against
    every provider — it hands back audio of whichever revision the candidate
    happens to be at now. The digest would then describe a voice that no
    evidence, no review and no publication ever mentions. So the revision
    travels with the read, and it is the one ``confirm`` produced.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_validating(repository, worker, port)

    await worker.advance("task-1")

    # Both auditions are read at the recorded revision: the reference when it
    # is bound, and the cross-text audio when the validation that produced it
    # has to be given a digest. Neither read may drift to whatever revision
    # the candidate happens to be at now.
    assert [request.candidate_revision for request in port.asset_requests] == [
        CONFIRMED_REVISION,
        CONFIRMED_REVISION,
    ]
    assert all(request.candidate_id == CANDIDATE_ID for request in port.asset_requests)
    assert port.asset_requests[1].validation_id is not None


async def _drive_to_awaiting_review(repository, worker, port):
    await _drive_to_validating(repository, worker, port)
    step = await worker.advance("task-1")
    assert step.record.stage is VoiceFoundryStage.AWAITING_REVIEW


async def test_a_listener_is_handed_the_audio_and_the_facts_that_identify_it(
    repository,
):
    """A review cannot exist without the audio, and cannot be checked without
    the facts. Both travel together or the verdict is about nothing."""
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_awaiting_review(repository, worker, port)

    asset = await worker.audition_asset(
        "task-1", candidate_id="task-1:candidate:0", kind="reference"
    )

    assert asset.audio == port.asset_audio
    assert asset.audio_digest == REFERENCE_AUDIO_DIGEST
    assert asset.candidate_revision == CONFIRMED_REVISION
    # The reference belongs to no validation, so it says so rather than
    # carrying an id a client might echo into a review.
    assert asset.validation_id is None


async def test_the_cross_text_asset_carries_the_validation_a_verdict_must_name(
    repository,
):
    """``voice.foundry.review`` demands a validation id no projection exposed.

    It is the provider's answer to the validate call and is recorded only in
    the operation journal, so this read is the one place a client can learn
    the value it is required to send back.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_awaiting_review(repository, worker, port)

    asset = await worker.audition_asset(
        "task-1", candidate_id="task-1:candidate:0", kind="validation"
    )

    assert asset.validation_id == VALIDATION_ID
    assert asset.audio_digest == VALIDATION_AUDIO_DIGEST


async def test_audio_that_is_not_what_we_recorded_is_never_auditioned(repository):
    """A verdict must describe the voice the evidence describes.

    The provider can move a design at any time. If the audio served today
    hashes to something other than what confirm and validate recorded, then a
    listener judging it signs for a voice no evidence mentions — so the read
    is refused instead of auditioning whatever is current.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_awaiting_review(repository, worker, port)
    port.asset_digest_override = "1" * 64

    with pytest.raises(VoiceFoundryPortError) as raised:
        await worker.audition_asset(
            "task-1", candidate_id="task-1:candidate:0", kind="reference"
        )

    assert raised.value.code == "audition_asset_drifted"


async def test_an_asset_too_large_for_one_frame_is_refused_not_truncated(repository):
    """Truncation is the worse failure by a wide margin.

    A WAV cut short still decodes, still plays, and still sounds like a voice —
    a listener would judge it and sign, while the evidence kept describing
    bytes they never heard. Refusing is the only honest outcome.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_awaiting_review(repository, worker, port)
    port.asset_audio = b"\0" * (MAX_AUDITION_ASSET_BYTES + 1)

    with pytest.raises(VoiceFoundryPortError) as raised:
        await worker.audition_asset(
            "task-1", candidate_id="task-1:candidate:0", kind="reference"
        )

    assert raised.value.code == "audition_asset_too_large"


async def test_an_asset_with_no_bytes_is_refused(repository):
    """A digest is a claim about audio, not the audio.

    A provider adapter that answers with a well-formed result and an empty
    payload must not be able to pass an empty audition off as a voice.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_awaiting_review(repository, worker, port)
    port.asset_audio = b""

    with pytest.raises(VoiceFoundryPortError) as raised:
        await worker.audition_asset(
            "task-1", candidate_id="task-1:candidate:0", kind="reference"
        )

    assert raised.value.code == "audition_asset_empty"


async def test_an_unknown_asset_kind_never_reaches_the_provider(repository):
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_awaiting_review(repository, worker, port)
    port.calls.clear()

    with pytest.raises(VoiceFoundryPortError) as raised:
        await worker.audition_asset(
            "task-1", candidate_id="task-1:candidate:0", kind="preview"
        )

    assert raised.value.code == "audition_asset_kind_unknown"
    assert port.calls == []


async def test_a_design_that_moved_where_we_have_no_record_of_is_refused(
    repository,
):
    """Every later step has to describe the voice the listener will hear.

    If the provider reports a revision at validate that this engine never
    recorded, the design moved somewhere unknown. The audition a listener is
    about to judge, and the evidence they would sign, would describe a
    different voice — so the run stops and says so.
    """

    class DriftingPort(RecordingPort):
        async def validate(self, candidate_id, *, test_text, capability_key):
            result = await super().validate(
                candidate_id, test_text=test_text, capability_key=capability_key
            )
            return replace(result, candidate_revision="vr_" + "f" * 32)

    port = DriftingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_validating(repository, worker, port)

    with pytest.raises(VoiceFoundryPortError) as caught:
        await worker.advance("task-1")

    assert caught.value.code == "foundry_revision_advanced"
    # Nothing was handed to a person on the strength of a voice whose
    # revision nobody here can account for.
    assert (await repository.load_task("task-1")).stage is VoiceFoundryStage.VALIDATING
    candidate = await repository.load_candidate("task-1", "task-1:candidate:0")
    assert candidate.state != "reviewing"


async def test_a_failed_cross_text_check_never_reaches_a_listener(repository):
    """A machine failure is not something to spend a human's attention on.
    Handing an unproven voice to the audition step would ask someone to approve
    a voice that already failed cross-text — and their approval would then be
    the only thing standing between it and a player.
    """
    port = RecordingPort(validation_passes=False)
    worker, _, _ = make_worker(repository, port)
    await _drive_to_validating(repository, worker, port)

    step = await worker.advance("task-1")

    assert step.record.stage is VoiceFoundryStage.FAILED
    assert step.record.reason_code == "machine_validation_failed"
    assert step.record.required_actions == ()
    candidate = await repository.load_candidate("task-1", "task-1:candidate:0")
    assert candidate.state == "failed"
    assert "review" not in step.record.required_actions


async def test_the_two_validation_steps_can_be_authorized_one_at_a_time(repository):
    """The control surface may drive the pair step by step.

    A client that wants to authorize "confirm the reference" and "prove it on
    other text" as two separately-recorded decisions has to reach the same
    place the unattended path reaches, through the same code.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_validating(repository, worker, port)

    confirmed = await worker.confirm_reference_step(
        "task-1",
        provider_candidate_revision="vr_" + "c" * 32,
        reference_text=task_spec().reference_text,
        reference_audio_digest=REFERENCE_AUDIO_DIGEST,
    )

    # Confirming the reference is not the same as having proved the voice, so
    # the task stays where it can still be stopped.
    assert confirmed.record.stage is VoiceFoundryStage.VALIDATING
    assert confirmed.slot_consumed is True
    candidate = await repository.load_candidate("task-1", "task-1:candidate:0")
    assert candidate.state == "validating"
    assert candidate.reference_audio_digest == REFERENCE_AUDIO_DIGEST

    step = await worker.validate_step(
        "task-1",
        test_text=task_spec().validation_text,
        capability_key=PRODUCTION_CAPABILITY_KEY,
    )

    assert step.record.stage is VoiceFoundryStage.AWAITING_REVIEW
    assert step.record.required_actions == (
        "listen_reference",
        "listen_validation",
        "review",
    )
    assert port.calls[-4:] == [
        "confirm",
        "read_asset",
        "validate",
        "read_asset",
    ]


async def test_asking_twice_does_not_bind_the_reference_twice(repository):
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_validating(repository, worker, port)

    for _ in range(2):
        await worker.confirm_reference_step(
            "task-1",
            provider_candidate_revision="vr_" + "c" * 32,
            reference_text=task_spec().reference_text,
            reference_audio_digest=REFERENCE_AUDIO_DIGEST,
        )

    assert port.calls.count("confirm") == 1


@pytest.mark.parametrize(
    "reference_text",
    ["这是另一段本任务从未授权用来绑定参考音色的完整句子。"],
)
async def test_a_reference_confirmation_about_other_text_is_refused_before_the_call(
    repository, reference_text
):
    """Text the task was never authorized to bind is detectable for free.

    Refusing here rather than after the call is the difference between a
    confused client and a billed one.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_validating(repository, worker, port)
    calls_before = list(port.calls)

    with pytest.raises(VoiceFoundryPortError) as caught:
        await worker.confirm_reference_step(
            "task-1",
            provider_candidate_revision="vr_" + "c" * 32,
            reference_text=reference_text,
            reference_audio_digest=REFERENCE_AUDIO_DIGEST,
        )

    assert caught.value.code == "confirm_reference_text_mismatch"
    assert port.calls == calls_before


async def test_a_reference_confirmation_about_regenerated_audio_is_refused(repository):
    """A verdict is only ever about the audio that exists now.

    The digest is the provider's to answer for, so this one can only be caught
    after the call — which is exactly why the reference is bound durably first
    and the caller's claim checked against it.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_validating(repository, worker, port)

    with pytest.raises(VoiceFoundryPortError) as caught:
        await worker.confirm_reference_step(
            "task-1",
            provider_candidate_revision="vr_" + "c" * 32,
            reference_text=task_spec().reference_text,
            reference_audio_digest="0" * 64,
        )

    assert caught.value.code == "confirm_reference_asset_mismatch"
    candidate = await repository.load_candidate("task-1", "task-1:candidate:0")
    assert candidate.reference_audio_digest == REFERENCE_AUDIO_DIGEST


async def test_a_reference_confirmation_about_another_revision_is_refused(repository):
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_validating(repository, worker, port)

    with pytest.raises(VoiceFoundryPortError) as caught:
        await worker.confirm_reference_step(
            "task-1",
            provider_candidate_revision="vr_" + "f" * 32,
            reference_text=task_spec().reference_text,
            reference_audio_digest=REFERENCE_AUDIO_DIGEST,
        )

    assert caught.value.code == "confirm_reference_revision_mismatch"


@pytest.mark.parametrize(
    ("test_text", "capability_key", "code"),
    [
        (
            "这是另一段本任务从未授权用来复验音色的完整文本。",
            PRODUCTION_CAPABILITY_KEY,
            "validation_text_mismatch",
        ),
        (
            task_spec().validation_text,
            "quality.draft",
            "validation_capability_mismatch",
        ),
    ],
)
async def test_a_validation_of_something_else_is_refused_before_the_call(
    repository, test_text, capability_key, code
):
    """Evidence a listener signs is evidence about one test at one tier.

    Proving the voice on other text, or at a cheaper tier, would produce a
    verdict describing a test the record does not name — so the call is never
    made, rather than made and quietly reinterpreted.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_validating(repository, worker, port)
    await worker.confirm_reference_step(
        "task-1",
        provider_candidate_revision="vr_" + "c" * 32,
        reference_text=task_spec().reference_text,
        reference_audio_digest=REFERENCE_AUDIO_DIGEST,
    )
    calls_before = list(port.calls)

    with pytest.raises(VoiceFoundryPortError) as caught:
        await worker.validate_step(
            "task-1", test_text=test_text, capability_key=capability_key
        )

    assert caught.value.code == code
    assert port.calls == calls_before
    assert (await repository.load_task("task-1")).stage is VoiceFoundryStage.VALIDATING


async def test_a_voice_is_not_proved_before_its_reference_is_bound(repository):
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_validating(repository, worker, port)

    with pytest.raises(VoiceFoundryPortError) as caught:
        await worker.validate_step(
            "task-1",
            test_text=task_spec().validation_text,
            capability_key=PRODUCTION_CAPABILITY_KEY,
        )

    assert caught.value.code == "reference_not_confirmed"
    assert "validate" not in port.calls


async def test_a_settled_validation_is_reread_rather_than_assumed(repository):
    """A crash between the answer and the record must not strand the task.

    The cross-text call was confirmed before the process died, so the outcome
    exists at the provider and nowhere in this database. A resume has to go
    and read it; treating the settled intent as if it carried an answer would
    either crash or, worse, publish a voice nobody ever heard pass.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(
        _DiesBeforeRecording(repository, "validation_audio_digest"), port
    )
    await _drive_to_validating(repository, worker, port)

    with pytest.raises(RuntimeError):
        await worker.advance("task-1")
    operation = await repository.load_operation("validate:task-1:0")
    assert operation.status == "confirmed"
    assert (await repository.load_task("task-1")).stage is VoiceFoundryStage.VALIDATING

    resumed, _, _ = make_worker(repository, port)
    step = await resumed.advance("task-1")

    assert step.record.stage is VoiceFoundryStage.AWAITING_REVIEW
    candidate = await repository.load_candidate("task-1", "task-1:candidate:0")
    assert candidate.state == "reviewing"
    assert candidate.validation_audio_digest == VALIDATION_AUDIO_DIGEST
    # Two calls, one logical check: the second read the original answer.
    assert port.calls.count("validate") == 2


async def test_a_provider_that_forgets_its_own_answer_is_not_guessed_around(
    repository,
):
    """Re-reading is only safe because the key replays. If it does not, stop.

    Silently keeping the recorded id, or silently keeping the new one, would
    both leave a record claiming a cross-text result that was never obtained.
    """
    port = _DriftingValidationPort()
    worker, _, _ = make_worker(
        _DiesBeforeRecording(repository, "validation_audio_digest"), port
    )
    await _drive_to_validating(repository, worker, port)
    with pytest.raises(RuntimeError):
        await worker.advance("task-1")

    resumed, _, _ = make_worker(repository, port)
    with pytest.raises(VoiceFoundryPortError) as caught:
        await resumed.advance("task-1")

    assert caught.value.code == "foundry_outcome_diverged"
    assert (await repository.load_task("task-1")).stage is VoiceFoundryStage.VALIDATING


async def test_publishing_and_binding_land_together(repository):
    """The evidence and the binding are one outcome, not two steps.

    Publishing first would leave a published voice nothing can render; binding
    first would bind a voice nobody published. The binding also has to be
    readable afterwards — an evidence triple that cannot be loaded strands the
    voice at exactly the moment it was supposed to go live.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_validating(repository, worker, port)
    await worker.advance("task-1")

    # Stand in for the accepted human review the command layer records.
    task = await repository.load_task("task-1")
    await repository.update_candidate(
        task.task_id,
        expected_revision=task.task_revision,
        candidate_id="task-1:candidate:0",
        state="published",
    )
    task = await repository.load_task(task.task_id)
    await repository.set_stage(
        task.task_id,
        expected_revision=task.task_revision,
        stage="published",
        operation_status="confirmed",
        required_actions=(),
    )

    step = await worker.publish_and_bind(
        "task-1", binding_id=task.scope.binding_identity
    )

    assert step.record.stage is VoiceFoundryStage.READY
    # Publishing is conditional on the revision the design is at *now*, which
    # is the one confirm produced — not the one create handed out. Sending the
    # older one is a 409 from any provider that moves the revision.
    assert port.published_revision == CONFIRMED_REVISION
    history = await repository.load_binding_history(task.scope.binding_identity)
    assert [(item.binding_revision, item.status) for item in history] == [
        (1, "reserved"),
        (2, "active"),
    ]
    assert all(item.evidence_id == "ev_1" for item in history)


async def test_the_published_document_satisfies_the_shipped_evidence_contract(repository):
    """The stored snapshot has to be the document, not a fragment of it.

    The worker used to persist six sections and stop. Everything else the
    evidence contract declares — when the snapshot was minted, whether it was
    revoked, which playback policy applies — had no producer at all, so the
    only way to read a voice back was to invent those facts.

    Validating the whole document against the schema comes one slice later,
    and deliberately not here: the contract's ``execution`` section currently
    forbids a field the gate requires, and this suite's provider fake is not
    contract-shaped either. Asserting validity now would be asserting a
    document the contract does not permit, against a fixture that never was.
    What this pins is the part that is genuinely the worker's — that the
    document is whole, and that it can be read back at all.
    """
    from application.voice_evidence import evidence_record

    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_validating(repository, worker, port)
    await worker.advance("task-1")

    task = await repository.load_task("task-1")
    await repository.update_candidate(
        task.task_id,
        expected_revision=task.task_revision,
        candidate_id="task-1:candidate:0",
        state="published",
    )
    task = await repository.load_task(task.task_id)
    await repository.set_stage(
        task.task_id,
        expected_revision=task.task_revision,
        stage="published",
        operation_status="confirmed",
        required_actions=(),
    )
    await worker.publish_and_bind("task-1", binding_id=task.scope.binding_identity)

    stored = await repository.load_evidence("speechrail-local", "ev_1")
    document = dict(stored.snapshot)
    assert set(document) == {
        "schema_version",
        "evidence_id",
        "evidence_digest",
        "provider_instance",
        "voice_id",
        "voice_revision",
        "execution",
        "reference",
        "output",
        "human",
        "publication",
        "rights",
        "created_at",
        "expires_at",
        "revoked",
        "cached_playback_policy",
    }

    # And it survives the trip back into the gate's own record, so a voice
    # that was admitted when it was published can still be recognised later.
    record = evidence_record(document)
    assert record is not None
    assert record.evidence_id == "ev_1"
    assert record.cached_playback_policy == "revocation_aware"
    assert record.revoked is False
    assert record.expires_at is None


async def test_publishing_a_task_that_is_not_published_is_refused(repository):
    """The worker will not improvise the step that needs a listener."""
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    registered = await repository.register_task(task_spec())

    step = await worker.publish_and_bind(
        "task-1", binding_id=registered.scope.binding_identity
    )

    assert step.record.stage is VoiceFoundryStage.REQUESTED
    assert step.slot_consumed is False
    assert port.calls == []


async def _drive_to_awaiting_review(repository, worker, port):
    step = await _drive_to_validating(repository, worker, port)
    assert step.record.stage is VoiceFoundryStage.VALIDATING
    step = await worker.advance("task-1")
    assert step.record.stage is VoiceFoundryStage.AWAITING_REVIEW
    return step


def _verdict(identity=FoundryReviewVerdict.PASS, naturalness=FoundryReviewVerdict.PASS):
    return {
        "task_id": "task-1",
        "candidate_id": "task-1:candidate:0",
        "validation_id": VALIDATION_ID,
        "reference_audio_digest": REFERENCE_AUDIO_DIGEST,
        "validation_audio_digest": VALIDATION_AUDIO_DIGEST,
        "identity": identity,
        "naturalness": naturalness,
    }


async def test_a_listener_verdict_reaches_the_provider_before_it_is_recorded(
    repository,
):
    """A review that never leaves this process is not a review.

    The provider only lets a voice be published once a human verdict has
    reached *it*. Recording the verdict locally first would mark the task
    published while the provider still refuses the publication, so the whole
    cast would end in a voice nobody is allowed to use.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_awaiting_review(repository, worker, port)

    step = await worker.submit_review(**_verdict())

    assert "review" in port.calls
    assert port.review_arguments["validation_id"] == VALIDATION_ID
    assert port.review_arguments["identity"] is FoundryReviewVerdict.PASS
    assert port.review_arguments["naturalness"] is FoundryReviewVerdict.PASS
    assert step.record.stage is VoiceFoundryStage.PUBLISHED
    candidate = await repository.load_candidate("task-1", "task-1:candidate:0")
    assert candidate.state == "published"


async def test_the_evidence_names_the_cross_text_audio_the_verdict_is_about(
    repository,
):
    """A verdict that reaches the provider has to say what it is a verdict on.

    The provider publishes no digest for a validation, so the evidence cannot
    recover one from the reply — it used to, from a field the service does not
    send, and published evidence that named a validation while saying nothing
    about the audio a person approved. That is the one claim an evidence
    bundle exists to make, so the digest travels in from the caller that read
    the asset.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_awaiting_review(repository, worker, port)

    candidate = await repository.load_candidate("task-1", "task-1:candidate:0")
    assert candidate.validation_audio_digest == VALIDATION_AUDIO_DIGEST

    await worker.submit_review(**_verdict())

    assert (
        port.review_arguments["validation_audio_digest"]
        == candidate.validation_audio_digest
    )


async def test_a_rejected_verdict_ends_the_task_and_says_why(repository):
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_awaiting_review(repository, worker, port)

    step = await worker.submit_review(
        **_verdict(naturalness=FoundryReviewVerdict.REJECT)
    )

    # The provider still hears the rejection: "a person heard this and said
    # no" is itself a fact worth having on record.
    assert "review" in port.calls
    assert step.record.stage is VoiceFoundryStage.FAILED
    assert step.record.reason_code == "human_review_rejected"
    candidate = await repository.load_candidate("task-1", "task-1:candidate:0")
    assert candidate.state == "failed"


async def test_one_reject_out_of_two_questions_is_a_rejection(repository):
    """Identity yes, naturalness no is still a no.

    A voice the listener would not sit through a scene with is not a casting
    they approved, and averaging the two questions into a score is exactly how
    an unheard voice ends up behind a player's ear.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_awaiting_review(repository, worker, port)

    step = await worker.submit_review(
        **_verdict(identity=FoundryReviewVerdict.PASS, naturalness=FoundryReviewVerdict.REJECT)
    )

    assert step.record.stage is VoiceFoundryStage.FAILED


async def test_a_verdict_about_regenerated_audio_is_refused(repository):
    """The old audition does not prove the new reference.

    If the reference or the cross-text audio was regenerated after somebody
    listened, their verdict describes audio that no longer exists. Carrying it
    forward would put an unheard voice behind their signature.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_awaiting_review(repository, worker, port)
    before = await repository.load_task("task-1")

    with pytest.raises(VoiceFoundryPortError) as caught:
        await worker.submit_review(**{**_verdict(), "reference_audio_digest": "b" * 64})

    assert caught.value.code == "review_asset_mismatch"
    assert "review" not in port.calls
    after = await repository.load_task("task-1")
    assert after.stage is VoiceFoundryStage.AWAITING_REVIEW
    assert after.task_revision == before.task_revision


async def test_a_verdict_about_a_validation_we_never_ran_is_refused(repository):
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_awaiting_review(repository, worker, port)

    with pytest.raises(VoiceFoundryPortError) as caught:
        await worker.submit_review(**{**_verdict(), "validation_id": "vv_" + "9" * 24})

    assert caught.value.code == "foundry_outcome_unknown"
    assert "review" not in port.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "verdict,expected",
    [
        (FoundryReviewVerdict.WARN, "review_verdict_requires_explicit_handling"),
        (FoundryReviewVerdict.NOT_REVIEWED, "review_verdict_absent"),
    ],
)
async def test_a_verdict_that_is_not_a_decision_never_reaches_the_provider(
    repository, verdict, expected
):
    """A warning is not a pass, and the absence of a review is not a pass.

    Both are refused before the call rather than mapped onto an outcome: the
    only thing worse than publishing unreviewed audio is publishing it by
    accident through a lenient default.
    """
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_awaiting_review(repository, worker, port)
    before = await repository.load_task("task-1")

    with pytest.raises(VoiceFoundryPortError) as caught:
        await worker.submit_review(**_verdict(identity=verdict))

    assert caught.value.code == expected
    assert "review" not in port.calls
    after = await repository.load_task("task-1")
    assert after.stage is VoiceFoundryStage.AWAITING_REVIEW
    assert after.task_revision == before.task_revision


async def test_an_unknown_review_outcome_leaves_the_task_reviewable(repository):
    """A timed-out review must not be mistaken for a completed one.

    The verdict may or may not have landed upstream. Marking the task
    published on a guess is how an unreviewed voice gets released; leaving the
    honest record lets a resume settle it under the same operation identity.
    """
    port = RecordingPort(review_error=VoiceFoundryPortError("foundry_transient"))
    worker, _, _ = make_worker(repository, port)
    await _drive_to_awaiting_review(repository, worker, port)

    with pytest.raises(VoiceFoundryPortError):
        await worker.submit_review(**_verdict())

    operation = await repository.load_operation("review:task-1:0")
    assert operation.status == "unknown"
    task = await repository.load_task("task-1")
    assert task.stage is VoiceFoundryStage.AWAITING_REVIEW
    candidate = await repository.load_candidate("task-1", "task-1:candidate:0")
    assert candidate.state == "reviewing"


async def test_a_review_is_not_repeated_once_it_is_confirmed(repository):
    port = RecordingPort()
    worker, _, _ = make_worker(repository, port)
    await _drive_to_awaiting_review(repository, worker, port)
    await worker.submit_review(**_verdict())

    # A client that never saw the answer retries. The task has left
    # ``awaiting_review``, so the retry is a no-op rather than a second
    # upstream review of a voice that is already published.
    step = await worker.submit_review(**_verdict())

    assert step.slot_consumed is False
    assert port.calls.count("review") == 1
