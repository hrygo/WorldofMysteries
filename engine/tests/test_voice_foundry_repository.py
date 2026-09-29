"""Voice Foundry durable presentation-task persistence (VF-02)."""

from __future__ import annotations

import asyncio
import json
import sqlite3

import pytest
import pytest_asyncio

from domain.voice_identity import VoiceBindingScope
from engine.infrastructure.database_manager import DatabaseManager, DatabasePaths
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
            binding_id="binding-1",
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
        binding_id="binding-1",
    )
    assert ready.stage is VoiceFoundryStage.READY
    assert ready.task_revision == 3

    history = await repo.load_binding_history("binding-1")
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
        ("binding-1",),
    )
    assert current == [
        {
            "binding_revision": 2,
            "status": "active",
            "evidence_id": "evidence-1",
        }
    ]
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
                binding_id=f"binding-{index}",
            )
            for index in range(6)
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
