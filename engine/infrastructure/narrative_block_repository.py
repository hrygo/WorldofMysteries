"""Durable post-COMMIT NarrativeBlock publication and disclosure reads."""
from __future__ import annotations

from dataclasses import dataclass
import json

from contracts import NarrativeBlock, TurnStatus, TurnTransaction

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
class NarrativePublishResult:
    turn: TurnTransaction
    narrative: NarrativeBlock
    replayed: bool


class SQLiteNarrativeBlockRepository:
    """Authoritative post-COMMIT narrative store and AudioDisclosurePort adapter."""

    _PUBLISHABLE = frozenset({TurnStatus.COMMITTED, TurnStatus.BEAT_READY})
    _ALREADY_PUBLISHED = frozenset(
        {TurnStatus.NARRATIVE_READY, TurnStatus.AUDIO_READY, TurnStatus.DELIVERED}
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

    async def load_narrative_block(self, narrative_block_id: str) -> NarrativeBlock:
        rows = await self.database.read_world(
            "SELECT payload_json FROM narrative_blocks WHERE id=?", (narrative_block_id,)
        )
        if len(rows) != 1:
            raise StorageError("NarrativeBlock not found")
        return NarrativeBlock.model_validate(json.loads(rows[0]["payload_json"]))

    async def publish(
        self,
        *,
        turn_id: str,
        narrative: NarrativeBlock,
    ) -> NarrativePublishResult:
        if not isinstance(narrative, NarrativeBlock):
            raise StorageError("Narrative publication requires a typed NarrativeBlock")

        # Freeze caller-owned model state before queue admission. Pydantic models
        # are mutable by default; writer contention must not let later caller
        # mutation alter the durable payload or identity checks.
        payload_json = _canonical_json(narrative)
        frozen_narrative = NarrativeBlock.model_validate_json(payload_json)
        if frozen_narrative.source_state_delta_id is None:
            raise StorageError("NarrativeBlock must reference the committed StateDelta")

        def apply(tx: PostCommitTransaction):
            turn_rows = tx.execute(
                "SELECT transaction_json FROM turn_transactions WHERE id=?", (turn_id,)
            )
            if len(turn_rows) != 1:
                raise StorageError("TurnTransaction not found")
            current = TurnTransaction.model_validate(
                json.loads(turn_rows[0]["transaction_json"])
            )
            if current.id != turn_id:
                raise StorageError("TurnTransaction identity mismatch")
            if current.committed_story_revision is None:
                raise StorageError("Narrative publication requires a committed story revision")
            if frozen_narrative.story_session_id != current.session_id:
                raise StorageError("NarrativeBlock belongs to another StorySession")
            if frozen_narrative.source_story_revision != current.committed_story_revision:
                raise StorageError("NarrativeBlock story revision does not match committed turn")
            if frozen_narrative.source_state_delta_id != current.state_delta_id:
                raise StorageError("NarrativeBlock StateDelta does not match committed turn")

            existing_rows = tx.execute(
                "SELECT id,payload_json FROM narrative_blocks WHERE turn_id=?", (turn_id,)
            )
            if existing_rows:
                if len(existing_rows) != 1:
                    raise StorageError("NarrativeBlock turn uniqueness is corrupted")
                existing = existing_rows[0]
                if (
                    current.narrative_block_id != existing["id"]
                    or existing["id"] != frozen_narrative.id
                    or existing["payload_json"] != payload_json
                    or current.status not in self._ALREADY_PUBLISHED
                ):
                    raise StorageError("Turn already has a different NarrativeBlock")
                return {"turn": current, "narrative": frozen_narrative, "replayed": True}

            if current.narrative_block_id is not None:
                raise StorageError("Turn references a missing or conflicting NarrativeBlock")
            if current.status not in self._PUBLISHABLE:
                raise StorageError("Turn is not ready for NarrativeBlock publication")

            tx.execute(
                "INSERT INTO narrative_blocks("
                "id,turn_id,session_id,source_story_revision,source_state_delta_id,payload_json"
                ") VALUES (?,?,?,?,?,?)",
                (
                    frozen_narrative.id,
                    current.id,
                    frozen_narrative.story_session_id,
                    frozen_narrative.source_story_revision,
                    frozen_narrative.source_state_delta_id,
                    payload_json,
                ),
            )
            updated = current.model_copy(
                update={
                    "status": TurnStatus.NARRATIVE_READY,
                    "narrative_block_id": frozen_narrative.id,
                }
            )
            updated_json = _canonical_json(updated)
            tx.execute(
                "UPDATE turn_transactions SET status=?,narrative_block_id=?,transaction_json=? "
                "WHERE id=?",
                (
                    updated.status.value,
                    frozen_narrative.id,
                    updated_json,
                    current.id,
                ),
            )
            persisted = tx.execute(
                "SELECT status,narrative_block_id,transaction_json FROM turn_transactions WHERE id=?",
                (current.id,),
            )
            if len(persisted) != 1 or persisted[0]["status"] != TurnStatus.NARRATIVE_READY.value:
                raise StorageError("Narrative publication did not persist turn status")
            if persisted[0]["narrative_block_id"] != frozen_narrative.id:
                raise StorageError("Narrative publication did not persist narrative identity")
            if persisted[0]["transaction_json"] != updated_json:
                raise StorageError("Narrative publication turn JSON is inconsistent")
            return {"turn": updated, "narrative": frozen_narrative, "replayed": False}

        result = await self.database.post_commit_write(apply)
        authoritative_turn = await self.load_turn(turn_id)
        authoritative_narrative = await self.load_narrative_block(frozen_narrative.id)
        if authoritative_turn != result["turn"] or authoritative_narrative != result["narrative"]:
            raise StorageError("Post-COMMIT narrative result differs from durable state")
        return NarrativePublishResult(
            turn=authoritative_turn,
            narrative=authoritative_narrative,
            replayed=bool(result["replayed"]),
        )
