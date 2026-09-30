"""The Voice Foundry control surface: what a client is allowed to ask for.

The invariants here are about the envelope rather than about casting. A
command names its own action, quotes a digest of its own payload and states
the revision it acted on; the surface is what turns those three claims into
an action it is willing to take, and what it refuses when they do not line
up.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import sqlite3

import jsonschema
import pytest
import pytest_asyncio

from application.voice_foundry import FoundryRetryPolicy, VoiceFoundryWorker
from application.voice_foundry_commands import VoiceFoundryCommandService
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
)
from application.voice_foundry_service import VoiceSupplyService
from domain.voice_identity import VoiceBindingScope

# Spelled without the ``engine.`` prefix on purpose: the application layer
# under test imports ``infrastructure.voice_foundry_repository`` bare, and a
# second module object would fail its own type guards.
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.voice_foundry_control import voice_foundry_control_handlers
from infrastructure.voice_design_catalog import load_voice_design_catalog
from infrastructure.voice_foundry_repository import (
    SQLiteVoiceFoundryRepository,
    VoiceFoundryStage,
    VoiceFoundryTaskSpec,
)

#: What ``create`` answers with. The provider moves the design on when the
#: reference text is bound, so this is never the revision a caller may act on.
CREATED_REVISION = "vr_" + "b" * 32
#: Where the candidate actually is once ``confirm`` has run.
CANDIDATE_REVISION = "vr_" + "c" * 32
PREVIEW_AUDIO_DIGEST = "b" * 64
REFERENCE_AUDIO_DIGEST = "9" * 64
VALIDATION_AUDIO_DIGEST = "d" * 64
VALIDATION_ID = "vv_" + "e" * 24
#: What the provider actually serves. The digests above are recorded values, so
#: the bytes have to be carried separately — a caller that decodes this has to
#: get audio, not a well-formed envelope around nothing.
ASSET_AUDIO = b"RIFF----WAVEfake"


def digest(payload) -> str:
    """The wire digest, recomputed rather than imported.

    Tying the test to the implementation's own helper would prove only that
    the function agrees with itself. Spelling the formula out here is what
    pins what a client actually has to compute.
    """
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


@pytest.fixture
def paths(tmp_path):
    layout = DatabasePaths.for_world(tmp_path, "foundry-control-world")
    layout.canon.parent.mkdir(parents=True)
    with sqlite3.connect(layout.canon) as conn:
        conn.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    return layout


@pytest_asyncio.fixture
async def repository(paths):
    db = await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )
    try:
        yield SQLiteVoiceFoundryRepository(db)
    finally:
        await db.close()


class _NoBindings:
    async def load_scope(self, _scope):
        return None


class _Port:
    """Just enough provider to walk one task to a listener."""

    def __init__(self, *, explode: bool = False):
        self.calls: list[str] = []
        self.asset_requests: list[AssetRequest] = []
        self.explode = explode

    async def preview(self, request: PreviewRequest) -> PreviewResult:
        self.calls.append("preview")
        return PreviewResult(
            preview_id="pv_1",
            audio_digest=PREVIEW_AUDIO_DIGEST,
            audio_bytes=16,
            duration_seconds=1.0,
            recipe={"seed": request.seed},
            recipe_digest="c" * 64,
        )

    async def create(self, request: CreateRequest) -> CandidateState:
        self.calls.append("create")
        return CandidateState(
            candidate_id="vd_" + "a" * 24,
            candidate_revision=CREATED_REVISION,
            state="created",
            reference_confirmed=False,
        )

    async def confirm(self, candidate_id, request) -> CandidateState:
        self.calls.append("confirm")
        return CandidateState(
            candidate_id=candidate_id,
            candidate_revision=CANDIDATE_REVISION,
            state="confirmed",
            reference_confirmed=True,
        )

    async def validate(self, candidate_id, *, test_text, capability_key):
        self.calls.append("validate")
        if self.explode:
            raise ValueError("a provider body that must never reach a caller")
        return ValidationResult(
            validation_id=VALIDATION_ID,
            candidate_id=candidate_id,
            candidate_revision=CANDIDATE_REVISION,
            capability_key=capability_key,
            audio_digest=VALIDATION_AUDIO_DIGEST,
            text_digest="e" * 64,
            passed=True,
        )

    async def read_asset(self, request: AssetRequest) -> AssetResult:
        self.calls.append("read_asset")
        self.asset_requests.append(request)
        # Which asset is being read is decided by the validation id, as upstream
        # decides it: the reference belongs to no validation.
        return AssetResult(
            audio_digest=(
                REFERENCE_AUDIO_DIGEST
                if request.validation_id is None
                else VALIDATION_AUDIO_DIGEST
            ),
            audio_bytes=len(ASSET_AUDIO),
            duration_seconds=1.0,
            audio=ASSET_AUDIO,
        )

    async def review(
        self,
        candidate_id,
        *,
        validation_id,
        identity,
        naturalness,
        validation_audio_digest="",
    ):
        self.calls.append("review")
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
            reference={"audio_sha256": REFERENCE_AUDIO_DIGEST},
            output={"audio_sha256": VALIDATION_AUDIO_DIGEST},
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
            voice_id="vd_published",
            voice_revision="wvr_" + "9" * 24,
            evidence=EvidenceBundle(
                evidence_id="ev_published",
                evidence_digest="7" * 64,
                execution={
                    "model_id": "qwen3-tts",
                    "model_artifact_revision": "art-1",
                    "variant": "custom_voice",
                    "locale": "zh",
                    "validation_policy_revision": "policy-1",
                    "processing_fingerprint": "8" * 64,
                },
                reference={"audio_sha256": REFERENCE_AUDIO_DIGEST},
                output={"audio_sha256": VALIDATION_AUDIO_DIGEST},
                human={"identity_status": "pass", "naturalness_status": "pass"},
                publication={"published": True},
                rights={"cleared": True},
            ),
        )

    @property
    def locale_map(self):
        return ProviderLocaleMap({"zh-CN": "zh"})

    @property
    def capabilities(self):
        return VoiceFoundryCapabilities(
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


def task_spec(**overrides) -> VoiceFoundryTaskSpec:
    base = {
        "task_id": "task-1",
        "request_id": "request-1",
        "request_digest": "a" * 64,
        "authorization_ref": "authz-1",
        "scope": VoiceBindingScope(
            owner_id="player",
            world_id="foundry-control-world",
            worldline_id="line-1",
            presentation_identity="klein-visible",
            phase="narrative",
            locale="zh-CN",
        ),
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


@pytest.fixture
def port():
    return _Port()


@pytest.fixture
def worker(repository, port):
    return VoiceFoundryWorker(
        repository,
        port,
        policy=FoundryRetryPolicy(backoff_seconds=(0.0, 0.0, 0.0)),
    )


@pytest.fixture
def handlers(repository, worker):
    supply = VoiceSupplyService(repository=repository, bindings=_NoBindings())
    commands = VoiceFoundryCommandService(
        repository=repository, supply=supply, driver=worker
    )
    return voice_foundry_control_handlers(
        repository=repository,
        supply=supply,
        commands=commands,
        worker=worker,
    )


def _command(task_id, revision, action, payload, *, command_id="cmd-1"):
    return {
        "schema_version": "1.0",
        "command_id": command_id,
        "payload_digest": digest(payload),
        "task_id": task_id,
        "expected_task_revision": revision,
        "action": action,
        "payload": payload,
    }


async def _drive_to_validating(repository, worker):
    task = await repository.register_task(task_spec())
    await worker.advance(task.task_id)
    task = await repository.load_task(task.task_id)
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


async def _reviewed(repository, worker, handlers, port):
    """Walk one casting all the way to a listener, through the surface."""
    await _confirmed(repository, worker, handlers, port)
    task = await repository.load_task("task-1")
    await handlers["voice.foundry.validate"](
        _command(
            "task-1",
            task.task_revision,
            "validate",
            {
                "test_text": task_spec().validation_text,
                "capability_key": "quality.render",
            },
            command_id="cmd-validate",
        )
    )
    assert port.calls[-4:] == [
        "confirm",
        "read_asset",
        "validate",
        "read_asset",
    ]
    return await repository.load_task("task-1")


async def _confirmed(repository, worker, handlers, port):
    """Walk one casting up to the point where the voice can be proved."""
    await _drive_to_validating(repository, worker)
    task = await repository.load_task("task-1")
    await handlers["voice.foundry.confirm_reference"](
        _command(
            "task-1",
            task.task_revision,
            "confirm_reference",
            {
                "provider_candidate_revision": CANDIDATE_REVISION,
                "reference_text": task_spec().reference_text,
                "reference_audio_digest": REFERENCE_AUDIO_DIGEST,
            },
            command_id="cmd-confirm",
        )
    )
    return await repository.load_task("task-1")


async def _published(repository, worker, handlers, port):
    """Walk one casting all the way through a listener's approval."""
    task = await _reviewed(repository, worker, handlers, port)
    body, code = await handlers["voice.foundry.review"](
        _command(
            "task-1",
            task.task_revision,
            "review",
            {
                "human_review": {
                    "validation_id": VALIDATION_ID,
                    "reference_audio_digest": REFERENCE_AUDIO_DIGEST,
                    "validation_audio_digest": VALIDATION_AUDIO_DIGEST,
                    "identity": "pass",
                    "naturalness": "pass",
                }
            },
            command_id="cmd-review",
        )
    )
    assert code is None, body
    return await repository.load_task("task-1")


