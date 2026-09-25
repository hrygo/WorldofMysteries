"""SQLite adapter for the Application StoryCommitPort."""
from __future__ import annotations

import json

from application.story_turn_commit import StoryCommitPort, StoryTurnCommitResult
from contracts import StateDelta, StorySession, StoryState, TurnTransaction

from .database_manager import (
    CommitRequest,
    DatabaseManager,
    DomainTransaction,
    RevisionConflict,
    StorageError,
    StoredEvent,
)


def _canonical_json(model) -> str:
    return json.dumps(
        model.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class SQLiteStorySessionCommitPort(StoryCommitPort):
    def __init__(self, database: DatabaseManager):
        self.database = database

    async def load_session(self, session_id: str) -> StorySession:
        rows = await self.database.read_world(
            "SELECT * FROM story_sessions WHERE id=?", (session_id,)
        )
        if len(rows) != 1:
            raise StorageError("StorySession not found")
        row = rows[0]
        state = StoryState.model_validate(json.loads(row["story_state_json"]))
        return StorySession.model_validate(
            {
                "schema_version": "1.0",
                "id": row["id"],
                "world_id": row["world_id"],
                "worldline_id": row["worldline_id"],
                "protagonist_id": row["protagonist_id"],
                "story_seed_id": row["story_seed_id"],
                "base_revisions": {
                    "world": row["base_world_revision"],
                    "character": row["base_character_revision"],
                    "story": row["base_story_revision"],
                },
                "story_state": state.model_dump(mode="json", exclude_none=True),
                "status": row["status"],
            }
        )

    async def load_delta(self, delta_id: str) -> StateDelta:
        rows = await self.database.read_world(
            "SELECT payload_json FROM story_state_deltas WHERE id=?", (delta_id,)
        )
        if len(rows) != 1:
            raise StorageError("StateDelta not found")
        return StateDelta.model_validate(json.loads(rows[0]["payload_json"]))

    async def load_turn(self, turn_id: str) -> TurnTransaction:
        rows = await self.database.read_world(
            "SELECT transaction_json FROM turn_transactions WHERE id=?", (turn_id,)
        )
        if len(rows) != 1:
            raise StorageError("TurnTransaction not found")
        return TurnTransaction.model_validate(json.loads(rows[0]["transaction_json"]))

    async def commit_turn(
        self,
        session: StorySession,
        delta: StateDelta,
        turn: TurnTransaction,
        *,
        store_expected_revision: int,
        request_id: str,
        trace_id: str,
    ) -> StoryTurnCommitResult:
        if session.story_state.world_time is None:
            raise StorageError("Committed StoryState requires world_time")
        if turn.committed_story_revision != session.story_state.revision:
            raise StorageError("Committed turn/story revisions differ")

        operation = {
            "kind": "story.turn.commit",
            "session_id": session.id,
            "turn_id": turn.id,
            "state_delta_id": delta.id,
            "story_revision": session.story_state.revision,
            "domain_base_world_revision": session.base_revisions.world,
            "domain_base_character_revision": session.base_revisions.character,
        }
        event = StoredEvent(
            event_id=f"story.turn.{turn.id}.r{session.story_state.revision}",
            aggregate_id=session.id,
            event_type="story.turn.committed",
            payload={
                "state_delta_id": delta.id,
                "story_revision": session.story_state.revision,
                "outcome": delta.outcome,
            },
            cause_id=delta.id,
            turn_id=turn.id,
        )
        request = CommitRequest(
            worldline_id=session.worldline_id,
            world_time=session.story_state.world_time,
            expected_revision=store_expected_revision,
            idempotency_key=turn.idempotency_key,
            request_id=request_id,
            trace_id=trace_id,
            operation=operation,
            events=(event,),
        )

        def apply(tx: DomainTransaction):
            intake_rows = tx.execute(
                "SELECT * FROM turn_intake_commands WHERE turn_id=?",
                (turn.id,),
            )
            intake = None
            if intake_rows:
                if len(intake_rows) != 1:
                    raise StorageError("Turn intake identity is corrupted")
                intake = intake_rows[0]
                if (
                    intake["session_id"] != session.id
                    or intake["idempotency_key"] != turn.idempotency_key
                    or intake["base_world_revision"] != turn.base_revisions.world
                    or intake["base_character_revision"] != turn.base_revisions.character
                    or intake["base_story_revision"] != turn.base_revisions.story
                ):
                    raise StorageError("Turn intake does not match committed turn")
                if intake["status"] == "cancelled":
                    raise StorageError("Turn intake was cancelled before COMMIT")
                if intake["status"] != "received":
                    raise StorageError("Turn intake is not committable")

            existing = tx.execute(
                "SELECT id,world_id,worldline_id,story_revision,status "
                "FROM story_sessions WHERE id=?",
                (session.id,),
            )
            if existing:
                current = existing[0]
                if (
                    current["world_id"] != session.world_id
                    or current["worldline_id"] != session.worldline_id
                ):
                    raise StorageError("StorySession identity mismatch")
                if current["story_revision"] != turn.base_revisions.story:
                    raise RevisionConflict("Story revision does not match")
                tx.execute(
                    "UPDATE story_sessions SET story_revision=?,status=?,story_state_json=?,"
                    "committed_world_revision=? WHERE id=?",
                    (
                        session.story_state.revision,
                        session.status.value,
                        _canonical_json(session.story_state),
                        tx.revision,
                        session.id,
                    ),
                )
            else:
                if turn.base_revisions.story != 0:
                    raise RevisionConflict("StorySession is missing its prior revision")
                tx.execute(
                    "INSERT INTO story_sessions("
                    "id,world_id,worldline_id,protagonist_id,story_seed_id,"
                    "base_world_revision,base_character_revision,base_story_revision,"
                    "story_revision,status,story_state_json,committed_world_revision"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        session.id,
                        session.world_id,
                        session.worldline_id,
                        session.protagonist_id,
                        session.story_seed_id,
                        session.base_revisions.world,
                        session.base_revisions.character,
                        session.base_revisions.story,
                        session.story_state.revision,
                        session.status.value,
                        _canonical_json(session.story_state),
                        tx.revision,
                    ),
                )

            tx.execute(
                "INSERT INTO story_state_deltas("
                "id,session_id,turn_id,story_revision,payload_json,committed_world_revision"
                ") VALUES (?,?,?,?,?,?)",
                (
                    delta.id,
                    session.id,
                    turn.id,
                    session.story_state.revision,
                    _canonical_json(delta),
                    tx.revision,
                ),
            )
            tx.execute(
                "INSERT INTO turn_transactions("
                "id,session_id,idempotency_key,status,"
                "base_world_revision,base_character_revision,base_story_revision,"
                "player_advice_id,action_intent_id,state_delta_id,"
                "committed_story_revision,narrative_block_id,transaction_json,"
                "committed_world_revision"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    turn.id,
                    session.id,
                    turn.idempotency_key,
                    turn.status.value,
                    turn.base_revisions.world,
                    turn.base_revisions.character,
                    turn.base_revisions.story,
                    turn.player_advice_id,
                    turn.action_intent_id,
                    turn.state_delta_id,
                    turn.committed_story_revision,
                    turn.narrative_block_id,
                    _canonical_json(turn),
                    tx.revision,
                ),
            )
            if intake is not None:
                tx.execute(
                    "UPDATE turn_intake_commands "
                    "SET status='committed',committed_world_revision=? "
                    "WHERE turn_id=? AND status='received'",
                    (tx.revision, turn.id),
                )
                intake_after = tx.execute(
                    "SELECT status,committed_world_revision FROM turn_intake_commands WHERE turn_id=?",
                    (turn.id,),
                )
                if (
                    len(intake_after) != 1
                    or intake_after[0]["status"] != "committed"
                    or intake_after[0]["committed_world_revision"] != tx.revision
                ):
                    raise StorageError("Turn intake was not atomically promoted at COMMIT")

            return {
                "session_id": session.id,
                "turn_id": turn.id,
                "state_delta_id": delta.id,
                "story_revision": session.story_state.revision,
            }

        committed = await self.database.commit_resolved(request, apply)
        expected = {
            "session_id": session.id,
            "turn_id": turn.id,
            "state_delta_id": delta.id,
            "story_revision": session.story_state.revision,
        }
        if committed.value != expected:
            raise StorageError("Idempotent Story commit result does not match request")

        # Re-read authoritative rows even on the first commit. This proves the
        # result exposed to Application is exactly what survived SQLite COMMIT.
        persisted_session = await self.load_session(session.id)
        persisted_delta = await self.load_delta(delta.id)
        persisted_turn = await self.load_turn(turn.id)
        return StoryTurnCommitResult(
            store_revision=committed.revision,
            session=persisted_session,
            turn=persisted_turn,
            delta=persisted_delta,
            replayed=committed.replayed,
        )
