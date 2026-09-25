"""Fresh authorization boundary for W-V08 StoryBook replay and redub.

Historical tracks/takes remain immutable evidence. This module controls *new
consumption* of those assets. There is intentionally no allow-by-default policy:
production callers must inject the current Application authorization decision.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal


StoryBookAuthorizationAction = Literal["replay", "redub"]
StoryBookAuthorizationStage = Literal[
    "before_lookup",
    "before_delivery",
    "before_publish",
]


class StoryBookAuthorizationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class StoryBookAuthorizationRequest:
    action: StoryBookAuthorizationAction
    stage: StoryBookAuthorizationStage
    track_id: str
    track_family_id: str
    story_session_id: str
    revision: int
    take_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.action not in {"replay", "redub"}:
            raise StoryBookAuthorizationError("storybook_invalid_action")
        if self.stage not in {"before_lookup", "before_delivery", "before_publish"}:
            raise StoryBookAuthorizationError("storybook_invalid_stage")
        for value in (
            self.track_id,
            self.track_family_id,
            self.story_session_id,
        ):
            if not isinstance(value, str) or not value.strip():
                raise StoryBookAuthorizationError("storybook_invalid_identity")
        if type(self.revision) is not int or self.revision < 1:
            raise StoryBookAuthorizationError("storybook_invalid_revision")
        if (
            not isinstance(self.take_ids, tuple)
            or not self.take_ids
            or any(not isinstance(value, str) or not value.strip() for value in self.take_ids)
        ):
            raise StoryBookAuthorizationError("storybook_invalid_take_set")


StoryBookAuthorizationCheck = Callable[
    [StoryBookAuthorizationRequest],
    Awaitable[bool],
]


async def require_storybook_authorization(
    authorize: StoryBookAuthorizationCheck,
    request: StoryBookAuthorizationRequest,
) -> None:
    if not callable(authorize):
        raise StoryBookAuthorizationError("storybook_authorization_required")
    try:
        allowed = await authorize(request)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise StoryBookAuthorizationError(
            "storybook_authorization_unavailable"
        ) from exc
    if allowed is not True:
        raise StoryBookAuthorizationError("storybook_not_authorized")
