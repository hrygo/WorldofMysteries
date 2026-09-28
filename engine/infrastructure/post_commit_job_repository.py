"""Durable scheduling and public status projection for Post-COMMIT work.

Job source fields are immutable after registration. Domain commits may register
jobs in their own transaction through an insert-only capability; scheduling,
leases, retries, and acknowledgements use the dedicated job writer.
"""
from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from .database_manager import (
    DatabaseManager,
    DomainTransaction,
    PostCommitJobRegistrationTransaction,
    PostCommitJobTransaction,
)
from .database_schema import StorageError


_JOB_KINDS = frozenset(
    {"episode_finalize", "narrative_publish", "audio_prepare"}
)
_COMMITTED_TURN_STATES = frozenset(
    {"committed", "beat_ready", "narrative_ready", "audio_ready", "delivered"}
)
_RETRY_DELAYS = (1, 5, 30)
_CLAIM_SCAN_LIMIT = 100
_PUBLIC_ERROR_CODES = frozenset(
    {
        "audio_not_scheduled",
        "dependency_unavailable",
        "handoff_expired",
        "handoff_unverified",
        "provider_unavailable",
        "recipe_unavailable",
        "work_unavailable",
    }
)
_PUBLIC_ERROR_ALIASES = {
    "dependency_source_mismatch": "dependency_unavailable",
    "source_mismatch": "work_unavailable",
}


class PostCommitJobConflict(StorageError):
    """A durable job identity or retry request is bound to different input."""


class PostCommitLeaseConflict(StorageError):
    """A job acknowledgement does not hold the current owner/generation lease."""


