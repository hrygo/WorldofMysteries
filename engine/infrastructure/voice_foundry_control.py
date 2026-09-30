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

``voice.foundry.asset.get`` is the one read that carries audio out of this
process. It is served here rather than by the client reaching the provider
itself so that the digest a review is checked against describes the very bytes
the client was handed.

Deliberately still absent: ``voice.binding.replace``. It re-points a binding
that already exists, so it has no task to hang its idempotency receipt on,
and the command journal this surface uses is keyed by task.
"""

from __future__ import annotations

import base64
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

from domain.voice_identity import VoiceBindingScope

from .voice_design_catalog import VoiceDesignCatalog
from .voice_foundry_repository import (
    SQLiteVoiceFoundryRepository,
    VoiceCastBudget,
    VoiceCandidateRecord,
    VoiceCommandAck,
    VoiceExecutionScope,
    VoiceFoundryTaskSpec,
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
    designs: VoiceDesignCatalog | None = None,
) -> dict[str, ControlHandler]:
    """The registered methods, keyed by the capability the client asks for."""
    handlers = {
        "voice.foundry.request": _wire(_request_op, repository, supply, None, None),
        "voice.foundry.get": _wire(_get, repository, supply, None, None),
        "voice.foundry.list": _wire(_list, repository, supply, None, None),
        "voice.foundry.asset.get": _wire(
            _asset, repository, supply, worker, None
        ),
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
    if designs is not None:
        # Absent rather than answering "service_unavailable": a catalog that
        # would not load means this process genuinely cannot describe a
        # casting, and a handshake that lists the method anyway is a promise
        # the engine is not keeping.
        handlers["voice.foundry.list_designs"] = _designs(designs)
    return handlers


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


def _designs(designs: VoiceDesignCatalog) -> ControlHandler:
    """Publish the casting briefs a person chooses from.

    The App needs these to offer a choice of whom to cast, and it needs the
    brief's own text because a ``voice.foundry.request`` carries the whole
    brief and the engine recomputes its digest — a client that invented its
    own wording would be refused. Handing out the catalog rather than a
    display name is what keeps one authority over what a character sounds
    like: the content, not the interface.

    A pure read. It starts nothing, casts nothing, and says nothing about any
    task — which is the whole reason the App can show a picker without a
    player being interrupted by the mere act of opening one.
    """

    async def handler(
        payload: Mapping[str, object],
    ) -> tuple[dict[str, object] | None, str | None]:
        try:
            request = _request(payload, {"schema_version"})
            _version(request["schema_version"])
        except _Rejected as exc:
            return None, exc.code
        return (
            {
                "schema_version": "1.0",
                "catalog_version": designs.catalog_version,
                "designs": [
                    {
                        "schema_version": "1.0",
                        "design_id": design.design_id,
                        "display_name": design.display_name,
                        "presentation_identity": design.presentation_identity,
                        "usage": design.usage,
                        "locale": design.locale,
                        "design_revision": design.design_revision,
                        "public_traits": list(design.public_traits),
                        "voice_description": design.voice_description,
                        "reference_text": design.reference_text,
                        "validation_text": design.validation_text,
                    }
                    for design in designs.designs
                ],
            },
            None,
        )

    return handler


# -- intake --------------------------------------------------------------


async def _request_op(
    payload: Mapping[str, object],
    repository: SQLiteVoiceFoundryRepository,
    supply: VoiceSupplyService,
    driver: object,
    action: str | None,
) -> dict[str, object]:
    """Open a casting task, or report that this identity already has a voice.

    The one write here that is not a command: it acts on no existing task, so
    there is no revision to be stale against and no command id to replay
    under. Idempotence is the request's own — ``request_id`` replays, and a
    payload that changed underneath the same id is a conflict rather than a
    second casting.

    The digest is recomputed rather than believed. "Same request id, different
    digest" is only a conflict if the digest describes the request; a caller
    free to send any 64 hex characters would make that check vacuous, and the
    scope-in-flight guard behind it would stop detecting a changed recipe.
    """
    request = _request(payload, {"schema_version", "request"})
    _version(request["schema_version"])
    body = _request(
        request["request"],
        {
            "schema_version",
            "request_id",
            "request_digest",
            "authorization_ref",
            "scope",
            "persona_revision",
            "usage",
            "locale",
            "public_traits",
            "voice_description",
            "reference_text",
            "validation_text",
            "provider_instance",
            "requested_execution_scope",
            "budget",
            "origin",
        },
    )
    _version(body["schema_version"])
    claimed = _digest_field(body["request_digest"])
    if _digest({key: value for key, value in body.items() if key != "request_digest"}) != claimed:
        raise _Rejected("request_digest_mismatch")

    scope = _request(
        body["scope"],
        {
            "owner_id",
            "world_id",
            "worldline_id",
            "presentation_identity",
            "phase",
            "locale",
        },
    )
    origin = _request(body["origin"], {"kind", "source_ref", "source_revision"})
    traits = body["public_traits"]
    if not isinstance(traits, list) or not all(
        isinstance(item, str) for item in traits
    ):
        raise _Rejected("schema_invalid")
    execution = _request(
        body["requested_execution_scope"],
        {"model_id", "model_artifact_revision", "variant"},
    )
    budget = _request(
        body["budget"], {"candidate_count", "timeout_ms", "max_audio_bytes"}
    )

    request_id = _identifier(body["request_id"])
    result = await supply.request(
        VoiceFoundryTaskSpec(
            # Derived, not supplied: the contract has no task id, and one
            # derived from the request id means a retry addresses the same
            # row without the caller having to remember what it asked for.
            task_id="task-" + hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24],
            request_id=request_id,
            request_digest=claimed,
            authorization_ref=_identifier(body["authorization_ref"]),
            scope=VoiceBindingScope(
                owner_id=_identifier(scope["owner_id"]),
                world_id=_identifier(scope["world_id"]),
                worldline_id=_identifier(scope["worldline_id"]),
                presentation_identity=_identifier(scope["presentation_identity"]),
                phase=_identifier(scope["phase"]),
                locale=_identifier(scope["locale"]),
            ),
            persona_revision=_identifier(body["persona_revision"]),
            usage=_identifier(body["usage"]),
            provider_instance=_identifier(body["provider_instance"]),
            public_traits=tuple(traits),
            voice_description=_identifier(body["voice_description"]),
            reference_text=_text(body["reference_text"]),
            validation_text=_text(body["validation_text"]),
            origin_kind=_identifier(origin["kind"]),
            origin_ref=_identifier(origin["source_ref"]),
            origin_revision=_integer(origin["source_revision"]),
            execution_scope=VoiceExecutionScope(
                variant=_identifier(execution["variant"]),
                model_id=_optional(execution.get("model_id")),
                model_artifact_revision=_optional(
                    execution.get("model_artifact_revision")
                ),
            ),
            budget=VoiceCastBudget(
                candidate_count=_integer(budget["candidate_count"]),
                timeout_ms=_integer(budget["timeout_ms"]),
                max_audio_bytes=_integer(budget["max_audio_bytes"]),
            ),
        )
    )
    return _supply_of(result)


def _supply_of(result: object) -> dict[str, object]:
    """A voice that already exists is an answer, not an empty casting.

    The task keys are left out when there is no task, which is the case the
    contract forbids pairing with ``ready``: reporting a task id for a
    casting that never happened would send someone looking for candidates
    that were never minted.
    """
    outcome = getattr(result, "outcome", None)
    if outcome is None:
        raise _Rejected("service_unavailable")
    body: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "outcome": str(outcome),
    }
    state = getattr(result, "state", None)
    if state is not None:
        body["task_id"] = state.task_id
        body["task"] = state.to_contract()
    binding_id = getattr(result, "binding_id", None)
    if binding_id is not None:
        body["binding_id"] = binding_id
    reason_code = getattr(result, "reason_code", None)
    if reason_code is not None:
        body["reason_code"] = reason_code
    return body


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


async def _asset(
    payload: Mapping[str, object],
    repository: SQLiteVoiceFoundryRepository,
    supply: VoiceSupplyService,
    driver: object,
    action: str | None,
) -> dict[str, object]:
    """Hand a listener the audio, and the facts that say what it is.

    The bytes are read here rather than fetched by the client from the
    provider, because ``review`` accepts digests and this engine has to be
    able to stand behind them. A client that fetched the audio itself could
    hand back a digest for whatever it liked; reading it here means the
    digest in the answer describes the same bytes the answer carries, and the
    review that follows is checked against exactly what a person heard.

    Nothing here is journalled. An audition moves no state, so a repeat costs
    one provider read and nothing else.
    """
    request = _request(
        payload, {"schema_version", "task_id", "candidate_id", "kind"}
    )
    _version(request["schema_version"])
    kind = request["kind"]
    if kind not in ("reference", "validation"):
        raise _Rejected("schema_invalid")
    task_id = _identifier(request["task_id"])
    asset = await _worker(driver).audition_asset(
        task_id,
        candidate_id=_identifier(request["candidate_id"]),
        kind=kind,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "candidate_id": asset.candidate_id,
        "kind": asset.kind,
        "candidate_revision": asset.candidate_revision,
        "validation_id": asset.validation_id,
        "audio_digest": asset.audio_digest,
        "audio_bytes": len(asset.audio),
        "audio_base64": base64.b64encode(asset.audio).decode("ascii"),
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


def _integer(value: object) -> int:
    # ``type(...) is int`` rather than isinstance: a bool is an int in
    # Python, and ``candidate_count: true`` is not a candidate count.
    if type(value) is not int:
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
