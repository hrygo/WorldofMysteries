"""W-V09 finalized input command routing.

A finalized voice/text input becomes a durable turn command before AI reasoning.
Lost-ACK recovery always checks the durable input-turn identity first, so a retry
cannot accidentally capture a newer Story revision. Presentation ControlIntents
are explicitly routed away from the Story intake port.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import hashlib
from typing import Protocol

from contracts import BaseRevisions, InputMode, StorySession, StorySessionStatus


class StoryInputCommandError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TurnInputStatus(StrEnum):
    RECEIVED = "received"
    CANCELLED = "cancelled"
    COMMITTED = "committed"


@dataclass(frozen=True, slots=True)
class FinalizedStoryInput:
    input_turn_id: str
    session_id: str
    input_mode: InputMode
    raw_input: str


@dataclass(frozen=True, slots=True)
class TurnInputCommand:
    input_turn_id: str
    session_id: str
    turn_id: str
    idempotency_key: str
    input_mode: InputMode
    raw_input: str
    input_sha256: str
    base_revisions: BaseRevisions


@dataclass(frozen=True, slots=True)
class TurnInputReceipt:
    input_turn_id: str
    session_id: str
    turn_id: str
    idempotency_key: str
    input_mode: InputMode
    input_sha256: str
    base_revisions: BaseRevisions
    status: TurnInputStatus
    committed_world_revision: int | None
    replayed: bool = False


class DurableTurnIntakePort(Protocol):
    async def load(self, input_turn_id: str) -> TurnInputReceipt | None: ...

    async def receive(self, command: TurnInputCommand) -> TurnInputReceipt: ...

    async def cancel(self, input_turn_id: str) -> TurnInputReceipt: ...


class StorySessionReadPort(Protocol):
    async def load_session(self, session_id: str) -> StorySession: ...


class ControlIntentKind(StrEnum):
    STOP = "stop"
    CONTINUE = "continue"
    SET_VOLUME = "set_volume"


@dataclass(frozen=True, slots=True)
class ControlIntent:
    kind: ControlIntentKind
    volume: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ControlIntentKind):
            raise StoryInputCommandError("invalid_control_intent")
        if self.kind is ControlIntentKind.SET_VOLUME:
            if (
                isinstance(self.volume, bool)
                or not isinstance(self.volume, (int, float))
                or not 0.0 <= float(self.volume) <= 1.0
            ):
                raise StoryInputCommandError("invalid_control_volume")
        elif self.volume is not None:
            raise StoryInputCommandError("unexpected_control_volume")


class ControlIntentPort(Protocol):
    async def execute(self, intent: ControlIntent) -> None: ...


def _bounded(value: str, field: str, *, limit: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or "\x00" in value
    ):
        raise StoryInputCommandError(f"invalid_{field}")
    return value


def _input_digest(raw_input: str) -> str:
    return hashlib.sha256(raw_input.encode("utf-8")).hexdigest()


def _turn_identity(session_id: str, input_turn_id: str) -> tuple[str, str]:
    seed = f"wom-turn-input/v1\0{session_id}\0{input_turn_id}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    return f"turn_{digest[:32]}", f"turn-input:{digest}"


class StoryTurnInputService:
    def __init__(
        self,
        *,
        sessions: StorySessionReadPort,
        intake: DurableTurnIntakePort,
    ) -> None:
        self._sessions = sessions
        self._intake = intake

    async def receive(self, value: FinalizedStoryInput) -> TurnInputReceipt:
        if not isinstance(value, FinalizedStoryInput):
            raise StoryInputCommandError("invalid_story_input")
        _bounded(value.input_turn_id, "input_turn_id")
        _bounded(value.session_id, "session_id")
        if not isinstance(value.input_mode, InputMode):
            raise StoryInputCommandError("invalid_input_mode")
        _bounded(value.raw_input, "raw_input", limit=16_384)
        digest = _input_digest(value.raw_input)

        # Recovery precedes current-session lookup. A lost ACK may be retried after
        # later turns have advanced Story revision; the original frozen command wins.
        existing = await self._intake.load(value.input_turn_id)
        if existing is not None:
            if (
                existing.session_id != value.session_id
                or existing.input_mode is not value.input_mode
                or existing.input_sha256 != digest
            ):
                raise StoryInputCommandError("input_turn_identity_conflict")
            return replace(existing, replayed=True)

        session = await self._sessions.load_session(value.session_id)
        if not isinstance(session, StorySession) or session.id != value.session_id:
            raise StoryInputCommandError("story_session_identity_mismatch")
        if session.status is not StorySessionStatus.ACTIVE:
            raise StoryInputCommandError("story_session_not_active")

        turn_id, idempotency_key = _turn_identity(
            value.session_id,
            value.input_turn_id,
        )
        command = TurnInputCommand(
            input_turn_id=value.input_turn_id,
            session_id=value.session_id,
            turn_id=turn_id,
            idempotency_key=idempotency_key,
            input_mode=value.input_mode,
            raw_input=value.raw_input,
            input_sha256=digest,
            base_revisions=BaseRevisions(
                world=session.base_revisions.world,
                character=session.base_revisions.character,
                story=session.story_state.revision,
            ),
        )
        receipt = await self._intake.receive(command)
        self._require_receipt_matches(command, receipt)
        return receipt

    async def recover(self, input_turn_id: str) -> TurnInputReceipt:
        _bounded(input_turn_id, "input_turn_id")
        receipt = await self._intake.load(input_turn_id)
        if receipt is None:
            raise StoryInputCommandError("input_turn_not_found")
        return receipt

    async def cancel(self, input_turn_id: str) -> TurnInputReceipt:
        _bounded(input_turn_id, "input_turn_id")
        return await self._intake.cancel(input_turn_id)

    @staticmethod
    def _require_receipt_matches(
        command: TurnInputCommand,
        receipt: TurnInputReceipt,
    ) -> None:
        if (
            receipt.input_turn_id != command.input_turn_id
            or receipt.session_id != command.session_id
            or receipt.turn_id != command.turn_id
            or receipt.idempotency_key != command.idempotency_key
            or receipt.input_mode is not command.input_mode
            or receipt.input_sha256 != command.input_sha256
            or receipt.base_revisions != command.base_revisions
        ):
            raise StoryInputCommandError("durable_intake_receipt_mismatch")


@dataclass(frozen=True, slots=True)
class RoutedControlIntent:
    intent: ControlIntent


class InputCommandRouter:
    """Make Story input and local presentation controls mutually exclusive."""

    def __init__(
        self,
        *,
        story: StoryTurnInputService,
        controls: ControlIntentPort,
    ) -> None:
        self._story = story
        self._controls = controls

    async def route(
        self,
        value: FinalizedStoryInput | ControlIntent,
    ) -> TurnInputReceipt | RoutedControlIntent:
        if isinstance(value, ControlIntent):
            await self._controls.execute(value)
            return RoutedControlIntent(value)
        if isinstance(value, FinalizedStoryInput):
            return await self._story.receive(value)
        raise StoryInputCommandError("unsupported_input_command")
