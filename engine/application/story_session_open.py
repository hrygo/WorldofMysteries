"""Application boundary for opening and recovering durable Story Sessions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from contracts import StorySession, StorySessionStatus

_MAX_SQLITE_REVISION = 2**63 - 1


@dataclass(frozen=True, slots=True)
class OpenStorySessionCommand:
    initial_session: StorySession
    open_request_id: str
    store_expected_revision: int
    request_id: str
    trace_id: str


@dataclass(frozen=True, slots=True)
class StorySessionSnapshot:
    session: StorySession
    observed_store_revision: int


@dataclass(frozen=True, slots=True)
class StorySessionOpenResult:
    snapshot: StorySessionSnapshot
    opened_store_revision: int
    replayed: bool


class StorySessionOpenError(RuntimeError):
    """Stable, non-sensitive application error for session open and recovery."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class StorySessionOpenPort(Protocol):
    async def open_session(
        self, command: OpenStorySessionCommand
    ) -> StorySessionOpenResult: ...

    async def load_snapshot(self, session_id: str) -> StorySessionSnapshot: ...


class StorySessionOpenService:
    """Validate and freeze session-open requests before durable persistence."""

    def __init__(self, port: StorySessionOpenPort) -> None:
        self._port = port

    async def open(self, command: OpenStorySessionCommand) -> StorySessionOpenResult:
        frozen = _freeze_command(command)
        return await self._port.open_session(frozen)

    async def recover(self, session_id: str) -> StorySessionSnapshot:
        _require_text(session_id, "invalid_open_identity")
        snapshot = await self._port.load_snapshot(session_id)
        if not isinstance(snapshot, StorySessionSnapshot):
            raise StorySessionOpenError("story_session_snapshot_invalid")
        if not isinstance(snapshot.session, StorySession):
            raise StorySessionOpenError("story_session_snapshot_invalid")
        if snapshot.session.id != session_id:
            raise StorySessionOpenError("story_session_identity_mismatch")
        if (
            isinstance(snapshot.observed_store_revision, bool)
            or not isinstance(snapshot.observed_store_revision, int)
            or not 0 <= snapshot.observed_store_revision <= _MAX_SQLITE_REVISION
        ):
            raise StorySessionOpenError("story_session_snapshot_invalid")
        try:
            session = StorySession.model_validate(
                snapshot.session.model_dump(mode="json", exclude_none=True)
            )
        except (TypeError, ValueError, ValidationError):
            raise StorySessionOpenError("story_session_snapshot_invalid") from None
        return StorySessionSnapshot(
            session=session,
            observed_store_revision=snapshot.observed_store_revision,
        )


def _freeze_command(command: OpenStorySessionCommand) -> OpenStorySessionCommand:
    if not isinstance(command, OpenStorySessionCommand):
        raise StorySessionOpenError("invalid_open_command")

    initial = command.initial_session
    if not isinstance(initial, StorySession):
        raise StorySessionOpenError("invalid_initial_session")
    try:
        frozen_initial = StorySession.model_validate(
            initial.model_dump(mode="json", exclude_none=True)
        )
    except (TypeError, ValueError, ValidationError):
        raise StorySessionOpenError("invalid_initial_session") from None

    _require_text(
        frozen_initial.id,
        "invalid_open_identity",
    )
    for value in (
        frozen_initial.world_id,
        frozen_initial.worldline_id,
        frozen_initial.protagonist_id,
        frozen_initial.story_seed_id,
        command.open_request_id,
        command.request_id,
        command.trace_id,
    ):
        _require_text(value, "invalid_open_identity")

    if (
        isinstance(command.store_expected_revision, bool)
        or not isinstance(command.store_expected_revision, int)
        or not 0 <= command.store_expected_revision < _MAX_SQLITE_REVISION
    ):
        raise StorySessionOpenError("invalid_store_expected_revision")

    state = frozen_initial.story_state
    if (
        frozen_initial.status is not StorySessionStatus.ACTIVE
        or state.revision != 0
        or state.turn != 0
        or frozen_initial.base_revisions.story != 0
        or state.last_state_delta_id is not None
        or state.story_session_id != frozen_initial.id
    ):
        raise StorySessionOpenError("invalid_initial_session")

    _require_text(state.world_time, "invalid_world_time")

    return OpenStorySessionCommand(
        initial_session=frozen_initial,
        open_request_id=command.open_request_id,
        store_expected_revision=command.store_expected_revision,
        request_id=command.request_id,
        trace_id=command.trace_id,
    )


def _require_text(value: object, code: str, *, limit: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or "\x00" in value
    ):
        raise StorySessionOpenError(code)
    return value
