"""Types and application ports for durable work after a Story COMMIT.

This module has no persistence or IPC implementation. Immutable source identity
is carried separately from mutable scheduling data, and handlers only receive
the source snapshot they need to converge on an artifact.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import NewType, Protocol

_MAX_IDENTIFIER_LENGTH = 256
_MAX_PUBLIC_CODE_LENGTH = 128
_SHA256_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_PUBLIC_CODE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_CREDENTIAL_PATTERNS = (
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
        r"password|passwd|secret|token)\s*[:=]\s*\S+"
    ),
    re.compile(r"(?i)\bhttps?://[^/\s:@]+:[^/\s@]+@"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


class PostCommitKind(StrEnum):
    """Wire kind values; keep these strings aligned with the JSON Schema."""

    EPISODE_FINALIZE = "episode_finalize"
    NARRATIVE_PUBLISH = "narrative_publish"
    AUDIO_PREPARE = "audio_prepare"


class SettlementState(StrEnum):
    """Public settlement projection, exactly as defined by the wire schema."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    SUCCEEDED = "succeeded"


class NarrativeState(StrEnum):
    """Public narrative projection, exactly as defined by the wire schema."""

    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    READY = "ready"


class AudioState(StrEnum):
    """Public audio projection, exactly as defined by the wire schema."""

    PENDING = "pending"
    RUNNING = "running"
    UNAVAILABLE = "unavailable"
    READY = "ready"


class PostCommitJobState(StrEnum):
    """Internal durable scheduler states; not public work.get projections."""

    PENDING = "pending"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    BLOCKED = "blocked"
    SUCCEEDED = "succeeded"


class PostCommitErrorKind(StrEnum):
    """Closed classification used by the automatic retry policy."""

    TEMPORARY_NETWORK = "temporary_network"
    TIMEOUT = "timeout"
    CONFIGURATION = "configuration"
    PERMISSION = "permission"
    IDENTITY = "identity"


class PostCommitLifecycleAction(StrEnum):
    """Scheduler operations that must never advance authoritative world state."""

    CLAIM = "claim"
    RETRY = "retry"
    ACK = "ack"


class PostCommitResultState(StrEnum):
    """Stable outcome returned by one idempotent handler invocation."""

    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"


class PostCommitStoreCode(StrEnum):
    """Stable store operation outcomes without lease or exception details."""

    APPLIED = "applied"
    ALREADY_REGISTERED = "already_registered"
    STALE_CLAIM = "stale_claim"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"


PostCommitClaimToken = NewType("PostCommitClaimToken", object)
type RetryDecision = tuple[PostCommitJobState, int | None]


def _safe_text(value: object, field: str, *, limit: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or "\x00" in value
    ):
        raise ValueError(f"invalid_{field}")
    normalized = value.strip()
    if any(pattern.search(normalized) for pattern in _CREDENTIAL_PATTERNS):
        raise ValueError("credential_like_job_field")
    return normalized


def _reason_code(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > _MAX_PUBLIC_CODE_LENGTH
        or _PUBLIC_CODE.fullmatch(value) is None
    ):
        raise ValueError(f"invalid_{field}")
    return value


def _natural_number(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"invalid_{field}")
    return value


def _validate_digest(value: object) -> str:
    if not isinstance(value, str) or _SHA256_DIGEST.fullmatch(value) is None:
        raise ValueError("invalid_input_digest")
    return value


def _validate_source_fields(
    *,
    job_id: object,
    turn_id: object,
    session_id: object,
    kind: object,
    recipe_revision: object,
    source_story_revision: object,
    source_world_revision: object,
    input_digest: object,
) -> tuple[str, str, str, PostCommitKind, str, int, int, str]:
    if not isinstance(kind, PostCommitKind):
        raise TypeError("invalid_post_commit_kind")
    return (
        _safe_text(job_id, "job_id", limit=_MAX_IDENTIFIER_LENGTH),
        _safe_text(turn_id, "turn_id", limit=_MAX_IDENTIFIER_LENGTH),
        _safe_text(session_id, "session_id", limit=_MAX_IDENTIFIER_LENGTH),
        kind,
        _safe_text(
            recipe_revision,
            "recipe_revision",
            limit=_MAX_IDENTIFIER_LENGTH,
        ),
        _natural_number(source_story_revision, "source_story_revision"),
        _natural_number(source_world_revision, "source_world_revision"),
        _validate_digest(input_digest),
    )


