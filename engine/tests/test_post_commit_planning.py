"""Scenario-owned post-COMMIT job graph planning tests."""
from __future__ import annotations

import pytest

from application.post_commit_work import PostCommitJobState, PostCommitKind
from application.scenario_policy import (
    ScenarioIdentity,
    ScenarioPolicyError,
    TurnPolicyDecision,
)
from contracts import (
    BaseRevisions,
    SecretState,
    StateDelta,
    StoryPhase,
    StorySession,
    StoryState,
    TurnStatus,
    TurnTransaction,
)
from contracts.models import StoryCommitments, StoryDelta, StoryScene
from infrastructure.scenarios.post_commit_planning import (
    AUDIO_PREPARE_RECIPE,
    EPISODE_FINALIZE_RECIPE,
    NARRATIVE_RECIPE,
    PostCommitPlanningError,
    ScenarioPostCommitJobPlanner,
)

SESSION_ID = "session-planning"
SEED_ID = "seed-planning"


class StubScenarioPolicy:
    """Terminal verdict comes from the scenario, not from the turn counter."""

    def __init__(self, *, terminal_at: int) -> None:
        self._terminal_at = terminal_at

    def identity(self, bootstrap) -> ScenarioIdentity:  # pragma: no cover - unused
        raise ScenarioPolicyError("not_used")

    def decision(
        self, session: StorySession, committed_evidence: frozenset[str]
    ) -> TurnPolicyDecision:
        terminal = session.story_state.turn >= self._terminal_at
        return TurnPolicyDecision(
            allowed_to_submit=not terminal,
            terminal=terminal,
            reason="scenario_limit" if terminal else None,
        )


def _identity() -> ScenarioIdentity:
    return ScenarioIdentity(
        scenario_id="golden_001",
        content_digest="a" * 64,
        rules_revision="golden-v1",
    )


def _session(*, turn: int, clues: list[str] | None = None) -> StorySession:
    return StorySession(
        schema_version="1.0",
        id=SESSION_ID,
        world_id="world_test",
        worldline_id="wl_test",
        protagonist_id="character_test",
        story_seed_id=SEED_ID,
        base_revisions=BaseRevisions(world=0, character=0, story=0),
        story_state=StoryState(
            schema_version="1.0",
            story_session_id=SESSION_ID,
            revision=turn,
            turn=turn,
            phase=StoryPhase.INVESTIGATION,
            scene=StoryScene(id="scene_test"),
            world_time="1349-06-12T21:40:00",
            discovered_clue_ids=clues or [],
            secret_states={"secret_test": SecretState.HIDDEN},
            commitments=StoryCommitments(hard_ids=[], soft_ids=[]),
            pressure={},
        ),
        status="active",
    )


def _delta(*, turn_id: str, clue: str | None = None) -> StateDelta:
    # `clue_ids_add` may be omitted but must not be null, so build the payload
    # and drop the key entirely when there is no clue to add.
    story_delta = StoryDelta(**({"clue_ids_add": [clue]} if clue else {}))
    return StateDelta(
        schema_version="1.0",
        id=f"delta-{turn_id}",
        turn_id=turn_id,
        outcome="clean_success",
        story_delta=story_delta,
        character_deltas=[],
        world_event_candidates=[],
        evidence_ids=[],
    )


def _turn(*, turn_id: str, revision: int) -> TurnTransaction:
    return TurnTransaction(
        schema_version="1.0",
        id=turn_id,
        session_id=SESSION_ID,
        idempotency_key=f"input-{turn_id}",
        status=TurnStatus.COMMITTED,
        base_revisions=BaseRevisions(world=0, character=0, story=0),
        state_delta_id=f"delta-{turn_id}",
        committed_story_revision=revision,
    )


def _planner(
    *, terminal_at: int = 5, max_turn: int = 5, voice_configured: bool = True
) -> ScenarioPostCommitJobPlanner:
    return ScenarioPostCommitJobPlanner(
        scenario=StubScenarioPolicy(terminal_at=terminal_at),
        identity=_identity(),
        story_seed_id=SEED_ID,
        max_turn=max_turn,
        voice_configured=voice_configured,
    )


