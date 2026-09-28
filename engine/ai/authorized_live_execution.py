"""Authorized execution for one structured gameplay model call.

This path keeps the context, authorization, rendering, and provider wire separate.
It deliberately does not use ``GameplayAIGateway`` because the configured live
provider has no verified token counter. The request is bounded by deterministic
serialized-byte and message limits; this module makes no exact token-budget claim.
The returned value is a proposal only and has no persistence capability.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
import math
from time import monotonic
from typing import Any, Callable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from application.context_compiler import CacheAwareContextCompiler
from application.context_epoch import ContextEpochRegistry
from application.context_plan import (
    ContextError,
    ContextInput,
    PromptPlan,
    WorkerProfile,
    canonical_json,
    parse_json,
)
from application.gameplay_context import (
    GameplayCall,
    GameplayContextCoordinator,
    GameplayRecipe,
    ModelUse,
    gameplay_recipe,
)

from .openai_compatible import (
    ModelTransportError,
    OpenAICompatibleChatTransport,
    chat_wire,
)
from .prompt_renderer import PromptRenderer

_REPAIR_HINT = (
    "Return one valid JSON object matching the output schema. "
    "No markdown, no code fence, no commentary."
)
_MAX_REPLY_BYTES = 262_144
_MAX_OUTPUT_TOKENS = 8_192
_MAX_REQUEST_BYTES = 8 * 1024 * 1024
_NARRATIVE_TASK = canonical_json({
    "task": "Narrate only the Domain-authorized disclosed committed results."
})


@dataclass(frozen=True)
class AuthorizedExecutionBudget:
    """Deterministic provider bounds; no token-count estimate is accepted."""

    output_tokens: int
    timeout_seconds: float = 45.0
    max_reply_bytes: int = _MAX_REPLY_BYTES
    max_request_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        if type(self.output_tokens) is not int or not 1 <= self.output_tokens <= _MAX_OUTPUT_TOKENS:
            raise ValueError("invalid_execution_budget")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= 600
        ):
            raise ValueError("invalid_execution_budget")
        if (
            type(self.max_reply_bytes) is not int
            or not 1 <= self.max_reply_bytes <= _MAX_REPLY_BYTES
            or type(self.max_request_bytes) is not int
            or not 1 <= self.max_request_bytes <= _MAX_REQUEST_BYTES
        ):
            raise ValueError("invalid_execution_budget")


@dataclass(frozen=True, repr=False)
class AuthorizedProposalResult:
    """A validated candidate without token accounting or commit authority."""

    proposal_json: str = field(repr=False)
    attempts: int
    elapsed_seconds: float

    def proposal(self) -> dict[str, Any]:
        value = parse_json(self.proposal_json)
        assert isinstance(value, dict)
        return value


class AuthorizedLiveExecution:
    """Execute a prepared structured call using its Domain-authorized context."""

    def __init__(
        self,
        *,
        coordinator: GameplayContextCoordinator,
        renderer: PromptRenderer,
        transport: OpenAICompatibleChatTransport,
        validate_proposal: Callable[[dict[str, Any], ContextInput], bool],
        epochs: ContextEpochRegistry | None = None,
    ) -> None:
        if not isinstance(coordinator, GameplayContextCoordinator):
            raise ContextError("invalid_gameplay_coordinator")
        if not isinstance(renderer, PromptRenderer):
            raise ContextError("invalid_prompt_renderer")
        if not isinstance(transport, OpenAICompatibleChatTransport):
            raise ContextError("invalid_model_endpoint")
        if not callable(validate_proposal):
            raise ContextError("invalid_proposal_validator")
        self.coordinator = coordinator
        self.renderer = renderer
        self.transport = transport
        self.validate_proposal = validate_proposal
        self.epochs = epochs if epochs is not None else ContextEpochRegistry()
        self.compiler = CacheAwareContextCompiler()
        self._target = transport.config.provider_profile()

    async def execute(
        self,
        call: GameplayCall,
        budget: AuthorizedExecutionBudget,
    ) -> AuthorizedProposalResult:
        """Return a proposal or reject it; this method never writes Domain state."""
        started = monotonic()
        try:
            async with asyncio.timeout(budget.timeout_seconds):
                return await self._execute(call, budget, started)
        except TimeoutError:
            raise ContextError("model_stage_timeout") from None
        except ContextError:
            raise
        except ModelTransportError as exc:
            raise ContextError(exc.code) from None
        except asyncio.CancelledError:
            raise
        except Exception:
            # Provider and validation failures may contain private request material.
            raise ContextError("model_stage_failed") from None

    async def _execute(
        self,
        call: GameplayCall,
        budget: AuthorizedExecutionBudget,
        started: float,
    ) -> AuthorizedProposalResult:
        recipe = gameplay_recipe(call.mode)
        if recipe.model_use is not ModelUse.STRUCTURED:
            raise ContextError("structured_model_call_required")

        prepared = await self.coordinator.prepare(call)
        request = prepared.request
        if prepared.profile.consumer == "narrative_compiler":
            # This is a player-facing expression stage. Player task text is
            # untrusted intent and is not a committed or disclosed result.
            request = replace(request, task_json=_NARRATIVE_TASK)

        plan = await self._compile_fresh(request, prepared.profile, recipe)
        self.epochs.observe(plan)
        prompt = self.renderer.render(plan)
        validator = self._validator(prepared.profile)

        for attempt in range(2):
            if attempt:
                # Reauthorize the identical immutable request before repair. The
                # prompt is deliberately not recompiled into a wider context.
                await self._compile_fresh(request, prepared.profile, recipe)
            wire = chat_wire(
                prompt.messages(),
                target=self._target,
                output_tokens=budget.output_tokens,
                json_mode=True,
                repair_hint=_REPAIR_HINT if attempt else None,
            )
            if len(wire.body_json.encode("utf-8")) > budget.max_request_bytes:
                raise ContextError("model_request_too_large")

            reply = await self.transport.send(wire)
            # A model await can outlive the authorization/revision that produced
            # the prompt. A stale response is rejected before parsing or repair.
            await self._compile_fresh(request, prepared.profile, recipe)
            if (
                not isinstance(reply.text, str)
                or len(reply.text.encode("utf-8")) > budget.max_reply_bytes
            ):
                raise ContextError("reply_size_exceeded")

            try:
                proposal = parse_json(reply.text)
                if not isinstance(proposal, dict):
                    raise ContextError("invalid_proposal_shape")
                validator.validate(proposal)
            except (ContextError, ValidationError):
                if attempt == 0:
                    continue
                raise ContextError("proposal_schema_rejected") from None

            if self.validate_proposal(proposal, request) is not True:
                raise ContextError("proposal_domain_rejected")
            return AuthorizedProposalResult(
                canonical_json(proposal),
                attempt + 1,
                monotonic() - started,
            )

        raise ContextError("proposal_schema_rejected")

    async def _compile_fresh(
        self,
        request: ContextInput,
        profile: WorkerProfile,
        recipe: GameplayRecipe,
    ) -> PromptPlan:
        view = await self.coordinator.authorize(request, recipe)
        candidate_fingerprints = {item.fingerprint for item in request.evidence}
        if not view.grants.issubset(candidate_fingerprints):
            raise ContextError("authorization_grant_outside_candidates")
        return self.compiler.compile(request, view, profile)

    @staticmethod
    def _validator(profile: WorkerProfile) -> Draft202012Validator:
        try:
            schema = parse_json(profile.schema_json)
            Draft202012Validator.check_schema(schema)
        except (ContextError, SchemaError):
            raise ContextError("invalid_output_schema") from None
        if not isinstance(schema, dict):
            raise ContextError("invalid_output_schema")

        def reject_external_refs(value: Any) -> None:
            if isinstance(value, dict):
                if "$ref" in value or "$dynamicRef" in value:
                    raise ContextError("output_schema_must_be_resolved")
                for child in value.values():
                    reject_external_refs(child)
            elif isinstance(value, list):
                for child in value:
                    reject_external_refs(child)

        reject_external_refs(schema)
        return Draft202012Validator(schema)


__all__ = [
    "AuthorizedExecutionBudget",
    "AuthorizedLiveExecution",
    "AuthorizedProposalResult",
]