@dataclass(frozen=True, slots=True)
class PostCommitWorkSource:
    """Immutable, credential-free source identity passed to work handlers."""

    job_id: str
    turn_id: str
    session_id: str
    kind: PostCommitKind
    recipe_revision: str
    source_story_revision: int
    source_world_revision: int
    input_digest: str

    def __post_init__(self) -> None:
        validated = _validate_source_fields(
            job_id=self.job_id,
            turn_id=self.turn_id,
            session_id=self.session_id,
            kind=self.kind,
            recipe_revision=self.recipe_revision,
            source_story_revision=self.source_story_revision,
            source_world_revision=self.source_world_revision,
            input_digest=self.input_digest,
        )
        for field, value in zip(
            (
                "job_id",
                "turn_id",
                "session_id",
                "kind",
                "recipe_revision",
                "source_story_revision",
                "source_world_revision",
                "input_digest",
            ),
            validated,
            strict=True,
        ):
            object.__setattr__(self, field, value)


@dataclass(frozen=True, slots=True)
class PostCommitJob:
    """A job whose source identity cannot change after it is registered.

    ``input_digest`` identifies the frozen scenario version, committed delta,
    and bound recipe. Credentials are not part of the digest or job record.
    The fixed fields also exclude raw prompts and redundant world snapshots.
    """

    job_id: str
    turn_id: str
    session_id: str
    kind: PostCommitKind
    recipe_revision: str
    source_story_revision: int
    source_world_revision: int
    input_digest: str
    state: PostCommitJobState
    attempt: int
    lease_owner: str | None
    lease_generation: int
    next_attempt_at: datetime | None
    last_error_code: str | None
    result_ref: str | None

    def __post_init__(self) -> None:
        validated = _validate_source_fields(
            job_id=self.job_id,
            turn_id=self.turn_id,
            session_id=self.session_id,
            kind=self.kind,
            recipe_revision=self.recipe_revision,
            source_story_revision=self.source_story_revision,
            source_world_revision=self.source_world_revision,
            input_digest=self.input_digest,
        )
        for field, value in zip(
            (
                "job_id",
                "turn_id",
                "session_id",
                "kind",
                "recipe_revision",
                "source_story_revision",
                "source_world_revision",
                "input_digest",
            ),
            validated,
            strict=True,
        ):
            object.__setattr__(self, field, value)
        if not isinstance(self.state, PostCommitJobState):
            raise TypeError("invalid_post_commit_job_state")
        _natural_number(self.attempt, "attempt")
        _natural_number(self.lease_generation, "lease_generation")
        if self.lease_owner is not None:
            object.__setattr__(
                self,
                "lease_owner",
                _safe_text(
                    self.lease_owner,
                    "lease_owner",
                    limit=_MAX_IDENTIFIER_LENGTH,
                ),
            )
        if self.next_attempt_at is not None and (
            not isinstance(self.next_attempt_at, datetime)
            or self.next_attempt_at.tzinfo is None
            or self.next_attempt_at.utcoffset() is None
        ):
            raise ValueError("invalid_next_attempt_at")
        if self.last_error_code is not None:
            object.__setattr__(
                self,
                "last_error_code",
                _reason_code(self.last_error_code, "last_error_code"),
            )
        if self.result_ref is not None:
            object.__setattr__(
                self,
                "result_ref",
                _safe_text(
                    self.result_ref,
                    "result_ref",
                    limit=_MAX_IDENTIFIER_LENGTH,
                ),
            )

    @property
    def source(self) -> PostCommitWorkSource:
        """Return the immutable, handler-facing projection of this job."""

        return PostCommitWorkSource(
            job_id=self.job_id,
            turn_id=self.turn_id,
            session_id=self.session_id,
            kind=self.kind,
            recipe_revision=self.recipe_revision,
            source_story_revision=self.source_story_revision,
            source_world_revision=self.source_world_revision,
            input_digest=self.input_digest,
        )

    def with_schedule(
        self,
        *,
        state: PostCommitJobState,
        attempt: int,
        lease_owner: str | None,
        lease_generation: int,
        next_attempt_at: datetime | None,
        last_error_code: str | None,
        result_ref: str | None,
    ) -> PostCommitJob:
        """Return a new job with all mutable scheduling fields explicitly set."""

        return replace(
            self,
            state=state,
            attempt=attempt,
            lease_owner=lease_owner,
            lease_generation=lease_generation,
            next_attempt_at=next_attempt_at,
            last_error_code=last_error_code,
            result_ref=result_ref,
        )