# -- reads ---------------------------------------------------------------


async def test_reading_a_task_writes_nothing_and_calls_no_provider(
    repository, handlers, port
):
    await repository.register_task(task_spec())

    body, code = await handlers["voice.foundry.get"](
        {"schema_version": "1.0", "task_id": "task-1"}
    )

    assert code is None
    assert body["task"]["task_id"] == "task-1"
    assert body["task"]["stage"] == VoiceFoundryStage.REQUESTED.value
    assert port.calls == []


async def test_the_audition_hands_over_audio_and_the_facts_a_review_is_checked_against(
    repository, worker, handlers, port
):
    """Everything ``review`` demands has to come from somewhere.

    Its payload requires a validation id and both audio digests, and the task
    projection carries none of them. This read is where a client learns all
    three — and it learns them beside the bytes they describe, so the verdict
    it goes on to send is about audio it can prove it was given.
    """
    await _reviewed(repository, worker, handlers, port)

    body, code = await handlers["voice.foundry.asset.get"](
        {
            "schema_version": "1.0",
            "task_id": "task-1",
            "candidate_id": "task-1:candidate:0",
            "kind": "validation",
        }
    )

    assert code is None
    assert base64.b64decode(body["audio_base64"]) == ASSET_AUDIO
    assert body["audio_bytes"] == len(ASSET_AUDIO)
    assert body["audio_digest"] == VALIDATION_AUDIO_DIGEST
    assert body["validation_id"] == VALIDATION_ID
    assert body["candidate_revision"] == CANDIDATE_REVISION


