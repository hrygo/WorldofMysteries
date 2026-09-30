"""The typed IPC face of voice supply.

Everything a client can ask about a casting task arrives here first. The
module exists because the alternative is worse: a handler that trusts its
payload. Three things are checked before any of it is believed.

* **The envelope is exactly what the contract declares.** A command names
  its own action, so a caller cannot post ``voice.foundry.cancel`` carrying a
  publish; the method and the action have to agree.
* **The digest covers the payload it travelled with.** ``payload_digest`` is
  the caller's own claim about what it is asking for, and a claim that does
  not describe the bytes beside it is refused before it can be recorded as
  an authorization.
* **The revision the caller acted on is still the current one.** Every
  command carries ``expected_task_revision``. Without this check a client
  reading a stale task would still succeed, and the revision guard the
  contract promises would be decoration.

Writes are idempotent under the caller's ``command_id``: a repeat returns the
original answer instead of advancing the task a second time. Two verbs
(``select``, ``cancel``, ``retry``) are journalled by the command service
that owns them; the four worker verbs are journalled here, because the
worker settles its own provider intents and has no command journal of its
own.

``voice.foundry.publish`` is here because its binding key is not a client
choice: ``voice_bindings`` already declares the scope unique, so the key is
derived from the task's own scope and the repository refuses a mismatch.

Deliberately still absent: ``voice.binding.replace``. It re-points a binding
that already exists, so it has no task to hang its idempotency receipt on,
and the command journal this surface uses is keyed by task.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from application.voice_foundry import VoiceFoundryWorker
from application.voice_foundry_commands import (
    VoiceFoundryCommandError,
    VoiceFoundryCommandService,
)
from application.voice_foundry_ports import (
    FoundryReviewVerdict,
    VoiceFoundryPortError,
)
from application.voice_foundry_service import VoiceSupplyService

from .voice_foundry_repository import (
    SQLiteVoiceFoundryRepository,
    VoiceCandidateRecord,
    VoiceCommandAck,
)

ControlHandler = Callable[
    [Mapping[str, object]], Awaitable[tuple[dict[str, object] | None, str | None]]
]

SCHEMA_VERSION = "1.0"

_COMMAND_KEYS = frozenset(
    {
        "schema_version",
        "command_id",
        "payload_digest",
        "task_id",
        "expected_task_revision",
        "action",
        "payload",
    }
)

_VERDICTS = {"pass": FoundryReviewVerdict.PASS, "reject": FoundryReviewVerdict.REJECT}


class _Rejected(Exception):
    """A refusal the caller is allowed to see, in the caller's own words."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise _Rejected("schema_invalid")
    if "\x00" in value:
        raise _Rejected("schema_invalid")
    return value


def _request(
    payload: Mapping[str, object],
    required: set[str],
    optional: frozenset[str] = frozenset(),
) -> Mapping[str, object]:
    """Accept exactly the keys the contract declares, and no others.

    The whole payload is returned rather than a narrowed copy: dropping the
    keys a caller is allowed to omit is how a paging token silently becomes
    ``None`` on the way down and every page comes back identical.
    """
    keys = set(payload)
    if not required <= keys or not keys <= required | optional:
        raise _Rejected("schema_invalid")
    return payload


def voice_foundry_control_handlers(
    *,
    repository: SQLiteVoiceFoundryRepository,
    supply: VoiceSupplyService,
    commands: VoiceFoundryCommandService,
    worker: VoiceFoundryWorker,
) -> dict[str, ControlHandler]:
    """The registered methods, keyed by the capability the client asks for."""
    return {
        "voice.foundry.get": _wire(_get, repository, supply, None, None),
        "voice.foundry.list": _wire(_list, repository, supply, None, None),
        "voice.foundry.select": _wire(
            _select, repository, supply, commands, "select"
        ),
        "voice.foundry.confirm_reference": _wire(
            _confirm_reference, repository, supply, worker, "confirm_reference"
        ),
        "voice.foundry.validate": _wire(
            _validate, repository, supply, worker, "validate"
        ),
    "voice.foundry.review": _wire(_review, repository, supply, worker, "review"),
    "voice.foundry.publish": _wire(_publish, repository, supply, worker, "publish"),
    "voice.foundry.retry": _wire(_retry, repository, supply, commands, "retry"),
        "voice.foundry.cancel": _wire(
            _cancel, repository, supply, commands, "cancel"
        ),
    }