@dataclass(frozen=True, slots=True)
class RequiredPostCommitJob:
    """One deterministic job and its dependencies for a committed turn."""

    kind: PostCommitKind
    initial_state: PostCommitJobState
    depends_on: tuple[PostCommitKind, ...] = ()
    initial_reason_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PostCommitKind):
            raise TypeError("invalid_post_commit_kind")
        if not isinstance(self.initial_state, PostCommitJobState):
            raise TypeError("invalid_post_commit_job_state")
        if any(not isinstance(kind, PostCommitKind) for kind in self.depends_on):
            raise TypeError("invalid_post_commit_dependency")
        if self.initial_reason_code is not None:
            object.__setattr__(
                self,
                "initial_reason_code",
                _reason_code(self.initial_reason_code, "initial_reason_code"),
            )
        if (
            self.initial_state is PostCommitJobState.BLOCKED
        ) != (self.initial_reason_code is not None):
            raise ValueError("blocked_initial_job_reason_mismatch")


@dataclass(frozen=True, slots=True)
class PostCommitResult:
    """Public, structured outcome from a handler; never an exception string."""

    state: PostCommitResultState
    result_ref: str | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, PostCommitResultState):
            raise TypeError("invalid_post_commit_result_state")
        if self.result_ref is not None:
            object.__setattr__(
                self,
                "result_ref",
                _safe_text(
                    self.result_ref,
                    "result_ref",
                    limit=_MAX_IDENTIFIER_LENGTH,
                ),
            )
        if self.reason_code is not None:
            object.__setattr__(
                self,
                "reason_code",
                _reason_code(self.reason_code, "reason_code"),
            )
        if self.state is PostCommitResultState.SUCCEEDED:
            if self.result_ref is None or self.reason_code is not None:
                raise ValueError("invalid_succeeded_post_commit_result")
        elif self.reason_code is None:
            raise ValueError("blocked_post_commit_result_requires_reason")


@dataclass(frozen=True, slots=True)
class PostCommitExecutionClaim:
    """Handler input plus an opaque store capability for generation-CAS ACKs.

    The token is bound internally by the store to the current owner and
    ``lease_generation``. Neither value is exposed to handlers or callers.
    """

    source: PostCommitWorkSource
    attempt: int
    token: PostCommitClaimToken

    def __post_init__(self) -> None:
        if not isinstance(self.source, PostCommitWorkSource):
            raise TypeError("invalid_post_commit_work_source")
        _natural_number(self.attempt, "attempt")
        if self.token is None:
            raise ValueError("invalid_post_commit_claim_token")