def _plan(planner, *, turn: int, clues=None, delta_clue=None, turn_id="turn-1"):
    session = _session(turn=turn, clues=clues)
    return planner.plan_jobs(
        session=session,
        delta=_delta(turn_id=turn_id, clue=delta_clue),
        turn=_turn(turn_id=turn_id, revision=turn),
    )


def _by_kind(jobs) -> dict[str, object]:
    return {job.kind: job for job in jobs}


# ------------------------------------------------------------------ job graph


def test_every_turn_gets_narrative_and_audio() -> None:
    jobs = _by_kind(_plan(_planner(), turn=1))
    assert set(jobs) == {
        PostCommitKind.NARRATIVE_PUBLISH,
        PostCommitKind.AUDIO_PREPARE,
    }
    assert jobs[PostCommitKind.NARRATIVE_PUBLISH].initial_state is (
        PostCommitJobState.PENDING
    )


def test_terminal_turn_also_gets_episode_finalization() -> None:
    jobs = _by_kind(_plan(_planner(terminal_at=5, max_turn=5), turn=5))
    assert jobs[PostCommitKind.EPISODE_FINALIZE].initial_state is (
        PostCommitJobState.PENDING
    )


def test_scenario_may_end_before_its_safety_cap() -> None:
    """AO-04: the scenario, not ``turn == max_turn``, decides the ending."""
    jobs = _by_kind(_plan(_planner(terminal_at=2, max_turn=3), turn=2))
    assert jobs[PostCommitKind.EPISODE_FINALIZE].initial_state is (
        PostCommitJobState.PENDING
    )


def test_final_cap_turn_is_not_enough_when_the_scenario_says_otherwise() -> None:
    """A scenario may also keep playing past a turn another one would end."""
    jobs = _by_kind(_plan(_planner(terminal_at=4, max_turn=3), turn=3))
    assert PostCommitKind.EPISODE_FINALIZE not in jobs


def test_audio_is_blocked_with_a_reason_when_voice_is_absent() -> None:
    jobs = _by_kind(_plan(_planner(voice_configured=False), turn=1))
    audio = jobs[PostCommitKind.AUDIO_PREPARE]
    assert audio.initial_state is PostCommitJobState.BLOCKED
    assert audio.initial_reason_code == "voice_not_configured"
    # Blocking audio must never hold back the text or the Episode.
    assert jobs[PostCommitKind.NARRATIVE_PUBLISH].initial_state is (
        PostCommitJobState.PENDING
    )


# ------------------------------------------------------------- frozen identity


def test_identities_are_deterministic_across_calls() -> None:
    planner = _planner()
    first = _plan(planner, turn=2)
    second = _plan(planner, turn=2)
    assert [(j.job_id, j.recipe_revision, j.input_digest) for j in first] == [
        (j.job_id, j.recipe_revision, j.input_digest) for j in second
    ]


def test_recipe_revision_binds_the_rules_revision() -> None:
    jobs = _by_kind(_plan(_planner(), turn=1))
    assert jobs[PostCommitKind.NARRATIVE_PUBLISH].recipe_revision == (
        f"golden-v1:{NARRATIVE_RECIPE}"
    )
    assert jobs[PostCommitKind.AUDIO_PREPARE].recipe_revision == (
        f"golden-v1:{AUDIO_PREPARE_RECIPE}"
    )


def test_recipe_identity_changes_with_the_rules_revision() -> None:
    stale = ScenarioPostCommitJobPlanner(
        scenario=StubScenarioPolicy(terminal_at=5),
        identity=_identity(),
        story_seed_id=SEED_ID,
        max_turn=5,
        voice_configured=True,
    )
    revised = ScenarioPostCommitJobPlanner(
        scenario=StubScenarioPolicy(terminal_at=5),
        identity=ScenarioIdentity(
            scenario_id="golden_001", content_digest="a" * 64, rules_revision="golden-v2"
        ),
        story_seed_id=SEED_ID,
        max_turn=5,
        voice_configured=True,
    )
    assert _plan(stale, turn=1)[0].recipe_revision != _plan(revised, turn=1)[
        0
    ].recipe_revision


