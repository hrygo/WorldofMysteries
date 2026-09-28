"""Pure post-COMMIT work types, dependency rules, and retry policy tests."""
from __future__ import annotations

import inspect
import json
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import get_type_hints

import pytest

from application.post_commit_work import (
    AudioState,
    NarrativeState,
    PostCommitErrorKind,
    PostCommitJob,
    PostCommitJobState,
    PostCommitKind,
    PostCommitLifecycleAction,
    PostCommitResult,
    PostCommitResultState,
    SettlementState,
    decide_automatic_retry,
    required_jobs_for_turn,
    world_revision_increment_for_operation,
)


def _job(**overrides: object) -> PostCommitJob:
    values: dict[str, object] = {
        "job_id": "job-turn-1-narrative",
        "turn_id": "turn-1",
        "session_id": "session-1",
        "kind": PostCommitKind.NARRATIVE_PUBLISH,
        "recipe_revision": "narrative-v1",
        "source_story_revision": 1,
        "source_world_revision": 8,
        "input_digest": "a" * 64,
        "state": PostCommitJobState.PENDING,
        "attempt": 0,
        "lease_owner": None,
        "lease_generation": 0,
        "next_attempt_at": None,
        "last_error_code": None,
        "result_ref": None,
    }
    values.update(overrides)
    return PostCommitJob(**values)  # type: ignore[arg-type]


