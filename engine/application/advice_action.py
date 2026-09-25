"""W-V09 bounded ActionIntent proposal from durable PlayerAdvice.

Character reasoning may propose semantic actions, but it never owns turn
identity, actor identity, or evidence references.  Those fields are bound by
this Application boundary to the already durable input and PlayerAdvice.
The proposer receives only a minimal scope; full Domain state must pass through
the existing authorization/context compiler before any model call.
Persistence and deterministic outcome resolution remain later stages.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Protocol

from contracts import (
    ActionIntent,
    AdherenceType,
    BaseRevisions,
    PlayerAdvice,
    StorySession,
    StorySessionStatus,
)
from contracts.models import ExpectedCost, IntentAction, PerceivedRisk

from .advice_interpretation import FrozenTurnInput, StoredPlayerAdvice
from .turn_input import StorySessionReadPort, TurnInputStatus


class AdviceActionError(RuntimeError):
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
        raise AdviceActionError(f"invalid_{field}")
    return value.strip()


def _finite(value: object, field: str, *, minimum: float = 0.0, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdviceActionError(f"invalid_{field}")
    number = float(value)
    if not math.isfinite(number) or number < minimum or (maximum is not None and number > maximum):
        raise AdviceActionError(f"invalid_{field}")
    return number


def _bounded_json(parameters: dict[str, object] | None) -> None:
    if parameters is None:
        return
    if not isinstance(parameters, dict):
        raise AdviceActionError("invalid_action_parameters")
    try:
        encoded = json.dumps(
            parameters,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise AdviceActionError("invalid_action_parameters") from None
    if len(encoded) > 4096:
        raise AdviceActionError("action_parameters_too_large")


@dataclass(frozen=True, slots=True)
class ActionIntentCandidate:
    """Model-controlled semantic proposal without identity authority."""

    proposer_revision: str
    intent: str
    adherence: AdherenceType
    actions: tuple[IntentAction, ...]
    reason_summary: str | None = None
    speech_intent: str | None = None
    expected_costs: tuple[ExpectedCost, ...] = ()
    perceived_risks: tuple[PerceivedRisk, ...] = ()

    def __post_init__(self) -> None:
        _text(self.proposer_revision, "proposer_revision")
        _text(self.intent, "intent")
        if not isinstance(self.adherence, AdherenceType):
            raise AdviceActionError("invalid_adherence")
        if not isinstance(self.actions, tuple) or not 1 <= len(self.actions) <= 8:
            raise AdviceActionError("invalid_actions")
        for action in self.actions:
            if not isinstance(action, IntentAction):
                raise AdviceActionError("invalid_action")
            _text(action.type, "action_type", limit=128)
            if action.purpose is not None:
                _text(action.purpose, "action_purpose", limit=512)
            if action.target_ids is not None:
                if not isinstance(action.target_ids, list) or len(action.target_ids) > 16:
                    raise AdviceActionError("invalid_action_targets")
                for target_id in action.target_ids:
                    _text(target_id, "action_target", limit=256)
            _bounded_json(action.parameters)
        if self.reason_summary is not None:
            _text(self.reason_summary, "reason_summary", limit=2048)
        if self.speech_intent is not None:
            _text(self.speech_intent, "speech_intent", limit=1024)
        if not isinstance(self.expected_costs, tuple) or len(self.expected_costs) > 8:
            raise AdviceActionError("invalid_expected_costs")
        for cost in self.expected_costs:
            if not isinstance(cost, ExpectedCost):
                raise AdviceActionError("invalid_expected_cost")
            _text(cost.resource, "cost_resource", limit=128)
            _finite(cost.amount, "cost_amount")
            if cost.unit is not None:
                _text(cost.unit, "cost_unit", limit=64)
        if not isinstance(self.perceived_risks, tuple) or len(self.perceived_risks) > 8:
            raise AdviceActionError("invalid_perceived_risks")
        for risk in self.perceived_risks:
            if not isinstance(risk, PerceivedRisk):
                raise AdviceActionError("invalid_perceived_risk")
            _text(risk.risk, "risk", limit=256)
            _finite(risk.level, "risk_level", maximum=1.0)


@dataclass(frozen=True, slots=True)
class ActionIntentScope:
    """Minimal non-secret scope a proposer may use to request authorized context."""

    session_id: str
    world_id: str
    worldline_id: str
    protagonist_id: str
    base_revisions: BaseRevisions

    def __post_init__(self) -> None:
        for value, field in (
            (self.session_id, "session_id"),
            (self.world_id, "world_id"),
            (self.worldline_id, "worldline_id"),
            (self.protagonist_id, "protagonist_id"),
        ):
            _text(value, field)
        if not isinstance(self.base_revisions, BaseRevisions):
            raise AdviceActionError("invalid_base_revisions")


@dataclass(frozen=True, slots=True)
class AdviceActionProposal:
    input_turn_id: str
    advice: PlayerAdvice
    action_intent: ActionIntent
    proposer_revision: str


class DurableAdviceReadPort(Protocol):
    async def load_input(self, input_turn_id: str) -> FrozenTurnInput | None: ...

    async def load_advice(self, input_turn_id: str) -> StoredPlayerAdvice | None: ...


class ActionIntentProposerPort(Protocol):
    async def propose(
        self,
        *,
        frozen: FrozenTurnInput,
        advice: PlayerAdvice,
        scope: ActionIntentScope,
    ) -> ActionIntentCandidate: ...


def _action_intent_id(turn_id: str) -> str:
    digest = hashlib.sha256(
        f"wom-action-intent/v1\0{turn_id}".encode()
    ).hexdigest()
    return f"intent_{digest[:32]}"


class AdviceActionIntentService:
    """Bind a bounded model proposal to durable advice and session identity."""

    def __init__(
        self,
        *,
        durable: DurableAdviceReadPort,
        sessions: StorySessionReadPort,
        proposer: ActionIntentProposerPort,
    ) -> None:
        self._durable = durable
        self._sessions = sessions
        self._proposer = proposer

    async def propose(self, input_turn_id: str) -> AdviceActionProposal:
        _text(input_turn_id, "input_turn_id")

        frozen = await self._durable.load_input(input_turn_id)
        if frozen is None:
            raise AdviceActionError("input_turn_not_found")
        if frozen.status is TurnInputStatus.CANCELLED:
            raise AdviceActionError("input_turn_cancelled")
        if frozen.status is not TurnInputStatus.RECEIVED:
            raise AdviceActionError("input_turn_not_proposable")

        stored = await self._durable.load_advice(input_turn_id)
        if stored is None:
            raise AdviceActionError("player_advice_not_found")
        advice = stored.advice
        self._validate_binding(frozen, advice)

        session = await self._sessions.load_session(frozen.session_id)
        if not isinstance(session, StorySession) or session.id != frozen.session_id:
            raise AdviceActionError("story_session_identity_mismatch")
        if session.status is not StorySessionStatus.ACTIVE:
            raise AdviceActionError("story_session_not_active")
        if (
            session.base_revisions.world != frozen.base_revisions.world
            or session.base_revisions.character != frozen.base_revisions.character
        ):
            raise AdviceActionError("story_session_base_revision_mismatch")
        if session.story_state.revision != frozen.base_revisions.story:
            raise AdviceActionError("input_turn_stale")

        scope = ActionIntentScope(
            session_id=session.id,
            world_id=session.world_id,
            worldline_id=session.worldline_id,
            protagonist_id=session.protagonist_id,
            base_revisions=session.base_revisions,
        )
        candidate = await self._proposer.propose(
            frozen=frozen,
            advice=advice,
            scope=scope,
        )
        if not isinstance(candidate, ActionIntentCandidate):
            raise AdviceActionError("invalid_action_intent_candidate")

        payload: dict[str, object] = {
            "schema_version": "1.0",
            "id": _action_intent_id(frozen.turn_id),
            "turn_id": frozen.turn_id,
            "character_id": scope.protagonist_id,
            "intent": candidate.intent,
            "adherence": candidate.adherence.value,
            "actions": [action.model_dump(mode="json", exclude_none=True) for action in candidate.actions],
            "evidence_ids": [advice.id],
        }
        if candidate.reason_summary is not None:
            payload["reason_summary"] = candidate.reason_summary
        if candidate.speech_intent is not None:
            payload["speech_intent"] = candidate.speech_intent
        if candidate.expected_costs:
            payload["expected_costs"] = [
                cost.model_dump(mode="json", exclude_none=True) for cost in candidate.expected_costs
            ]
        if candidate.perceived_risks:
            payload["perceived_risks"] = [
                risk.model_dump(mode="json", exclude_none=True) for risk in candidate.perceived_risks
            ]

        action_intent = ActionIntent.model_validate(payload)
        return AdviceActionProposal(
            input_turn_id=frozen.input_turn_id,
            advice=advice,
            action_intent=action_intent,
            proposer_revision=candidate.proposer_revision,
        )

    @staticmethod
    def _validate_binding(frozen: FrozenTurnInput, advice: PlayerAdvice) -> None:
        if (
            advice.turn_id != frozen.turn_id
            or advice.raw_input != frozen.raw_input
            or advice.input_mode is not frozen.input_mode
        ):
            raise AdviceActionError("player_advice_binding_mismatch")
