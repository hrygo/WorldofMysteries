"""W-V09 durable PlayerAdvice interpretation semantics."""
from __future__ import annotations

from dataclasses import replace

import pytest

from application.advice_interpretation import (
    AdviceInterpretationCandidate,
    AdviceInterpretationError,
    FrozenTurnInput,
    PlayerAdviceInterpretationService,
    StoredPlayerAdvice,
)
from application.turn_input import TurnInputStatus
from contracts import BaseRevisions, InputMode, PlayerAdvice


def frozen(*, status=TurnInputStatus.RECEIVED):
    text = "检查预约簿，但别让他发现。"
    import hashlib
    return FrozenTurnInput(
        input_turn_id="input-1",
        session_id="session-1",
        turn_id="turn-1",
        idempotency_key="turn-input:one",
        input_mode=InputMode.VOICE,
        raw_input=text,
        input_sha256=hashlib.sha256(text.encode()).hexdigest(),
        base_revisions=BaseRevisions(world=10, character=4, story=3),
        status=status,
        committed_world_revision=None,
    )


def candidate(*, primary="investigate"):
    return AdviceInterpretationCandidate(
        interpreter_revision="advice-profile-v1",
        primary_intent=primary,
        secondary_intents=("conceal",),
        proposed_actions=("inspect_appointment_book", "avoid_detection"),
        risk_preference="cautious",
        confidence=0.98,
    )


class Store:
    def __init__(self):
        self.input = frozen()
        self.stored = None
        self.published = []

    async def load_input(self, input_turn_id):
        assert input_turn_id == "input-1"
        return self.input

    async def load_advice(self, input_turn_id):
        assert input_turn_id == "input-1"
        return self.stored

    async def publish(self, input_turn_id, advice, *, interpreter_revision):
        self.published.append((input_turn_id, advice, interpreter_revision))
        if self.stored is not None:
            return replace(self.stored, replayed=True)
        self.stored = StoredPlayerAdvice(
            input_turn_id=input_turn_id,
            advice=advice,
            interpreter_revision=interpreter_revision,
            replayed=False,
        )
        return self.stored


class Interpreter:
    def __init__(self):
        self.calls = 0
        self.value = candidate()

    async def interpret(self, value):
        self.calls += 1
        assert value.raw_input == "检查预约簿，但别让他发现。"
        return self.value


async def test_interpretation_freezes_identity_from_durable_input():
    store = Store()
    model = Interpreter()
    result = await PlayerAdviceInterpretationService(
        durable=store,
        interpreter=model,
    ).interpret("input-1")

    assert result.advice.turn_id == "turn-1"
    assert result.advice.raw_input == store.input.raw_input
    assert result.advice.input_mode is InputMode.VOICE
    assert result.advice.primary_intent == "investigate"
    assert result.advice.proposed_actions == [
        "inspect_appointment_book",
        "avoid_detection",
    ]
    assert result.interpreter_revision == "advice-profile-v1"
    assert model.calls == 1


async def test_existing_durable_advice_replays_without_model_call():
    store = Store()
    model = Interpreter()
    service = PlayerAdviceInterpretationService(durable=store, interpreter=model)
    first = await service.interpret("input-1")
    second = await service.interpret("input-1")

    assert second.replayed
    assert second.advice == first.advice
    assert model.calls == 1


async def test_cancelled_or_committed_input_never_starts_new_interpretation():
    for status, code in (
        (TurnInputStatus.CANCELLED, "input_turn_cancelled"),
        (TurnInputStatus.COMMITTED, "input_turn_not_interpretable"),
    ):
        store = Store()
        store.input = frozen(status=status)
        model = Interpreter()
        with pytest.raises(AdviceInterpretationError, match=code):
            await PlayerAdviceInterpretationService(
                durable=store,
                interpreter=model,
            ).interpret("input-1")
        assert model.calls == 0


def test_candidate_rejects_duplicate_or_empty_actions():
    with pytest.raises(AdviceInterpretationError, match="invalid_proposed_actions"):
        AdviceInterpretationCandidate(
            interpreter_revision="v1",
            primary_intent="observe",
            secondary_intents=(),
            proposed_actions=(),
            risk_preference=None,
            confidence=0.5,
        )
    with pytest.raises(AdviceInterpretationError, match="invalid_proposed_actions"):
        AdviceInterpretationCandidate(
            interpreter_revision="v1",
            primary_intent="observe",
            secondary_intents=(),
            proposed_actions=("look", "look"),
            risk_preference=None,
            confidence=0.5,
        )


def test_candidate_bounds_model_controlled_lists():
    with pytest.raises(AdviceInterpretationError, match="invalid_secondary_intents"):
        AdviceInterpretationCandidate(
            interpreter_revision="v1",
            primary_intent="observe",
            secondary_intents=tuple(f"secondary-{index}" for index in range(17)),
            proposed_actions=("look",),
            risk_preference=None,
            confidence=0.5,
        )
    with pytest.raises(AdviceInterpretationError, match="invalid_proposed_actions"):
        AdviceInterpretationCandidate(
            interpreter_revision="v1",
            primary_intent="observe",
            secondary_intents=(),
            proposed_actions=tuple(f"action-{index}" for index in range(33)),
            risk_preference=None,
            confidence=0.5,
        )
