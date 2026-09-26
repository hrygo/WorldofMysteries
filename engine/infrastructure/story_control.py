"""Public story control handlers bound to the frozen IPC request context.

Handlers only translate the wire payload into facade calls. Transport identity
(request_id / trace_id) and the business idempotency key come from the
authenticated envelope, never from payload duplicates.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from application.story_session_facade import (
    StoryFacadeError,
    StorySessionFacade,
    SubmitAdviceCommand,
)

from .story_bootstrap_repository import StoryBootstrapError
from .story_session_query import StoryQueryError

SCHEMA_VERSION = "1.0"
MAX_REVISION = 2**63 - 1
MAX_EXPECTED_REVISION = 2**63 - 2
MAX_IDENTIFIER = 256
MAX_RAW_INPUT = 16384

STORY_METHODS = (
    "story.entry.get",
    "story.session.open",
    "story.session.get",
    "story.advice.submit",
    "story.advice.get",
)
STORY_MUTATIONS = frozenset({"story.session.open", "story.advice.submit"})

StoryRequestHandler = Callable[
    [Mapping[str, object], Mapping[str, object]],
    Awaitable[tuple[dict[str, object] | None, str | None, bool]],
]

_PUBLIC_CODES = frozenset(
    {
        "schema_invalid",
        "authorization_denied",
        "deterministic_input_unsupported",
        "iteration_limit_reached",
        "input_turn_identity_conflict",
        "pending_turn_exists",
        "revision_conflict",
        "recovery_required",
        "input_turn_cancelled",
        "story_session_not_active",
        "service_unavailable",
        "storage_failure",
    }
)
_CODE_ALIASES = {
    "invalid_open_identity": "schema_invalid",
    "invalid_request_identity": "schema_invalid",
    "invalid_trace_identity": "schema_invalid",
    "invalid_store_expected_revision": "schema_invalid",
    "invalid_session_id": "schema_invalid",
    "invalid_input_turn_id": "schema_invalid",
    "unsupported_scenario": "schema_invalid",
    "story_session_not_found": "authorization_denied",
    "story_session_corrupt": "recovery_required",
    "committed_turn_missing_story_revision": "recovery_required",
}
_RETRYABLE_CODES = frozenset({"service_unavailable", "storage_failure"})


class _Rejected(RuntimeError):
    """Client payload rejected before any durable state was touched."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def story_control_handlers(
    facade: StorySessionFacade,
) -> dict[str, StoryRequestHandler]:
    return {
        "story.entry.get": _wire(_entry, facade, "story.entry.get"),
        "story.session.open": _wire(_open, facade, "story.session.open"),
        "story.session.get": _wire(_get, facade, "story.session.get"),
        "story.advice.submit": _wire(_submit, facade, "story.advice.submit"),
        "story.advice.get": _wire(_get_advice, facade, "story.advice.get"),
    }


def _wire(
    operation: Callable[..., Awaitable[Any]],
    facade: StorySessionFacade,
    method: str,
) -> StoryRequestHandler:
    async def handler(
        context: Mapping[str, object], payload: Mapping[str, object]
    ) -> tuple[dict[str, object] | None, str | None, bool]:
        try:
            view = await operation(facade, context, payload)
            return view.model_dump(mode="json", exclude_none=True), None, False
        except _Rejected as exc:
            return None, exc.code, False
        except (StoryFacadeError, StoryQueryError, StoryBootstrapError) as exc:
            code = _code(exc.code)
            return None, code, _retryable(code, method)
        except Exception:  # noqa: BLE001 - unknown failures get one stable public code
            code = "service_unavailable"
            return None, code, _retryable(code, method)

    return handler


def _code(value: str) -> str:
    if value in _CODE_ALIASES:
        return _CODE_ALIASES[value]
    if value in _PUBLIC_CODES:
        return value
    return "service_unavailable"


def _retryable(code: str, method: str) -> bool:
    # A mutation is never re-sent automatically: the caller must first read
    # back the durable result of the unknown outcome.
    return code in _RETRYABLE_CODES and method not in STORY_MUTATIONS


def _schema(payload: Mapping[str, object], required: tuple[str, ...]) -> None:
    if not isinstance(payload, Mapping):
        raise _Rejected("schema_invalid")
    if set(payload.keys()) != set(required):
        raise _Rejected("schema_invalid")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise _Rejected("schema_invalid")


def _identifier(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_IDENTIFIER
        or "\x00" in value
    ):
        raise _Rejected("schema_invalid")
    return value


def _revision(value: object, *, expected: bool = False) -> int:
    limit = MAX_EXPECTED_REVISION if expected else MAX_REVISION
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= limit:
        raise _Rejected("schema_invalid")
    return value


def _raw_input(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_RAW_INPUT
        or "\x00" in value
    ):
        raise _Rejected("schema_invalid")
    return value


def _context_text(context: Mapping[str, object], key: str) -> str:
    return _identifier(context.get(key))


def _idempotency(context: Mapping[str, object], expected: str) -> None:
    if context.get("idempotency_key") != expected:
        raise _Rejected("schema_invalid")


async def _entry(facade, context, payload):
    _schema(payload, ("schema_version", "scenario_id"))
    return await facade.entry(_identifier(payload["scenario_id"]))


async def _open(facade, context, payload):
    _schema(
        payload,
        ("schema_version", "scenario_id", "open_request_id", "expected_store_revision"),
    )
    scenario_id = _identifier(payload["scenario_id"])
    open_request_id = _identifier(payload["open_request_id"])
    expected_store_revision = _revision(
        payload["expected_store_revision"], expected=True
    )
    _idempotency(context, open_request_id)
    return await facade.open(
        scenario_id=scenario_id,
        open_request_id=open_request_id,
        expected_store_revision=expected_store_revision,
        request_id=_context_text(context, "request_id"),
        trace_id=_context_text(context, "trace_id"),
    )


async def _get(facade, context, payload):
    _schema(payload, ("schema_version", "session_id"))
    return await facade.get(_identifier(payload["session_id"]))


async def _submit(facade, context, payload):
    _schema(
        payload,
        (
            "schema_version",
            "session_id",
            "input_turn_id",
            "raw_input",
            "expected_story_revision",
            "expected_store_revision",
        ),
    )
    session_id = _identifier(payload["session_id"])
    input_turn_id = _identifier(payload["input_turn_id"])
    _idempotency(context, input_turn_id)
    return await facade.submit(
        SubmitAdviceCommand(
            session_id=session_id,
            input_turn_id=input_turn_id,
            raw_input=_raw_input(payload["raw_input"]),
            expected_story_revision=_revision(
                payload["expected_story_revision"], expected=True
            ),
            expected_store_revision=_revision(
                payload["expected_store_revision"], expected=True
            ),
            request_id=_context_text(context, "request_id"),
            trace_id=_context_text(context, "trace_id"),
        )
    )


async def _get_advice(facade, context, payload):
    _schema(payload, ("schema_version", "session_id", "input_turn_id"))
    return await facade.get_advice(
        _identifier(payload["session_id"]),
        _identifier(payload["input_turn_id"]),
    )