async def test_the_reference_asset_names_no_validation(
    repository, worker, handlers, port
):
    """It belongs to no validation, and says so rather than naming an empty one."""
    await _reviewed(repository, worker, handlers, port)

    body, code = await handlers["voice.foundry.asset.get"](
        {
            "schema_version": "1.0",
            "task_id": "task-1",
            "candidate_id": "task-1:candidate:0",
            "kind": "reference",
        }
    )

    assert code is None
    assert body["validation_id"] is None
    assert body["audio_digest"] == REFERENCE_AUDIO_DIGEST


async def test_an_asset_kind_that_is_not_an_asset_is_refused(
    repository, worker, handlers, port
):
    await _reviewed(repository, worker, handlers, port)
    port.calls.clear()

    body, code = await handlers["voice.foundry.asset.get"](
        {
            "schema_version": "1.0",
            "task_id": "task-1",
            "candidate_id": "task-1:candidate:0",
            "kind": "preview",
        }
    )

    assert (body, code) == (None, "schema_invalid")
    assert port.calls == []


async def test_an_asset_read_carries_no_command_envelope(
    repository, worker, handlers, port
):
    """It is a read. A client that brings a command id is asking to change
    something, and there is nothing here to change."""
    await _reviewed(repository, worker, handlers, port)

    body, code = await handlers["voice.foundry.asset.get"](
        _command(
            "task-1",
            1,
            "asset.get",
            {"kind": "reference"},
            command_id="cmd-asset",
        )
    )

    assert (body, code) == (None, "schema_invalid")


