"""Allowlisted public projection for the trusted first-turn flow."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from application.scenario_policy import TurnPolicyDecision
from application.story_initialization import StorySessionBootstrap
from contracts import StorySession, StorySessionStatus


class StoryPublicViewError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PublicActorView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=256)
    display_name: str = Field(min_length=1, max_length=256)


class PublicSceneView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=256)
    location_id: str = Field(min_length=1, max_length=256)
    display_name: str = Field(min_length=1, max_length=256)


class PublicClueView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=256)
    display_name: str = Field(min_length=1, max_length=256)


class PublicStorySessionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    scenario_id: str = Field(min_length=1, max_length=256)
    session_id: str = Field(min_length=1, max_length=256)
    mode: Literal["golden_deterministic"] = "golden_deterministic"
    status: str
    story_revision: int = Field(ge=0)
    turn: int = Field(ge=0)
    observed_store_revision: int = Field(ge=0)
    world_time: str = Field(min_length=1, max_length=128)
    protagonist: PublicActorView
    scene: PublicSceneView
    discovered_clues: list[PublicClueView]
    can_submit: bool
    last_committed_turn_id: str | None = Field(default=None, min_length=1, max_length=256)


@dataclass(frozen=True, slots=True)
class StoryPublicProjectionFacts:
    """The small, allowlisted presentation facts needed to project a session."""

    scenario_id: str
    session_id: str
    protagonist_display_name: str
    scene_display_name: str
    clue_display_names: tuple[tuple[str, str], ...]

    @classmethod
    def from_bootstrap(
        cls,
        bootstrap: StorySessionBootstrap,
    ) -> StoryPublicProjectionFacts:
        if not isinstance(bootstrap, StorySessionBootstrap):
            raise StoryPublicViewError("invalid_bootstrap")
        try:
            protagonist = bootstrap.character["identity"]["display_name"]
            scene_display_name = bootstrap.presentation.scene_display_name
            clue_mapping = tuple(
                sorted(dict(bootstrap.presentation.clue_display_names).items())
            )
            return cls(
                scenario_id=bootstrap.scenario_id,
                session_id=bootstrap.initial_session.id,
                protagonist_display_name=protagonist,
                scene_display_name=scene_display_name,
                clue_display_names=clue_mapping,
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            raise StoryPublicViewError("recovery_required") from None


class StoryPublicViewProjector:
    """Project only the fields authorized for the engineering UI."""

    def project(
        self,
        *,
        session: StorySession,
        bootstrap: StorySessionBootstrap,
        observed_store_revision: int,
        policy_decision: TurnPolicyDecision,
        last_committed_turn_id: str | None = None,
        has_pending_input: bool = False,
    ) -> PublicStorySessionView:
        if not isinstance(session, StorySession):
            raise StoryPublicViewError("invalid_story_session")
        if not isinstance(bootstrap, StorySessionBootstrap):
            raise StoryPublicViewError("invalid_bootstrap")
        if not isinstance(policy_decision, TurnPolicyDecision):
            raise StoryPublicViewError("invalid_turn_policy_decision")
        return self.project_from_facts(
            session=session,
            facts=StoryPublicProjectionFacts.from_bootstrap(bootstrap),
            observed_store_revision=observed_store_revision,
            policy_decision=policy_decision,
            last_committed_turn_id=last_committed_turn_id,
            has_pending_input=has_pending_input,
        )

    def project_from_facts(
        self,
        *,
        session: StorySession,
        facts: StoryPublicProjectionFacts,
        observed_store_revision: int,
        policy_decision: TurnPolicyDecision,
        last_committed_turn_id: str | None = None,
        has_pending_input: bool = False,
    ) -> PublicStorySessionView:
        if not isinstance(session, StorySession):
            raise StoryPublicViewError("invalid_story_session")
        if not isinstance(facts, StoryPublicProjectionFacts):
            raise StoryPublicViewError("invalid_projection_facts")
        if not isinstance(policy_decision, TurnPolicyDecision):
            raise StoryPublicViewError("invalid_turn_policy_decision")
        if session.id != facts.session_id:
            raise StoryPublicViewError("bootstrap_identity_mismatch")
        if (
            isinstance(observed_store_revision, bool)
            or not isinstance(observed_store_revision, int)
            or observed_store_revision < 0
        ):
            raise StoryPublicViewError("invalid_store_revision")

        clue_mapping = dict(facts.clue_display_names)

        clue_ids = session.story_state.discovered_clue_ids or []
        clues: list[PublicClueView] = []
        for clue_id in clue_ids:
            display_name = clue_mapping.get(clue_id)
            if display_name is None:
                raise StoryPublicViewError("recovery_required")
            clues.append(PublicClueView(id=clue_id, display_name=display_name))

        can_submit = (
            session.status is StorySessionStatus.ACTIVE
            and policy_decision.allowed_to_submit
            and not has_pending_input
        )
        try:
            return PublicStorySessionView(
                scenario_id=facts.scenario_id,
                session_id=session.id,
                status=session.status.value,
                story_revision=session.story_state.revision,
                turn=session.story_state.turn,
                observed_store_revision=observed_store_revision,
                world_time=session.story_state.world_time or "",
                protagonist=PublicActorView(
                    id=session.protagonist_id,
                    display_name=facts.protagonist_display_name,
                ),
                scene=PublicSceneView(
                    id=session.story_state.scene.id,
                    location_id=session.story_state.scene.location_id or "",
                    display_name=facts.scene_display_name,
                ),
                discovered_clues=clues,
                can_submit=can_submit,
                last_committed_turn_id=last_committed_turn_id,
            )
        except (TypeError, ValueError):
            raise StoryPublicViewError("invalid_public_projection") from None
