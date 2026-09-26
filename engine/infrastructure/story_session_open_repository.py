"""SQLite adapter for durable Story Session Open and recovery."""
from __future__ import annotations

import hashlib
import json

from application.story_session_open import (
    OpenStorySessionCommand,
    StorySessionOpenError,
    StorySessionOpenPort,
    StorySessionOpenResult,
    StorySessionSnapshot,
    _freeze_command,
)
from contracts import StorySession

from .database_manager import (
    CommitRequest,
    DatabaseManager,
    DomainTransaction,
    IdempotencyConflict,
    RevisionConflict,
    StoredEvent,
)
from .story_session_repository import _canonical_json, _decode_story_session_row
from .story_bootstrap_repository import (
    bootstrap_digest,
    canonical_bootstrap_json,
    insert_bootstrap,
)

_ACTIVE_WORLDLINE_STATUSES = ("active", "suspended", "closing", "recovery_required")
_MAX_SQLITE_REVISION = 2**63 - 1


class SQLiteStorySessionOpenPort(StorySessionOpenPort):
    """Persist opens through the world database's single authoritative writer."""

    def __init__(self, database: DatabaseManager):
        self.database = database

    async def open_session(
        self, command: OpenStorySessionCommand
    ) -> StorySessionOpenResult:
        # Clone and validate nested Pydantic models before the first await so a
        # caller cannot mutate the operation while it waits in the writer queue.
        frozen = _freeze_command(command)
        initial = frozen.initial_session
        session_payload = initial.model_dump(mode="json", exclude_none=True)
        session_digest = hashlib.sha256(
            _canonical_json(initial).encode("utf-8")
        ).hexdigest()
        operation = {
            "kind": "story.session.open",
            "open_request_id": frozen.open_request_id,
            "initial_session": session_payload,
        }
        identity_seed = (
            f"story.session.open:v1\0{initial.id}\0{frozen.open_request_id}"
        )
        frozen_bootstrap_digest: str | None = None
        if frozen.bootstrap is not None:
            frozen_bootstrap_digest = bootstrap_digest(frozen.bootstrap)
            operation["bootstrap"] = json.loads(
                canonical_bootstrap_json(frozen.bootstrap)
            )
        identity_digest = hashlib.sha256(identity_seed.encode()).hexdigest()
        request = CommitRequest(
            worldline_id=initial.worldline_id,
            world_time=initial.story_state.world_time,
            expected_revision=frozen.store_expected_revision,
            idempotency_key=f"story-session-open:{identity_digest}",
            request_id=frozen.request_id,
            trace_id=frozen.trace_id,
            operation=operation,
            events=(
                StoredEvent(
                    event_id=f"story-session-open-event:{identity_digest}",
                    aggregate_id=initial.id,
                    event_type="story.session.opened",
                    payload={
                        "session_id": initial.id,
                        "story_revision": 0,
                    },
                ),
            ),
        )

        def apply(tx: DomainTransaction) -> dict[str, str]:
            existing_id = tx.execute(
                "SELECT id FROM story_sessions WHERE id=?",
                (initial.id,),
            )
            if existing_id:
                raise StorySessionOpenError("story_session_exists")

            status_marks = ",".join("?" for _ in _ACTIVE_WORLDLINE_STATUSES)
            existing_worldline = tx.execute(
                "SELECT id FROM story_sessions "
                f"WHERE worldline_id=? AND status IN ({status_marks}) LIMIT 1",
                (initial.worldline_id, *_ACTIVE_WORLDLINE_STATUSES),
            )
            if existing_worldline:
                raise StorySessionOpenError("worldline_has_open_session")

            tx.execute(
                "INSERT INTO story_sessions("
                "id,world_id,worldline_id,protagonist_id,story_seed_id,"
                "base_world_revision,base_character_revision,base_story_revision,"
                "story_revision,status,story_state_json,committed_world_revision"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    initial.id,
                    initial.world_id,
                    initial.worldline_id,
                    initial.protagonist_id,
                    initial.story_seed_id,
                    initial.base_revisions.world,
                    initial.base_revisions.character,
                    initial.base_revisions.story,
                    0,
                    initial.status.value,
                    _canonical_json(initial.story_state),
                    tx.revision,
                ),
            )
            if frozen.bootstrap is not None:
                insert_bootstrap(
                    tx,
                    frozen.bootstrap,
                    opened_store_revision=tx.revision,
                )
            result = {
                "session_id": initial.id,
                "initial_session_digest": session_digest,
            }
            if frozen_bootstrap_digest is not None:
                result["bootstrap_digest"] = frozen_bootstrap_digest
            return result

        try:
            committed = await self.database.commit_resolved(request, apply)
        except RevisionConflict:
            raise StorySessionOpenError("revision_conflict") from None
        except IdempotencyConflict:
            raise StorySessionOpenError("session_open_identity_conflict") from None

        expected_result = {
            "session_id": initial.id,
            "initial_session_digest": session_digest,
        }
        if frozen_bootstrap_digest is not None:
            expected_result["bootstrap_digest"] = frozen_bootstrap_digest
        if committed.value != expected_result:
            raise StorySessionOpenError("story_session_corrupt")

        snapshot = await self.load_snapshot(initial.id)
        return StorySessionOpenResult(
            snapshot=snapshot,
            opened_store_revision=committed.revision,
            replayed=committed.replayed,
        )

    async def load_snapshot(self, session_id: str) -> StorySessionSnapshot:
        if (
            not isinstance(session_id, str)
            or not session_id.strip()
            or len(session_id) > 256
            or "\x00" in session_id
        ):
            raise StorySessionOpenError("invalid_open_identity")

        rows = await self.database.read_world(
            "SELECT story_sessions.*, "
            "world_meta.revision AS observed_store_revision "
            "FROM story_sessions CROSS JOIN world_meta "
            "WHERE story_sessions.id=? AND world_meta.singleton=1",
            (session_id,),
        )
        if not rows:
            raise StorySessionOpenError("story_session_not_found")
        if len(rows) != 1:
            raise StorySessionOpenError("story_session_corrupt")

        row = rows[0]
        revision = row.get("observed_store_revision")
        if (
            isinstance(revision, bool)
            or not isinstance(revision, int)
            or not 0 <= revision <= _MAX_SQLITE_REVISION
        ):
            raise StorySessionOpenError("story_session_corrupt")
        try:
            persisted_session: StorySession = _decode_story_session_row(row)
        except (KeyError, TypeError, ValueError):
            raise StorySessionOpenError("story_session_corrupt") from None

        return StorySessionSnapshot(
            session=persisted_session,
            observed_store_revision=revision,
        )
