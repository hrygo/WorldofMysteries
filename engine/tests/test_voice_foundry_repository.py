"""Voice Foundry durable presentation-task persistence (VF-02)."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import replace

import pytest
import pytest_asyncio

from domain.voice_identity import VoiceBindingScope, VoiceBindingStatus
from engine.infrastructure.database_manager import (
    DatabaseManager,
    DatabasePaths,
    StorageError,
)
from engine.infrastructure.voice_foundry_repository import (
    VoiceCandidateRecord,
    VoiceCommandAck,
    VoiceEvidenceSnapshot,
    VoiceFoundryCancelled,
    VoiceFoundryConflict,
    VoiceFoundryOperationIntent,
    VoiceFoundryStage,
    VoiceFoundryTaskSpec,
    SQLiteVoiceFoundryRepository,
)
from engine.infrastructure.voice_binding_repository import (
    SQLiteVoiceBindingRepository,
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
async def database(paths):
    db = await open_database(paths)
    try:
        yield db
    finally:
        await db.close()


def scope() -> VoiceBindingScope:
    return VoiceBindingScope(
        owner_id="player",
        world_id="voice-foundry-world",
        worldline_id="line-1",
        presentation_identity="klein-visible",
        phase="narrative",
        locale="zh-CN",
    )


def task_spec(
    *,
    task_id: str = "task-1",
    request_id: str = "request-1",
    request_digest: str = "a" * 64,
) -> VoiceFoundryTaskSpec:
    return VoiceFoundryTaskSpec(
        task_id=task_id,
        request_id=request_id,
        request_digest=request_digest,
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


def candidate() -> VoiceCandidateRecord:
    return VoiceCandidateRecord(
        candidate_id="candidate-1",
        slot=1,
        seed=101,
        state="ready",
        preview_audio_digest="b" * 64,
        recipe={"input": "instruction", "seed": 101},
        recipe_digest="c" * 64,
        provider_candidate_id="voice_design_01",
        provider_candidate_revision="candidate-revision-1",
    )


def evidence() -> VoiceEvidenceSnapshot:
    return VoiceEvidenceSnapshot(
        provider_instance="speechrail-local",
        evidence_id="evidence-1",
        evidence_digest="d" * 64,
        voice_id="voice-klein-01",
        voice_revision="voice-revision-1",
        snapshot={
            "execution": {"model_artifact_revision": "model-revision-1"},
            "human": {"identity_status": "pass"},
        },
    )


async def world_revision(database) -> int:
    return (
        await database.read_world("SELECT revision FROM world_meta WHERE singleton=1")
    )[0]["revision"]


async def test_current_schema_creates_durable_foundry_tables(database, paths):
    rows = await database.read_world(
        "SELECT name FROM sqlite_schema WHERE type='table' AND name LIKE 'voice_%' "
        "ORDER BY name"
    )
    assert {row["name"] for row in rows} >= {
        "voice_binding_revisions",
        "voice_bindings",
        "voice_evidence_snapshots",
        "voice_foundry_candidates",
        "voice_foundry_commands",
        "voice_foundry_operations",
        "voice_foundry_tasks",
    }
    # PRAGMA is not part of the application data plane; the read authorizer
    # deliberately rejects it, so schema-version assertions go through a
    # direct read-only connection rather than widening production privileges.
    with sqlite3.connect(f"file:{paths.world}?mode=ro", uri=True) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 16
        # v16 completes the evidence triple on voice_bindings. The foundry
        # tables above must still exist: a schema bump adds to the world, it
        # never replaces it.
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(voice_bindings)").fetchall()
        }
        assert {
            "evidence_id",
            "evidence_digest",
            "model_artifact_revision",
        } <= columns


async def test_register_is_idempotent_by_request_and_active_scope(database):
    repo = SQLiteVoiceFoundryRepository(database)
    first = await repo.register_task(task_spec())
    replay = await repo.register_task(task_spec())
    assert replay == first
    assert first.stage is VoiceFoundryStage.REQUESTED
    assert first.task_revision == 1

    with pytest.raises(VoiceFoundryConflict):
        await repo.register_task(
            task_spec(request_digest="e" * 64)
        )

    same_active_different_request = await repo.register_task(
        task_spec(task_id="task-2", request_id="request-2")
    )
    assert same_active_different_request == first
    assert await world_revision(database) == 0


async def test_stage_transition_uses_revision_cas_and_cancel_wins_before_ready(database):
    repo = SQLiteVoiceFoundryRepository(database)
    task = await repo.register_task(task_spec())
    previewing = await repo.set_stage(
        task.task_id,
        expected_revision=1,
        stage=VoiceFoundryStage.PREVIEWING,
        operation_status="prepared",
        required_actions=(),
    )
    assert previewing.task_revision == 2

    with pytest.raises(VoiceFoundryConflict):
        await repo.set_stage(
            task.task_id,
            expected_revision=1,
            stage=VoiceFoundryStage.FAILED,
            operation_status="rejected",
            required_actions=(),
            reason_code="stale",
        )

    cancelled = await repo.request_cancel(
        task.task_id, expected_revision=2, reason_code="user_cancelled"
    )
    assert cancelled.cancel_requested is True
    assert cancelled.stage is VoiceFoundryStage.CANCELLED

    with pytest.raises(VoiceFoundryCancelled):
        await repo.commit_ready_binding(
            task.task_id,
            expected_task_revision=3,
            evidence=evidence(),
            binding_id=task.scope.binding_identity,
        )
    assert await world_revision(database) == 0


async def test_candidates_and_operation_intent_survive_restart(database, paths):
    repo = SQLiteVoiceFoundryRepository(database)
    task = await repo.register_task(task_spec())
    await repo.add_candidate(
        task.task_id,
        expected_revision=1,
        candidate=candidate(),
    )
    intent = await repo.record_operation(
        VoiceFoundryOperationIntent(
            operation_id="operation-1",
            task_id=task.task_id,
            stage="preview",
            attempt_identity="attempt-1",
            idempotency_key="preview-key-1",
            payload={"seed": 101},
            payload_digest="f" * 64,
        )
    )
    assert intent.status == "prepared"
    unknown = await repo.mark_operation_unknown(intent.operation_id)
    assert unknown.status == "unknown"
    confirmed = await repo.confirm_operation(
        intent.operation_id,
        expected_status="unknown",
        provider_result_ref="preview-1",
    )
    assert confirmed.status == "confirmed"
    with pytest.raises(VoiceFoundryConflict):
        await repo.confirm_operation(
            intent.operation_id,
            expected_status="prepared",
            provider_result_ref="other",
        )

    await database.close()
    reopened = await open_database(paths)
    try:
        restored_repo = SQLiteVoiceFoundryRepository(reopened)
        assert (await restored_repo.load_task(task.task_id)).task_revision == 2
        assert (await restored_repo.load_candidate(task.task_id, "candidate-1")).seed == 101
        assert (
            await restored_repo.load_operation("operation-1")
        ).provider_result_ref == "preview-1"
    finally:
        await reopened.close()


async def test_command_acceptance_replays_only_identical_payload(database):
    repo = SQLiteVoiceFoundryRepository(database)
    task = await repo.register_task(task_spec())
    first = await repo.accept_command(
        VoiceCommandAck(
            command_id="command-1",
            task_id=task.task_id,
            payload_digest="1" * 64,
            accepted_result={"stage": "awaiting_selection"},
        )
    )
    replay = await repo.accept_command(
        VoiceCommandAck(
            command_id="command-1",
            task_id=task.task_id,
            payload_digest="1" * 64,
            accepted_result={"stage": "awaiting_selection"},
        )
    )
    assert replay == first
    with pytest.raises(VoiceFoundryConflict):
        await repo.accept_command(
            VoiceCommandAck(
                command_id="command-1",
                task_id=task.task_id,
                payload_digest="2" * 64,
                accepted_result={"stage": "ready"},
            )
        )


async def test_an_unseen_command_has_no_receipt(database):
    repo = SQLiteVoiceFoundryRepository(database)
    await repo.register_task(task_spec())
    assert await repo.load_command("command-never-ran") is None


async def test_a_command_receipt_reads_back_what_it_accepted(database):
    """The receipt is what a replayed command answers from.

    If it came back lossy — a tuple where a list was stored, an int turned into
    a float, a nested map flattened — the replay would tell the caller
    something different from what its first attempt was told.
    """
    repo = SQLiteVoiceFoundryRepository(database)
    task = await repo.register_task(task_spec())
    accepted = {
        "stage": "awaiting_review",
        "required_actions": ["listen_reference", "review"],
        "binding_revision": 2,
        "cancelled": False,
        "nested": {"candidate_id": "candidate-1", "slots": [1, 2]},
    }
    written = await repo.accept_command(
        VoiceCommandAck(
            command_id="command-1",
            task_id=task.task_id,
            payload_digest="1" * 64,
            accepted_result=accepted,
        )
    )

    read_back = await repo.load_command("command-1")
    assert read_back == written
    assert read_back.accepted_result == accepted


async def test_a_command_receipt_survives_restart(database, paths):
    """A command id stays spent across a restart.

    Otherwise a client that retried after a crash would look like a first
    attempt, and the supply task would be driven twice for one decision.
    """
    repo = SQLiteVoiceFoundryRepository(database)
    task = await repo.register_task(task_spec())
    await repo.accept_command(
        VoiceCommandAck(
            command_id="command-1",
            task_id=task.task_id,
            payload_digest="1" * 64,
            accepted_result={"stage": "provisioning"},
        )
    )

    await database.close()
    reopened = await open_database(paths)
    try:
        restored = await SQLiteVoiceFoundryRepository(reopened).load_command("command-1")
        assert restored is not None
        assert restored.payload_digest == "1" * 64
        assert restored.accepted_result == {"stage": "provisioning"}
    finally:
        await reopened.close()


async def test_ready_binding_atomically_records_evidence_history_and_task(database):
    repo = SQLiteVoiceFoundryRepository(database)
    task = await repo.register_task(task_spec())
    await repo.set_stage(
        task.task_id,
        expected_revision=1,
        stage=VoiceFoundryStage.PUBLISHED,
        operation_status="confirmed",
        required_actions=(),
    )
    ready = await repo.commit_ready_binding(
        task.task_id,
        expected_task_revision=2,
        evidence=evidence(),
        binding_id=task.scope.binding_identity,
    )
    assert ready.stage is VoiceFoundryStage.READY
    assert ready.task_revision == 3

    history = await repo.load_binding_history(task.scope.binding_identity)
    assert [(item.binding_revision, item.status) for item in history] == [
        (1, "reserved"),
        (2, "active"),
    ]
    assert all(item.evidence_id == "evidence-1" for item in history)
    assert (await repo.load_evidence("speechrail-local", "evidence-1")).voice_revision == (
        "voice-revision-1"
    )
    current = await database.read_world(
        "SELECT binding_revision,status,evidence_id FROM voice_bindings WHERE binding_id=?",
        (task.scope.binding_identity,),
    )
    assert current == [
        {
            "binding_revision": 2,
            "status": "active",
            "evidence_id": "evidence-1",
        }
    ]
    assert await world_revision(database) == 0


async def test_a_binding_id_borrowed_from_another_scope_is_refused(database):
    """The row key and the row's scope have to be the same fact.

    Both uniqueness checks would otherwise pass for a key borrowed from
    somewhere else: the borrowed key is either unused, or it belongs to a
    scope this task is not. The row would satisfy the constraint and still be
    unreachable, because everything that renders a voice looks it up by scope.
    Nothing downstream would report an error — the voice would simply never
    be heard.
    """
    repo = SQLiteVoiceFoundryRepository(database)
    task = await _publish_task(repo)

    with pytest.raises(VoiceFoundryConflict):
        await repo.commit_ready_binding(
            task.task_id,
            expected_task_revision=task.task_revision,
            evidence=evidence(),
            binding_id="vb-0000000000000000",
        )

    assert await database.read_world(
        "SELECT binding_id FROM voice_bindings WHERE binding_id=?",
        ("vb-0000000000000000",),
    ) == []
    assert (await repo.load_task(task.task_id)).stage is VoiceFoundryStage.PUBLISHED
    assert await world_revision(database) == 0


async def test_concurrent_ready_commits_elect_one_history_and_do_not_duplicate_evidence(
    database,
):
    repo = SQLiteVoiceFoundryRepository(database)
    task = await repo.register_task(task_spec())
    await repo.set_stage(
        task.task_id,
        expected_revision=1,
        stage=VoiceFoundryStage.PUBLISHED,
        operation_status="confirmed",
        required_actions=(),
    )
    results = await asyncio.gather(
        *(
            repo.commit_ready_binding(
                task.task_id,
                expected_task_revision=2,
                evidence=evidence(),
                binding_id=task.scope.binding_identity,
            )
            for _ in range(6)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(item, VoiceFoundryConflict) for item in results) == 5
    winners = [item for item in results if not isinstance(item, BaseException)]
    assert len(winners) == 1
    rows = await database.read_world(
        "SELECT count(*) AS n FROM voice_evidence_snapshots"
    )
    assert rows == [{"n": 1}]


async def test_foundry_write_scope_cannot_touch_world_facts_or_delete_history(database):
    repo = SQLiteVoiceFoundryRepository(database)
    task = await repo.register_task(task_spec())
    await repo.add_candidate(
        task.task_id,
        expected_revision=1,
        candidate=candidate(),
    )

    async def unsafe(sql: str):
        def apply(tx):
            tx.execute(sql)

        return await database.voice_foundry_write(apply)

    for sql in (
        "UPDATE world_meta SET revision=99",
        "DELETE FROM voice_foundry_tasks",
        "UPDATE voice_foundry_tasks SET request_digest='" + "0" * 64 + "'",
        "INSERT INTO domain_commits VALUES('forged','',0,'','','','',0)",
    ):
        with pytest.raises(sqlite3.DatabaseError):
            await unsafe(sql)
    assert (await repo.load_task(task.task_id)).task_revision == 2
    assert json.loads(
        (
            await database.read_world(
                "SELECT recipe_json FROM voice_foundry_candidates WHERE candidate_id=?",
                ("candidate-1",),
            )
        )[0]["recipe_json"]
    ) == candidate().recipe
async def _seeded_candidate(repo, task):
    """Register a task and give it one previewed candidate at slot 1."""
    await repo.add_candidate(
        task.task_id,
        expected_revision=task.task_revision,
        candidate=VoiceCandidateRecord(
            candidate_id=f"{task.task_id}:candidate:0",
            slot=1,
            seed=7,
            state="ready",
            preview_audio_digest="a" * 64,
            recipe={"seed": 7},
            recipe_digest="b" * 64,
        ),
    )
    return await repo.load_task(task.task_id)


async def test_candidate_provider_identity_is_attached_once_and_never_swapped(
    database,
):
    """A candidate that already carries a provider identity must never be
    re-pointed at another one; that would be a silent re-cast."""
    repo = SQLiteVoiceFoundryRepository(database)
    task = await repo.register_task(task_spec())
    task = await _seeded_candidate(repo, task)

    # A human picks the candidate before it is provisioned.
    await repo.update_candidate(
        task.task_id,
        expected_revision=task.task_revision,
        candidate_id=f"{task.task_id}:candidate:0",
        state="selected",
    )
    task = await repo.load_task(task.task_id)
    attached = await repo.update_candidate(
        task.task_id,
        expected_revision=task.task_revision,
        candidate_id=f"{task.task_id}:candidate:0",
        state="provisioning",
        provider_candidate_id="vd_" + "a" * 24,
        provider_candidate_revision="vr_" + "b" * 32,
    )
    assert attached.provider_candidate_id == "vd_" + "a" * 24
    assert attached.provider_candidate_revision == "vr_" + "b" * 32
    assert attached.state == "provisioning"

    # Re-sending the identical identity is idempotent...
    task = await repo.load_task(task.task_id)
    again = await repo.update_candidate(
        task.task_id,
        expected_revision=task.task_revision,
        candidate_id=f"{task.task_id}:candidate:0",
        state="validating",
    )
    assert again.provider_candidate_id == "vd_" + "a" * 24
    assert again.state == "validating"

    # ...but pointing the same slot at a different candidate is refused.
    task = await repo.load_task(task.task_id)
    with pytest.raises(VoiceFoundryConflict):
        await repo.update_candidate(
            task.task_id,
            expected_revision=task.task_revision,
            candidate_id=f"{task.task_id}:candidate:0",
            provider_candidate_id="vd_" + "9" * 24,
        )


async def test_candidate_state_must_advance_forward_and_terminal_is_final(database):
    repo = SQLiteVoiceFoundryRepository(database)
    task = await repo.register_task(task_spec())
    task = await _seeded_candidate(repo, task)

    # ready cannot jump straight to published.
    with pytest.raises(VoiceFoundryConflict):
        await repo.update_candidate(
            task.task_id,
            expected_revision=task.task_revision,
            candidate_id=f"{task.task_id}:candidate:0",
            state="published",
        )

    # A failed candidate is terminal; it cannot come back into review.
    task = await repo.load_task(task.task_id)
    await repo.update_candidate(
        task.task_id,
        expected_revision=task.task_revision,
        candidate_id=f"{task.task_id}:candidate:0",
        state="failed",
    )
    task = await repo.load_task(task.task_id)
    with pytest.raises(VoiceFoundryConflict):
        await repo.update_candidate(
            task.task_id,
            expected_revision=task.task_revision,
            candidate_id=f"{task.task_id}:candidate:0",
            state="reviewing",
        )


async def test_candidate_update_is_guarded_by_task_revision(database):
    repo = SQLiteVoiceFoundryRepository(database)
    task = await repo.register_task(task_spec())
    task = await _seeded_candidate(repo, task)

    with pytest.raises(VoiceFoundryConflict):
        await repo.update_candidate(
            task.task_id,
            expected_revision=task.task_revision + 5,
            candidate_id=f"{task.task_id}:candidate:0",
            state="selected",
        )


def _candidate_at(slot: int, candidate_id: str) -> VoiceCandidateRecord:
    return VoiceCandidateRecord(
        candidate_id=candidate_id,
        slot=slot,
        seed=100 + slot,
        state="ready",
        preview_audio_digest="d" * 64,
        recipe={"seed": 100 + slot},
        recipe_digest="e" * 64,
    )


async def test_load_candidates_presents_every_slot_in_slot_order(database):
    """Preview order is provider timing; presentation order is the slot.

    A player comparing candidates must see the same candidate in the same
    place every time, otherwise a selection recorded as "the third one" names a
    different voice on a re-read.
    """
    repo = SQLiteVoiceFoundryRepository(database)
    task = await repo.register_task(task_spec())
    revision = task.task_revision
    # Land the slots out of order, the way concurrent previews would finish.
    for slot in (3, 1, 4, 2):
        task = await repo.add_candidate(
            task.task_id,
            expected_revision=revision,
            candidate=_candidate_at(slot, f"candidate-{slot}"),
        )
        revision = task.task_revision

    loaded = await repo.load_candidates("task-1")
    assert [item.slot for item in loaded] == [1, 2, 3, 4]
    assert [item.candidate_id for item in loaded] == [
        "candidate-1",
        "candidate-2",
        "candidate-3",
        "candidate-4",
    ]


async def test_load_candidates_is_empty_before_any_preview_lands(database):
    repo = SQLiteVoiceFoundryRepository(database)
    await repo.register_task(task_spec())
    assert await repo.load_candidates("task-1") == ()


async def test_load_scope_tasks_keeps_the_history_a_precheck_needs(database):
    """A scope that failed once must not look like a scope never asked.

    Pre-warming reads this list to decide whether an identity still needs
    supply. If abandoned tasks were filtered out, a cancelled or failed task
    would read as "nothing was ever requested" and the scene would queue the
    same work again.
    """
    repo = SQLiteVoiceFoundryRepository(database)
    first = await repo.register_task(task_spec())
    cancelled = await repo.request_cancel(
        first.task_id,
        expected_revision=first.task_revision,
        reason_code="operator_withdrew",
    )
    assert cancelled.stage is VoiceFoundryStage.CANCELLED

    await repo.register_task(
        task_spec(task_id="task-2", request_id="request-2", request_digest="b" * 64)
    )

    listed = await repo.load_scope_tasks(scope())
    assert [item.task_id for item in listed] == ["task-1", "task-2"]
    assert listed[0].stage is VoiceFoundryStage.CANCELLED
    assert listed[1].stage is VoiceFoundryStage.REQUESTED


async def test_load_scope_tasks_is_scoped_to_one_presentation_identity(database):
    repo = SQLiteVoiceFoundryRepository(database)
    await repo.register_task(task_spec())

    other = VoiceBindingScope(
        owner_id="player",
        world_id="voice-foundry-world",
        worldline_id="line-1",
        presentation_identity="amanda-visible",
        phase="narrative",
        locale="zh-CN",
    )
    assert await repo.load_scope_tasks(other) == ()


async def test_load_scope_tasks_refuses_an_untyped_scope(database):
    repo = SQLiteVoiceFoundryRepository(database)
    with pytest.raises(StorageError):
        await repo.load_scope_tasks(
            {
                "owner_id": "player",
                "world_id": "voice-foundry-world",
                "worldline_id": "line-1",
                "presentation_identity": "klein-visible",
                "phase": "narrative",
                "locale": "zh-CN",
            }
        )


async def _publish_task(repo: SQLiteVoiceFoundryRepository):
    task = await repo.register_task(task_spec())
    return await repo.set_stage(
        task.task_id,
        expected_revision=task.task_revision,
        stage=VoiceFoundryStage.PUBLISHED,
        operation_status="confirmed",
        required_actions=(),
    )


async def test_a_committed_binding_is_loadable_and_can_actually_render(database):
    """The whole point of committing a binding is that it can be used.

    Its review is an all-or-nothing triple. Writing only the evidence id and
    digest produced a row that raised the moment the engine read it back, so a
    published voice was stranded before anyone heard it — the task said ready
    and the binding was unreadable.
    """
    repo = SQLiteVoiceFoundryRepository(database)
    task = await _publish_task(repo)

    ready = await repo.commit_ready_binding(
        task.task_id,
        expected_task_revision=task.task_revision,
        evidence=evidence(),
        binding_id=task.scope.binding_identity,
    )
    assert ready.stage is VoiceFoundryStage.READY

    bound = await SQLiteVoiceBindingRepository(database).load(
        task.scope.binding_identity
    )
    assert bound.status is VoiceBindingStatus.ACTIVE
    assert bound.permits_new_render
    assert bound.evidence is not None
    assert bound.evidence.evidence_id == "evidence-1"
    assert bound.evidence.model_artifact_revision == "model-revision-1"
    assert bound.persona.revision == "persona-1"
    assert await world_revision(database) == 0


async def test_evidence_without_an_artifact_revision_never_becomes_a_binding(database):
    """Refused at commit, so there is no half-reviewed row to find later."""
    repo = SQLiteVoiceFoundryRepository(database)
    task = await _publish_task(repo)
    incomplete = replace(
        evidence(), snapshot={"execution": {"model_id": "qwen3-tts"}}
    )

    with pytest.raises(StorageError):
        await repo.commit_ready_binding(
            task.task_id,
            expected_task_revision=task.task_revision,
            evidence=incomplete,
            binding_id=task.scope.binding_identity,
        )

    assert await database.read_world(
        "SELECT binding_id FROM voice_bindings WHERE binding_id=?",
        (task.scope.binding_identity,),
    ) == []
    assert (await repo.load_task(task.task_id)).stage is VoiceFoundryStage.PUBLISHED
    assert await world_revision(database) == 0


async def test_load_tasks_page_walks_the_whole_list_without_repeating_or_gapping(
    database,
):
    repo = SQLiteVoiceFoundryRepository(database)
    for index in range(5):
        await repo.register_task(
            task_spec(
                task_id=f"task-{index}",
                request_id=f"request-{index}",
                request_digest=f"{index}" * 64,
            )
        )

    first = await repo.load_tasks_page(page_size=2)
    second = await repo.load_tasks_page(
        page_size=2,
        after_created_at=first[-1].created_at,
        after_task_id=first[-1].task_id,
    )
    third = await repo.load_tasks_page(
        page_size=2,
        after_created_at=second[-1].created_at,
        after_task_id=second[-1].task_id,
    )

    walked = [*first, *second, *third]
    assert [item.task_id for item in walked] == [
        "task-0",
        "task-1",
        "task-2",
        "task-3",
        "task-4",
    ]


async def test_a_task_registered_mid_walk_does_not_disturb_the_page_being_read(
    database,
):
    """A keyset page is anchored on the last row, not on an offset.

    An offset would shift every later row by one the moment a new task landed,
    so a caller paging through supply would silently skip a task. Anchoring on
    ``(created_at, task_id)`` means the window only ever moves forward.
    """
    repo = SQLiteVoiceFoundryRepository(database)
    await repo.register_task(task_spec())
    await repo.register_task(
        task_spec(task_id="task-2", request_id="request-2", request_digest="b" * 64)
    )
    first = await repo.load_tasks_page(page_size=1)

    # A pre-warm registers a third identity while the caller is still paging.
    await repo.register_task(
        task_spec(task_id="task-3", request_id="request-3", request_digest="c" * 64)
    )

    second = await repo.load_tasks_page(
        page_size=5,
        after_created_at=first[-1].created_at,
        after_task_id=first[-1].task_id,
    )
    assert "task-1" not in [item.task_id for item in second]
    assert second[0].task_id == "task-2"


async def test_load_tasks_page_filters_by_stage(database):
    repo = SQLiteVoiceFoundryRepository(database)
    first = await repo.register_task(task_spec())
    await repo.request_cancel(
        first.task_id, expected_revision=first.task_revision, reason_code="withdrew"
    )
    await repo.register_task(
        task_spec(task_id="task-2", request_id="request-2", request_digest="b" * 64)
    )

    cancelled = await repo.load_tasks_page(page_size=10, stage="cancelled")
    live = await repo.load_tasks_page(page_size=10, stage="requested")

    assert [item.task_id for item in cancelled] == ["task-1"]
    assert [item.task_id for item in live] == ["task-2"]


@pytest.mark.parametrize("page_size", [0, 101, -1, True, "10"])
async def test_load_tasks_page_refuses_a_page_size_it_cannot_serve(database, page_size):
    repo = SQLiteVoiceFoundryRepository(database)
    with pytest.raises(StorageError):
        await repo.load_tasks_page(page_size=page_size)


async def test_load_tasks_page_covers_every_task_whatever_the_stage(database):
    """The list is a status board, not a work queue.

    A caller reading supply state must see the tasks that were withdrawn and
    failed too; filtering them out is what makes a scope that failed once look
    like a scope that was never asked.
    """
    repo = SQLiteVoiceFoundryRepository(database)
    await repo.register_task(task_spec())
    second = await repo.register_task(
        task_spec(task_id="task-2", request_id="request-2", request_digest="b" * 64)
    )
    await repo.request_cancel(
        second.task_id, expected_revision=second.task_revision, reason_code="withdrew"
    )

    listed = await repo.load_tasks_page(page_size=10)
    assert {item.stage for item in listed} == {
        VoiceFoundryStage.REQUESTED,
        VoiceFoundryStage.CANCELLED,
    }
