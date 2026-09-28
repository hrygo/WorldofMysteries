"""Conservative, idempotent reconciliation of historical post-COMMIT work.

Reconciliation never executes a recipe. It records already-persisted artifacts
as succeeded and leaves missing legacy work blocked when its original recipe
cannot be proven.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass

from .database_manager import DatabaseManager, PostCommitJobTransaction
from .post_commit_job_repository import (
    _COMMITTED_TURN_STATES,
    PostCommitJobRegistration,
    PostCommitJobSpec,
    SQLitePostCommitJobRepository,
)

_LEGACY_RECIPE_UNKNOWN = "legacy_recipe_unknown"
_NARRATIVE_PUBLISH = "narrative_publish"
_EPISODE_FINALIZE = "episode_finalize"

_TURN_SCAN_SQL = (
    "SELECT "
    "t.id AS turn_id,t.session_id,t.status AS turn_status,t.state_delta_id,"
    "t.committed_story_revision,t.committed_world_revision,t.base_story_revision,"
    "t.narrative_block_id,"
    "s.world_id,s.worldline_id,s.status AS session_status,"
    "s.story_revision AS session_story_revision,"
    "s.committed_world_revision AS session_committed_world_revision,"
    "d.id AS delta_id,d.session_id AS delta_session_id,d.turn_id AS delta_turn_id,"
    "d.story_revision AS delta_story_revision,"
    "d.committed_world_revision AS delta_world_revision,"
    "n.id AS narrative_id,n.session_id AS narrative_session_id,"
    "n.source_story_revision AS narrative_story_revision,"
    "n.source_world_revision AS narrative_world_revision,"
    "n.source_state_delta_id AS narrative_delta_id,"
    "e.id AS episode_id,e.world_id AS episode_world_id,"
    "e.worldline_id AS episode_worldline_id,"
    "e.committed_world_revision AS episode_world_revision,"
    "ef.committed_world_revision AS episode_finalization_world_revision,"
    "edc.revision AS episode_domain_revision "
    "FROM turn_transactions AS t "
    "JOIN story_sessions AS s ON s.id=t.session_id "
    "LEFT JOIN story_state_deltas AS d ON d.id=t.state_delta_id "
    "LEFT JOIN narrative_blocks AS n ON n.turn_id=t.id "
    "LEFT JOIN episodes AS e ON e.session_id=s.id "
    "LEFT JOIN episode_finalizations AS ef ON ef.episode_id=e.id "
    "LEFT JOIN domain_commits AS edc ON edc.revision=e.committed_world_revision "
    "ORDER BY t.session_id,t.committed_story_revision,t.id"
)


@dataclass(frozen=True, slots=True)
class PostCommitReconciliationReport:
    """Counts from one read scan and its single scoped registration write."""

    scanned_turns: int
    registered_jobs: int
    succeeded_jobs: int
    blocked_jobs: int
    preserved_jobs: int
    unverifiable_turns: int


def _source_is_verified(row: dict) -> bool:
    return (
        row["turn_status"] in _COMMITTED_TURN_STATES
        and row["state_delta_id"] is not None
        and row["session_id"] is not None
        and row["committed_story_revision"] is not None
        and row["committed_world_revision"] is not None
        and row["state_delta_id"] == row["delta_id"]
        and row["delta_session_id"] == row["session_id"]
        and row["delta_turn_id"] == row["turn_id"]
        and row["delta_story_revision"] == row["committed_story_revision"]
        and row["delta_world_revision"] == row["committed_world_revision"]
    )


def _narrative_matches(row: dict) -> bool:
    return (
        row["narrative_id"] is not None
        and row["narrative_id"] == row["narrative_block_id"]
        and row["narrative_session_id"] == row["session_id"]
        and row["narrative_story_revision"] == row["committed_story_revision"]
        and row["narrative_world_revision"] == row["committed_world_revision"]
        and row["narrative_delta_id"] == row["state_delta_id"]
    )


def _episode_matches(row: dict) -> bool:
    episode_revision = row["episode_world_revision"]
    return (
        row["episode_id"] is not None
        and row["episode_world_id"] == row["world_id"]
        and row["episode_worldline_id"] == row["worldline_id"]
        and episode_revision is not None
        and episode_revision == row["episode_finalization_world_revision"]
        and episode_revision == row["episode_domain_revision"]
        and episode_revision == row["session_committed_world_revision"]
        and episode_revision > row["committed_world_revision"]
    )


def _registration(
    row: dict,
    *,
    kind: str,
    state: str,
    result_ref: str | None = None,
) -> PostCommitJobRegistration:
    """Build a stable, non-executable identity for legacy reconciliation."""
    # These hashes identify the reconciliation row only; blocked/succeeded
    # records are never treated as evidence of a runnable historical recipe.
    identity = {
        "kind": kind,
        "turn_id": row["turn_id"],
    }
    job_id_digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    input_identity = {
        "kind": kind,
        "turn_id": row["turn_id"],
        "session_id": row["session_id"],
        "state_delta_id": row["state_delta_id"],
        "source_story_revision": row["committed_story_revision"],
        "source_world_revision": row["committed_world_revision"],
        "result_ref": result_ref,
    }
    input_digest = hashlib.sha256(
        json.dumps(
            input_identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    spec = PostCommitJobSpec(
        job_id=f"reconcile-{kind}-{job_id_digest}",
        turn_id=row["turn_id"],
        session_id=row["session_id"],
        kind=kind,
        recipe_revision=_LEGACY_RECIPE_UNKNOWN,
        source_story_revision=row["committed_story_revision"],
        source_world_revision=row["committed_world_revision"],
        input_digest=input_digest,
    )
    return PostCommitJobRegistration(
        spec=spec,
        initial_state=state,
        initial_reason_code=(
            _LEGACY_RECIPE_UNKNOWN if state == "blocked" else None
        ),
        initial_result_ref=result_ref,
    )


def _plan_reconciliation(
    rows: list[dict],
) -> tuple[tuple[PostCommitJobRegistration, ...], set[str]]:
    planned: list[PostCommitJobRegistration] = []
    unverifiable: set[str] = set()
    by_session: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        by_session[row["session_id"]].append(row)
        if row["turn_status"] not in _COMMITTED_TURN_STATES:
            unverifiable.add(row["turn_id"])
            continue
        if not _source_is_verified(row):
            unverifiable.add(row["turn_id"])
            continue

        if _narrative_matches(row):
            planned.append(
                _registration(
                    row,
                    kind=_NARRATIVE_PUBLISH,
                    state="succeeded",
                    result_ref=row["narrative_id"],
                )
            )
        else:
            # A BeatPlan is only a narrative input, never proof of publication.
            planned.append(
                _registration(
                    row, kind=_NARRATIVE_PUBLISH, state="blocked"
                )
            )

    for session_rows in by_session.values():
        session = session_rows[0]
        if session["session_status"] not in {"closing", "finalized"}:
            if session["episode_id"] is not None:
                latest = _latest_verified_turn(session_rows)
                if latest is not None:
                    unverifiable.add(latest["turn_id"])
            continue

        latest = _latest_verified_turn(session_rows)
        if latest is None:
            continue
        story_revision = session["session_story_revision"]
        if (
            latest["committed_story_revision"] != story_revision
            or _has_uncertain_later_turn(session_rows, story_revision)
        ):
            unverifiable.add(latest["turn_id"])
            continue

        if session["session_status"] == "closing":
            if session["episode_id"] is not None:
                # Episode rows and the finalized session status commit together.
                unverifiable.add(latest["turn_id"])
                continue
            planned.append(
                _registration(
                    latest, kind=_EPISODE_FINALIZE, state="blocked"
                )
            )
        elif _episode_matches(latest):
            planned.append(
                _registration(
                    latest,
                    kind=_EPISODE_FINALIZE,
                    state="succeeded",
                    result_ref=latest["episode_id"],
                )
            )
        else:
            # A finalized session without a matching Episode/finalization commit
            # is inconsistent; do not manufacture a job identity for it.
            unverifiable.add(latest["turn_id"])

    return tuple(planned), unverifiable


def _latest_verified_turn(session_rows: list[dict]) -> dict | None:
    verified = [
        row
        for row in session_rows
        if row["turn_status"] in _COMMITTED_TURN_STATES
        and _source_is_verified(row)
    ]
    if not verified:
        return None
    story_revision = max(row["committed_story_revision"] for row in verified)
    latest = [
        row
        for row in verified
        if row["committed_story_revision"] == story_revision
    ]
    return latest[0] if len(latest) == 1 else None


def _has_uncertain_later_turn(
    session_rows: list[dict], latest_story_revision: int
) -> bool:
    return any(
        row["turn_status"] not in _COMMITTED_TURN_STATES
        and row["base_story_revision"] >= latest_story_revision
        for row in session_rows
    ) or any(
        row["turn_status"] in _COMMITTED_TURN_STATES
        and not _source_is_verified(row)
        and (
            row["committed_story_revision"] is None
            or row["committed_story_revision"] >= latest_story_revision
        )
        for row in session_rows
    )


class PostCommitReconciler:
    """Reconcile only durable source rows and artifacts; never run handlers."""

    def __init__(
        self,
        database: DatabaseManager,
        jobs: SQLitePostCommitJobRepository | None = None,
    ) -> None:
        self._database = database
        self._jobs = jobs or SQLitePostCommitJobRepository(database)

    async def reconcile(self) -> PostCommitReconciliationReport:
        # The read API is the only scan surface. The write transaction repeats
        # the source read under the writer lock so an artifact published between
        # the read and insert cannot be misclassified as missing.
        scanned = await self._database.read_world(_TURN_SCAN_SQL)
        scanned_count = len(scanned)

        def register_in_transaction(
            transaction: PostCommitJobTransaction,
        ) -> tuple[int, int, int, int, set[str]]:
            current = transaction.execute(_TURN_SCAN_SQL)
            planned, unverifiable = _plan_reconciliation(current)
            existing = transaction.execute(
                "SELECT job_id,turn_id,kind FROM post_commit_jobs"
            )
            existing_keys = {
                (row["turn_id"], row["kind"]) for row in existing
            }
            new_jobs = tuple(
                job
                for job in planned
                if (job.spec.turn_id, job.spec.kind) not in existing_keys
            )
            records = self._jobs.register(transaction, new_jobs)
            return (
                len(records),
                sum(record.state == "succeeded" for record in records),
                sum(record.state == "blocked" for record in records),
                len(existing),
                unverifiable,
            )

        (
            registered_count,
            succeeded_count,
            blocked_count,
            preserved_count,
            unverifiable,
        ) = await self._database.post_commit_job_write(register_in_transaction)
        return PostCommitReconciliationReport(
            scanned_turns=scanned_count,
            registered_jobs=registered_count,
            succeeded_jobs=succeeded_count,
            blocked_jobs=blocked_count,
            preserved_jobs=preserved_count,
            unverifiable_turns=len(unverifiable),
        )