@dataclass(frozen=True, slots=True)
class PostCommitJobSnapshot:
    """Read-only store view with scheduler status but no owner/generation."""

    source: PostCommitWorkSource
    state: PostCommitJobState
    attempt: int
    next_attempt_at: datetime | None
    last_error_code: str | None
    result_ref: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.source, PostCommitWorkSource):
            raise TypeError("invalid_post_commit_work_source")
        if not isinstance(self.state, PostCommitJobState):
            raise TypeError("invalid_post_commit_job_state")
        _natural_number(self.attempt, "attempt")
        if self.next_attempt_at is not None and (
            not isinstance(self.next_attempt_at, datetime)
            or self.next_attempt_at.tzinfo is None
            or self.next_attempt_at.utcoffset() is None
        ):
            raise ValueError("invalid_next_attempt_at")
        if self.last_error_code is not None:
            object.__setattr__(
                self,
                "last_error_code",
                _reason_code(self.last_error_code, "last_error_code"),
            )
        if self.result_ref is not None:
            object.__setattr__(
                self,
                "result_ref",
                _safe_text(
                    self.result_ref,
                    "result_ref",
                    limit=_MAX_IDENTIFIER_LENGTH,
                ),
            )


@dataclass(frozen=True, slots=True)
class PostCommitStoreResult:
    """Stable outcome code for a store mutation or compare-and-swap."""

    code: PostCommitStoreCode

    def __post_init__(self) -> None:
        if not isinstance(self.code, PostCommitStoreCode):
            raise TypeError("invalid_post_commit_store_code")


@dataclass(frozen=True, slots=True)
class PostCommitRetryReceipt:
    """Idempotent retry acceptance; contains no internal scheduler identity."""

    accepted: bool
    replayed: bool
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if type(self.accepted) is not bool or type(self.replayed) is not bool:
            raise ValueError("invalid_post_commit_retry_receipt")
        if self.accepted and self.reason_code is not None:
            raise ValueError("accepted_retry_cannot_have_reason")
        if not self.accepted and self.reason_code is None:
            raise ValueError("rejected_retry_requires_reason")
        if self.reason_code is not None:
            object.__setattr__(
                self,
                "reason_code",
                _reason_code(self.reason_code, "reason_code"),
            )


class PostCommitJobStore(Protocol):
    """Persistence boundary for atomic registration and durable scheduling.

    ``register_in_commit`` must be called by the same transaction adapter that
    commits the source Story turn. Claims are ordered by source turn within a
    session and are issued only when dependencies are complete. The opaque
    claim token lets ACK/failure operations compare the current generation
    without returning owner or generation to a handler.
    """

    async def register_in_commit(
        self,
        job: PostCommitJob,
    ) -> PostCommitStoreResult: ...

    async def claim_next(
        self,
        session_id: str,
        *,
        now: datetime,
    ) -> PostCommitExecutionClaim | None: ...

    async def acknowledge_success(
        self,
        claim: PostCommitExecutionClaim,
        result: PostCommitResult,
    ) -> PostCommitStoreResult: ...

    async def acknowledge_failure(
        self,
        claim: PostCommitExecutionClaim,
        *,
        decision: RetryDecision,
        reason_code: str,
    ) -> PostCommitStoreResult: ...

    async def request_retry(
        self,
        session_id: str,
        turn_id: str,
        kind: PostCommitKind,
        retry_request_id: str,
    ) -> PostCommitRetryReceipt: ...

    async def load_turn_jobs(
        self,
        session_id: str,
        turn_id: str,
    ) -> tuple[PostCommitJobSnapshot, ...]: ...


class NarrativePublishHandler(Protocol):
    """Idempotently publish the turn narrative after checking for an artifact."""

    async def execute(self, source: PostCommitWorkSource) -> PostCommitResult:
        """Load and validate an existing narrative before creating one."""
        ...


class EpisodeFinalizeHandler(Protocol):
    """Idempotently finalize an Episode after checking whether it already exists."""

    async def execute(self, source: PostCommitWorkSource) -> PostCommitResult:
        """Load the Episode first; only its successful domain commit advances world revision."""
        ...


class AudioPrepareHandler(Protocol):
    """Idempotently prepare audio after checking for a persisted sealed result."""

    async def execute(self, source: PostCommitWorkSource) -> PostCommitResult:
        """Reuse a valid sealed result and never downgrade narrative readiness."""
        ...