async def test_the_list_pages_without_losing_a_task(repository, handlers):
    for index in range(3):
        await repository.register_task(
            task_spec(
                task_id=f"task-{index}",
                request_id=f"request-{index}",
                request_digest=f"{index}" * 64,
            )
        )

    first, code = await handlers["voice.foundry.list"](
        {"schema_version": "1.0", "page_size": 2}
    )
    assert code is None
    assert len(first["tasks"]) == 2
    assert first["next_page_token"] is not None

    second, code = await handlers["voice.foundry.list"](
        {
            "schema_version": "1.0",
            "page_size": 2,
            "page_token": first["next_page_token"],
        }
    )
    assert code is None
    assert len(second["tasks"]) == 1
    # A short page is the last page. Claiming otherwise sends the caller back
    # for a read that can only come back empty.
    assert second["next_page_token"] is None
    assert first["tasks"][0]["task_id"] != second["tasks"][0]["task_id"]


# -- the envelope is checked before any of it is believed ----------------


async def test_a_key_the_contract_does_not_declare_is_refused(repository, handlers):
    await repository.register_task(task_spec())

    body, code = await handlers["voice.foundry.get"](
        {
            "schema_version": "1.0",
            "task_id": "task-1",
            "also_send": "the provider credentials, why not",
        }
    )

    assert (body, code) == (None, "schema_invalid")


async def test_a_forged_page_token_is_refused_rather_than_re_read(
    repository, handlers
):
    await repository.register_task(task_spec())

    body, code = await handlers["voice.foundry.list"](
        {"schema_version": "1.0", "page_size": 2, "page_token": "not-a-cursor"}
    )

    # Showing a different page for a cursor this service never issued is the
    # failure mode worth avoiding: it reads as "there is nothing here".
    assert (body, code) == (None, "page_token_invalid")


async def test_a_selection_made_from_another_preview_is_refused(
    repository, handlers, worker
):
    """The client says which preview it chose between; that has to be checked.

    ``select_payload`` carries a preview digest, and nothing downstream of the
    wire uses it — the command service selects on candidate id alone. Left
    unchecked it is a field that looks like an authorization and is not one.
    """
    task = await repository.register_task(task_spec())
    await worker.advance(task.task_id)
    task = await repository.load_task(task.task_id)
    assert task.stage is VoiceFoundryStage.AWAITING_SELECTION

    selected, code = await handlers["voice.foundry.select"](
        _command(
            "task-1",
            task.task_revision,
            "select",
            {
                "candidate_id": "task-1:candidate:0",
                "preview_audio_digest": "0" * 64,
            },
        )
    )

    assert (selected, code) == (None, "select_asset_mismatch")

    accepted, code = await handlers["voice.foundry.select"](
        _command(
            "task-1",
            task.task_revision,
            "select",
            {
                "candidate_id": "task-1:candidate:0",
                "preview_audio_digest": PREVIEW_AUDIO_DIGEST,
            },
        )
    )
    assert code is None
    assert accepted["task"]["stage"] == VoiceFoundryStage.PROVISIONING.value


async def test_a_command_cannot_wear_another_actions_name(repository, handlers):
    await repository.register_task(task_spec())
    task = await repository.load_task("task-1")

    body, code = await handlers["voice.foundry.cancel"](
        _command(
            "task-1", task.task_revision, "publish", {"provider_candidate_revision": "vr_x"}
        )
    )

    assert (body, code) == (None, "action_not_available_on_this_method")