def test_input_digest_covers_the_committed_delta() -> None:
    planner = _planner()
    with_clue = _plan(planner, turn=1, delta_clue="clue-a")
    without_clue = _plan(planner, turn=1)
    digests = {
        job.kind: job.input_digest for job in (*with_clue, *without_clue)
    }
    assert (
        digests[PostCommitKind.NARRATIVE_PUBLISH]
        != digests[PostCommitKind.AUDIO_PREPARE]
    ), "different kinds must not share a digest"
    narrative_only = _plan(planner, turn=1, delta_clue="clue-b")
    assert narrative_only[0].input_digest != with_clue[0].input_digest


def test_input_digest_is_a_plain_sha256_hex_digest() -> None:
    for job in _plan(_planner(), turn=1):
        assert len(job.input_digest) == 64
        assert all(char in "0123456789abcdef" for char in job.input_digest)
        int(job.input_digest, 16)


def test_supported_recipes_lists_every_kind() -> None:
    recipes = _planner().supported_recipes
    assert recipes[PostCommitKind.NARRATIVE_PUBLISH.value] == frozenset(
        {f"golden-v1:{NARRATIVE_RECIPE}"}
    )
    assert recipes[PostCommitKind.EPISODE_FINALIZE.value] == frozenset(
        {f"golden-v1:{EPISODE_FINALIZE_RECIPE}"}
    )
    assert recipes[PostCommitKind.AUDIO_PREPARE.value] == frozenset(
        {f"golden-v1:{AUDIO_PREPARE_RECIPE}"}
    )


# ------------------------------------------------------------------- fail closed


def test_untrusted_story_seed_fails_closed() -> None:
    planner = _planner()
    session = _session(turn=1)
    session = session.model_copy(update={"story_seed_id": "seed-other"})
    with pytest.raises(PostCommitPlanningError) as refusal:
        planner.plan_jobs(
            session=session, delta=_delta(turn_id="turn-1"), turn=_turn(
                turn_id="turn-1", revision=1
            )
        )
    assert refusal.value.code == "post_commit_untrusted_story_seed"


def test_source_identity_mismatch_fails_closed() -> None:
    planner = _planner()
    with pytest.raises(PostCommitPlanningError) as refusal:
        planner.plan_jobs(
            session=_session(turn=1),
            delta=_delta(turn_id="turn-other"),
            turn=_turn(turn_id="turn-1", revision=1),
        )
    assert refusal.value.code == "post_commit_source_identity_mismatch"


def test_revision_mismatch_fails_closed() -> None:
    planner = _planner()
    with pytest.raises(PostCommitPlanningError) as refusal:
        planner.plan_jobs(
            session=_session(turn=2),
            delta=_delta(turn_id="turn-1"),
            turn=_turn(turn_id="turn-1", revision=1),
        )
    assert refusal.value.code == "post_commit_revision_mismatch"


def test_turn_beyond_the_scenario_cap_fails_closed() -> None:
    with pytest.raises(PostCommitPlanningError) as refusal:
        _plan(_planner(max_turn=3), turn=4)
    assert refusal.value.code == "post_commit_turn_out_of_range"


def test_invalid_planner_construction_is_rejected() -> None:
    for bad in (0, -1, True):
        with pytest.raises(PostCommitPlanningError):
            ScenarioPostCommitJobPlanner(
                scenario=StubScenarioPolicy(terminal_at=5),
                identity=_identity(),
                story_seed_id=SEED_ID,
                max_turn=bad,
                voice_configured=True,
            )
    with pytest.raises(PostCommitPlanningError):
        ScenarioPostCommitJobPlanner(
            scenario=StubScenarioPolicy(terminal_at=5),
            identity=_identity(),
            story_seed_id=SEED_ID,
            max_turn=5,
            voice_configured="yes",
        )