def _wire(
    operation: Callable[..., Awaitable[dict[str, object]]],
    repository: SQLiteVoiceFoundryRepository,
    supply: VoiceSupplyService,
    driver: VoiceFoundryCommandService | VoiceFoundryWorker | None,
    action: str | None,
) -> ControlHandler:
    """One public refusal shape, whatever went wrong underneath.

    Only the ``code`` of an error this system's own layers raise is passed
    through; those are written as wire codes precisely so a client can act on
    them. Everything else collapses to ``service_unavailable`` rather than
    carrying an internal message out to a caller.
    """

    async def handler(
        payload: Mapping[str, object],
    ) -> tuple[dict[str, object] | None, str | None]:
        try:
            return (
                await operation(payload, repository, supply, driver, action),
                None,
            )
        except _Rejected as exc:
            return None, exc.code
        except (VoiceFoundryCommandError, VoiceFoundryPortError) as exc:
            return None, exc.code
        except Exception:  # noqa: BLE001 - one stable public code for the rest
            return None, "service_unavailable"

    return handler


# -- reads ---------------------------------------------------------------


async def _get(
    payload: Mapping[str, object],
    repository: SQLiteVoiceFoundryRepository,
    supply: VoiceSupplyService,
    driver: object,
    action: str | None,
) -> dict[str, object]:
    request = _request(payload, {"schema_version", "task_id"})
    _version(request["schema_version"])
    result = await supply.get(_identifier(request["task_id"]))
    return {"schema_version": SCHEMA_VERSION, "task": _task_of(result)}


async def _list(
    payload: Mapping[str, object],
    repository: SQLiteVoiceFoundryRepository,
    supply: VoiceSupplyService,
    driver: object,
    action: str | None,
) -> dict[str, object]:
    request = _request(
        payload, {"schema_version", "page_size"}, frozenset({"page_token", "stage"})
    )
    _version(request["schema_version"])
    page_size = request["page_size"]
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise _Rejected("schema_invalid")
    try:
        page = await supply.list(
            page_size=page_size,
            page_token=_optional(request.get("page_token")),
            stage=_optional(request.get("stage")),
        )
    except ValueError:
        # The token is opaque on purpose, so this is the only place a caller
        # can hand back something the service did not issue. It is told so
        # rather than shown a different page: a paging bug that reads as
        # "there is nothing here" is harder to notice than one that announces
        # itself.
        raise _Rejected("page_token_invalid") from None
    return {
        "schema_version": SCHEMA_VERSION,
        "tasks": [_task_of(item) for item in page.tasks],
        "next_page_token": page.next_page_token,
    }


# -- commands ------------------------------------------------------------


async def _select(
    payload: Mapping[str, object],
    repository: SQLiteVoiceFoundryRepository,
    supply: VoiceSupplyService,
    driver: object,
    action: str | None,
) -> dict[str, object]:
    command = await _command(payload, repository, action)
    body = _request(
        command["payload"], {"candidate_id", "preview_audio_digest"}
    )
    candidate_id = _identifier(body["candidate_id"])
    # The client names the preview it chose between. Checking it against the
    # candidate's own record is what makes that claim mean something: a
    # selection made from a preview that no longer exists is a decision
    # nobody made.
    candidate = await repository.load_candidate(command["task_id"], candidate_id)
    if candidate.preview_audio_digest != _digest_field(body["preview_audio_digest"]):
        raise _Rejected("select_asset_mismatch")
    await _commands(driver).select_candidate(
        command_id=command["command_id"],
        task_id=command["task_id"],
        candidate_id=candidate_id,
    )
    return await _acknowledged(command, supply)


async def _confirm_reference(
    payload: Mapping[str, object],
    repository: SQLiteVoiceFoundryRepository,
    supply: VoiceSupplyService,
    driver: object,
    action: str | None,
) -> dict[str, object]:
    command = await _command(payload, repository, action)
    body = _request(
        command["payload"],
        {"provider_candidate_revision", "reference_text", "reference_audio_digest"},
    )
    await _worker(driver).confirm_reference_step(
        command["task_id"],
        provider_candidate_revision=_identifier(body["provider_candidate_revision"]),
        reference_text=_text(body["reference_text"]),
        reference_audio_digest=_digest_field(body["reference_audio_digest"]),
    )
    return await _journalled(command, repository, supply, "confirm_reference")


