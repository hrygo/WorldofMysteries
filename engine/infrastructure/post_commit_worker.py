"""Bounded Engine-local executor for durable work after a Story COMMIT.

The database manager owns the exclusive world writer lease. This worker is
created only after that manager is open, recovers abandoned job leases once,
and leaves all artifact creation and artifact-first idempotency to the three
typed handlers.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from application.post_commit_work import (
    AudioPrepareHandler,
    EpisodeFinalizeHandler,
    NarrativePublishHandler,
    PostCommitClaimToken,
    PostCommitErrorKind,
    PostCommitExecutionClaim,
    PostCommitJobState,
    PostCommitKind,
    PostCommitLifecycleAction,
    PostCommitResult,
    PostCommitResultState,
    PostCommitWorkSource,
    decide_automatic_retry,
    world_revision_increment_for_operation,
)

from .database_manager import DatabaseManager, PostCommitJobTransaction
from .post_commit_job_repository import (
    PostCommitJobRecord,
    PostCommitLeaseConflict,
    SQLitePostCommitJobRepository,
)

logger = logging.getLogger(__name__)
MAX_WORKER_CONCURRENCY = 8
DEFAULT_POLL_INTERVAL_SECONDS = 1.0
_REASON_CODE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")


class PostCommitHandlerError(Exception):
    """A classified, credential-free handler failure suitable for persistence."""

    def __init__(
        self,
        *,
        kind: PostCommitErrorKind,
        reason_code: str,
    ) -> None:
        if not isinstance(kind, PostCommitErrorKind):
            raise TypeError("invalid_post_commit_error_kind")
        if not isinstance(reason_code, str) or _REASON_CODE.fullmatch(reason_code) is None:
            raise ValueError("invalid_post_commit_reason_code")
        self.kind = kind
        self.reason_code = reason_code
        super().__init__(reason_code)


# The repository owns the CAS exception. Keep the worker-facing spelling clear
# without introducing a second exception type or changing repository behavior.
PostCommitJobLeaseConflict = PostCommitLeaseConflict


def _timestamp(value: datetime | None) -> str:
    instant = datetime.now(UTC) if value is None else value
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("post_commit_worker_time_must_be_timezone_aware")
    return instant.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _classify_handler_error(
    error: Exception,
) -> tuple[PostCommitErrorKind, str]:
    if isinstance(error, PostCommitHandlerError):
        return error.kind, error.reason_code
    if isinstance(error, TimeoutError):
        return PostCommitErrorKind.TIMEOUT, "temporary_timeout"
    if isinstance(error, ConnectionError):
        return PostCommitErrorKind.TEMPORARY_NETWORK, "temporary_network_failure"
    if isinstance(error, PermissionError):
        return PostCommitErrorKind.PERMISSION, "permission_denied"
    # Unknown failures are fail-closed. Automatic retries are reserved for
    # positively classified transient network and timeout failures.
    return PostCommitErrorKind.CONFIGURATION, "handler_failed"


def _require_ack_revision_neutral(*, succeeded: bool) -> None:
    if (
        world_revision_increment_for_operation(
            PostCommitLifecycleAction.ACK,
            succeeded=succeeded,
        )
        != 0
    ):
        raise RuntimeError("post_commit_job_ack_must_not_advance_world_revision")


@dataclass(frozen=True, slots=True)
class _SQLiteLeaseCapability:
    """Private repository lease data carried only in the opaque claim token."""

    owner: str
    generation: int


class PostCommitWorker:
    """Run durable post-COMMIT handlers with bounded concurrency.

    A worker is bound to one already-open ``DatabaseManager``. Opening that
    manager acquires the exclusive OS writer lease for its world; therefore
    only that Engine may recover abandoned ``running`` rows or execute claims.
    A session is never given a second in-flight claim while its earlier source
    is executing, even when the worker is configured for multiple sessions.
    """

    def __init__(
        self,
        *,
        database: DatabaseManager,
        repository: SQLitePostCommitJobRepository,
        narrative_handler: NarrativePublishHandler,
        episode_finalize_handler: EpisodeFinalizeHandler,
        audio_prepare_handler: AudioPrepareHandler,
        supported_recipes: Mapping[str, Collection[str]],
        max_concurrency: int = 1,
        lease_owner: str | None = None,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        if not isinstance(database, DatabaseManager):
            raise TypeError("post_commit_worker_requires_database_manager")
        if not isinstance(repository, SQLitePostCommitJobRepository):
            raise TypeError("post_commit_worker_requires_sqlite_job_repository")
        if repository.database is not database:
            raise ValueError("post_commit_worker_database_repository_mismatch")
        if (
            isinstance(max_concurrency, bool)
            or not isinstance(max_concurrency, int)
            or not 1 <= max_concurrency <= MAX_WORKER_CONCURRENCY
        ):
            raise ValueError(f"max_concurrency must be between 1 and {MAX_WORKER_CONCURRENCY}")
        if (
            isinstance(poll_interval_seconds, bool)
            or not isinstance(poll_interval_seconds, (int, float))
            or poll_interval_seconds <= 0
        ):
            raise ValueError("poll_interval_seconds_must_be_positive")

        self._database = database
        self._repository = repository
        self._handlers = {
            PostCommitKind.NARRATIVE_PUBLISH.value: narrative_handler,
            PostCommitKind.EPISODE_FINALIZE.value: episode_finalize_handler,
            PostCommitKind.AUDIO_PREPARE.value: audio_prepare_handler,
        }
        self._supported_recipes = self._validate_recipes(supported_recipes)
        self.max_concurrency = max_concurrency
        self._lease_owner = lease_owner or f"engine-worker-{uuid.uuid4().hex}"
        self._poll_interval_seconds = float(poll_interval_seconds)
        self._stop_event = asyncio.Event()
        self._startup_event = asyncio.Event()
        self._startup_error: BaseException | None = None
        self._task: asyncio.Task[None] | None = None
        self._started = False
        self._recovered_abandoned_jobs = False

    @staticmethod
    def _validate_recipes(
        recipes: Mapping[str, Collection[str]],
    ) -> dict[str, frozenset[str]]:
        if not isinstance(recipes, Mapping):
            raise TypeError("supported_recipes_must_be_mapping")
        allowed = {kind.value for kind in PostCommitKind}
        normalized: dict[str, frozenset[str]] = {}
        for kind, revisions in recipes.items():
            if kind not in allowed or isinstance(revisions, str):
                raise ValueError("invalid_supported_post_commit_recipes")
            try:
                frozen = frozenset(revisions)
            except TypeError:
                raise ValueError("invalid_supported_post_commit_recipes") from None
            if any(not isinstance(revision, str) or not revision.strip() for revision in frozen):
                raise ValueError("invalid_supported_post_commit_recipes")
            normalized[kind] = frozen
        return normalized

    @property
    def is_stopping(self) -> bool:
        """Whether lifecycle shutdown has stopped further claim attempts."""

        return self._stop_event.is_set()

    @property
    def is_running(self) -> bool:
        """Whether the background lifecycle task is active."""

        return self._task is not None and not self._task.done()

    def request_stop(self) -> None:
        """Stop new claims; in-flight handlers are allowed to finish and ACK."""

        self._stop_event.set()

    async def start(self) -> None:
        """Start the polling lifecycle once; ``stop`` drains it before DB close."""

        if self._started:
            if self.is_running:
                return
            raise RuntimeError("post_commit_worker_cannot_be_restarted")
        self._started = True
        self._task = asyncio.create_task(
            self._serve(),
            name=f"post-commit-worker:{self._lease_owner}",
        )
        await self._startup_event.wait()
        if self._startup_error is not None:
            await self._task

    async def stop(self) -> None:
        """Stop claiming and wait for in-flight handler tasks to settle."""

        self.request_stop()
        task = self._task
        if task is None:
            return
        if task is asyncio.current_task():
            raise RuntimeError("post_commit_worker_cannot_stop_itself")
        await asyncio.shield(task)

    async def run_once(self, *, now: datetime | None = None) -> int:
        """Process currently eligible work and return the number of claims run.

        This single-pass API is useful for deterministic orchestration and
        testing. Production lifecycle code normally calls ``start`` and
        ``stop`` so newly committed jobs are picked up without another submit.
        """

        if self._task is not None and asyncio.current_task() is not self._task:
            raise RuntimeError("post_commit_worker_already_running")
        if self._stop_event.is_set():
            return 0
        await self._recover_abandoned_once()
        return await self._run_available(now=now)

    async def _serve(self) -> None:
        try:
            await self._recover_abandoned_once()
        except BaseException as error:
            self._startup_error = error
            self._startup_event.set()
            raise
        self._startup_event.set()
        try:
            while not self._stop_event.is_set():
                processed = await self._run_available(now=None)
                if processed == 0 and not self._stop_event.is_set():
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=self._poll_interval_seconds,
                        )
                    except TimeoutError:
                        pass
        except asyncio.CancelledError:
            self.request_stop()
            raise

    async def _recover_abandoned_once(self) -> None:
        if self._recovered_abandoned_jobs:
            return

        def recover(transaction: PostCommitJobTransaction) -> None:
            transaction.execute(
                "UPDATE post_commit_jobs SET state='pending',lease_owner=NULL,"
                "next_attempt_at=NULL,last_error_code=NULL "
                "WHERE state='running'"
            )

        # DatabaseManager.open already owns the world writer lock before a
        # worker can be constructed. Resetting all old running rows is safe only
        # under that Engine-wide lease, never by a job-level timeout.
        await self._database.post_commit_job_write(recover)
        self._recovered_abandoned_jobs = True

    async def _sessions_with_eligible_work(self, now: datetime) -> tuple[str, ...]:
        rows = await self._database.read_world(
            "SELECT session_id,MIN(source_world_revision) AS first_world_revision,"
            "MIN(source_story_revision) AS first_story_revision "
            "FROM post_commit_jobs WHERE state='pending' OR "
            "(state='retry_wait' AND next_attempt_at<=?) "
            "GROUP BY session_id "
            "ORDER BY first_world_revision,first_story_revision,session_id",
            (_timestamp(now),),
        )
        return tuple(row["session_id"] for row in rows)

    async def _run_available(self, *, now: datetime | None) -> int:
        instant = datetime.now(UTC) if now is None else now
        _timestamp(instant)  # validate before querying or claiming.
        active: dict[asyncio.Task[None], str] = {}
        busy_sessions: set[str] = set()
        unclaimable_sessions: set[str] = set()
        claimed_count = 0

        try:
            while not self._stop_event.is_set():
                sessions = await self._sessions_with_eligible_work(instant)
                for session_id in sessions:
                    if self._stop_event.is_set() or len(active) >= self.max_concurrency:
                        break
                    if session_id in busy_sessions or session_id in unclaimable_sessions:
                        continue
                    claim = await self._repository.claim(
                        session_id=session_id,
                        lease_owner=self._lease_owner,
                        supported_recipes=self._supported_recipes,
                        now=instant,
                    )
                    if claim is None:
                        # Dependencies such as narrative publication are
                        # checked by the repository against their source rows.
                        # Missing audio input remains unclaimed and unmodified.
                        unclaimable_sessions.add(session_id)
                        continue
                    execution_claim = self._execution_claim(claim)
                    task = asyncio.create_task(
                        self._execute_claim(execution_claim, now=instant),
                        name=f"post-commit-job:{claim.job_id}",
                    )
                    active[task] = session_id
                    busy_sessions.add(session_id)
                    claimed_count += 1

                if not active:
                    break

                done, _ = await asyncio.wait(
                    active,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    session_id = active.pop(task)
                    busy_sessions.remove(session_id)
                    try:
                        task.result()
                    except BaseException:
                        self.request_stop()
                        await self._drain(active)
                        raise
                # A completed narrative may have made this session's audio job
                # eligible. Re-query source and dependency state on the next
                # pass instead of caching a claimable job list.
                unclaimable_sessions.clear()
        except asyncio.CancelledError:
            self.request_stop()
            await self._drain(active)
            raise

        return claimed_count

    @staticmethod
    def _execution_claim(record: PostCommitJobRecord) -> PostCommitExecutionClaim:
        if record.lease_owner is None:
            raise PostCommitJobLeaseConflict("Claimed post-COMMIT job has no active lease owner")
        return PostCommitExecutionClaim(
            source=PostCommitWorkSource(
                job_id=record.job_id,
                turn_id=record.turn_id,
                session_id=record.session_id,
                kind=PostCommitKind(record.kind),
                recipe_revision=record.recipe_revision,
                source_story_revision=record.source_story_revision,
                source_world_revision=record.source_world_revision,
                input_digest=record.input_digest,
            ),
            attempt=record.attempt,
            token=PostCommitClaimToken(
                _SQLiteLeaseCapability(
                    owner=record.lease_owner,
                    generation=record.lease_generation,
                )
            ),
        )

    @staticmethod
    async def _drain(active: Mapping[asyncio.Task[None], str]) -> None:
        if not active:
            return
        drain = asyncio.gather(*active, return_exceptions=True)
        await asyncio.shield(drain)

    async def _execute_claim(
        self,
        claim: PostCommitExecutionClaim,
        *,
        now: datetime,
    ) -> None:
        source = claim.source
        capability = cast(_SQLiteLeaseCapability, claim.token)
        handler = self._handlers[source.kind.value]
        try:
            result = await handler.execute(source)
        except asyncio.CancelledError:
            # A canceled handler is left running durably. On a later Engine
            # start, after its world writer lease is acquired, it is recovered
            # and the handler's artifact-first check can converge it.
            raise
        except Exception as error:  # noqa: BLE001 - unknown errors are blocked, never retried
            await self._record_handler_failure(claim, error, now=now)
            return

        if not isinstance(result, PostCommitResult):
            _require_ack_revision_neutral(succeeded=False)
            await self._repository.fail(
                source.job_id,
                lease_owner=capability.owner,
                lease_generation=capability.generation,
                error_code="invalid_handler_result",
                retryable=False,
                now=now,
            )
            return
        if result.state is PostCommitResultState.BLOCKED:
            assert result.reason_code is not None
            _require_ack_revision_neutral(succeeded=False)
            await self._repository.fail(
                source.job_id,
                lease_owner=capability.owner,
                lease_generation=capability.generation,
                error_code=result.reason_code,
                retryable=False,
                now=now,
            )
            return
        _require_ack_revision_neutral(succeeded=True)
        await self._repository.complete(
            source.job_id,
            lease_owner=capability.owner,
            lease_generation=capability.generation,
            result_ref=result.result_ref,
        )

    async def _record_handler_failure(
        self,
        claim: PostCommitExecutionClaim,
        error: Exception,
        *,
        now: datetime,
    ) -> None:
        error_kind, reason_code = _classify_handler_error(error)
        capability = cast(_SQLiteLeaseCapability, claim.token)
        next_state, _delay_seconds = decide_automatic_retry(
            max(0, claim.attempt - 1),
            error_kind,
        )
        _require_ack_revision_neutral(succeeded=False)
        await self._repository.fail(
            claim.source.job_id,
            lease_owner=capability.owner,
            lease_generation=capability.generation,
            error_code=reason_code,
            retryable=next_state is PostCommitJobState.RETRY_WAIT,
            now=now,
        )
        logger.info(
            "Post-COMMIT handler failed",
            extra={
                "job_id": claim.source.job_id,
                "kind": claim.source.kind.value,
                "attempt": claim.attempt,
                "state": (
                    next_state.value
                    if next_state is not PostCommitJobState.RETRY_WAIT
                    else "retry_wait"
                ),
                "reason_code": reason_code,
            },
        )


__all__ = [
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "MAX_WORKER_CONCURRENCY",
    "PostCommitHandlerError",
    "PostCommitJobLeaseConflict",
    "PostCommitWorker",
]
