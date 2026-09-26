"""Allowlisted public projection for the trusted first-turn flow."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class StoryPublicViewProjector:
    """Project only the fields authorized for the engineering UI."""

    def project(
        self,
        *,
        session: StorySession,
        bootstrap: StorySessionBootstrap,
        observed_store_revision: int,
        last_committed_turn_id: str | None = None,
        has_pending_input: bool = False,
    ) -> PublicStorySessionView:
        if not isinstance(session, StorySession):
            raise StoryPublicViewError("invalid_story_session")
        if not isinstance(bootstrap, StorySessionBootstrap):
            raise StoryPublicViewError("invalid_bootstrap")
        if session.id != bootstrap.initial_session.id:
            raise StoryPublicViewError("bootstrap_identity_mismatch")
        if (
            isinstance(observed_store_revision, bool)
            or not isinstance(observed_store_revision, int)
            or observed_store_revision < 0
        ):
            raise StoryPublicViewError("invalid_store_revision")

        try:
            protagonist = bootstrap.character["identity"]["display_name"]
        except (KeyError, TypeError):
            raise StoryPublicViewError("recovery_required") from None
        try:
            scene_display_name = bootstrap.presentation.scene_display_name
            clue_mapping = dict(bootstrap.presentation.clue_display_names)
        except (AttributeError, TypeError, ValueError):
            raise StoryPublicViewError("recovery_required") from None

        clue_ids = session.story_state.discovered_clue_ids or []
        clues: list[PublicClueView] = []
        for clue_id in clue_ids:
            display_name = clue_mapping.get(clue_id)
            if display_name is None:
                raise StoryPublicViewError("recovery_required")
            clues.append(PublicClueView(id=clue_id, display_name=display_name))

        can_submit = (
            session.status is StorySessionStatus.ACTIVE
            and session.story_state.turn == 0
            and not has_pending_input
        )
        try:
            return PublicStorySessionView(
                scenario_id=bootstrap.scenario_id,
                session_id=session.id,
                status=session.status.value,
                story_revision=session.story_state.revision,
                turn=session.story_state.turn,
                observed_store_revision=observed_store_revision,
                world_time=session.story_state.world_time or "",
                protagonist=PublicActorView(
                    id=session.protagonist_id,
                    display_name=protagonist,
                ),
                scene=PublicSceneView(
                    id=session.story_state.scene.id,
                    location_id=session.story_state.scene.location_id or "",
                    display_name=scene_display_name,
                ),
                discovered_clues=clues,
                can_submit=can_submit,
                last_committed_turn_id=last_committed_turn_id,
            )
        except (TypeError, ValueError):
            raise StoryPublicViewError("invalid_public_projection") from None