async def _validate(
    payload: Mapping[str, object],
    repository: SQLiteVoiceFoundryRepository,
    supply: VoiceSupplyService,
    driver: object,
    action: str | None,
) -> dict[str, object]:
    command = await _command(payload, repository, action)
    body = _request(command["payload"], {"test_text", "capability_key"})
    await _worker(driver).validate_step(
        command["task_id"],
        test_text=_text(body["test_text"]),
        capability_key=_identifier(body["capability_key"]),
    )
    return await _journalled(command, repository, supply, "validate")


async def _review(
    payload: Mapping[str, object],
    repository: SQLiteVoiceFoundryRepository,
    supply: VoiceSupplyService,
    driver: object,
    action: str | None,
) -> dict[str, object]:
    command = await _command(payload, repository, action)
    body = _request(command["payload"], {"human_review"})
    if not isinstance(body["human_review"], Mapping):
        raise _Rejected("schema_invalid")
    review = _request(
        body["human_review"],
        {
            "validation_id",
            "reference_audio_digest",
            "validation_audio_digest",
            "identity",
            "naturalness",
        },
    )
    # The candidate is read back from the task rather than taken from the
    # request: a verdict is about the voice this task actually parked for
    # review, and a client naming a different one is describing something
    # that was never auditioned.
    candidate = await _candidate_in_state(
        repository,
        command["task_id"],
        "reviewing",
        absent="candidate_not_awaiting_review",
    )
    await _worker(driver).submit_review(
        command["task_id"],
        candidate_id=candidate.candidate_id,
        validation_id=_identifier(review["validation_id"]),
        reference_audio_digest=_digest_field(review["reference_audio_digest"]),
        validation_audio_digest=_digest_field(review["validation_audio_digest"]),
        identity=_verdict(review["identity"]),
        naturalness=_verdict(review["naturalness"]),
    )
    return await _journalled(command, repository, supply, "review")


async def _publish(
    payload: Mapping[str, object],
    repository: SQLiteVoiceFoundryRepository,
    supply: VoiceSupplyService,
    driver: object,
    action: str | None,
) -> dict[str, object]:
    """Release the reviewed voice and bind it, in one authorized step.

    The binding key is not asked for. It is derived from the task's own scope,
    which is the same fact ``voice_bindings`` already declares unique, so a
    caller cannot point one character's voice at another character's row. The
    repository refuses a mismatch as well; deriving it here is what keeps the
    request from being built wrong in the first place.
    """
    command = await _command(payload, repository, action)
    body = _request(command["payload"], {"provider_candidate_revision"})
    candidate = await _candidate_in_state(
        repository,
        command["task_id"],
        "published",
        absent="candidate_not_published",
    )
    # The caller names the revision it approved. Publishing is irreversible
    # upstream, so the revision that goes out has to be the one a person
    # actually heard, not merely the one on the row today.
    if (
        candidate.provider_candidate_revision
        != _identifier(body["provider_candidate_revision"])
    ):
        raise _Rejected("publish_revision_mismatch")
    task = await repository.load_task(command["task_id"])
    await _worker(driver).publish_and_bind(
        command["task_id"],
        binding_id=task.scope.binding_identity,
    )
    return await _journalled(command, repository, supply, "publish")


async def _retry(
    payload: Mapping[str, object],
    repository: SQLiteVoiceFoundryRepository,
    supply: VoiceSupplyService,
    driver: object,
    action: str | None,
) -> dict[str, object]:
    command = await _command(payload, repository, action)
    _request(command["payload"], set())
    await _commands(driver).retry(
        command_id=command["command_id"], task_id=command["task_id"]
    )
    return await _acknowledged(command, supply)


async def _cancel(
    payload: Mapping[str, object],
    repository: SQLiteVoiceFoundryRepository,
    supply: VoiceSupplyService,
    driver: object,
    action: str | None,
) -> dict[str, object]:
    command = await _command(payload, repository, action)
    body = _request(command["payload"], set(), frozenset({"reason_code"}))
    reason = body.get("reason_code")
    await _commands(driver).cancel(
        command_id=command["command_id"],
        task_id=command["task_id"],
        reason_code=None if reason is None else _identifier(reason),
    )
    return await _acknowledged(command, supply)


# -- envelope ------------------------------------------------------------