def required_jobs_for_turn(
    turn_number: int,
    max_turn: int,
    *,
    voice_configured: bool,
) -> tuple[RequiredPostCommitJob, ...]:
    """Return the minimal dependency graph for one committed Story turn.

    Narrative and Episode initial states do not depend on voice configuration.
    Audio waits on narrative and is initially blocked only when voice is absent.
    """

    if (
        isinstance(turn_number, bool)
        or not isinstance(turn_number, int)
        or isinstance(max_turn, bool)
        or not isinstance(max_turn, int)
        or max_turn < 1
        or turn_number < 1
        or turn_number > max_turn
    ):
        raise ValueError("invalid_turn_range")
    if type(voice_configured) is not bool:
        raise ValueError("invalid_voice_configuration")

    jobs = [
        RequiredPostCommitJob(
            kind=PostCommitKind.NARRATIVE_PUBLISH,
            initial_state=PostCommitJobState.PENDING,
        )
    ]
    if turn_number == max_turn:
        jobs.append(
            RequiredPostCommitJob(
                kind=PostCommitKind.EPISODE_FINALIZE,
                initial_state=PostCommitJobState.PENDING,
            )
        )
    jobs.append(
        RequiredPostCommitJob(
            kind=PostCommitKind.AUDIO_PREPARE,
            initial_state=(
                PostCommitJobState.PENDING
                if voice_configured
                else PostCommitJobState.BLOCKED
            ),
            depends_on=(PostCommitKind.NARRATIVE_PUBLISH,),
            initial_reason_code=(
                None if voice_configured else "voice_not_configured"
            ),
        )
    )
    return tuple(jobs)


def decide_automatic_retry(
    attempt: int,
    error_kind: PostCommitErrorKind,
) -> RetryDecision:
    """Choose an automatic retry state and delay for a classified failure.

    ``attempt`` counts automatic retries already scheduled. The 1/5/30 second
    delays and three-retry cap are proposed local policy values from the Guide,
    not measured performance characteristics.
    """

    _natural_number(attempt, "attempt")
    if not isinstance(error_kind, PostCommitErrorKind):
        raise TypeError("invalid_post_commit_error_kind")
    if error_kind not in {
        PostCommitErrorKind.TEMPORARY_NETWORK,
        PostCommitErrorKind.TIMEOUT,
    }:
        return (PostCommitJobState.BLOCKED, None)

    retry_delays = (1, 5, 30)
    if attempt >= len(retry_delays):
        return (PostCommitJobState.BLOCKED, None)
    return (PostCommitJobState.RETRY_WAIT, retry_delays[attempt])


def world_revision_increment_for_operation(
    operation: PostCommitKind | PostCommitLifecycleAction,
    *,
    succeeded: bool,
) -> int:
    """Return the revision change allowed by a post-COMMIT operation.

    Claim, retry, and ACK are scheduling operations and always return zero.
    Narrative/audio work also return zero; only successful Episode finalization
    advances world revision through its existing domain transaction.
    """

    if not isinstance(operation, (PostCommitKind, PostCommitLifecycleAction)):
        raise TypeError("invalid_post_commit_operation")
    if type(succeeded) is not bool:
        raise ValueError("invalid_success_flag")
    return int(operation is PostCommitKind.EPISODE_FINALIZE and succeeded)


__all__ = [
    "AudioPrepareHandler",
    "AudioState",
    "EpisodeFinalizeHandler",
    "NarrativePublishHandler",
    "NarrativeState",
    "PostCommitClaimToken",
    "PostCommitErrorKind",
    "PostCommitExecutionClaim",
    "PostCommitJob",
    "PostCommitJobSnapshot",
    "PostCommitJobState",
    "PostCommitJobStore",
    "PostCommitKind",
    "PostCommitLifecycleAction",
    "PostCommitResult",
    "PostCommitResultState",
    "PostCommitRetryReceipt",
    "PostCommitStoreCode",
    "PostCommitStoreResult",
    "PostCommitWorkSource",
    "RequiredPostCommitJob",
    "RetryDecision",
    "SettlementState",
    "decide_automatic_retry",
    "required_jobs_for_turn",
    "world_revision_increment_for_operation",
]