async def test_a_digest_that_does_not_cover_its_own_payload_is_refused(
    repository, handlers
):
    await repository.register_task(task_spec())
    task = await repository.load_task("task-1")
    command = _command(
        "task-1", task.task_revision, "cancel", {"reason_code": "user_asked"}
    )
    command["payload"] = {"reason_code": "someone_elses_reason"}

    body, code = await handlers["voice.foundry.cancel"](command)

    assert (body, code) == (None, "command_digest_mismatch")


async def test_a_command_acted_on_a_stale_revision_is_refused(repository, handlers):
    """The revision guard is the contract's, so it has to be real.

    Nothing in the command service compares the caller's revision against the
    current one — it guards its own writes. Without this check a client
    holding a task it read an hour ago could still select, cancel or retry,
    and the ``expected_task_revision`` the contract declares would be
    decoration.
    """
    await repository.register_task(task_spec())

    body, code = await handlers["voice.foundry.cancel"](
        _command("task-1", 99, "cancel", {"reason_code": "user_asked"})
    )

    assert (body, code) == (None, "stale_task_revision")


async def test_a_command_id_reused_for_another_task_is_refused(repository, handlers):
    await repository.register_task(task_spec())
    await repository.register_task(
        task_spec(task_id="task-2", request_id="request-2", request_digest="b" * 64)
    )
    task = await repository.load_task("task-1")
    await handlers["voice.foundry.cancel"](
        _command(
            "task-1", task.task_revision, "cancel", {"reason_code": "user_asked"}
        )
    )

    other = await repository.load_task("task-2")
    body, code = await handlers["voice.foundry.cancel"](
        _command(
            "task-2",
            other.task_revision,
            "cancel",
            {"reason_code": "user_asked"},
            command_id="cmd-1",
        )
    )

    assert (body, code) == (None, "command_id_rebound_to_different_input")


# -- idempotency ---------------------------------------------------------


async def test_repeating_a_command_returns_the_first_answer_not_a_second_action(
    repository, handlers
):
    await repository.register_task(task_spec())
    task = await repository.load_task("task-1")
    command = _command(
        "task-1", task.task_revision, "cancel", {"reason_code": "user_asked"}
    )

    first, first_code = await handlers["voice.foundry.cancel"](command)
    second, second_code = await handlers["voice.foundry.cancel"](command)

    assert first_code is None and second_code is None
    assert first["replayed"] is False
    # The retry carries the revision it saw before the first attempt moved it.
    # Answering that with a stale-revision error would make the command id
    # useless as an idempotency key, which is the only thing it is.
    assert second["replayed"] is True
    assert second["task"]["task_revision"] == first["task"]["task_revision"]


# -- the worker verbs reach the worker -----------------------------------


async def test_a_casting_walks_the_two_explicit_steps_and_stops_at_the_listener(
    repository, handlers, worker, port
):
    parked = await _drive_to_validating(repository, worker)
    assert parked.record.stage is VoiceFoundryStage.VALIDATING

    confirmed, code = await handlers["voice.foundry.confirm_reference"](
        _command(
            "task-1",
            parked.record.task_revision,
            "confirm_reference",
            {
                "provider_candidate_revision": CANDIDATE_REVISION,
                "reference_text": task_spec().reference_text,
                "reference_audio_digest": REFERENCE_AUDIO_DIGEST,
            },
            command_id="cmd-confirm",
        )
    )
    assert code is None
    assert confirmed["task"]["stage"] == VoiceFoundryStage.VALIDATING.value

    validated, code = await handlers["voice.foundry.validate"](
        _command(
            "task-1",
            confirmed["task"]["task_revision"],
            "validate",
            {
                "test_text": task_spec().validation_text,
                "capability_key": "quality.render",
            },
            command_id="cmd-validate",
        )
    )

    assert code is None
    assert validated["task"]["stage"] == VoiceFoundryStage.AWAITING_REVIEW.value
    assert validated["task"]["required_actions"] == [
        "listen_reference",
        "listen_validation",
        "review",
    ]
    assert port.calls[-4:] == [
        "confirm",
        "read_asset",
        "validate",
        "read_asset",
    ]


