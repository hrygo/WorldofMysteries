"""Focused tests for durable advice -> deterministic resolution -> COMMIT."""

from __future__ import annotations

import hashlib

import pytest

from application.advice_action import (
    ActionIntentCandidate,
    AdviceActionIntentService,
)
from application.advice_commit import AdviceCommitError, AdviceCommitService
from application.advice_interpretation import FrozenTurnInput, StoredPlayerAdvice
from application.story_turn_commit import DomainValidationContext, StoryTurnCommitResult
from application.turn_context_binding import (
    AuthorizedContextSource,
    AuthorizedTurnContextBinding,
)
from application.turn_input import TurnInputStatus
from contracts import (
    AdherenceType,
    BaseRevisions,
    InputMode,
    PlayerAdvice,
    StateDelta,
    StorySession,
    StoryState,
    TurnStatus,
    TurnTransaction,
)
from contracts.models import IntentAction
from domain.resolution_policy import ResolutionPolicy, ResolutionRule, StoryEffect
from domain.resolver import DeterministicOutcomeResolver

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


def _advice() -> PlayerAdvice:
    return PlayerAdvice.model_validate(
        {
            "schema_version": "1.0",
            "id": "advice.001",
            "turn_id": "turn.001",
            "raw_input": RAW_INPUT,
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
            "turn": story_revision,
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


def _candidate(
    *,
    context_binding: AuthorizedTurnContextBinding | None = None,
) -> ActionIntentCandidate:
    return ActionIntentCandidate(
        proposer_revision="character-reasoner.v1",
        intent="observe_subject",
        adherence=AdherenceType.FULL,
        actions=(IntentAction(type="continue_conversation"),),
        reason_summary="先观察对方反应。",
        context_binding=context_binding,
    )


def _policy() -> ResolutionPolicy:
    return ResolutionPolicy.from_story_seed(
        {"clues": [], "secrets": []},
        [
            ResolutionRule(
                rule_id="rule.observe",
                intent="observe_subject",
                action_types=("continue_conversation",),
                effect=StoryEffect(outcome="partial_success"),
            )
        ],
        policy_id="test-policy",
    )


class _Durable:
    def __init__(self, frozen: FrozenTurnInput, advice: PlayerAdvice | None = None):
        self.frozen = frozen
        self.advice = advice if advice is not None else _advice()

    async def load_input(self, input_turn_id: str) -> FrozenTurnInput | None:
        return self.frozen if self.frozen.input_turn_id == input_turn_id else None

    async def load_advice(self, input_turn_id: str) -> StoredPlayerAdvice | None:
        if input_turn_id != self.frozen.input_turn_id:
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
        self.calls = 0

    async def propose(
        self,
        *,
        frozen,
        advice,
        scope,
        expected_context_binding=None,
    ):
        self.calls += 1
        self.expected_context_binding = expected_context_binding
        return self.candidate


class _Story:
    def __init__(
        self,
        session: StorySession,
        *,
        turn: TurnTransaction | None = None,
        delta: StateDelta | None = None,
    ):
        self.session = session
        self.turn = turn
        self.delta = delta
        self.commit_calls = []

    async def load_session(self, session_id: str) -> StorySession:
        return self.session

    async def load_turn(self, turn_id: str) -> TurnTransaction:
        assert self.turn is not None
        return self.turn

    async def load_delta(self, delta_id: str) -> StateDelta:
        assert self.delta is not None
        return self.delta

    async def commit_turn(
        self, session, delta, turn, *, store_expected_revision, request_id, trace_id
    ):
        self.session = session
        self.delta = delta
        self.turn = turn
        self.commit_calls.append(
            (session, delta, turn, store_expected_revision, request_id, trace_id)
        )
        return StoryTurnCommitResult(
            store_revision=store_expected_revision + 1,
            session=session,
            turn=turn,
            delta=delta,
            replayed=False,
        )


def _service(
    *,
    frozen: FrozenTurnInput | None = None,
    session: StorySession | None = None,
    story: _Story | None = None,
    context_bindings=None,
    action_binding: AuthorizedTurnContextBinding | None = None,
    domain_context=None,
):
    durable = _Durable(frozen or _frozen())
    proposer = _Proposer(_candidate(context_binding=action_binding))
    proposal = AdviceActionIntentService(
        durable=durable,
        sessions=_Sessions(session or _session()),
        proposer=proposer,
        context_bindings=context_bindings,
    )
    story_port = story or _Story(session or _session())
    service = AdviceCommitService(
        durable=durable,
        proposal=proposal,
        story=story_port,
        resolver=DeterministicOutcomeResolver(),
        domain_context=domain_context,
        context_bindings=context_bindings,
    )
    return service, story_port, proposal, proposer


def _binding(
    stage: str,
    *,
    store_revision: int = 0,
    story_revision: int = 0,
    source_id: str,
) -> AuthorizedTurnContextBinding:
    return AuthorizedTurnContextBinding(
        turn_id="turn.001",
        stage=stage,
        input_turn_id="input.turn.001",
        source_store_revision=store_revision,
        source_story_revision=story_revision,
        policy_revision="policy.v1",
        content_digest="a" * 64,
        lineage_digest="lineage.v1",
        manifest=(
            AuthorizedContextSource(
                source_id=source_id,
                source_revision=store_revision,
                fingerprint="b" * 64,
            ),
        ),
    )


class _ContextBindings:
    def __init__(self, interpretation, action=None):
        self.values = {
            "interpretation": interpretation,
            "action": action,
        }

    async def load(self, *, turn_id, stage):
        assert turn_id == "turn.001"
        return self.values[stage]

    async def save(self, binding):
        self.values[binding.stage] = binding
        return binding


@pytest.mark.asyncio
async def test_advice_proposal_is_resolved_and_committed_once():
    service, story, _, proposer = _service()

    result = await service.commit(
        "input.turn.001",
        policy=_policy(),
        store_expected_revision=0,
        request_id="request.001",
        trace_id="trace.001",
    )

    assert proposer.calls == 1
    assert len(story.commit_calls) == 1
    assert result.replayed is False
    assert result.store_revision == 1
    assert result.turn.status is TurnStatus.COMMITTED
    assert result.turn.player_advice_id == "advice.001"
    assert result.turn.action_intent_id
    assert result.turn.action_intent_id in result.delta.evidence_ids
    assert result.turn.state_delta_id == result.delta.id
    assert result.delta.turn_id == "turn.001"
    assert result.delta.outcome == "partial_success"


@pytest.mark.asyncio
async def test_final_commit_uses_the_action_intents_exact_authorized_source_set():
    interpretation = _binding(
        "interpretation",
        source_id="interpretation-source",
    )
    action = _binding("action", source_id="action-source")
    contexts = _ContextBindings(interpretation)

    class RecordingDomainContext:
        known_character_ids = ()
        authorized_evidence_ids = frozenset({"policy.golden001.opening"})
        hidden_fact_literals = ()

        def __init__(self):
            self.identities = ()

        def with_runtime_identities(self, *identities):
            self.identities = identities
            return DomainValidationContext(
                known_character_ids=self.known_character_ids,
                authorized_evidence_ids=self.authorized_evidence_ids
                | frozenset(identities),
                hidden_fact_literals=self.hidden_fact_literals,
            )

    domain_context = RecordingDomainContext()
    service, story, _, proposer = _service(
        context_bindings=contexts,
        action_binding=action,
        domain_context=lambda _revision: domain_context,
    )

    await service.commit(
        "input.turn.001",
        policy=_policy(),
        store_expected_revision=0,
        request_id="request.bound",
        trace_id="trace.bound",
    )

    assert proposer.expected_context_binding == interpretation
    assert contexts.values["action"] == action
    assert "action-source" in domain_context.identities
    assert "interpretation-source" not in domain_context.identities
    assert story.commit_calls


@pytest.mark.asyncio
async def test_stale_action_binding_stops_before_commit_without_rebinding():
    interpretation = _binding(
        "interpretation",
        source_id="interpretation-source",
    )
    stale_action = _binding(
        "action",
        store_revision=1,
        source_id="new-action-source",
    )
    contexts = _ContextBindings(interpretation)
    service, story, _, _ = _service(
        context_bindings=contexts,
        action_binding=stale_action,
    )

    with pytest.raises(AdviceCommitError, match="context_stale"):
        await service.commit(
            "input.turn.001",
            policy=_policy(),
            store_expected_revision=0,
            request_id="request.stale",
            trace_id="trace.stale",
        )

    assert story.commit_calls == []
    assert contexts.values["interpretation"] == interpretation
    assert contexts.values["action"] is None


@pytest.mark.asyncio
async def test_legacy_interpretation_without_binding_stays_pending():
    contexts = _ContextBindings(None)
    service, story, _, _ = _service(
        context_bindings=contexts,
        action_binding=_binding("action", source_id="action-source"),
    )

    with pytest.raises(AdviceCommitError, match="legacy_context_unbound"):
        await service.commit(
            "input.turn.001",
            policy=_policy(),
            store_expected_revision=0,
            request_id="request.legacy",
            trace_id="trace.legacy",
        )

    assert story.commit_calls == []
    assert contexts.values["action"] is None


@pytest.mark.asyncio
async def test_committed_input_replays_without_second_proposal_or_commit():
    delta = StateDelta.model_validate(
        {
            "schema_version": "1.0",
            "id": "delta.replayed",
            "turn_id": "turn.001",
            "outcome": "partial_success",
            "story_delta": {},
            "character_deltas": [],
            "world_event_candidates": [],
            "evidence_ids": ["advice.001"],
        }
    )
    turn = TurnTransaction.model_validate(
        {
            "schema_version": "1.0",
            "id": "turn.001",
            "session_id": "session.001",
            "idempotency_key": "idem.turn.001",
            "status": "committed",
            "base_revisions": {"world": 103, "character": 27, "story": 0},
            "player_advice_id": "advice.001",
            "action_intent_id": "intent.001",
            "state_delta_id": delta.id,
            "committed_story_revision": 1,
        }
    )
    story = _Story(_session(story_revision=1), turn=turn, delta=delta)
    service, story, _, proposer = _service(
        frozen=_frozen(status=TurnInputStatus.COMMITTED, committed_world_revision=7),
        session=_session(story_revision=1),
        story=story,
    )

    result = await service.commit(
        "input.turn.001",
        policy=_policy(),
        store_expected_revision=0,
        request_id="request.replay",
        trace_id="trace.replay",
    )

    assert proposer.calls == 0
    assert story.commit_calls == []
    assert result.replayed is True
    assert result.store_revision == 7
    assert result.turn.status is TurnStatus.COMMITTED


@pytest.mark.asyncio
async def test_cancelled_input_never_commits():
    service, story, _, proposer = _service(frozen=_frozen(status=TurnInputStatus.CANCELLED))

    with pytest.raises(AdviceCommitError, match="input_turn_cancelled"):
        await service.commit(
            "input.turn.001",
            policy=_policy(),
            store_expected_revision=0,
            request_id="request.cancel",
            trace_id="trace.cancel",
        )
    assert proposer.calls == 0
    assert story.commit_calls == []


@pytest.mark.asyncio
async def test_unmatched_resolution_rule_fails_before_commit():
    service, story, _, _ = _service()
    unmatched = ResolutionPolicy.from_story_seed(
        {"clues": [], "secrets": []},
        [],
        policy_id="empty-policy",
    )

    with pytest.raises(Exception, match="No validated resolution rule"):
        await service.commit(
            "input.turn.001",
            policy=unmatched,
            store_expected_revision=0,
            request_id="request.unmatched",
            trace_id="trace.unmatched",
        )
    assert story.commit_calls == []
