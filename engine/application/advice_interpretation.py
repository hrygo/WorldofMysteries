"""W-V09 idempotent durable PlayerAdvice interpretation.

The model never owns turn identity or raw input. Those fields come exclusively
from the durable pre-COMMIT input command. The first persisted interpretation
wins; lost ACK/restart replays it without another model call.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import math
from typing import Protocol

from contracts import BaseRevisions, InputMode, PlayerAdvice

from .turn_input import TurnInputStatus


class AdviceInterpretationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _text(value: str, field: str, *, limit: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or "\x00" in value
    ):
        raise AdviceInterpretationError(f"invalid_{field}")
    return value.strip()


@dataclass(frozen=True, slots=True)
class FrozenTurnInput:
    input_turn_id: str
    session_id: str
    turn_id: str
    idempotency_key: str
    input_mode: InputMode
    raw_input: str
    input_sha256: str
    base_revisions: BaseRevisions
    status: TurnInputStatus
    committed_world_revision: int | None
    public_expected_store_revision: int | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.input_turn_id, "input_turn_id"),
            (self.session_id, "session_id"),
            (self.turn_id, "turn_id"),
            (self.idempotency_key, "idempotency_key"),
        ):
            _text(value, field)
        if not isinstance(self.input_mode, InputMode):
            raise AdviceInterpretationError("invalid_input_mode")
        _text(self.raw_input, "raw_input", limit=16_384)
        if (
            not isinstance(self.input_sha256, str)
            or len(self.input_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in self.input_sha256)
            or hashlib.sha256(self.raw_input.encode("utf-8")).hexdigest()
            != self.input_sha256
        ):
            raise AdviceInterpretationError("input_digest_mismatch")
        if not isinstance(self.base_revisions, BaseRevisions):
            raise AdviceInterpretationError("invalid_base_revisions")
        if not isinstance(self.status, TurnInputStatus):
            raise AdviceInterpretationError("invalid_input_status")
        if self.committed_world_revision is not None and (
            type(self.committed_world_revision) is not int
            or self.committed_world_revision < 0
        ):
            raise AdviceInterpretationError("invalid_committed_world_revision")
        if self.public_expected_store_revision is not None and (
            type(self.public_expected_store_revision) is not int
            or not 0 <= self.public_expected_store_revision < 2**63 - 1
        ):
            raise AdviceInterpretationError("invalid_public_expected_store_revision")


@dataclass(frozen=True, slots=True)
class AdviceInterpretationCandidate:
    interpreter_revision: str
    primary_intent: str
    secondary_intents: tuple[str, ...]
    proposed_actions: tuple[str, ...]
    risk_preference: str | None
    confidence: float

    def __post_init__(self) -> None:
        _text(self.interpreter_revision, "interpreter_revision")
        _text(self.primary_intent, "primary_intent")
        if (
            not isinstance(self.secondary_intents, tuple)
            or len(self.secondary_intents) > 16
            or len(set(self.secondary_intents)) != len(self.secondary_intents)
        ):
            raise AdviceInterpretationError("invalid_secondary_intents")
        for value in self.secondary_intents:
            _text(value, "secondary_intent")
        if (
            not isinstance(self.proposed_actions, tuple)
            or not 1 <= len(self.proposed_actions) <= 32
            or len(set(self.proposed_actions)) != len(self.proposed_actions)
        ):
            raise AdviceInterpretationError("invalid_proposed_actions")
        for value in self.proposed_actions:
            _text(value, "proposed_action")
        if self.risk_preference is not None:
            _text(self.risk_preference, "risk_preference")
        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not math.isfinite(float(self.confidence))
            or not 0.0 <= float(self.confidence) <= 1.0
        ):
            raise AdviceInterpretationError("invalid_confidence")


@dataclass(frozen=True, slots=True)
class StoredPlayerAdvice:
    input_turn_id: str
    advice: PlayerAdvice
    interpreter_revision: str
    replayed: bool = False


class DurableAdvicePort(Protocol):
    async def load_input(self, input_turn_id: str) -> FrozenTurnInput | None: ...

    async def load_advice(self, input_turn_id: str) -> StoredPlayerAdvice | None: ...

    async def publish(
        self,
        input_turn_id: str,
        advice: PlayerAdvice,
        *,
        interpreter_revision: str,
    ) -> StoredPlayerAdvice: ...


class AdviceInterpreterPort(Protocol):
    async def interpret(
        self,
        value: FrozenTurnInput,
    ) -> AdviceInterpretationCandidate: ...


def _advice_id(input_turn_id: str) -> str:
    digest = hashlib.sha256(
        f"wom-player-advice/v1\0{input_turn_id}".encode("utf-8")
    ).hexdigest()
    return f"advice_{digest[:32]}"


class PlayerAdviceInterpretationService:
    def __init__(
        self,
        *,
        durable: DurableAdvicePort,
        interpreter: AdviceInterpreterPort,
    ) -> None:
        self._durable = durable
        self._interpreter = interpreter

    async def interpret(self, input_turn_id: str) -> StoredPlayerAdvice:
        _text(input_turn_id, "input_turn_id")

        existing = await self._durable.load_advice(input_turn_id)
        if existing is not None:
            return replace(existing, replayed=True)

        frozen = await self._durable.load_input(input_turn_id)
        if frozen is None:
            raise AdviceInterpretationError("input_turn_not_found")
        if frozen.status is TurnInputStatus.CANCELLED:
            raise AdviceInterpretationError("input_turn_cancelled")
        if frozen.status is not TurnInputStatus.RECEIVED:
            raise AdviceInterpretationError("input_turn_not_interpretable")

        candidate = await self._interpreter.interpret(frozen)
        if not isinstance(candidate, AdviceInterpretationCandidate):
            raise AdviceInterpretationError("invalid_interpretation_candidate")

        payload: dict[str, object] = {
            "schema_version": "1.0",
            "id": _advice_id(frozen.input_turn_id),
            "turn_id": frozen.turn_id,
            "raw_input": frozen.raw_input,
            "input_mode": frozen.input_mode.value,
            "primary_intent": candidate.primary_intent,
            "proposed_actions": list(candidate.proposed_actions),
            "confidence": float(candidate.confidence),
        }
        if candidate.secondary_intents:
            payload["secondary_intents"] = list(candidate.secondary_intents)
        if candidate.risk_preference is not None:
            payload["risk_preference"] = candidate.risk_preference

        advice = PlayerAdvice.model_validate(payload)
        return await self._durable.publish(
            frozen.input_turn_id,
            advice,
            interpreter_revision=candidate.interpreter_revision,
        )