async def test_a_verdict_reaches_the_provider_before_it_is_recorded(
    repository, handlers, worker, port
):
    task = await _reviewed(repository, worker, handlers, port)
    assert task.stage is VoiceFoundryStage.AWAITING_REVIEW

    body, code = await handlers["voice.foundry.review"](
        _command(
            "task-1",
            task.task_revision,
            "review",
            {
                "human_review": {
                    "validation_id": VALIDATION_ID,
                    "reference_audio_digest": REFERENCE_AUDIO_DIGEST,
                    "validation_audio_digest": VALIDATION_AUDIO_DIGEST,
                    "identity": "pass",
                    "naturalness": "pass",
                }
            },
        )
    )

    assert code is None
    # ``awaiting_review`` means a person is the only thing left between this
    # task and a published voice, so an accepted verdict has to end there.
    assert body["task"]["stage"] == VoiceFoundryStage.PUBLISHED.value
    # The verdict reached the provider before it was recorded. A judgement
    # that only ever landed here would mark the task published while the
    # provider still refused to release the voice.
    assert port.calls[-1] == "review"
    assert port.review_arguments["validation_id"] == VALIDATION_ID


async def test_a_verdict_on_a_task_with_nothing_awaiting_review_is_refused(
    repository, handlers
):
    await repository.register_task(task_spec())
    task = await repository.load_task("task-1")

    body, code = await handlers["voice.foundry.review"](
        _command(
            "task-1",
            task.task_revision,
            "review",
            {
                "human_review": {
                    "validation_id": VALIDATION_ID,
                    "reference_audio_digest": REFERENCE_AUDIO_DIGEST,
                    "validation_audio_digest": VALIDATION_AUDIO_DIGEST,
                    "identity": "pass",
                    "naturalness": "pass",
                }
            },
        )
    )

    assert (body, code) == (None, "candidate_not_awaiting_review")


# -- what is deliberately not here ---------------------------------------


def test_binding_replace_is_not_registered_yet(handlers):
    """It re-points a binding that already exists, so it has no task to hang
    its idempotency receipt on.

    The journal these commands replay through is keyed by task, and a
    replacement names a binding rather than a casting. Registering it against
    that journal would either lose the receipt or invent a second one.
    """
    assert "voice.binding.replace" not in handlers
    assert set(handlers) == {
        "voice.foundry.get",
        "voice.foundry.list",
        "voice.foundry.asset.get",
        "voice.foundry.select",
        "voice.foundry.confirm_reference",
        "voice.foundry.validate",
        "voice.foundry.review",
        "voice.foundry.publish",
        "voice.foundry.retry",
        "voice.foundry.cancel",
        "voice.foundry.request",
    }


async def test_an_unexpected_failure_reaches_the_caller_as_one_stable_code(
    repository, handlers, worker, port
):
    port.explode = True
    task = await _confirmed(repository, worker, handlers, port)

    body, code = await handlers["voice.foundry.validate"](
        _command(
            "task-1",
            task.task_revision,
            "validate",
            {
                "test_text": task_spec().validation_text,
                "capability_key": "quality.render",
            },
        )
    )

    assert body is None
    # One public code, and nothing of what actually went wrong: an internal
    # message can carry a path, a provider body, or a field nobody outside
    # this process is allowed to see.
    assert code == "service_unavailable"


async def test_publishing_binds_the_voice_under_the_scope_it_was_cast_for(
    repository, handlers, worker, port
):
    """The binding key is derived, not chosen.

    ``voice_bindings`` is unique on the scope, so a caller that named its own
    key could point one character's voice at another character's row and
    nothing would report an error — the row would satisfy the constraint and
    still be unreachable, because rendering looks a voice up by scope.
    """
    task = await _published(repository, worker, handlers, port)
    assert task.stage is VoiceFoundryStage.PUBLISHED

    body, code = await handlers["voice.foundry.publish"](
        _command(
            "task-1",
            task.task_revision,
            "publish",
            {"provider_candidate_revision": CANDIDATE_REVISION},
            command_id="cmd-publish",
        )
    )

    assert code is None
    assert body["task"]["stage"] == VoiceFoundryStage.READY.value
    assert port.calls[-1] == "publish"
    assert port.published_revision == CANDIDATE_REVISION