async def _command(
    payload: Mapping[str, object],
    repository: SQLiteVoiceFoundryRepository,
    action: str | None,
) -> dict[str, Any]:
    if set(payload) != _COMMAND_KEYS:
        raise _Rejected("schema_invalid")
    _version(payload["schema_version"])
    if payload["action"] != action:
        # The contract binds each action to its own payload shape, so a
        # mismatch is not a caller that wants something else — it is a caller
        # that has not read which method it is calling.
        raise _Rejected("action_not_available_on_this_method")
    body = payload["payload"]
    if not isinstance(body, Mapping):
        raise _Rejected("schema_invalid")
    if _digest(body) != payload["payload_digest"]:
        raise _Rejected("command_digest_mismatch")

    task_id = _identifier(payload["task_id"])
    command_id = _identifier(payload["command_id"])

    # A receipt is asked for before the revision is, because a client that
    # never saw the answer retries with the revision it *did* see. Checking
    # the revision first would answer every honest retry with
    # ``stale_task_revision`` and make the command id useless as an
    # idempotency key — which is the one thing it exists to be.
    receipt = await repository.load_command(command_id)
    if receipt is not None and receipt.task_id != task_id:
        raise _Rejected("command_id_rebound_to_different_input")

    expected = payload["expected_task_revision"]
    if type(expected) is not int or expected < 1:
        raise _Rejected("schema_invalid")
    if receipt is None:
        task = await repository.load_task(task_id)
        if task.task_revision != expected:
            raise _Rejected("stale_task_revision")
    return {
        "command_id": command_id,
        "task_id": task_id,
        "payload": body,
        "replayed": receipt is not None,
    }


async def _journalled(
    command: Mapping[str, Any],
    repository: SQLiteVoiceFoundryRepository,
    supply: VoiceSupplyService,
    action: str,
) -> dict[str, object]:
    """Record the worker's acceptance, then answer.

    The worker settles its provider intents against its own operation
    journal, so this is the only place a repeat of a worker verb is
    recognised. Writing the receipt after the step — not before — means a
    crash in between costs a repeated call, and every worker verb is
    idempotent under its operation identity anyway.
    """
    if not command["replayed"]:
        await repository.accept_command(
            VoiceCommandAck(
                command_id=command["command_id"],
                task_id=command["task_id"],
                payload_digest=_digest(command["payload"]),
                accepted_result={"verb": action},
            )
        )
    return await _acknowledged(command, supply)


async def _acknowledged(
    command: Mapping[str, Any],
    supply: VoiceSupplyService,
) -> dict[str, object]:
    result = await supply.get(command["task_id"])
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": command["task_id"],
        "command_id": command["command_id"],
        "accepted": True,
        "replayed": command["replayed"],
        "task": _task_of(result),
    }


# -- field readers -------------------------------------------------------


def _version(value: object) -> None:
    if value != SCHEMA_VERSION:
        raise _Rejected("schema_invalid")


def _text(value: object) -> str:
    if not isinstance(value, str) or not 20 <= len(value) <= 240:
        raise _Rejected("schema_invalid")
    return value


def _digest_field(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise _Rejected("schema_invalid")
    if any(character not in "0123456789abcdef" for character in value):
        raise _Rejected("schema_invalid")
    return value


def _verdict(value: object) -> FoundryReviewVerdict:
    try:
        return _VERDICTS[str(value)]
    except KeyError:
        raise _Rejected("schema_invalid") from None


def _optional(value: object) -> str | None:
    return None if value is None else _identifier(value)


def _commands(driver: object) -> VoiceFoundryCommandService:
    if not isinstance(driver, VoiceFoundryCommandService):
        raise _Rejected("service_unavailable")
    return driver


def _worker(driver: object) -> VoiceFoundryWorker:
    if not isinstance(driver, VoiceFoundryWorker):
        raise _Rejected("service_unavailable")
    return driver


async def _candidate_in_state(
    repository: SQLiteVoiceFoundryRepository,
    task_id: str,
    state: str,
    *,
    absent: str,
) -> VoiceCandidateRecord:
    """The one candidate this task parked in a given state, read back.

    A client that named the candidate itself would be naming a row it could
    have read at any time; the state the task is sitting in is the fact that
    says which row the decision is actually about.
    """
    for candidate in await repository.load_candidates(task_id):
        if candidate.state == state:
            return candidate
    raise _Rejected(absent)


def _task_of(result: object) -> dict[str, object]:
    state = getattr(result, "state", None)
    if state is None:
        raise _Rejected("service_unavailable")
    return state.to_contract()


__all__ = ["ControlHandler", "SCHEMA_VERSION", "voice_foundry_control_handlers"]
