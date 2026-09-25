"""Focused tests for durable PlayerAdvice -> bounded ActionIntent proposal."""
from __future__ import annotations

import hashlib

import pytest

from application.advice_action import (
    ActionIntentCandidate,
    AdviceActionError,
    AdviceActionIntentService,
)
from application.advice_interpretation import FrozenTurnInput, StoredPlayerAdvice
from application.turn_input import TurnInputStatus
from contracts import (
    AdherenceType,
    BaseRevisions,
    InputMode,
    PlayerAdvice,
    StorySession,
    StoryState,
)
from contracts.models import IntentAction

RAW_INPUT = "先观察医生对话题的反应。"


def _frozen(
    *,
    status: TurnInputStatus = TurnInputStatus.RECEIVED,
    committed_world_revision: int | None = None,
) -> FrozenTurnInput:
    return FrozenTurnInput(
        input_turn_id="input.turn.001",
        session_id="session.001",
        turn_id="turn.001",
        idempotency_key="idem.turn.001",
        input_mode=InputMode.VOICE,
        raw_input=RAW_INPUT,
        input_sha256=hashlib.sha256(RAW_INPUT.encode("utf-8")).hexdigest(),
        base_revisions=BaseRevisions(world=103, character=27, story=0),
        status=status,
        committed_world_revision=committed_world_revision,
    )


def _advice(*, raw_input: str = RAW_INPUT) -> PlayerAdvice:
    return PlayerAdvice.model_validate(
        {
            "schema_version": "1.0",
            "id": "advice.001",
            "turn_id": "turn.001",
            "raw_input": raw_input,
            "input_mode": "voice",
            "primary_intent": "observe_subject",
            "proposed_actions": ["continue_conversation"],
            "confidence": 0.8,
        }
    )


def _session(*, story_revision: int = 0, status: str = "active") -> StorySession:
    state = StoryState.model_validate(
        {
            "schema_version": "1.0",
            "story_session_id": "session.001",
            "revision": story_revision,
            "turn": 0,
            "phase": "discovery",
            "scene": {
                "id": "consultation_room",
                "location_id": "location.consultation",
                "active_character_ids": ["char.evelyn", "char.morris"],
            },
            "world_time": "1889-05-01T09:00:00+00:00",
            "active_conflicts": [],
            "discovered_clue_ids": [],
            "secret_states": {},
            "commitments": {"hard_ids": [], "soft_ids": []},
            "pressure": {},
            "last_state_delta_id": None,
        }
    )
    return StorySession.model_validate(
        {
            "schema_version": "1.0",
            "id": "session.001",
            "world_id": "world.001",
            "worldline_id": "worldline.001",
            "protagonist_id": "char.evelyn",
            "story_seed_id": "seed.001",
            "base_revisions": {"world": 103, "character": 27, "story": 0},
            "story_state": state.model_dump(mode="json", exclude_none=True),
            "status": status,
        }
    )


def _candidate(*actions: IntentAction) -> ActionIntentCandidate:
    return ActionIntentCandidate(
        proposer_revision="character-reasoner.v1",
        intent="observe_subject",
        adherence=AdherenceType.FULL,
        actions=actions or (IntentAction(type="continue_conversation"),),
        reason_summary="先观察对方反应。",
    )


class _Durable:
    def __init__(self, frozen: FrozenTurnInput | None, advice: PlayerAdvice | None):
        self.frozen = frozen
        self.advice = advice

    async def load_input(self, input_turn_id: str) -> FrozenTurnInput | None:
        return self.frozen if self.frozen and self.frozen.input_turn_id == input_turn_id else None

    async def load_advice(self, input_turn_id: str) -> StoredPlayerAdvice | None:
        if self.advice is None or input_turn_id != "input.turn.001":
            return None
        return StoredPlayerAdvice(
            input_turn_id=input_turn_id,
            advice=self.advice,
            interpreter_revision="advice-interpreter.v1",
        )


class _Sessions:
    def __init__(self, session: StorySession):
        self.session = session

    async def load_session(self, session_id: str) -> StorySession:
        return self.session


class _Proposer:
    def __init__(self, candidate: ActionIntentCandidate):
        self.candidate = candidate
        self.calls: list[tuple[FrozenTurnInput, PlayerAdvice, object]] = []

    async def propose(
        self,
        *,
        frozen: FrozenTurnInput,
        advice: PlayerAdvice,
        scope,
    ) -> ActionIntentCandidate:
        self.calls.append((frozen, advice, scope))
        return self.candidate


def _service(
    *,
    frozen: FrozenTurnInput | None = None,
    advice: PlayerAdvice | None = None,
    session: StorySession | None = None,
    candidate: ActionIntentCandidate | None = None,
) -> tuple[AdviceActionIntentService, _Proposer]:
    proposer = _Proposer(candidate or _candidate())
    service = AdviceActionIntentService(
        durable=_Durable(frozen or _frozen(), advice if advice is not None else _advice()),
        sessions=_Sessions(session or _session()),
        proposer=proposer,
    )
    return service, proposer


@pytest.mark.asyncio
async def test_application_owns_action_identity_turn_actor_and_evidence():
    service, proposer = _service()

    result = await service.propose("input.turn.001")

    assert len(proposer.calls) == 1
    assert proposer.calls[0][2].session_id == "session.001"
    assert proposer.calls[0][2].protagonist_id == "char.evelyn"
    assert result.input_turn_id == "input.turn.001"
    assert result.advice.id == "advice.001"
    assert result.action_intent.id.startswith("intent_")
    assert result.action_intent.turn_id == "turn.001"
    assert result.action_intent.character_id == "char.evelyn"
    assert result.action_intent.evidence_ids == ["advice.001"]
    assert result.action_intent.actions[0].type == "continue_conversation"
    assert result.proposer_revision == "character-reasoner.v1"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (TurnInputStatus.CANCELLED, "input_turn_cancelled"),
        (TurnInputStatus.COMMITTED, "input_turn_not_proposable"),
    ],
)
@pytest.mark.asyncio
async def test_terminal_or_cancelled_input_never_calls_proposer(status, code):
    service, proposer = _service(
        frozen=_frozen(status=status, committed_world_revision=1 if status is TurnInputStatus.COMMITTED else None)
    )

    with pytest.raises(AdviceActionError, match=code):
        await service.propose("input.turn.001")
    assert proposer.calls == []


@pytest.mark.asyncio
async def test_player_advice_binding_mismatch_is_rejected_before_model_call():
    service, proposer = _service(advice=_advice(raw_input="被替换的输入"))

    with pytest.raises(AdviceActionError, match="player_advice_binding_mismatch"):
        await service.propose("input.turn.001")
    assert proposer.calls == []


@pytest.mark.asyncio
async def test_stale_story_revision_is_rejected_before_model_call():
    service, proposer = _service(session=_session(story_revision=1))

    with pytest.raises(AdviceActionError, match="input_turn_stale"):
        await service.propose("input.turn.001")
    assert proposer.calls == []


@pytest.mark.asyncio
async def test_inactive_session_is_rejected_before_model_call():
    service, proposer = _service(session=_session(status="suspended"))

    with pytest.raises(AdviceActionError, match="story_session_not_active"):
        await service.propose("input.turn.001")
    assert proposer.calls == []


def test_candidate_rejects_unbounded_action_lists():
    with pytest.raises(AdviceActionError, match="invalid_actions"):
        _candidate(*(IntentAction(type="act") for _ in range(9)))
