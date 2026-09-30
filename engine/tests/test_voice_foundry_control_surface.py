"""The Voice Foundry control surface: what a client is allowed to ask for.

The invariants here are about the envelope rather than about casting. A
command names its own action, quotes a digest of its own payload and states
the revision it acted on; the surface is what turns those three claims into
an action it is willing to take, and what it refuses when they do not line
up.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

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
from infrastructure.voice_foundry_repository import (
    SQLiteVoiceFoundryRepository,
    VoiceFoundryStage,
    VoiceFoundryTaskSpec,
)

CANDIDATE_REVISION = "vr_" + "c" * 32
PREVIEW_AUDIO_DIGEST = "b" * 64
REFERENCE_AUDIO_DIGEST = "9" * 64
VALIDATION_AUDIO_DIGEST = "d" * 64
VALIDATION_ID = "vv_" + "e" * 24


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
            candidate_revision="vr_" + "b" * 32,
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
            candidate_revision="vr_" + "b" * 32,
            capability_key=capability_key,
            audio_digest=VALIDATION_AUDIO_DIGEST,
            text_digest="e" * 64,
            passed=True,
        )

    async def read_asset(self, request: AssetRequest) -> AssetResult:
        self.calls.append("read_asset")
        return AssetResult(
            audio_digest=REFERENCE_AUDIO_DIGEST, audio_bytes=16, duration_seconds=1.0
        )

    async def review(self, candidate_id, *, validation_id, identity, naturalness):
        self.calls.append("review")
        self.review_arguments = {
            "candidate_id": candidate_id,
            "validation_id": validation_id,
            "identity": identity,
            "naturalness": naturalness,
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
    assert port.calls[-3:] == ["confirm", "read_asset", "validate"]
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
    assert port.calls[-3:] == ["confirm", "read_asset", "validate"]


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


def test_publish_and_binding_replace_are_not_registered_yet(handlers):
    """Both need a binding id for a binding that does not exist yet.

    No production path mints one: every call site takes ``binding_id`` as a
    parameter and the wire contract carries no field that could supply it.
    Registering them here would mean inventing a binding identity scheme in a
    data-layer slice, where nothing would catch it being wrong.
    """
    assert set(handlers) == {
        "voice.foundry.get",
        "voice.foundry.list",
        "voice.foundry.select",
        "voice.foundry.confirm_reference",
        "voice.foundry.validate",
        "voice.foundry.review",
        "voice.foundry.retry",
        "voice.foundry.cancel",
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