async def test_publishing_a_revision_nobody_approved_is_refused(
    repository, handlers, worker, port
):
    """Publication is irreversible upstream.

    The caller names the revision it approved; the row carries the revision
    that exists today. Releasing the one on the row when the caller approved a
    different one would put a voice in front of players that no person ever
    heard.
    """
    task = await _published(repository, worker, handlers, port)
    calls_before = list(port.calls)

    body, code = await handlers["voice.foundry.publish"](
        _command(
            "task-1",
            task.task_revision,
            "publish",
            # The revision the design was *created* at. It is the one value a
            # caller must not be able to publish: the provider moved the
            # design past it when the reference text was bound.
            {"provider_candidate_revision": CREATED_REVISION},
            command_id="cmd-publish",
        )
    )

    assert (body, code) == (None, "publish_revision_mismatch")
    assert port.calls == calls_before


async def test_publishing_a_task_no_listener_approved_is_refused(
    repository, handlers, worker, port
):
    await _confirmed(repository, worker, handlers, port)
    task = await repository.load_task("task-1")

    body, code = await handlers["voice.foundry.publish"](
        _command(
            "task-1",
            task.task_revision,
            "publish",
            {"provider_candidate_revision": CANDIDATE_REVISION},
            command_id="cmd-publish",
        )
    )

    assert (body, code) == (None, "candidate_not_published")
    assert "publish" not in port.calls


# -- intake --------------------------------------------------------------


def _cast_request(**overrides) -> dict:
    """A well-formed VoiceCastRequest, digest computed the way the wire does."""
    body = {
        "schema_version": "1.0",
        "request_id": "vfr_01",
        "authorization_ref": "authz-1",
        "scope": {
            "owner_id": "player",
            "world_id": "foundry-control-world",
            "worldline_id": "line-1",
            "presentation_identity": "klein-visible",
            "phase": "narrative",
            "locale": "zh-CN",
        },
        "persona_revision": "persona-1",
        "usage": "dialogue",
        "locale": "zh-CN",
        "public_traits": ["低沉", "克制"],
        "voice_description": "克制而警觉的年轻男性声音。",
        "reference_text": "这是用于确认音色参考的完整句子，必须足够长以通过校验。",
        "validation_text": "这是用于跨文本复验的另一句完整文本，不能与参考文本相同。",
        "provider_instance": "speechrail-local",
        "requested_execution_scope": {
            "model_id": None,
            "model_artifact_revision": None,
            "variant": "custom_voice",
        },
        "budget": {
            "candidate_count": 3,
            "timeout_ms": 300000,
            "max_audio_bytes": 4194304,
        },
        "origin": {
            "kind": "content",
            "source_ref": "npc:klein",
            "source_revision": 1,
        },
    }
    body.update(overrides)
    body["request_digest"] = digest({k: v for k, v in body.items() if k != "request_digest"})
    return body


async def test_intake_opens_a_task_and_answers_what_may_happen_next(handlers):
    body, code = await handlers["voice.foundry.request"](
        {"schema_version": "1.0", "request": _cast_request()}
    )
    assert code is None, code
    assert body["outcome"] == "supply_required"
    assert body["task"]["scope"]["presentation_identity"] == "klein-visible"
    assert body["task"]["stage"] == "requested"
    # A task id the caller never chose: it is derived from the request, so a
    # retry addresses the same row without remembering what it asked for.
    assert body["task_id"]
    assert "binding_id" not in body


async def test_a_declared_execution_scope_and_budget_survive_intake(
    handlers, repository
):
    body, _ = await handlers["voice.foundry.request"](
        {"schema_version": "1.0", "request": _cast_request()}
    )

    task = await repository.load_task(body["task_id"])
    # "Unpinned" is an answer the contract allows, and it has to stay
    # distinguishable from "pinned to something we have forgotten".
    assert task.execution_scope.model_id is None
    assert task.execution_scope.variant == "custom_voice"
    assert task.budget.candidate_count == 3
    assert task.budget.timeout_ms == 300000
    assert task.budget.max_audio_bytes == 4194304


