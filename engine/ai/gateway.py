"""Bounded prepared-request execution. No database access or commit capability."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Awaitable, Callable, Mapping, Protocol

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from engine.application.context_compiler import CacheAwareContextCompiler
from engine.application.context_epoch import ContextEpochRegistry
from engine.application.context_plan import (
    AuthorizationView, ContextError, ContextInput, WorkerProfile, canonical_json, parse_json,
)
from .cache_metrics import CacheUsage, normalize_usage
from .prompt_cache_policy import ProviderProfile, WireRequest, render_wire
from .prompt_renderer import PromptRenderer


@dataclass(frozen=True)
class TokenCount:
    input_tokens: int
    assurance: str  # exact or certified_upper_bound, supplied by a model-bound counter


@dataclass(frozen=True, repr=False)
class ModelReply:
    text: str = field(repr=False)
    usage: Mapping[str, Any] | None = field(default=None, repr=False)


class PreparedTransport(Protocol):
    async def send(self, request: WireRequest) -> ModelReply: ...


@dataclass(frozen=True)
class ExecutionBudget:
    context_window: int
    output_tokens: int
    timeout_seconds: float = 20.0
    schema_retries: int = 1
    max_reply_bytes: int = 262144

    def __post_init__(self) -> None:
        import math
        if any(type(v) is not int or v < 1 for v in (
            self.context_window, self.output_tokens, self.max_reply_bytes
        )):
            raise ValueError("invalid_execution_budget")
        if self.output_tokens >= self.context_window or type(self.schema_retries) is not int or not 0 <= self.schema_retries <= 2:
            raise ValueError("invalid_execution_budget")
        if not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool) or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("invalid_execution_budget")


@dataclass(frozen=True, repr=False)
class ProposalResult:
    proposal_json: str = field(repr=False)
    usage: tuple[CacheUsage, ...]
    attempts: int
    elapsed_seconds: float
    cache_key: str
    prefix_fingerprint: str

    def proposal(self) -> dict[str, Any]:
        return parse_json(self.proposal_json)


@dataclass(frozen=True)
class AttemptObservation:
    attempt: int
    counted_input: int | None
    counter_assurance: str | None
    usage: CacheUsage
    status: str
    elapsed_seconds: float
    cache_key: str


class AIGatewayProtocol(Protocol):
    async def execute(self, request: ContextInput, profile: WorkerProfile,
                      target: ProviderProfile, budget: ExecutionBudget) -> ProposalResult: ...


class CacheAwareGateway:
    """A dependency-injected execution path usable without changing Domain/IPC.

    authorize must return a fresh Domain-issued view for every invocation. Counter
    must measure the entire final body for this exact endpoint/model, including
    messages, schema, tools and protocol framing. This module provides no heuristic
    counter and no implicit network client or credentials.
    """
    def __init__(self, *, renderer: PromptRenderer, transport: PreparedTransport,
                 authorize: Callable[[ContextInput], Awaitable[AuthorizationView]],
                 count_tokens: Callable[[WireRequest], Awaitable[TokenCount]],
                 validate_proposal: Callable[[dict[str, Any], ContextInput], bool],
                 epochs: ContextEpochRegistry | None = None,
                 observe_attempt: Callable[[AttemptObservation], None] | None = None):
        self.renderer, self.transport = renderer, transport
        self.authorize, self.count_tokens = authorize, count_tokens
        self.validate_proposal = validate_proposal
        self.epochs = epochs if epochs is not None else ContextEpochRegistry()
        self.compiler = CacheAwareContextCompiler()
        self.observe_attempt = observe_attempt

    async def execute(self, request: ContextInput, profile: WorkerProfile,
                      target: ProviderProfile, budget: ExecutionBudget) -> ProposalResult:
        started = monotonic()
        try:
            async with asyncio.timeout(budget.timeout_seconds):
                return await self._execute(request, profile, target, budget, started)
        except TimeoutError:
            raise ContextError("model_stage_timeout") from None
        except ContextError:
            raise
        except Exception:
            # Do not expose provider exceptions containing request text or credentials.
            raise ContextError("model_stage_failed") from None

    async def _execute(self, request: ContextInput, profile: WorkerProfile,
                       target: ProviderProfile, budget: ExecutionBudget, started: float) -> ProposalResult:
        try:
            schema = parse_json(profile.schema_json)
            Draft202012Validator.check_schema(schema)
        except (ContextError, SchemaError):
            raise ContextError("invalid_output_schema") from None
        # Reject external refs: output validation must not trigger network retrieval.
        def no_refs(item: Any) -> None:
            if isinstance(item, dict):
                if any(k in item for k in ("$ref", "$dynamicRef")):
                    raise ContextError("output_schema_must_be_resolved")
                for value in item.values():
                    no_refs(value)
            elif isinstance(item, list):
                for value in item:
                    no_refs(value)
        no_refs(schema)
        validator = Draft202012Validator(schema)
        plan = self.compiler.compile(request, await self.authorize(request), profile)
        self.epochs.observe(plan)
        prompt = self.renderer.render(plan)
        usage: list[CacheUsage] = []
        for attempt in range(budget.schema_retries + 1):
            wire = render_wire(prompt, target, budget.output_tokens, repair=attempt > 0)
            count: TokenCount | None = None
            observed = normalize_usage(None, target.usage_format)
            status = "failed_or_cancelled"
            attempt_start = monotonic()
            try:
                count = await self.count_tokens(wire)
                if (not isinstance(count, TokenCount) or type(count.input_tokens) is not int or count.input_tokens < 0
                        or count.assurance not in {"exact", "certified_upper_bound"}):
                    count = None
                    raise ContextError("unverified_token_count")
                if count.input_tokens + budget.output_tokens > budget.context_window:
                    status = "budget_rejected"
                    raise ContextError("context_budget_exceeded")
                # The counter may await a service; reauthorize immediately before
                # sending. Provider usage is observed even if the result is stale.
                self.compiler.compile(request, await self.authorize(request), profile)
                reply = await self.transport.send(wire)
                observed = normalize_usage(reply.usage, target.usage_format)
                usage.append(observed)
                status = "freshness_rejected"
                self.compiler.compile(request, await self.authorize(request), profile)
                if not isinstance(reply.text, str) or len(reply.text.encode("utf-8")) > budget.max_reply_bytes:
                    status = "reply_size_rejected"
                    raise ContextError("reply_size_exceeded")
                try:
                    proposal = parse_json(reply.text)
                    if not isinstance(proposal, dict):
                        raise ContextError("invalid_proposal_shape")
                    validator.validate(proposal)
                except (ContextError, ValidationError):
                    status = "schema_rejected"
                    if attempt < budget.schema_retries:
                        continue
                    raise ContextError("proposal_schema_rejected") from None
                status = "domain_rejected"
                if self.validate_proposal(proposal, request) is not True:
                    raise ContextError("proposal_domain_rejected")
                status = "accepted_proposal"
                return ProposalResult(canonical_json(proposal), tuple(usage), attempt + 1,
                                      monotonic() - started, wire.cache_key, wire.prefix_fingerprint)
            finally:
                if self.observe_attempt is not None:
                    observation = AttemptObservation(
                        attempt + 1, count.input_tokens if count else None,
                        count.assurance if count else None, observed, status,
                        monotonic() - attempt_start, wire.cache_key)
                    try:
                        self.observe_attempt(observation)
                    except Exception:
                        # Telemetry failure must not mutate or retry domain work.
                        # Hosts must monitor their own sink health/coverage.
                        pass
        raise ContextError("proposal_schema_rejected")