class SettlementPublicState(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    SUCCEEDED = "succeeded"


class NarrativePublicState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    READY = "ready"


class AudioPublicState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    UNAVAILABLE = "unavailable"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class PostCommitJobSpec:
    """Immutable source identity frozen by the caller at Domain COMMIT."""

    job_id: str
    turn_id: str
    session_id: str
    kind: str
    recipe_revision: str
    source_story_revision: int
    source_world_revision: int
    input_digest: str


@dataclass(frozen=True, slots=True)
class PostCommitJobRecord:
    """Internal durable job record, including lease fields for the worker."""

    job_id: str
    turn_id: str
    session_id: str
    kind: str
    recipe_revision: str
    source_story_revision: int
    source_world_revision: int
    input_digest: str
    state: str
    attempt: int
    lease_owner: str | None
    lease_generation: int
    next_attempt_at: str | None
    last_error_code: str | None
    result_ref: str | None


@dataclass(frozen=True, slots=True)
class PostCommitRetryResult:
    accepted: bool
    replayed: bool


@dataclass(frozen=True, slots=True)
class PostCommitPublicStatus:
    """Stable public status lower bound, with no worker lease/internal fields.

    This repository can report durable work, but it cannot inspect the in-memory
    sealed-unit registry. The control adapter may report audio ``ready`` only
    after both the persisted sealed result and a live handoff unit are verified.
    """

    settlement: SettlementPublicState
    narrative: NarrativePublicState
    audio: AudioPublicState
    settlement_reason: str | None = None
    narrative_reason: str | None = None
    audio_reason: str | None = None


def _identifier(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 256
        or "\x00" in value
    ):
        raise StorageError(f"Invalid post-COMMIT job {field}")
    return value


def _revision(value: int, field: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value >= 2**63
    ):
        raise StorageError(f"Invalid post-COMMIT job {field}")
    return value


def _spec_values(spec: PostCommitJobSpec) -> tuple:
    if not isinstance(spec, PostCommitJobSpec):
        raise StorageError("Job registration requires typed job specifications")
    identifiers = (
        ("job id", spec.job_id),
        ("turn id", spec.turn_id),
        ("session id", spec.session_id),
        ("recipe revision", spec.recipe_revision),
        ("input digest", spec.input_digest),
    )
    for field, value in identifiers:
        _identifier(value, field)
    if not isinstance(spec.kind, str) or spec.kind not in _JOB_KINDS:
        raise StorageError("Invalid post-COMMIT job kind")
    _revision(spec.source_story_revision, "source story revision")
    _revision(spec.source_world_revision, "source world revision")
    if spec.source_world_revision == 0:
        raise StorageError("Post-COMMIT job requires a committed world revision")
    return (
        spec.job_id,
        spec.turn_id,
        spec.session_id,
        spec.kind,
        spec.recipe_revision,
        spec.source_story_revision,
        spec.source_world_revision,
        spec.input_digest,
    )


def _record(row: dict) -> PostCommitJobRecord:
    return PostCommitJobRecord(
        job_id=row["job_id"],
        turn_id=row["turn_id"],
        session_id=row["session_id"],
        kind=row["kind"],
        recipe_revision=row["recipe_revision"],
        source_story_revision=row["source_story_revision"],
        source_world_revision=row["source_world_revision"],
        input_digest=row["input_digest"],
        state=row["state"],
        attempt=row["attempt"],
        lease_owner=row["lease_owner"],
        lease_generation=row["lease_generation"],
        next_attempt_at=row["next_attempt_at"],
        last_error_code=row["last_error_code"],
        result_ref=row["result_ref"],
    )


def _timestamp(value: datetime | None) -> str:
    value = datetime.now(UTC) if value is None else value
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise StorageError("Post-COMMIT scheduling time must be timezone-aware")
    return (
        value.astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _public_reason(error_code: str | None) -> str | None:
    if error_code is None:
        return None
    alias = _PUBLIC_ERROR_ALIASES.get(error_code)
    if alias is not None:
        return alias
    if error_code in _PUBLIC_ERROR_CODES:
        return error_code
    return "work_unavailable"


class SQLitePostCommitJobRepository:
    """Specialized job store; it never owns or advances Domain world revision."""

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def register(
        self,
        transaction: DomainTransaction | PostCommitJobTransaction,
        jobs: Iterable[PostCommitJobSpec],
    ) -> tuple[PostCommitJobRecord, ...]:
        """Insert/reuse frozen jobs in the caller's existing transaction.

        A DomainTransaction is temporarily narrowed to an insert-only job scope,
        keeping task registration atomic with its committed turn. A dedicated
        PostCommitJobTransaction can be used for repair/reconciliation callers.
        """
        if isinstance(transaction, DomainTransaction):
            with transaction._post_commit_job_registration_scope() as scoped:
                return self._register_in_transaction(scoped, jobs)
        if isinstance(transaction, PostCommitJobTransaction):
            return self._register_in_transaction(transaction, jobs)
        raise StorageError("Job registration requires a caller-owned transaction")

    def _register_in_transaction(
        self,
        transaction: PostCommitJobRegistrationTransaction | PostCommitJobTransaction,
        jobs: Iterable[PostCommitJobSpec],
    ) -> tuple[PostCommitJobRecord, ...]:
        try:
            frozen_jobs = tuple(jobs)
        except TypeError:
            raise StorageError("Job registration requires an iterable") from None
        if any(not isinstance(spec, PostCommitJobSpec) for spec in frozen_jobs):
            raise StorageError("Job registration requires typed job specifications")

        registered: list[PostCommitJobRecord] = []
        for spec in frozen_jobs:
            values = _spec_values(spec)
            self._require_source_match(transaction, spec)
            rows = transaction.execute(
                "SELECT * FROM post_commit_jobs "
                "WHERE turn_id=? AND kind=? AND recipe_revision=?",
                (spec.turn_id, spec.kind, spec.recipe_revision),
            )
            if rows:
                if len(rows) != 1:
                    raise PostCommitJobConflict(
                        "Post-COMMIT job identity is corrupted"
                    )
                existing = _record(rows[0])
                if existing.job_id != spec.job_id or (
                    existing.session_id,
                    existing.source_story_revision,
                    existing.source_world_revision,
                    existing.input_digest,
                ) != (
                    spec.session_id,
                    spec.source_story_revision,
                    spec.source_world_revision,
                    spec.input_digest,
                ):
                    raise PostCommitJobConflict(
                        "Post-COMMIT job identity is already bound to different input"
                    )
                registered.append(existing)
                continue

            id_rows = transaction.execute(
                "SELECT * FROM post_commit_jobs WHERE job_id=?", (spec.job_id,)
            )
            if id_rows:
                raise PostCommitJobConflict(
                    "Post-COMMIT job id is already bound to another identity"
                )
            transaction.execute(
                "INSERT INTO post_commit_jobs("
                "job_id,turn_id,session_id,kind,recipe_revision,"
                "source_story_revision,source_world_revision,input_digest,"
                "state,attempt,lease_owner,lease_generation,next_attempt_at,"
                "last_error_code,result_ref"
                ") VALUES (?,?,?,?,?,?,?,?,'pending',0,NULL,0,NULL,NULL,NULL)",
                values,
            )
            inserted = transaction.execute(
                "SELECT * FROM post_commit_jobs WHERE job_id=?", (spec.job_id,)
            )
            if len(inserted) != 1:
                raise StorageError("Post-COMMIT job registration did not persist")
            registered.append(_record(inserted[0]))
        return tuple(registered)

    @staticmethod
    def _require_source_match(transaction, spec: PostCommitJobSpec) -> None:
        rows = transaction.execute(
            "SELECT t.session_id AS turn_session_id,t.status,t.state_delta_id,"
            "t.committed_story_revision,t.committed_world_revision,"
            "d.id AS delta_id,d.session_id AS delta_session_id,d.turn_id AS delta_turn_id,"
            "d.story_revision AS delta_story_revision,"
            "d.committed_world_revision AS delta_world_revision "
            "FROM turn_transactions AS t "
            "LEFT JOIN story_state_deltas AS d ON d.id=t.state_delta_id "
            "WHERE t.id=?",
            (spec.turn_id,),
        )
        if len(rows) != 1:
            raise PostCommitJobConflict(
                "Post-COMMIT job source turn is missing"
            )
        source = rows[0]
        consistent = (
            source["status"] in _COMMITTED_TURN_STATES
            and source["turn_session_id"] == spec.session_id
            and source["committed_story_revision"] == spec.source_story_revision
            and source["committed_world_revision"] == spec.source_world_revision
            and source["state_delta_id"] == source["delta_id"]
            and source["delta_session_id"] == spec.session_id
            and source["delta_turn_id"] == spec.turn_id
            and source["delta_story_revision"] == spec.source_story_revision
            and source["delta_world_revision"] == spec.source_world_revision
        )
        if not consistent:
            raise PostCommitJobConflict(
                "Post-COMMIT job source does not match its committed turn"
            )

    async def claim(
        self,
        *,
        session_id: str,
        lease_owner: str,
        supported_recipes: Mapping[str, Collection[str]],
        now: datetime | None = None,
    ) -> PostCommitJobRecord | None:
        """Claim the earliest eligible job for a session in one short write."""
        _identifier(session_id, "session id")
        _identifier(lease_owner, "lease owner")
        if not isinstance(supported_recipes, Mapping):
            raise StorageError("Claim requires a recipe capability mapping")
        capabilities: dict[str, frozenset[str]] = {}
        for kind, recipes in supported_recipes.items():
            if kind not in _JOB_KINDS or isinstance(recipes, str):
                raise StorageError("Invalid supported post-COMMIT recipe set")
            try:
                capabilities[kind] = frozenset(
                    _identifier(recipe, "recipe revision") for recipe in recipes
                )
            except TypeError:
                raise StorageError("Invalid supported post-COMMIT recipe set") from None
        now_value = _timestamp(now)

        def apply(tx: PostCommitJobTransaction):
            candidates = tx.execute(
                "SELECT j.* FROM post_commit_jobs AS j "
                "WHERE j.session_id=? AND (j.state='pending' OR "
                "(j.state='retry_wait' AND j.next_attempt_at<=?)) "
                "AND (j.kind!='audio_prepare' OR EXISTS ("
                "SELECT 1 FROM narrative_blocks AS n WHERE n.turn_id=j.turn_id"
                ")) "
                "ORDER BY j.source_world_revision,j.source_story_revision,j.turn_id,"
                "CASE j.kind WHEN 'narrative_publish' THEN 0 "
                "WHEN 'episode_finalize' THEN 1 ELSE 2 END,j.job_id "
                "LIMIT ?",
                (session_id, now_value, _CLAIM_SCAN_LIMIT),
            )
            for candidate in candidates:
                if not self._source_matches_row(tx, candidate):
                    tx.execute(
                        "UPDATE post_commit_jobs SET state='blocked',lease_owner=NULL,"
                        "next_attempt_at=NULL,last_error_code='source_mismatch' "
                        "WHERE job_id=? AND state=?",
                        (candidate["job_id"], candidate["state"]),
                    )
                    continue
                if candidate["recipe_revision"] not in capabilities.get(
                    candidate["kind"], frozenset()
                ):
                    tx.execute(
                        "UPDATE post_commit_jobs SET state='blocked',lease_owner=NULL,"
                        "next_attempt_at=NULL,last_error_code='recipe_unavailable' "
                        "WHERE job_id=? AND state=?",
                        (candidate["job_id"], candidate["state"]),
                    )
                    continue
                dependency = self._dependency_status(tx, candidate)
                if dependency == "missing":
                    continue
                if dependency == "mismatch":
                    tx.execute(
                        "UPDATE post_commit_jobs SET state='blocked',lease_owner=NULL,"
                        "next_attempt_at=NULL,"
                        "last_error_code='dependency_source_mismatch' "
                        "WHERE job_id=? AND state=?",
                        (candidate["job_id"], candidate["state"]),
                    )
                    continue
                next_generation = candidate["lease_generation"] + 1
                tx.execute(
                    "UPDATE post_commit_jobs SET state='running',attempt=attempt+1,"
                    "lease_owner=?,lease_generation=?,next_attempt_at=NULL,"
                    "last_error_code=NULL "
                    "WHERE job_id=? AND state=? AND lease_generation=?",
                    (
                        lease_owner,
                        next_generation,
                        candidate["job_id"],
                        candidate["state"],
                        candidate["lease_generation"],
                    ),
                )
                claimed = self._load_job(tx, candidate["job_id"])
                if (
                    claimed.state != "running"
                    or claimed.lease_owner != lease_owner
                    or claimed.lease_generation != next_generation
                ):
                    raise PostCommitLeaseConflict(
                        "Post-COMMIT job claim lost its scheduling compare-and-swap"
                    )
                return claimed
            return None

        return await self.database.post_commit_job_write(apply)

    @staticmethod
    def _source_matches_row(
        transaction: PostCommitJobTransaction, job: dict
    ) -> bool:
        rows = transaction.execute(
            "SELECT t.session_id AS turn_session_id,t.status,t.state_delta_id,"
            "t.committed_story_revision,t.committed_world_revision,"
            "d.id AS delta_id,d.session_id AS delta_session_id,d.turn_id AS delta_turn_id,"
            "d.story_revision AS delta_story_revision,"
            "d.committed_world_revision AS delta_world_revision "
            "FROM turn_transactions AS t "
            "LEFT JOIN story_state_deltas AS d ON d.id=t.state_delta_id "
            "WHERE t.id=?",
            (job["turn_id"],),
        )
        if len(rows) != 1:
            return False
        source = rows[0]
        return (
            source["status"] in _COMMITTED_TURN_STATES
            and source["turn_session_id"] == job["session_id"]
            and source["committed_story_revision"] == job["source_story_revision"]
            and source["committed_world_revision"] == job["source_world_revision"]
            and source["state_delta_id"] == source["delta_id"]
            and source["delta_session_id"] == job["session_id"]
            and source["delta_turn_id"] == job["turn_id"]
            and source["delta_story_revision"] == job["source_story_revision"]
            and source["delta_world_revision"] == job["source_world_revision"]
        )

    @staticmethod
    def _dependency_status(transaction: PostCommitJobTransaction, job: dict) -> str:
        if job["kind"] != "audio_prepare":
            return "ready"
        rows = transaction.execute(
            "SELECT n.session_id,n.source_story_revision,n.source_world_revision,"
            "n.source_state_delta_id,d.session_id AS delta_session_id,"
            "d.turn_id AS delta_turn_id,d.story_revision AS delta_story_revision,"
            "d.committed_world_revision AS delta_world_revision "
            "FROM narrative_blocks AS n "
            "LEFT JOIN story_state_deltas AS d ON d.id=n.source_state_delta_id "
            "WHERE n.turn_id=?",
            (job["turn_id"],),
        )
        if not rows:
            return "missing"
        if len(rows) != 1:
            return "mismatch"
        narrative = rows[0]
        if (
            narrative["session_id"] != job["session_id"]
            or narrative["source_story_revision"] != job["source_story_revision"]
            or narrative["source_world_revision"] != job["source_world_revision"]
            or narrative["delta_session_id"] != job["session_id"]
            or narrative["delta_turn_id"] != job["turn_id"]
            or narrative["delta_story_revision"] != job["source_story_revision"]
            or narrative["delta_world_revision"] != job["source_world_revision"]
        ):
            return "mismatch"
        return "ready"

    async def complete(
        self,
        job_id: str,
        *,
        lease_owner: str,
        lease_generation: int,
        result_ref: str | None = None,
    ) -> PostCommitJobRecord:
        """Acknowledge successful work through the scoped job writer."""
        return await self.database.post_commit_job_write(
            lambda tx: self.complete_in(
                tx,
                job_id,
                lease_owner=lease_owner,
                lease_generation=lease_generation,
                result_ref=result_ref,
            )
        )

    @staticmethod
    def complete_in(
        transaction: PostCommitJobTransaction,
        job_id: str,
        *,
        lease_owner: str,
        lease_generation: int,
        result_ref: str | None = None,
    ) -> PostCommitJobRecord:
        """Complete inside a caller-owned job transaction, optionally with result insert."""
        _identifier(job_id, "job id")
        _identifier(lease_owner, "lease owner")
        _revision(lease_generation, "lease generation")
        if result_ref is not None:
            _identifier(result_ref, "result reference")
        current = SQLitePostCommitJobRepository._load_job(transaction, job_id)
        SQLitePostCommitJobRepository._require_lease(
            current, lease_owner, lease_generation
        )
        transaction.execute(
            "UPDATE post_commit_jobs SET state='succeeded',lease_owner=NULL,"
            "next_attempt_at=NULL,last_error_code=NULL,"
            "result_ref=COALESCE(?,result_ref) "
            "WHERE job_id=? AND state='running' AND lease_owner=? "
            "AND lease_generation=?",
            (result_ref, job_id, lease_owner, lease_generation),
        )
        updated = SQLitePostCommitJobRepository._load_job(transaction, job_id)
        if updated.state != "succeeded" or updated.lease_owner is not None:
            raise PostCommitLeaseConflict(
                "Post-COMMIT job completion did not match the active lease"
            )
        return updated

    async def fail(
        self,
        job_id: str,
        *,
        lease_owner: str,
        lease_generation: int,
        error_code: str,
        retryable: bool,
        now: datetime | None = None,
    ) -> PostCommitJobRecord:
        """Record failure with bounded automatic retry scheduling."""
        return await self.database.post_commit_job_write(
            lambda tx: self.fail_in(
                tx,
                job_id,
                lease_owner=lease_owner,
                lease_generation=lease_generation,
                error_code=error_code,
                retryable=retryable,
                now=now,
            )
        )

    @staticmethod
    def fail_in(
        transaction: PostCommitJobTransaction,
        job_id: str,
        *,
        lease_owner: str,
        lease_generation: int,
        error_code: str,
        retryable: bool,
        now: datetime | None = None,
    ) -> PostCommitJobRecord:
        """Persist a worker failure inside an existing job writer transaction."""
        _identifier(job_id, "job id")
        _identifier(lease_owner, "lease owner")
        _identifier(error_code, "error code")
        _revision(lease_generation, "lease generation")
        if type(retryable) is not bool:
            raise StorageError("Invalid post-COMMIT retryability")
        current = SQLitePostCommitJobRepository._load_job(transaction, job_id)
        SQLitePostCommitJobRepository._require_lease(
            current, lease_owner, lease_generation
        )
        now_value = _timestamp(now)
        retry_index = current.attempt - 1
        if retryable and 0 <= retry_index < len(_RETRY_DELAYS):
            delay = _RETRY_DELAYS[retry_index]
            next_state = "retry_wait"
            next_attempt_at = (
                datetime.fromisoformat(now_value.replace("Z", "+00:00"))
                + timedelta(seconds=delay)
            ).astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
        else:
            next_state = "blocked"
            next_attempt_at = None
        transaction.execute(
            "UPDATE post_commit_jobs SET state=?,lease_owner=NULL,next_attempt_at=?,"
            "last_error_code=? WHERE job_id=? AND state='running' "
            "AND lease_owner=? AND lease_generation=?",
            (
                next_state,
                next_attempt_at,
                error_code,
                job_id,
                lease_owner,
                lease_generation,
            ),
        )
        updated = SQLitePostCommitJobRepository._load_job(transaction, job_id)
        if updated.state != next_state or updated.lease_owner is not None:
            raise PostCommitLeaseConflict(
                "Post-COMMIT job failure did not match the active lease"
            )
        return updated

    async def retry(
        self, job_id: str, *, request_id: str
    ) -> PostCommitRetryResult:
        """Accept an explicit retry once, bound to its request ID and job ID."""
        _identifier(job_id, "job id")
        _identifier(request_id, "retry request id")
        return await self.database.post_commit_job_write(
            lambda tx: self.retry_in(tx, job_id, request_id=request_id)
        )

    @staticmethod
    def retry_in(
        transaction: PostCommitJobTransaction,
        job_id: str,
        *,
        request_id: str,
    ) -> PostCommitRetryResult:
        """Retry in the existing job transaction without touching stored results."""
        _identifier(job_id, "job id")
        _identifier(request_id, "retry request id")
        requests = transaction.execute(
            "SELECT job_id FROM post_commit_retry_requests WHERE request_id=?",
            (request_id,),
        )
        if requests:
            if requests[0]["job_id"] != job_id:
                raise PostCommitJobConflict(
                    "Retry request id is already bound to another job"
                )
            return PostCommitRetryResult(accepted=True, replayed=True)
        current = SQLitePostCommitJobRepository._load_job(transaction, job_id)
        if current.state not in {"retry_wait", "blocked"}:
            raise PostCommitJobConflict(
                "Post-COMMIT job is not eligible for an explicit retry"
            )
        transaction.execute(
            "INSERT INTO post_commit_retry_requests(request_id,job_id) VALUES (?,?)",
            (request_id, job_id),
        )
        transaction.execute(
            "UPDATE post_commit_jobs SET state='pending',attempt=0,lease_owner=NULL,"
            "next_attempt_at=NULL,last_error_code=NULL WHERE job_id=? "
            "AND state IN ('retry_wait','blocked')",
            (job_id,),
        )
        updated = SQLitePostCommitJobRepository._load_job(transaction, job_id)
        if updated.state != "pending":
            raise PostCommitJobConflict(
                "Post-COMMIT job retry did not persist"
            )
        return PostCommitRetryResult(accepted=True, replayed=False)

    async def get_status(
        self, *, session_id: str, turn_id: str
    ) -> PostCommitPublicStatus:
        """Read a durable-only projection without changing durable state.

        Audio ``ready`` requires the persisted sealed result and a live Engine
        registry handoff. This database-only layer reports ``unavailable`` with
        ``handoff_unverified`` after durable success; the control adapter may
        refine that lower bound after checking the registry.
        """
        _identifier(session_id, "session id")
        _identifier(turn_id, "turn id")
        rows = await self.database.read_world(
            "SELECT kind,state,last_error_code FROM post_commit_jobs "
            "WHERE session_id=? AND turn_id=? "
            "ORDER BY CASE kind WHEN 'episode_finalize' THEN 0 "
            "WHEN 'narrative_publish' THEN 1 ELSE 2 END,recipe_revision",
            (session_id, turn_id),
        )
        grouped: dict[str, list[dict]] = {kind: [] for kind in _JOB_KINDS}
        for row in rows:
            grouped[row["kind"]].append(row)

        settlement, settlement_reason = self._public_group_state(
            grouped["episode_finalize"], default="not_required", target="settlement"
        )
        narrative, narrative_reason = self._public_group_state(
            grouped["narrative_publish"], default="pending", target="narrative"
        )
        audio, audio_reason = self._public_group_state(
            grouped["audio_prepare"], default="unavailable", target="audio"
        )
        if not grouped["audio_prepare"]:
            audio_reason = "audio_not_scheduled"
        return PostCommitPublicStatus(
            settlement=SettlementPublicState(settlement),
            narrative=NarrativePublicState(narrative),
            audio=AudioPublicState(audio),
            settlement_reason=settlement_reason,
            narrative_reason=narrative_reason,
            audio_reason=audio_reason,
        )

    @staticmethod
    def _public_group_state(
        jobs: list[dict], *, default: str, target: str
    ) -> tuple[str, str | None]:
        if not jobs:
            return default, None
        states = {job["state"] for job in jobs}
        if "succeeded" in states:
            internal_state = "succeeded"
        elif "running" in states:
            internal_state = "running"
        elif states & {"pending", "retry_wait"}:
            internal_state = "pending"
        else:
            internal_state = "blocked"
        reason = next(
            (
                _public_reason(job["last_error_code"])
                for job in jobs
                if job["state"] == internal_state
                and job["last_error_code"] is not None
            ),
            None,
        )
        if target == "settlement":
            return internal_state, reason
        if target == "narrative":
            return (
                "ready" if internal_state == "succeeded" else internal_state,
                reason,
            )
        if internal_state == "succeeded":
            return "unavailable", "handoff_unverified"
        if internal_state == "blocked":
            return "unavailable", reason
        return internal_state, reason

    @staticmethod
    def _load_job(
        transaction: PostCommitJobTransaction
        | PostCommitJobRegistrationTransaction,
        job_id: str,
    ) -> PostCommitJobRecord:
        rows = transaction.execute(
            "SELECT * FROM post_commit_jobs WHERE job_id=?", (job_id,)
        )
        if len(rows) != 1:
            raise PostCommitJobConflict("Post-COMMIT job not found")
        return _record(rows[0])

    @staticmethod
    def _require_lease(
        current: PostCommitJobRecord,
        lease_owner: str,
        lease_generation: int,
    ) -> None:
        if (
            current.state != "running"
            or current.lease_owner != lease_owner
            or current.lease_generation != lease_generation
        ):
            raise PostCommitLeaseConflict(
                "Post-COMMIT job lease owner or generation does not match"
            )
