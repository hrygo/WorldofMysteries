"""Scenario policy contracts and a test-only non-Golden terminal rule."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai.authorized_live_execution import AuthorizedLiveExecution
from ai.live_turn_workers import LiveFirstTurnFactory
from ai.openai_compatible import (
    ModelEndpointConfig,
    OpenAICompatibleChatTransport,
)
from ai.prompt_renderer import PromptRenderer
from application.advice_interpretation import (
    AdviceInterpretationError,
    FrozenTurnInput,
)
from application.context_plan import ContextError
from application.gameplay_context import GameplayContextCoordinator
from application.scenario_policy import (
    FinalizationRecipe,
    ScenarioIdentity,
    ScenarioPolicyError,
    ScenarioPolicyPort,
    TurnPolicyDecision,
)
from application.story_initialization import (
    GOLDEN_POLICY_VERSION,
    GOLDEN_SCENARIO_ID,
    StorySessionBootstrap,
)
from application.turn_input import TurnInputStatus
from contracts import (
    BaseRevisions,
    InputMode,
    SecretState,
    StoryPhase,
    StorySession,
    StorySessionStatus,
    StoryState,
)
from contracts.models import StoryCommitments, StoryScene
from infrastructure.scenarios.golden_policy import (
    _GOLDEN_RULES_BY_CONTENT_DIGEST,
    GoldenScenarioPolicy,
)

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "scenarios"
    / "conditional_exit"
    / "policy.json"
)


class ConditionalExitTestPolicy:
    """Private test adapter; it is never registered by the production runtime."""

    def __init__(self) -> None:
        self._policy = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def identity(self, bootstrap) -> ScenarioIdentity:
        return ScenarioIdentity(
            scenario_id=bootstrap.scenario_id,
            content_digest=bootstrap.content_digest,
            rules_revision=bootstrap.policy_version,
        )

    def decision(
        self, session: StorySession, committed_evidence: frozenset[str]
    ) -> TurnPolicyDecision:
        if self._policy["exit_evidence_id"] in committed_evidence:
            return TurnPolicyDecision(
                allowed_to_submit=False,
                terminal=True,
                reason=self._policy["terminal_reasons"]["exit_evidence"],
            )
        if session.story_state.turn >= self._policy["maximum_turn"]:
            return TurnPolicyDecision(
                allowed_to_submit=False,
                terminal=True,
                reason=self._policy["terminal_reasons"]["maximum_turn"],
            )
        return TurnPolicyDecision(
            allowed_to_submit=True,
            terminal=False,
            reason=None,
        )


def _session(*, turn: int, discovered_clues: list[str]) -> StorySession:
    return StorySession(
        schema_version="1.0",
        id="session_conditional_exit",
        world_id="world_test",
        worldline_id="wl_test",
        protagonist_id="character_test",
        story_seed_id="seed_conditional_exit_test_only",
        base_revisions=BaseRevisions(world=0, character=0, story=0),
        story_state=StoryState(
            schema_version="1.0",
            story_session_id="session_conditional_exit",
            revision=turn,
            turn=turn,
            phase=StoryPhase.INVESTIGATION,
            scene=StoryScene(id="scene_test"),
            world_time="1349-06-12T21:40:00",
            active_conflicts=[],
            discovered_clue_ids=discovered_clues,
            secret_states={"secret_test": SecretState.HIDDEN},
            commitments=StoryCommitments(hard_ids=[], soft_ids=[]),
            local_state={},
            pressure={},
        ),
        status=StorySessionStatus.ACTIVE,
    )


def _golden_bootstrap(**overrides):
    values = {
        "scenario_id": GOLDEN_SCENARIO_ID,
        "content_digest": "610ecbdb2875b86ac5ed52b100d5def3481408d5f4e16030cec2ed09da288d07",
        "policy_version": GOLDEN_POLICY_VERSION,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_golden_policy_binds_known_content_to_its_rules_revision() -> None:
    policy = GoldenScenarioPolicy(object())

    identity = policy.identity(_golden_bootstrap())

    assert identity == ScenarioIdentity(
        scenario_id=GOLDEN_SCENARIO_ID,
        content_digest=_golden_bootstrap().content_digest,
        rules_revision=GOLDEN_POLICY_VERSION,
    )


@pytest.mark.parametrize(
    "identity",
    [
        _golden_bootstrap(content_digest="f" * 64),
        _golden_bootstrap(policy_version="unregistered-rules-v9"),
        _golden_bootstrap(scenario_id="unregistered_scenario"),
    ],
)
def test_golden_policy_rejects_unknown_content_or_rules_identity(identity) -> None:
    policy = GoldenScenarioPolicy(object())

    with pytest.raises(ScenarioPolicyError, match="unknown_scenario_identity"):
        policy.identity(identity)


def test_the_registry_tracks_the_shipped_bundle_and_keeps_its_predecessor() -> None:
    """The registry is a list of live content digests, not a single current value.

    Two things have to hold at once, and this test is the only place both are
    asserted:

    1. The digest the shipped bundle actually produces is registered. Renaming
       a public name (VF-111) moves that digest, and the policy gate refuses
       an unregistered one — so a rename that skipped registration would leave
       the product unable to open a fresh session, while a registry that kept
       only its predecessor would keep every assertion here green.
    2. The predecessor stays registered. A session bootstrapped under the old
       digest carries that content in its own bootstrap, so deleting the older
       entry makes it un-restorable over a change that says nothing about the
       rules governing it. Removing it reads as housekeeping and is data loss.
    """
    import sys

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "scripts"))
    try:
        import build_story_content as builder
    finally:
        sys.path.pop(0)

    shipped = builder.build_payload()["content_digest"]

    assert shipped in _GOLDEN_RULES_BY_CONTENT_DIGEST, (
        "出货固件的内容摘要未注册：新开局将因 unknown_scenario_identity 而失败"
    )
    assert len(_GOLDEN_RULES_BY_CONTENT_DIGEST) >= 2, (
        "改名会移动内容摘要；只保留当前一个会让旧 bootstrap 的会话无法恢复"
    )
    for digest in _GOLDEN_RULES_BY_CONTENT_DIGEST:
        policy = GoldenScenarioPolicy(object())
        identity = policy.identity(_golden_bootstrap(content_digest=digest))
        assert identity.rules_revision == GOLDEN_POLICY_VERSION


def test_golden_policy_uses_its_turn_decision_for_finalization_recipe() -> None:
    class Rules:
        max_turn = 5

    policy = GoldenScenarioPolicy(Rules())
    bootstrap = _golden_bootstrap()

    before_terminal = _session(turn=4, discovered_clues=[])
    assert policy.decision(before_terminal, frozenset()).terminal is False
    assert policy.finalization_recipe(bootstrap, before_terminal) is None

    terminal = _session(turn=5, discovered_clues=[])
    assert policy.decision(terminal, frozenset()).terminal is True
    assert policy.finalization_recipe(bootstrap, terminal) == FinalizationRecipe(
        episode_filename="episode.json",
        memory_filename="episode_memory.json",
    )


def test_scenario_policy_types_preserve_identity_and_terminal_reason() -> None:
    identity = ScenarioIdentity(
        scenario_id="conditional_exit",
        content_digest="a" * 64,
        rules_revision="conditional-exit-v1",
    )
    decision = TurnPolicyDecision(
        allowed_to_submit=False,
        terminal=True,
        reason="exit_clue_committed",
    )

    assert identity.scenario_id == "conditional_exit"
    assert identity.content_digest == "a" * 64
    assert identity.rules_revision == "conditional-exit-v1"
    assert decision.allowed_to_submit is False
    assert decision.terminal is True
    assert decision.reason == "exit_clue_committed"


def test_conditional_exit_ends_on_turn_two_when_exit_clue_is_committed() -> None:
    policy: ScenarioPolicyPort = ConditionalExitTestPolicy()  # type: ignore[assignment]
    session = _session(turn=2, discovered_clues=["exit_clue"])

    decision = policy.decision(
        session, frozenset(session.story_state.discovered_clue_ids or ())
    )

    assert decision == TurnPolicyDecision(
        allowed_to_submit=False,
        terminal=True,
        reason="exit_clue_committed",
    )


def test_conditional_exit_ends_at_turn_three_with_explicit_limit_reason() -> None:
    policy: ScenarioPolicyPort = ConditionalExitTestPolicy()  # type: ignore[assignment]
    session = _session(turn=3, discovered_clues=[])

    decision = policy.decision(
        session, frozenset(session.story_state.discovered_clue_ids or ())
    )

    assert decision == TurnPolicyDecision(
        allowed_to_submit=False,
        terminal=True,
        reason="maximum_turn_reached",
    )


@pytest.mark.asyncio
async def test_live_worker_factory_uses_scenario_supplied_action_signatures() -> None:
    transport = OpenAICompatibleChatTransport(
        ModelEndpointConfig(
            base_url="http://127.0.0.1:1",
            api_key="test-only",
            model="test-model",
        )
    )
    execution = AuthorizedLiveExecution(
        coordinator=GameplayContextCoordinator(
            snapshot=object(),
            authorization=object(),
            profiles=object(),
        ),
        renderer=PromptRenderer(b"r" * 32),
        transport=transport,
        validate_proposal=lambda _proposal, _request: True,
    )
    factory = LiveFirstTurnFactory(execution)
    bootstrap = StorySessionBootstrap.model_construct(
        scenario_id="conditional_exit",
        character={
            "identity": {"display_name": "测试角色"},
            "core": {"role": "调查者"},
        },
        world={"name": "测试世界"},
        presentation=SimpleNamespace(
            scene_display_name="测试地点",
            scenario_title="测试场景",
        ),
        initial_session=SimpleNamespace(protagonist_id="character_test"),
    )
    signatures = (("inspect_exit", ("examine_clue",)),)

    try:
        worker = factory.proposer_for(bootstrap, 2, signatures)

        assert factory.supports_live_input is True
        assert worker._allowed == signatures
        assert not hasattr(factory, "max_turn")
        assert not hasattr(factory, "policy_for_turn")
        assert not hasattr(factory, "domain_validation_for")
        assert not hasattr(factory, "expected_input")
    finally:
        await factory.aclose()


def _live_bootstrap() -> StorySessionBootstrap:
    return StorySessionBootstrap.model_construct(
        scenario_id="conditional_exit",
        content_digest="d" * 64,
        character={
            "identity": {"display_name": "测试角色"},
            "core": {"role": "调查者"},
        },
        world={"name": "测试世界"},
        presentation=SimpleNamespace(
            scene_display_name="测试地点",
            scenario_title="测试场景",
        ),
        initial_session=SimpleNamespace(
            protagonist_id="character_test",
            world_id="world_test",
            worldline_id="worldline_test",
        ),
    )


def _frozen_turn_input() -> FrozenTurnInput:
    raw = "我要调查这扇门"
    return FrozenTurnInput(
        input_turn_id="input_turn_test",
        session_id="session_test",
        turn_id="turn_test",
        idempotency_key="idem_test",
        input_mode=InputMode.TEXT,
        raw_input=raw,
        input_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        base_revisions=BaseRevisions(world=1, character=1, story=1),
        status=TurnInputStatus.RECEIVED,
        committed_world_revision=1,
        public_expected_store_revision=1,
    )


def _execution_with_refusing_coordinator(code: str) -> AuthorizedLiveExecution:
    """Real execution seam whose coordinator refuses with a Domain ContextError."""
    coordinator = GameplayContextCoordinator(
        snapshot=object(),
        authorization=object(),
        profiles=object(),
    )

    async def refuse(_call) -> None:
        raise ContextError(code)

    coordinator.prepare = refuse
    return AuthorizedLiveExecution(
        coordinator=coordinator,
        renderer=PromptRenderer(b"r" * 32),
        transport=OpenAICompatibleChatTransport(
            ModelEndpointConfig(
                base_url="http://127.0.0.1:1",
                api_key="test-only",
                model="test-model",
            )
        ),
        validate_proposal=lambda _proposal, _request: True,
    )


@pytest.mark.parametrize(
    ("domain_code", "expected_code"),
    [
        ("context_stale", "context_stale"),
        ("stale_snapshot", "context_stale"),
        ("evidence_not_authorized", "context_stale"),
        ("missing_current_state", "model_proposal_invalid"),
        ("unknown_consumer", "model_proposal_invalid"),
    ],
)
@pytest.mark.asyncio
async def test_live_worker_surfaces_domain_context_error_code(
    domain_code: str, expected_code: str
) -> None:
    """A Domain refusal must reach the caller as a typed, honest code.

    `ContextError` carries its stable code as the *message*; the worker used to read
    a `.code` attribute, so every authorization refusal died as `AttributeError` and
    the IPC boundary reported an opaque `service_unavailable` instead.
    """
    factory = LiveFirstTurnFactory(_execution_with_refusing_coordinator(domain_code))
    worker = factory.interpreter_for(_live_bootstrap(), 1)

    try:
        with pytest.raises(AdviceInterpretationError) as raised:
            await worker.interpret(_frozen_turn_input())
    finally:
        await factory.aclose()

    assert raised.value.code == expected_code
