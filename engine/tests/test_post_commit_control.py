"""Public post-COMMIT work projection and explicit-retry boundary tests."""
from __future__ import annotations

from pathlib import Path
import sqlite3 as stdlib_sqlite3

import pytest

from application.speech_unit import SealedSpeechUnit
from application.story_expression import (
    StoryExpressionError,
    StoryExpressionResponse,
    StoryExpressionSegment,
)
from infrastructure.audio.sealed_unit_codec import SealedSpeechUnitCodec
from infrastructure.audio.voice_runtime import SealedSpeechUnitRegistry
from infrastructure.database_manager import DatabaseManager, DatabasePaths
from infrastructure.post_commit_control import (
    AUDIO_NOT_SCHEDULED,
    HANDOFF_EXPIRED,
    HANDOFF_UNVERIFIED,
    NARRATIVE_ARTIFACT_UNAVAILABLE,
    PostCommitControlError,
    PostCommitControlService,
)
from infrastructure.post_commit_job_repository import (
    SQLitePostCommitJobRepository,
)
from infrastructure.sqlite_runtime import sqlite3

CODEC = SealedSpeechUnitCodec()


# --------------------------------------------------------------- fixtures


async def _open_database(tmp_path: Path) -> DatabaseManager:
    paths = DatabasePaths.for_world(tmp_path / "app-support", "post-commit-control")
    paths.canon.parent.mkdir(parents=True, exist_ok=True)
    with stdlib_sqlite3.connect(paths.canon) as canon:
        canon.execute("CREATE TABLE canon_fixture(id TEXT PRIMARY KEY) STRICT")
    return await DatabaseManager.open(
        paths, expected_sqlite_version=sqlite3.sqlite_version
    )


def _seed_turn(connection, *, turn_id: str = "turn-1", session_id: str = "session-1"):
    """Insert the committed turn plus its delta, as registration requires."""
    connection.execute("BEGIN IMMEDIATE")
    if connection.execute(
        "SELECT 1 FROM domain_commits WHERE revision=1"
    ).fetchone() is None:
        connection.execute(
            "INSERT INTO domain_commits("
            "revision,worldline_id,idempotency_key,request_digest,request_id,trace_id,"
            "world_time,commit_time,operation_json,result_json"
            ") VALUES (1,'line-test','idem','digest','request','trace',"
            "'1349-01-01T00:00:00Z','2026-09-28T00:00:00Z','{}','{}')"
        )
        connection.execute(
            "INSERT INTO projection_outbox(revision,processed) VALUES (1,0)"
        )
        connection.execute("UPDATE world_meta SET revision=1 WHERE singleton=1")
        connection.execute(
            "INSERT INTO story_sessions("
            "id,world_id,worldline_id,protagonist_id,story_seed_id,"
            "base_world_revision,base_character_revision,base_story_revision,"
            "story_revision,status,story_state_json,committed_world_revision"
            f") VALUES ('{session_id}','world-test','line-test','player-test','seed-test',"
            "0,0,0,1,'active','{}',1)"
        )
    if connection.execute(
        "SELECT 1 FROM turn_transactions WHERE id=?", (turn_id,)
    ).fetchone() is None:
        connection.execute(
            "INSERT INTO story_state_deltas("
            "id,session_id,turn_id,story_revision,payload_json,committed_world_revision"
            ") VALUES (?,?,?,1,'{}',1)",
            (f"delta-{turn_id}", session_id, turn_id),
        )
        connection.execute(
            "INSERT INTO turn_transactions("
            "id,session_id,idempotency_key,status,base_world_revision,"
            "base_character_revision,base_story_revision,state_delta_id,"
            "committed_story_revision,transaction_json,committed_world_revision"
            ") VALUES (?,?,?,'committed',0,0,0,?,1,'{}',1)",
            (turn_id, session_id, f"idem-{turn_id}", f"delta-{turn_id}"),
        )
    connection.execute("COMMIT")