def test_public_projection_enums_match_wire_schema_exactly() -> None:
    schema_path = (
        Path(__file__).parents[2]
        / "contracts"
        / "protocol"
        / "story_post_commit_control.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    definitions = schema["$defs"]

    assert [state.value for state in SettlementState] == definitions[
        "settlement_state"
    ]["enum"]
    assert [state.value for state in NarrativeState] == definitions[
        "narrative_state"
    ]["enum"]
    assert [state.value for state in AudioState] == definitions["audio_state"]["enum"]
    assert [kind.value for kind in PostCommitKind] == definitions["work_kind"]["enum"]


def test_source_fields_are_frozen_and_schedule_changes_return_a_new_job() -> None:
    original = _job()

    with pytest.raises(FrozenInstanceError):
        original.turn_id = "another-turn"  # type: ignore[misc]

    scheduled = original.with_schedule(
        state=PostCommitJobState.RETRY_WAIT,
        attempt=1,
        lease_owner="engine-worker",
        lease_generation=4,
        next_attempt_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        last_error_code="provider_timeout",
        result_ref=None,
    )

    assert scheduled is not original
    assert scheduled.turn_id == original.turn_id
    assert scheduled.session_id == original.session_id
    assert scheduled.kind is original.kind
    assert scheduled.recipe_revision == original.recipe_revision
    assert scheduled.source_story_revision == original.source_story_revision
    assert scheduled.source_world_revision == original.source_world_revision
    assert scheduled.input_digest == original.input_digest
    assert scheduled.job_id == original.job_id
    assert scheduled.state is PostCommitJobState.RETRY_WAIT
    assert scheduled.lease_generation == 4
    assert original.state is PostCommitJobState.PENDING
    assert "lease_generation" in {field.name for field in fields(PostCommitJob)}


@pytest.mark.parametrize(
    "overrides",
    [
        {"input_digest": ""},
        {"input_digest": "a" * 65},
        {"input_digest": "not-a-sha256-digest"},
        {"lease_owner": "Bearer sk-secret-token"},
        {"recipe_revision": "https://user:password@example.invalid/recipe"},
        {"job_id": "api_key=sk-secret-token"},
    ],
)
def test_job_rejects_invalid_digest_and_credential_like_values(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        _job(**overrides)


def test_job_shape_cannot_store_prompt_or_snapshot_payloads() -> None:
    assert {field.name for field in fields(PostCommitJob)} == {
        "job_id",
        "turn_id",
        "session_id",
        "kind",
        "recipe_revision",
        "source_story_revision",
        "source_world_revision",
        "input_digest",
        "state",
        "attempt",
        "lease_owner",
        "lease_generation",
        "next_attempt_at",
        "last_error_code",
        "result_ref",
    }


@pytest.mark.parametrize(
    ("turn_number", "voice_configured"),
    [(turn, voice) for turn in range(1, 6) for voice in (True, False)],
)
def test_required_jobs_have_independent_initial_states_and_narrative_dependency(
    turn_number: int,
    voice_configured: bool,
) -> None:
    jobs = required_jobs_for_turn(
        turn_number,
        5,
        voice_configured=voice_configured,
    )

    states = {job.kind: job.initial_state for job in jobs}
    assert states[PostCommitKind.NARRATIVE_PUBLISH] is PostCommitJobState.PENDING
    assert states[PostCommitKind.AUDIO_PREPARE] is (
        PostCommitJobState.PENDING
        if voice_configured
        else PostCommitJobState.BLOCKED
    )
    assert (PostCommitKind.EPISODE_FINALIZE in states) is (turn_number == 5)
    audio_job = next(
        job for job in jobs if job.kind is PostCommitKind.AUDIO_PREPARE
    )
    assert audio_job.depends_on == (PostCommitKind.NARRATIVE_PUBLISH,)
    assert audio_job.initial_reason_code == (
        None if voice_configured else "voice_not_configured"
    )
    if turn_number == 5:
        assert next(
            job.initial_state
            for job in jobs
            if job.kind is PostCommitKind.EPISODE_FINALIZE
        ) is PostCommitJobState.PENDING


@pytest.mark.parametrize(
    ("attempt", "error_kind", "expected"),
    [
        (0, PostCommitErrorKind.TEMPORARY_NETWORK, (PostCommitJobState.RETRY_WAIT, 1)),
        (1, PostCommitErrorKind.TIMEOUT, (PostCommitJobState.RETRY_WAIT, 5)),
        (2, PostCommitErrorKind.TEMPORARY_NETWORK, (PostCommitJobState.RETRY_WAIT, 30)),
        (3, PostCommitErrorKind.TIMEOUT, (PostCommitJobState.BLOCKED, None)),
        (0, PostCommitErrorKind.CONFIGURATION, (PostCommitJobState.BLOCKED, None)),
        (0, PostCommitErrorKind.PERMISSION, (PostCommitJobState.BLOCKED, None)),
        (0, PostCommitErrorKind.IDENTITY, (PostCommitJobState.BLOCKED, None)),
        (3, PostCommitErrorKind.PERMISSION, (PostCommitJobState.BLOCKED, None)),
    ],
)
def test_automatic_retry_policy_uses_bounded_delays_and_blocks_permanent_errors(
    attempt: int,
    error_kind: PostCommitErrorKind,
    expected: tuple[PostCommitJobState, int | None],
) -> None:
    assert decide_automatic_retry(attempt, error_kind) == expected


def test_post_commit_result_exposes_only_public_artifact_and_reason() -> None:
    succeeded = PostCommitResult(
        state=PostCommitResultState.SUCCEEDED,
        result_ref="narrative:turn-1",
    )
    blocked = PostCommitResult(
        state=PostCommitResultState.BLOCKED,
        reason_code="voice_provider_unavailable",
    )

    assert succeeded.result_ref == "narrative:turn-1"
    assert blocked.reason_code == "voice_provider_unavailable"
    assert not {
        "lease_owner",
        "lease_generation",
        "owner",
        "exception",
    } & {field.name for field in fields(PostCommitResult)}
    with pytest.raises(ValueError):
        PostCommitResult(
            state=PostCommitResultState.BLOCKED,
            reason_code="provider failed with private traceback",
        )


def test_handler_port_outputs_do_not_expose_store_lease_identity() -> None:
    from application.post_commit_work import (
        AudioPrepareHandler,
        EpisodeFinalizeHandler,
        NarrativePublishHandler,
    )

    for handler in (
        AudioPrepareHandler,
        EpisodeFinalizeHandler,
        NarrativePublishHandler,
    ):
        execute = inspect.signature(handler.execute)
        assert get_type_hints(handler.execute)["return"] is PostCommitResult
        assert "lease" not in str(execute.return_annotation).lower()
        assert "generation" not in str(execute.return_annotation).lower()


@pytest.mark.parametrize(
    ("kind", "succeeded", "expected_increment"),
    [
        (PostCommitLifecycleAction.CLAIM, True, 0),
        (PostCommitLifecycleAction.RETRY, True, 0),
        (PostCommitLifecycleAction.ACK, True, 0),
        (PostCommitKind.NARRATIVE_PUBLISH, True, 0),
        (PostCommitKind.AUDIO_PREPARE, True, 0),
        (PostCommitKind.EPISODE_FINALIZE, False, 0),
        (PostCommitKind.EPISODE_FINALIZE, True, 1),
    ],
)
def test_only_successful_episode_finalization_advances_world_revision(
    kind: PostCommitKind | PostCommitLifecycleAction,
    succeeded: bool,
    expected_increment: int,
) -> None:
    assert (
        world_revision_increment_for_operation(kind, succeeded=succeeded)
        == expected_increment
    )


def test_required_jobs_reject_turns_outside_the_episode_range() -> None:
    with pytest.raises(ValueError):
        required_jobs_for_turn(0, 5, voice_configured=True)

    with pytest.raises(ValueError):
        required_jobs_for_turn(6, 5, voice_configured=True)


def test_retry_policy_rejects_negative_retry_count() -> None:
    with pytest.raises(ValueError):
        decide_automatic_retry(-1, PostCommitErrorKind.TIMEOUT)


def test_module_does_not_export_an_unimplemented_store_protocol() -> None:
    """AO-03: the application layer must not advertise a store port nobody implements.

    ``PostCommitJobStore`` was an orphan design sketch. Nothing implemented it,
    nothing consumed it, and its method names (``register_in_commit`` /
    ``claim_next`` / ``acknowledge_success`` / ``acknowledge_failure``) never
    matched the one real boundary, ``SQLitePostCommitJobRepository``
    (``register`` / ``claim`` / ``complete`` / ``fail``). Exporting both
    spellings made the architecture look like it had a swappable persistence
    port when it had exactly one implementation, which is precisely the
    "contract and behaviour must agree" failure the capsule set out to remove.

    The retirement is safe only because the concrete boundary is what the
    worker and the control surface actually use, so that half is asserted too.
    """
    import application.post_commit_work as work

    retired = {
        "PostCommitJobStore",
        "PostCommitStoreResult",
        "PostCommitStoreCode",
        "PostCommitRetryReceipt",
        "PostCommitJobSnapshot",
    }
    assert retired.isdisjoint(work.__all__)
    for name in sorted(retired):
        assert not hasattr(work, name), name

    # The boundary that is actually implemented stays exported, because
    # infrastructure/post_commit_worker.py annotates against it.
    assert "PostCommitExecutionClaim" in work.__all__
    assert hasattr(work, "PostCommitExecutionClaim")
