"""Durable W-V09 PlayerAdvice interpretation storage.

The first persisted interpretation for one input_turn is immutable command
evidence. It is not a Domain fact and never advances world_meta revision.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from application.advice_interpretation import (
    FrozenTurnInput,
    StoredPlayerAdvice,
)
from application.turn_input import TurnInputStatus
from contracts import BaseRevisions, InputMode, PlayerAdvice

from .database_manager import DatabaseManager, TurnCommandTransaction
from .database_schema import StorageError


class PlayerAdviceStorageConflict(StorageError):
    pass


def _canonical_advice(advice: PlayerAdvice) -> str:
    try:
        return json.dumps(
            advice.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise StorageError("PlayerAdvice is not canonical JSON") from None


def _stored(row: dict, *, replayed: bool) -> StoredPlayerAdvice:
    try:
        advice = PlayerAdvice.model_validate(json.loads(row["advice_json"]))
    except (TypeError, ValueError, json.JSONDecodeError):
        raise StorageError("Stored PlayerAdvice is invalid") from None
    canonical = _canonical_advice(advice)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if digest != row["advice_sha256"]:
        raise StorageError("Stored PlayerAdvice digest mismatch")
    return StoredPlayerAdvice(
        input_turn_id=row["input_turn_id"],
        advice=advice,
        interpreter_revision=row["interpreter_revision"],
        replayed=replayed,
    )


def _frozen(row: dict) -> FrozenTurnInput:
    return FrozenTurnInput(
        input_turn_id=row["input_turn_id"],
        session_id=row["session_id"],
        turn_id=row["turn_id"],
        idempotency_key=row["idempotency_key"],
        input_mode=InputMode(row["input_mode"]),
        raw_input=row["raw_input"],
        input_sha256=row["input_sha256"],
        base_revisions=BaseRevisions(
            world=row["base_world_revision"],
            character=row["base_character_revision"],
            story=row["base_story_revision"],
        ),
        status=TurnInputStatus(row["status"]),
        committed_world_revision=row["committed_world_revision"],
    )


class SQLitePlayerAdviceRepository:
    def __init__(self, database: DatabaseManager) -> None:
        self._database = database

    async def load_input(self, input_turn_id: str) -> FrozenTurnInput | None:
        rows = await self._database.read_world(
            "SELECT * FROM turn_intake_commands WHERE input_turn_id=?",
            (input_turn_id,),
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise StorageError("Turn input identity is ambiguous")
        return _frozen(rows[0])

    async def load_advice(self, input_turn_id: str) -> StoredPlayerAdvice | None:
        rows = await self._database.read_world(
            "SELECT * FROM turn_advice_interpretations WHERE input_turn_id=?",
            (input_turn_id,),
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise StorageError("PlayerAdvice identity is ambiguous")
        return _stored(rows[0], replayed=True)

    async def publish(
        self,
        input_turn_id: str,
        advice: PlayerAdvice,
        *,
        interpreter_revision: str,
    ) -> StoredPlayerAdvice:
        if not isinstance(advice, PlayerAdvice):
            raise StorageError("PlayerAdvice publication requires a typed value")
        if (
            not isinstance(interpreter_revision, str)
            or not interpreter_revision.strip()
            or len(interpreter_revision) > 256
            or "\x00" in interpreter_revision
        ):
            raise StorageError("Invalid PlayerAdvice interpreter revision")
        canonical = _canonical_advice(advice)
        advice_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        def apply(tx: TurnCommandTransaction):
            existing = tx.execute(
                "SELECT * FROM turn_advice_interpretations WHERE input_turn_id=?",
                (input_turn_id,),
            )
            if existing:
                if len(existing) != 1:
                    raise StorageError("PlayerAdvice identity is corrupted")
                return _stored(existing[0], replayed=True)

            inputs = tx.execute(
                "SELECT * FROM turn_intake_commands WHERE input_turn_id=?",
                (input_turn_id,),
            )
            if len(inputs) != 1:
                raise StorageError("PlayerAdvice input command not found")
            frozen = _frozen(inputs[0])
            if frozen.status is TurnInputStatus.CANCELLED:
                raise PlayerAdviceStorageConflict(
                    "Cancelled input cannot publish PlayerAdvice"
                )
            if frozen.status is not TurnInputStatus.RECEIVED:
                raise PlayerAdviceStorageConflict(
                    "Only a received input can publish first PlayerAdvice"
                )
            if (
                advice.turn_id != frozen.turn_id
                or advice.raw_input != frozen.raw_input
                or advice.input_mode is not frozen.input_mode
            ):
                raise PlayerAdviceStorageConflict(
                    "PlayerAdvice does not match durable input identity"
                )

            aliases = tx.execute(
                "SELECT input_turn_id FROM turn_advice_interpretations "
                "WHERE advice_id=? OR turn_id=?",
                (advice.id, advice.turn_id),
            )
            if aliases:
                raise PlayerAdviceStorageConflict(
                    "PlayerAdvice identity is already bound to another input"
                )

            tx.execute(
                "INSERT INTO turn_advice_interpretations("
                "input_turn_id,advice_id,turn_id,input_sha256,interpreter_revision,"
                "advice_sha256,advice_json) VALUES (?,?,?,?,?,?,?)",
                (
                    frozen.input_turn_id,
                    advice.id,
                    advice.turn_id,
                    frozen.input_sha256,
                    interpreter_revision,
                    advice_sha,
                    canonical,
                ),
            )
            rows = tx.execute(
                "SELECT * FROM turn_advice_interpretations WHERE input_turn_id=?",
                (input_turn_id,),
            )
            if len(rows) != 1:
                raise StorageError("PlayerAdvice was not durably inserted")
            return _stored(rows[0], replayed=False)

        return await self._database.turn_command_write(apply)
