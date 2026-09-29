"""Scenario-owned planning of the minimal post-COMMIT job graph for one turn.

The durable job graph is a Domain fact, so it is decided at COMMIT from the
same frozen scenario the turn was played under. This planner is pure: it reads
no database, performs no I/O, and never awaits. The commit port calls it inside
the turn's own transaction so the intents appear atomically with the turn.

Two rules from the AO-03/AO-04 guides are load-bearing here:

* the **scenario** decides whether a turn ends the session, not ``turn ==
  max_turn``. A scenario may end earlier than its safety cap, so the end verdict
  comes from ``ScenarioPolicyPort.decision``;
* ``rules_revision`` participates in the job recipe, so re-committing a turn
  under changed content never silently reuses a recipe frozen under old rules.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json

from application.post_commit_work import (
    PostCommitJobState,
    PostCommitKind,
    RequiredPostCommitJob,
    required_jobs_for_turn,
)
from application.scenario_policy import ScenarioIdentity, ScenarioPolicyPort
from contracts import StateDelta, StorySession, TurnTransaction

from ..story_session_repository import PlannedPostCommitJob

#: Recipe identities a handler must advertise before it may run a job.
NARRATIVE_RECIPE = "narrative-publish-v1"
EPISODE_FINALIZE_RECIPE = "episode-finalize-v1"
AUDIO_PREPARE_RECIPE = "audio-prepare-v1"

RECIPES_BY_KIND: Mapping[PostCommitKind, str] = {
    PostCommitKind.NARRATIVE_PUBLISH: NARRATIVE_RECIPE,
    PostCommitKind.EPISODE_FINALIZE: EPISODE_FINALIZE_RECIPE,
    PostCommitKind.AUDIO_PREPARE: AUDIO_PREPARE_RECIPE,
}

_MAX_JOB_ID = 256


class PostCommitPlanningError(RuntimeError):
    """The committed turn cannot be bound to a durable post-COMMIT job graph."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _job_identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PostCommitPlanningError(f"invalid_{field}")
    if len(value) > _MAX_JOB_ID:
        raise PostCommitPlanningError(f"invalid_{field}")
    if not value.isascii() or any(char.isspace() for char in value):
        raise PostCommitPlanningError(f"invalid_{field}")
    return value


class ScenarioPostCommitJobPlanner:
    """Turn a committed turn plus its frozen scenario into durable intents."""

    def __init__(
        self,
        *,
        scenario: ScenarioPolicyPort,
        identity: ScenarioIdentity,
        story_seed_id: str,
        max_turn: int,
        voice_configured: bool,
    ) -> None:
        self._scenario = scenario
        self._identity = identity
        self._story_seed_id = _job_identifier(story_seed_id, "story_seed_id")
        if isinstance(max_turn, bool) or not isinstance(max_turn, int) or max_turn < 1:
            raise PostCommitPlanningError("invalid_max_turn")
        if type(voice_configured) is not bool:
            raise PostCommitPlanningError("invalid_voice_configuration")
        self._max_turn = max_turn
        self._voice_configured = voice_configured

    @property
    def supported_recipes(self) -> dict[str, frozenset[str]]:
        """Recipe revisions this planner can emit, keyed by job kind."""
        return {
            kind.value: frozenset({self._recipe_revision(kind)})
            for kind in PostCommitKind
        }

    def _recipe_revision(self, kind: PostCommitKind) -> str:
        return f"{self._identity.rules_revision}:{RECIPES_BY_KIND[kind]}"

    def plan_jobs(
        self,
        *,
        session: StorySession,
        delta: StateDelta,
        turn: TurnTransaction,
    ) -> tuple[PlannedPostCommitJob, ...]:
        """Return the frozen job intents for one already-committed turn."""
        if session.id != turn.session_id or delta.turn_id != turn.id:
            raise PostCommitPlanningError("post_commit_source_identity_mismatch")
        if session.story_seed_id != self._story_seed_id:
            # Content was replaced under a live session. Failing closed keeps
            # the old rules bound to the old session; upgrading it needs an
            # explicit migration, which this package deliberately does not do.
            raise PostCommitPlanningError("post_commit_untrusted_story_seed")
        if turn.committed_story_revision != session.story_state.revision:
            raise PostCommitPlanningError("post_commit_revision_mismatch")

        turn_number = session.story_state.turn
        if turn_number < 1 or turn_number > self._max_turn:
            raise PostCommitPlanningError("post_commit_turn_out_of_range")
        committed_evidence = frozenset(
            session.story_state.discovered_clue_ids or ()
        )
        terminal = self._scenario.decision(session, committed_evidence).terminal

        required = required_jobs_for_turn(
            turn_number,
            self._max_turn,
            voice_configured=self._voice_configured,
            terminal=terminal,
        )
        frozen_delta = delta.model_dump(mode="json", exclude_none=True)
        return tuple(
            self._planned(turn, job, frozen_delta) for job in required
        )

    def _planned(
        self,
        turn: TurnTransaction,
        job: RequiredPostCommitJob,
        frozen_delta: object,
    ) -> PlannedPostCommitJob:
        recipe_revision = self._recipe_revision(job.kind)
        job_id = _job_identifier(
            f"{turn.id}:{job.kind.value}:{recipe_revision}", "job_id"
        )
        # The digest binds the frozen scenario version, the committed delta and
        # the bound recipe. It never hashes a credential, a URL or a token.
        input_digest = hashlib.sha256(
            _canonical(
                {
                    "scenario_id": self._identity.scenario_id,
                    "content_digest": self._identity.content_digest,
                    "rules_revision": self._identity.rules_revision,
                    "kind": job.kind.value,
                    "recipe_revision": recipe_revision,
                    "turn_id": turn.id,
                    "source_story_revision": turn.committed_story_revision,
                    "delta": frozen_delta,
                }
            ).encode("utf-8")
        ).hexdigest()
        return PlannedPostCommitJob(
            job_id=job_id,
            kind=job.kind,
            recipe_revision=recipe_revision,
            input_digest=input_digest,
            initial_state=job.initial_state,
            initial_reason_code=job.initial_reason_code,
        )


__all__ = [
    "AUDIO_PREPARE_RECIPE",
    "EPISODE_FINALIZE_RECIPE",
    "NARRATIVE_RECIPE",
    "PostCommitPlanningError",
    "RECIPES_BY_KIND",
    "ScenarioPostCommitJobPlanner",
]