async def test_the_same_request_twice_opens_one_casting(handlers):
    first, code = await handlers["voice.foundry.request"](
        {"schema_version": "1.0", "request": _cast_request()}
    )
    assert code is None, code

    replay, code = await handlers["voice.foundry.request"](
        {"schema_version": "1.0", "request": _cast_request()}
    )

    assert code is None, code
    assert replay["task_id"] == first["task_id"]


async def test_a_digest_that_does_not_describe_the_request_is_refused(handlers):
    """Otherwise "same request id, different digest" detects nothing at all."""
    body = _cast_request()
    body["voice_description"] = "换了一段描述。"
    # The digest still describes the original request.

    answer, code = await handlers["voice.foundry.request"](
        {"schema_version": "1.0", "request": body}
    )

    assert (answer, code) == (None, "request_digest_mismatch")


async def test_a_key_the_contract_does_not_declare_is_refused(handlers):
    answer, code = await handlers["voice.foundry.request"](
        {"schema_version": "1.0", "request": _cast_request(force=True)}
    )

    assert (answer, code) == (None, "schema_invalid")


@pytest.mark.asyncio
def _supply(repository) -> VoiceSupplyService:
    class Nothing:
        async def load_scope(self, _scope):
            return None

    return VoiceSupplyService(repository=repository, bindings=Nothing())


async def test_the_casting_catalog_is_readable_and_starts_nothing(repository):
    """The picker needs the briefs; opening the picker must not cast anything."""
    supply = _supply(repository)
    handlers = voice_foundry_control_handlers(
        repository=repository,
        supply=supply,
        commands=None,
        worker=None,
        designs=load_voice_design_catalog(),
    )

    payload, code = await handlers["voice.foundry.list_designs"](
        {"schema_version": "1.0"}
    )

    assert code is None
    assert payload is not None
    assert len(payload["designs"]) == 5
    assert sum(1 for item in payload["designs"] if item["usage"] == "narration") == 1
    # Pure read: no task was created by describing what a voice would sound like.
    page = await supply.list(page_size=100)
    assert page.tasks == ()


@pytest.mark.asyncio
async def test_an_engine_without_a_catalog_does_not_advertise_the_read(repository):
    """A handshake must not promise a catalog this process failed to load."""
    handlers = voice_foundry_control_handlers(
        repository=repository,
        supply=_supply(repository),
        commands=None,
        worker=None,
        designs=None,
    )

    assert "voice.foundry.list_designs" not in handlers


@pytest.mark.asyncio
async def test_the_catalog_rejects_a_payload_that_is_not_a_versioned_read(repository):
    handlers = voice_foundry_control_handlers(
        repository=repository,
        supply=_supply(repository),
        commands=None,
        worker=None,
        designs=load_voice_design_catalog(),
    )

    payload, code = await handlers["voice.foundry.list_designs"](
        {"schema_version": "1.0", "identity": "victor-osborn"}
    )

    assert payload is None
    assert code == "schema_invalid"


def test_every_published_design_matches_the_published_contract():
    """The engine's output and the contract's shape must not be able to drift."""
    schema = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "contracts"
            / "schemas"
            / "voice_design.schema.json"
        ).read_text(encoding="utf-8")
    )
    catalog = load_voice_design_catalog()
    for design in catalog.designs:
        jsonschema.Draft202012Validator(schema).validate(
            {
                "schema_version": "1.0",
                "design_id": design.design_id,
                "display_name": design.display_name,
                "presentation_identity": design.presentation_identity,
                "usage": design.usage,
                "locale": design.locale,
                "design_revision": design.design_revision,
                "public_traits": list(design.public_traits),
                "voice_description": design.voice_description,
                "reference_text": design.reference_text,
                "validation_text": design.validation_text,
            }
        )
