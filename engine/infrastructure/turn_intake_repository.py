"""Durable W-V09 pre-COMMIT input-turn command storage.

A FinalTranscript/text input first receives a stable command identity here.
RECEIVED/CANCELLED never advance world facts. Domain COMMIT uses the same
DatabaseManager writer and atomically promotes the matching command to COMMITTED.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib

from application.turn_input import (
    TurnInputCommand,
    TurnInputReceipt,
    TurnInputStatus as ApplicationTurnInputStatus,
)
from contracts import BaseRevisions, InputMode

from .database_manager import DatabaseManager, TurnCommandTransaction
from .database_schema import StorageError


_ID_LIMIT = 256
_INPUT_LIMIT = 16_384


class TurnIntakeConflict(StorageError):
    pass


class TurnIntakeStatus(StrEnum):
    RECEIVED = "received"
    CANCELLED = "cancelled"
    COMMITTED = "committed"


def _identifier(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > _ID_LIMIT
        or "\x00" in value
    ):
        raise StorageError(f"Invalid turn intake {field}")
    return value


@dataclass(frozen=True, slots=True)
class TurnIntakeRequest:
    input_turn_id: str
    session_id: str
    turn_id: str
    idempotency_key: str
    input_mode: InputMode
    raw_input: str
    base_revisions: BaseRevisions

    def __post_init__(self) -> None:
        for value, field in (
            (self.input_turn_id, "input turn id"),
            (self.session_id, "session id"),
            (self.turn_id, "turn id"),
            (self.idempotency_key, "idempotency key"),
        ):
            _identifier(value, field)
        if not isinstance(self.input_mode, InputMode):
            raise StorageError("Invalid turn intake input mode")
        if (
            not isinstance(self.raw_input, str)
            or not self.raw_input.strip()
            or len(self.raw_input) > _INPUT_LIMIT
            or "\x00" in self.raw_input
        ):
            raise StorageError("Invalid turn intake raw input")
        if not isinstance(self.base_revisions, BaseRevisions):
            raise StorageError("Invalid turn intake base revisions")

    @property
    def input_sha256(self) -> str:
        return hashlib.sha256(self.raw_input.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TurnIntakeRecord:
    input_turn_id: str
    session_id: str
    turn_id: str
    idempotency_key: str
    input_mode: InputMode
    raw_input: str
    input_sha256: str
    base_revisions: BaseRevisions
    status: TurnIntakeStatus
    committed_world_revision: int | None


@dataclass(frozen=True, slots=True)
class TurnIntakeReceiveResult:
    record: TurnIntakeRecord
    replayed: bool


def _from_row(row: dict) -> TurnIntakeRecord:
    return TurnIntakeRecord(
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
        status=TurnIntakeStatus(row["status"]),
        committed_world_revision=row["committed_world_revision"],
    )


def _same_request(record: TurnIntakeRecord, request: TurnIntakeRequest) -> bool:
    return (
        record.input_turn_id == request.input_turn_id
        and record.session_id == request.session_id
        and record.turn_id == request.turn_id
        and record.idempotency_key == request.idempotency_key
        and record.input_mode is request.input_mode
        and record.raw_input == request.raw_input
        and record.input_sha256 == request.input_sha256
        and record.base_revisions == request.base_revisions
    )


class SQLiteTurnIntakeRepository:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    async def receive(self, request: TurnIntakeRequest) -> TurnIntakeReceiveResult:
        if not isinstance(request, TurnIntakeRequest):
            raise StorageError("Turn intake requires a typed request")

        def apply(tx: TurnCommandTransaction):
            rows = tx.execute(
                "SELECT * FROM turn_intake_commands "
                "WHERE input_turn_id=? OR turn_id=? OR idempotency_key=?",
                (request.input_turn_id, request.turn_id, request.idempotency_key),
            )
            if rows:
                if len(rows) != 1:
                    raise TurnIntakeConflict("Turn intake identity aliases conflict")
                current = _from_row(rows[0])
                if not _same_request(current, request):
                    raise TurnIntakeConflict(
                        "Turn intake identity is already bound to different input"
                    )
                return {"record": current, "replayed": True}

            tx.execute(
                "INSERT INTO turn_intake_commands("
                "input_turn_id,session_id,turn_id,idempotency_key,input_mode,"
                "raw_input,input_sha256,base_world_revision,base_character_revision,"
                "base_story_revision,status,committed_world_revision"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)",
                (
                    request.input_turn_id,
                    request.session_id,
                    request.turn_id,
                    request.idempotency_key,
                    request.input_mode.value,
                    request.raw_input,
                    request.input_sha256,
                    request.base_revisions.world,
                    request.base_revisions.character,
                    request.base_revisions.story,
                    TurnIntakeStatus.RECEIVED.value,
                ),
            )
            rows = tx.execute(
                "SELECT * FROM turn_intake_commands WHERE input_turn_id=?",
                (request.input_turn_id,),
            )
            if len(rows) != 1:
                raise StorageError("Turn intake was not durably inserted")
            return {"record": _from_row(rows[0]), "replayed": False}

        result = await self.database.turn_command_write(apply)
        return TurnIntakeReceiveResult(
            record=result["record"],
            replayed=bool(result["replayed"]),
        )

    async def find(self, input_turn_id: str) -> TurnIntakeRecord | None:
        _identifier(input_turn_id, "input turn id")
        rows = await self.database.read_world(
            "SELECT * FROM turn_intake_commands WHERE input_turn_id=?",
            (input_turn_id,),
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise StorageError("Turn intake identity is corrupted")
        return _from_row(rows[0])

    async def load(self, input_turn_id: str) -> TurnIntakeRecord:
        value = await self.find(input_turn_id)
        if value is None:
            raise StorageError("Turn intake command not found")
        return value

    async def cancel(self, input_turn_id: str) -> TurnIntakeRecord:
        _identifier(input_turn_id, "input turn id")

        def apply(tx: TurnCommandTransaction):
            rows = tx.execute(
                "SELECT * FROM turn_intake_commands WHERE input_turn_id=?",
                (input_turn_id,),
            )
            if len(rows) != 1:
                raise StorageError("Turn intake command not found")
            current = _from_row(rows[0])
            if current.status is TurnIntakeStatus.COMMITTED:
                raise TurnIntakeConflict("Committed turn intake cannot be cancelled")
            if current.status is TurnIntakeStatus.CANCELLED:
                return current
            tx.execute(
                "UPDATE turn_intake_commands SET status='cancelled' "
                "WHERE input_turn_id=? AND status='received'",
                (input_turn_id,),
            )
            rows = tx.execute(
                "SELECT * FROM turn_intake_commands WHERE input_turn_id=?",
                (input_turn_id,),
            )
            updated = _from_row(rows[0])
            if updated.status is not TurnIntakeStatus.CANCELLED:
                raise StorageError("Turn intake cancellation did not persist")
            return updated

        return await self.database.turn_command_write(apply)



def _to_application_receipt(
    record: TurnIntakeRecord,
    *,
    replayed: bool,
) -> TurnInputReceipt:
    return TurnInputReceipt(
        input_turn_id=record.input_turn_id,
        session_id=record.session_id,
        turn_id=record.turn_id,
        idempotency_key=record.idempotency_key,
        input_mode=record.input_mode,
        input_sha256=record.input_sha256,
        base_revisions=record.base_revisions,
        status=ApplicationTurnInputStatus(record.status.value),
        committed_world_revision=record.committed_world_revision,
        replayed=replayed,
    )


class SQLiteTurnInputCommandPort:
    """Application DurableTurnIntakePort adapter over SQLite storage."""

    def __init__(self, database: DatabaseManager) -> None:
        self._repository = SQLiteTurnIntakeRepository(database)

    async def load(self, input_turn_id: str) -> TurnInputReceipt | None:
        record = await self._repository.find(input_turn_id)
        return None if record is None else _to_application_receipt(
            record,
            replayed=True,
        )

    async def receive(self, command: TurnInputCommand) -> TurnInputReceipt:
        if not isinstance(command, TurnInputCommand):
            raise StorageError("Turn input port requires a typed command")
        request = TurnIntakeRequest(
            input_turn_id=command.input_turn_id,
            session_id=command.session_id,
            turn_id=command.turn_id,
            idempotency_key=command.idempotency_key,
            input_mode=command.input_mode,
            raw_input=command.raw_input,
            base_revisions=command.base_revisions,
        )
        if request.input_sha256 != command.input_sha256:
            raise TurnIntakeConflict(
                "Turn input command digest does not match raw input"
            )
        result = await self._repository.receive(request)
        return _to_application_receipt(
            result.record,
            replayed=result.replayed,
        )

    async def cancel(self, input_turn_id: str) -> TurnInputReceipt:
        record = await self._repository.cancel(input_turn_id)
        return _to_application_receipt(record, replayed=False)