def _insert_job(tx, *, job_id: str, kind: str, state: str, reason=None, turn="turn-1"):
    tx.execute(
        "INSERT INTO post_commit_jobs("
        "job_id,turn_id,session_id,kind,recipe_revision,source_story_revision,"
        "source_world_revision,input_digest,state,attempt,lease_owner,"
        "lease_generation,next_attempt_at,last_error_code,result_ref"
        ") VALUES (?,?,'session-1',?,'recipe-v1',1,1,?,?,0,NULL,0,NULL,?,NULL)",
        (job_id, turn, kind, "sha256:" + "e" * 64, state, reason),
    )


async def _seed_jobs(database: DatabaseManager, *rows) -> None:
    await database._submit(lambda: _seed_turn(database._connection))

    def insert(tx):
        for row in rows:
            _insert_job(tx, **row)

    await database.post_commit_job_write(insert)


async def _store_sealed_result(
    database: DatabaseManager,
    job_id: str,
    unit: SealedSpeechUnit,
    *,
    digest: str | None = None,
) -> None:
    payload_json, encoded_digest = CODEC.encode(unit)

    def insert(tx):
        tx.execute(
            "INSERT INTO post_commit_job_results("
            "job_id,format_version,payload_json,payload_digest"
            ") VALUES (?,?,?,?)",
            (
                job_id,
                CODEC.format_version,
                payload_json,
                digest if digest is not None else encoded_digest,
            ),
        )

    await database.post_commit_job_write(insert)


def sealed_unit(*, unit_id: str = "speech_" + "a" * 32) -> SealedSpeechUnit:
    from application.speech_unit import (
        DesiredPerformance,
        EffectiveBackendPerformance,
        EffectivePlaybackPerformance,
    )

    return SealedSpeechUnit(
        unit_id=unit_id,
        turn_id="turn-1",
        story_session_id="session-1",
        story_revision=7,
        narrative_block_id="narrative-1",
        segment_index=0,
        presentation_identity="klein-visible",
        binding_id="binding-1",
        binding_revision=2,
        logical_voice_id="voice-klein",
        persona_revision="persona-r1",
        provider_instance="speechrail-local",
        voice_id="klein-approved",
        voice_revision="voice-" + "b" * 40,
        model_id="speechrail/qwen3-tts",
        model_revision="c" * 40,
        evidence_id="ev_postcommit_1",
        evidence_digest="d" * 64,
        model_artifact_revision="artifact-" + "e" * 24,
        language="zh-CN",
        performance_plan_id="perf_" + "d" * 24,
        display_text="克莱恩没有开门。",
        spoken_text="克莱恩没有开门。",
        pronunciation_revision="pron-v1",
        pronunciation_mappings=(),
        desired=DesiredPerformance(),
        backend=EffectiveBackendPerformance(speed=1.0),
        playback=EffectivePlaybackPerformance(volume="normal", pause_before_ms=0),
        unsupported=(),
        degradation=(),
    )


