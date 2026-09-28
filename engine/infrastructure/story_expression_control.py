"""Read-only IPC control for player-visible persisted story expression."""
from __future__ import annotations

from collections.abc import Mapping

from application.story_expression import (
    StoryExpressionError,
    StoryExpressionQueryService,
)

from .database_manager import StorageError
from .story_bootstrap_repository import (
    SQLiteStoryBootstrapRepository,
    StoryBootstrapError,
)
from .story_control import StoryRequestHandler
from .story_session_query import StoryQueryError

STORY_EXPRESSION_GET_METHOD = "story.expression.get"
_REQUIRED_KEYS = frozenset({"schema_version", "session_id", "turn_id"})


class SQLiteNarrativePublicIdentityReader:
    """Resolve only the protagonist name already approved in the session."""

    def __init__(self, bootstraps: SQLiteStoryBootstrapRepository) -> None:
        self._bootstraps = bootstraps

    async def display_name(
        self, *, session_id: str, speaker_id: str
    ) -> str | None:
        bootstrap = await self._bootstraps.load(session_id)
        if (
            bootstrap is None
            or bootstrap.initial_session.protagonist_id != speaker_id
        ):
            return None
        try:
            name = bootstrap.character["identity"]["display_name"]
        except (KeyError, TypeError):
            return None
        return name if isinstance(name, str) else None


def story_expression_control_handlers(
    query: StoryExpressionQueryService,
) -> dict[str, StoryRequestHandler]:
    """Return the strict, read-only ``story.expression.get`` request handler."""

    async def get_expression(
        _context: Mapping[str, object], payload: Mapping[str, object]
    ) -> tuple[dict[str, object] | None, str | None, bool]:
        if (
            not isinstance(payload, Mapping)
            or set(payload.keys()) != _REQUIRED_KEYS
            or payload.get("schema_version") != "1.0"
        ):
            return None, "schema_invalid", False
        session_id = _identifier(payload.get("session_id"))
        turn_id = _identifier(payload.get("turn_id"))
        if session_id is None or turn_id is None:
            return None, "schema_invalid", False
        try:
            response = await query.get(session_id=session_id, turn_id=turn_id)
        except StoryExpressionError as exc:
            return None, _public_expression_error(exc.code), False
        except (StorageError, StoryQueryError, StoryBootstrapError):
            return None, "service_unavailable", True
        except Exception:  # noqa: BLE001 - keep storage details off the wire
            return None, "service_unavailable", True
        return (
            response.model_dump(mode="json", exclude_none=True),
            None,
            False,
        )

    return {STORY_EXPRESSION_GET_METHOD: get_expression}


def _identifier(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 256
        or "\x00" in value
    ):
        return None
    return value


def _public_expression_error(code: str) -> str:
    if code in {"turn_identity_mismatch", "turn_session_mismatch"}:
        return "authorization_denied"
    if code in {"invalid_session_id", "invalid_turn_id"}:
        return "schema_invalid"
    return "recovery_required"


__all__ = [
    "STORY_EXPRESSION_GET_METHOD",
    "SQLiteNarrativePublicIdentityReader",
    "story_expression_control_handlers",
]
