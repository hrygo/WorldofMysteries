"""Durable post-COMMIT BeatPlan publication and reads.

A BeatPlan is frozen expression, never a fact source: it is admitted only after
the authoritative turn has COMMITted, is unique per turn, and replays
idempotently. Turn status advances COMMITTED -> BEAT_READY; the NarrativeBlock
repository then accepts the same turn and advances it to NARRATIVE_READY.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from contracts import BeatPlan, TurnStatus, TurnTransaction

from .database_manager import DatabaseManager, PostCommitTransaction, StorageError


def _canonical_json(model) -> str:
    return json.dumps(
        model.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


@dataclass(frozen=True, slots=True)
class BeatPlanPublishResult:
    turn: TurnTransaction
    beat_plan: BeatPlan
    replayed: bool


class SQLiteBeatPlanRepository:
    """Authoritative post-COMMIT beat plan store."""

    _PUBLISHABLE = frozenset({TurnStatus.COMMITTED})
    _ALREADY_PUBLISHED = frozenset(
        {TurnStatus.BEAT_READY, TurnStatus.NARRATIVE_READY, TurnStatus.AUDIO_READY, TurnStatus.DELIVERED}
    )

    def __init__(self, database: DatabaseManager):
        self.database = database

    async def load_turn(self, turn_id: str) -> TurnTransaction:
        rows = await self.database.read_world(
            "SELECT transaction_json FROM turn_transactions WHERE id=?", (turn_id,)
        )
        if len(rows) != 1:
            raise StorageError("TurnTransaction not found")
        return TurnTransaction.model_validate(json.loads(rows[0]["transaction_json"]))

    async def load_beat_plan(self, beat_plan_id: str) -> BeatPlan:
        rows = await self.database.read_world(
            "SELECT payload_json FROM beat_plans WHERE id=?", (beat_plan_id,)
        )
        if len(rows) != 1:
            raise StorageError("BeatPlan not found")
        return BeatPlan.model_validate(json.loads(rows[0]["payload_json"]))

    async def load_turn_beat_plan(self, turn_id: str) -> BeatPlan | None:
        rows = await self.database.read_world(
            "SELECT id FROM beat_plans WHERE turn_id=?", (turn_id,)
        )
        if not rows:
            return None
        return await self.load_beat_plan(rows[0]["id"])

    async def publish(
        self,
        *,
        turn_id: str,
        beat_plan: BeatPlan,
    ) -> BeatPlanPublishResult:
        if not isinstance(beat_plan, BeatPlan):
            raise StorageError("BeatPlan publication requires a typed BeatPlan")

        # Freeze caller-owned model state before queue admission.
        payload_json = _canonical_json(beat_plan)
        frozen_beat = BeatPlan.model_validate_json(payload_json)

        def apply(tx: PostCommitTransaction):
            turn_rows = tx.execute(
                "SELECT transaction_json,committed_world_revision FROM turn_transactions WHERE id=?",
                (turn_id,),
            )
            if len(turn_rows) != 1:
                raise StorageError("TurnTransaction not found")
            current = TurnTransaction.model_validate(
                json.loads(turn_rows[0]["transaction_json"])
            )
            if current.id != turn_id:
                raise StorageError("TurnTransaction identity mismatch")
            if current.committed_story_revision is None:
                raise StorageError("BeatPlan publication requires a committed story revision")
            source_world_revision = turn_rows[0]["committed_world_revision"]
            if type(source_world_revision) is not int or source_world_revision <= 0:
                raise StorageError("BeatPlan publication requires a committed world revision")
            if frozen_beat.story_session_id != current.session_id:
                raise StorageError("BeatPlan belongs to another StorySession")
            if frozen_beat.source_story_revision != current.committed_story_revision:
                raise StorageError("BeatPlan story revision does not match committed turn")

            existing_rows = tx.execute(
                "SELECT id,payload_json FROM beat_plans WHERE turn_id=?", (turn_id,)
            )
            if existing_rows:
                if len(existing_rows) != 1:
                    raise StorageError("BeatPlan turn uniqueness is corrupted")
                existing = existing_rows[0]
                if (
                    existing["id"] != frozen_beat.id
                    or existing["payload_json"] != payload_json
                    or current.status not in self._ALREADY_PUBLISHED
                ):
                    raise StorageError("Turn already has a different BeatPlan")
                return {"turn": current, "beat_plan": frozen_beat, "replayed": True}

            if current.status not in self._PUBLISHABLE:
                raise StorageError("Turn is not ready for BeatPlan publication")

            tx.execute(
                "INSERT INTO beat_plans("
                "id,turn_id,session_id,source_story_revision,source_world_revision,"
                "payload_json"
                ") VALUES (?,?,?,?,?,?)",
                (
                    frozen_beat.id,
                    current.id,
                    frozen_beat.story_session_id,
                    frozen_beat.source_story_revision,
                    source_world_revision,
                    payload_json,
                ),
            )
            updated = current.model_copy(update={"status": TurnStatus.BEAT_READY})
            updated_json = _canonical_json(updated)
            tx.execute(
                "UPDATE turn_transactions SET status=?,transaction_json=? WHERE id=?",
                (updated.status.value, updated_json, current.id),
            )
            persisted = tx.execute(
                "SELECT status,transaction_json FROM turn_transactions WHERE id=?",
                (current.id,),
            )
            if len(persisted) != 1 or persisted[0]["status"] != TurnStatus.BEAT_READY.value:
                raise StorageError("BeatPlan publication did not persist turn status")
            if persisted[0]["transaction_json"] != updated_json:
                raise StorageError("BeatPlan publication turn JSON is inconsistent")
            return {"turn": updated, "beat_plan": frozen_beat, "replayed": False}

        result = await self.database.post_commit_write(apply)
        authoritative_turn = await self.load_turn(turn_id)
        authoritative_beat = await self.load_beat_plan(frozen_beat.id)
        if authoritative_turn != result["turn"] or authoritative_beat != result["beat_plan"]:
            raise StorageError("Post-COMMIT BeatPlan result differs from durable state")
        return BeatPlanPublishResult(
            turn=authoritative_turn,
            beat_plan=authoritative_beat,
            replayed=bool(result["replayed"]),
        )