class FakeExpression:
    """Minimal stand-in for the AO-01 disclosed-narrative reader."""

    def __init__(self, response=None, *, error: str | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[tuple[str, str]] = []

    async def get(self, *, session_id: str, turn_id: str) -> StoryExpressionResponse:
        self.calls.append((session_id, turn_id))
        if self._error is not None:
            raise StoryExpressionError(self._error)
        if self._response is None:
            return StoryExpressionResponse(
                session_id=session_id,
                turn_id=turn_id,
                narrative_state="pending",
                segments=[],
            )
        return self._response


def _segment() -> StoryExpressionSegment:
    return StoryExpressionSegment(
        type="character",
        speaker_display_name="克莱恩",
        text="克莱恩没有开门。",
    )


def _service(database, expression, registry=None):
    return PostCommitControlService(
        database=database,
        jobs=SQLitePostCommitJobRepository(database),
        expression=expression,
        # SealedSpeechUnitRegistry defines __len__, so an empty registry is
        # falsy; `registry or ...` would silently discard the injected instance.
        registry=(
            registry
            if registry is not None
            else SealedSpeechUnitRegistry(ttl_seconds=60.0)
        ),
    )


# ------------------------------------------------------------------ tests


@pytest.mark.asyncio
async def test_work_get_refuses_a_turn_owned_by_another_session(tmp_path):
    database = await _open_database(tmp_path)
    await database._submit(lambda: _seed_turn(database._connection, turn_id="turn-x"))
    service = _service(database, FakeExpression())

    with pytest.raises(PostCommitControlError) as refusal:
        await service.get_work(session_id="session-other", turn_id="turn-x")
    assert refusal.value.code == "turn_session_mismatch"


@pytest.mark.asyncio
async def test_work_get_projects_three_independent_states_when_nothing_ran(tmp_path):
    database = await _open_database(tmp_path)
    await _seed_jobs(
        database,
        {"job_id": "n1", "kind": "narrative_publish", "state": "pending"},
        {"job_id": "a1", "kind": "audio_prepare", "state": "blocked",
         "reason": "voice_not_configured"},
    )
    service = _service(database, FakeExpression())

    view = await service.get_work(session_id="session-1", turn_id="turn-1")
    payload = view.to_payload()

    assert payload["settlement_state"] == "not_required"
    assert "settlement_reason" not in payload
    assert payload["narrative_state"] == "pending"
    assert payload["narrative_segments"] == []
    assert "narrative_reason" not in payload
    assert payload["audio_state"] == "unavailable"
    assert payload["audio_reason"] == "work_unavailable"
    assert "delivery" not in payload
    assert "narrative_block_id" not in payload


@pytest.mark.asyncio
async def test_work_get_reports_ready_narrative_from_disclosed_segments(tmp_path):
    database = await _open_database(tmp_path)
    await _seed_jobs(
        database,
        {"job_id": "n1", "kind": "narrative_publish", "state": "succeeded"},
    )
    expression = FakeExpression(
        StoryExpressionResponse(
            session_id="session-1",
            turn_id="turn-1",
            narrative_state="ready",
            segments=[_segment()],
        )
    )
    service = _service(database, expression)

    payload = (await service.get_work(
        session_id="session-1", turn_id="turn-1"
    )).to_payload()

    assert payload["narrative_state"] == "ready"
    assert len(payload["narrative_segments"]) == 1
    assert "narrative_reason" not in payload


@pytest.mark.asyncio
async def test_work_get_never_reports_ready_narrative_without_segments(tmp_path):
    database = await _open_database(tmp_path)
    await _seed_jobs(
        database,
        {"job_id": "n1", "kind": "narrative_publish", "state": "succeeded"},
    )
    service = _service(database, FakeExpression())

    payload = (await service.get_work(
        session_id="session-1", turn_id="turn-1"
    )).to_payload()

    assert payload["narrative_state"] == "blocked"
    assert payload["narrative_segments"] == []
    assert payload["narrative_reason"] == NARRATIVE_ARTIFACT_UNAVAILABLE


@pytest.mark.asyncio
async def test_work_get_reports_audio_ready_only_with_a_live_handoff_unit(tmp_path):
    database = await _open_database(tmp_path)
    await _seed_jobs(
        database,
        {"job_id": "a1", "kind": "audio_prepare", "state": "succeeded"},
    )
    unit = sealed_unit()
    await _store_sealed_result(database, "a1", unit)
    registry = SealedSpeechUnitRegistry(ttl_seconds=60.0)
    registry.publish(unit)
    service = _service(database, FakeExpression(), registry)

    payload = (await service.get_work(
        session_id="session-1", turn_id="turn-1"
    )).to_payload()

    assert payload["audio_state"] == "ready"
    assert "audio_reason" not in payload
    delivery = payload["delivery"]
    assert delivery["state"] == "ready"
    assert delivery["speech_unit_id"] == unit.unit_id
    assert delivery["render_recipe"]["expected_voice_revision"] == unit.voice_revision
    assert delivery["render_recipe"]["spoken_text"] == unit.spoken_text


@pytest.mark.asyncio
async def test_work_get_reports_handoff_expired_once_the_registry_entry_is_gone(tmp_path):
    database = await _open_database(tmp_path)
    await _seed_jobs(
        database,
        {"job_id": "a1", "kind": "audio_prepare", "state": "succeeded"},
    )
    await _store_sealed_result(database, "a1", sealed_unit())
    service = _service(database, FakeExpression(), SealedSpeechUnitRegistry())

    payload = (await service.get_work(
        session_id="session-1", turn_id="turn-1"
    )).to_payload()

    assert payload["audio_state"] == "unavailable"
    assert payload["audio_reason"] == HANDOFF_EXPIRED
    assert "delivery" not in payload


@pytest.mark.asyncio
async def test_work_get_reports_handoff_expired_after_the_unit_is_consumed(tmp_path):
    database = await _open_database(tmp_path)
    await _seed_jobs(
        database,
        {"job_id": "a1", "kind": "audio_prepare", "state": "succeeded"},
    )
    unit = sealed_unit()
    await _store_sealed_result(database, "a1", unit)
    registry = SealedSpeechUnitRegistry(ttl_seconds=60.0)
    registry.publish(unit)
    service = _service(database, FakeExpression(), registry)
    registry.consume(unit.unit_id)

    payload = (await service.get_work(
        session_id="session-1", turn_id="turn-1"
    )).to_payload()

    assert payload["audio_state"] == "unavailable"
    assert payload["audio_reason"] == HANDOFF_EXPIRED


@pytest.mark.asyncio
async def test_work_get_does_not_trust_a_corrupt_sealed_result(tmp_path):
    database = await _open_database(tmp_path)
    await _seed_jobs(
        database,
        {"job_id": "a1", "kind": "audio_prepare", "state": "succeeded"},
    )
    unit = sealed_unit()
    await _store_sealed_result(database, "a1", unit, digest="0" * 64)
    registry = SealedSpeechUnitRegistry(ttl_seconds=60.0)
    registry.publish(unit)
    service = _service(database, FakeExpression(), registry)

    payload = (await service.get_work(
        session_id="session-1", turn_id="turn-1"
    )).to_payload()
    assert payload["audio_state"] == "unavailable"
    assert payload["audio_reason"] == HANDOFF_UNVERIFIED
    assert "delivery" not in payload


@pytest.mark.asyncio
async def test_work_get_is_a_pure_read_of_durable_state(tmp_path):
    database = await _open_database(tmp_path)
    await _seed_jobs(
        database,
        {"job_id": "n1", "kind": "narrative_publish", "state": "succeeded"},
        {"job_id": "a1", "kind": "audio_prepare", "state": "succeeded"},
    )
    unit = sealed_unit()
    await _store_sealed_result(database, "a1", unit)
    registry = SealedSpeechUnitRegistry(ttl_seconds=60.0)
    service = _service(database, FakeExpression(), registry)

    def snapshot():
        return database._connection.execute(
            "SELECT job_id,state,attempt,lease_owner,lease_generation,"
            "last_error_code,result_ref FROM post_commit_jobs ORDER BY job_id"
        ).fetchall()

    before = await database._submit(snapshot)
    await service.get_work(session_id="session-1", turn_id="turn-1")
    await service.get_work(session_id="session-1", turn_id="turn-1")
    assert await database._submit(snapshot) == before
    # A pure read never publishes a handoff and never seals audio.
    assert len(registry) == 0


@pytest.mark.asyncio
async def test_work_get_reports_missing_audio_schedule_distinctly(tmp_path):
    database = await _open_database(tmp_path)
    await _seed_jobs(
        database,
        {"job_id": "n1", "kind": "narrative_publish", "state": "pending"},
    )
    service = _service(database, FakeExpression())

    payload = (await service.get_work(
        session_id="session-1", turn_id="turn-1"
    )).to_payload()

    assert payload["audio_state"] == "unavailable"
    assert payload["audio_reason"] == AUDIO_NOT_SCHEDULED


# ------------------------------------------------------------------ retry


@pytest.mark.asyncio
async def test_retry_rearms_a_blocked_job_and_replays_idempotently(tmp_path):
    database = await _open_database(tmp_path)
    await _seed_jobs(
        database,
        {"job_id": "a1", "kind": "audio_prepare", "state": "blocked",
         "reason": "voice_not_configured"},
    )
    service = _service(database, FakeExpression())

    first = await service.retry_work(
        session_id="session-1",
        turn_id="turn-1",
        kind="audio_prepare",
        retry_request_id="retry-1",
    )
    second = await service.retry_work(
        session_id="session-1",
        turn_id="turn-1",
        kind="audio_prepare",
        retry_request_id="retry-1",
    )

    assert first.accepted is True and first.replayed is False
    assert second.accepted is True and second.replayed is True
    rows = await database.read_world(
        "SELECT state FROM post_commit_jobs WHERE job_id='a1'"
    )
    assert rows[0]["state"] == "pending"


@pytest.mark.asyncio
async def test_retry_request_id_cannot_be_rebound_to_another_job(tmp_path):
    database = await _open_database(tmp_path)
    await _seed_jobs(
        database,
        {"job_id": "a1", "kind": "audio_prepare", "state": "blocked",
         "reason": "voice_not_configured"},
        {"job_id": "n1", "kind": "narrative_publish", "state": "blocked",
         "reason": "narrative_failed"},
    )
    service = _service(database, FakeExpression())
    await service.retry_work(
        session_id="session-1",
        turn_id="turn-1",
        kind="audio_prepare",
        retry_request_id="retry-shared",
    )

    with pytest.raises(PostCommitControlError) as refusal:
        await service.retry_work(
            session_id="session-1",
            turn_id="turn-1",
            kind="narrative_publish",
            retry_request_id="retry-shared",
        )
    assert refusal.value.code == "work_retry_conflict"


@pytest.mark.asyncio
async def test_retry_rebuilds_an_expired_handoff_without_resealing(tmp_path):
    database = await _open_database(tmp_path)
    await _seed_jobs(
        database,
        {"job_id": "a1", "kind": "audio_prepare", "state": "succeeded"},
    )
    unit = sealed_unit()
    await _store_sealed_result(database, "a1", unit)
    registry = SealedSpeechUnitRegistry(ttl_seconds=60.0)
    service = _service(database, FakeExpression(), registry)

    first = await service.retry_work(
        session_id="session-1",
        turn_id="turn-1",
        kind="audio_prepare",
        retry_request_id="replay-1",
    )
    assert first.accepted is True and first.replayed is False
    assert registry.peek(unit.unit_id) == unit

    # Replaying the same request must not produce a second sealed unit.
    second = await service.retry_work(
        session_id="session-1",
        turn_id="turn-1",
        kind="audio_prepare",
        retry_request_id="replay-1",
    )
    assert second.replayed is True
    assert len(registry) == 1
    assert registry.peek(unit.unit_id) == unit

    # The durable sealed result is untouched by a handoff rebuild.
    rows = await database.read_world(
        "SELECT job_id,payload_digest FROM post_commit_job_results"
    )
    assert [row["job_id"] for row in rows] == ["a1"]


@pytest.mark.asyncio
async def test_retry_cannot_reset_other_succeeded_work(tmp_path):
    database = await _open_database(tmp_path)
    await _seed_jobs(
        database,
        {"job_id": "n1", "kind": "narrative_publish", "state": "succeeded"},
    )
    service = _service(database, FakeExpression())

    with pytest.raises(PostCommitControlError) as refusal:
        await service.retry_work(
            session_id="session-1",
            turn_id="turn-1",
            kind="narrative_publish",
            retry_request_id="retry-narrative",
        )
    assert refusal.value.code == "work_not_eligible"
    rows = await database.read_world(
        "SELECT state FROM post_commit_jobs WHERE job_id='n1'"
    )
    assert rows[0]["state"] == "succeeded"


@pytest.mark.asyncio
async def test_retry_refuses_unknown_kind_and_unknown_work(tmp_path):
    database = await _open_database(tmp_path)
    await _seed_jobs(
        database,
        {"job_id": "n1", "kind": "narrative_publish", "state": "blocked",
         "reason": "narrative_failed"},
    )
    service = _service(database, FakeExpression())

    with pytest.raises(PostCommitControlError) as bad_kind:
        await service.retry_work(
            session_id="session-1",
            turn_id="turn-1",
            kind="audio_render",
            retry_request_id="retry-x",
        )
    assert bad_kind.value.code == "invalid_work_kind"

    with pytest.raises(PostCommitControlError) as missing:
        await service.retry_work(
            session_id="session-1",
            turn_id="turn-1",
            kind="episode_finalize",
            retry_request_id="retry-y",
        )
    assert missing.value.code == "work_not_found"
