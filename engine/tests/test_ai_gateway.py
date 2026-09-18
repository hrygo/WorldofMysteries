import asyncio
from dataclasses import replace
import pytest

from engine.application.context_plan import ContextError
from engine.ai.agentscope_adapter import PreparedAgentScopeAdapter
from engine.ai.gateway import CacheAwareGateway, ExecutionBudget, ModelReply, TokenCount
from engine.ai.prompt_cache_policy import ProviderProfile, Protocol
from engine.ai.prompt_renderer import PromptRenderer
from engine.tests.test_context_compiler import sample


class Harness:
    def __init__(self, replies=None):
        self.request, self.view, self.profile = sample()
        self.target = ProviderProfile("synthetic", "mock-model", Protocol.CHAT, usage_format="openai_chat")
        self.sent = []
        self.counted = []
        self.replies = list(replies or [ModelReply('{"action":"wait"}')])
        self.count = TokenCount(100, "exact")  # synthetic counter, not a live tokenizer
        self.reject = False
        self.mutate_on_send = False
        self.mutate_on_count = False
        self.delay = 0
        self.raise_secret = False

    async def authorize(self, request):
        return self.view

    async def counter(self, wire):
        self.counted.append(wire)
        if self.mutate_on_count:
            self.view = replace(self.view, grants=frozenset())
        return self.count

    async def send(self, wire):
        self.sent.append(wire)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raise_secret:
            raise RuntimeError("SECRET-API-KEY-private-prompt")
        if self.mutate_on_send:
            self.view = replace(self.view, world_revision=self.view.world_revision+1)
        return self.replies.pop(0)

    def gateway(self):
        return CacheAwareGateway(renderer=PromptRenderer(b"x"*32),
            transport=PreparedAgentScopeAdapter(self.target, self.send), authorize=self.authorize,
            count_tokens=self.counter, validate_proposal=lambda proposal, request: not self.reject)

    async def run(self, budget=None):
        return await self.gateway().execute(self.request, self.profile, self.target,
                                             budget or ExecutionBudget(1000, 100))


@pytest.mark.asyncio
async def test_ai_gateway_runs_actual_compiler_renderer_policy_and_validator():
    h = Harness()
    result = await h.run()
    assert result.proposal() == {"action": "wait"}
    assert result.attempts == 1
    assert h.sent == h.counted
    assert result.usage[0].cache_read is None
    assert "req1" not in h.sent[0].body_json
    assert "wait" not in repr(result)


@pytest.mark.asyncio
async def test_ai_gateway_schema_retry_preserves_prefix_and_counts_each_request():
    h = Harness([ModelReply('{"wrong":1}'), ModelReply('{"action":"wait"}')])
    result = await h.run()
    assert result.attempts == 2
    assert len(h.counted) == len(h.sent) == len(result.usage) == 2
    assert h.sent[0].prefix_fingerprint == h.sent[1].prefix_fingerprint
    assert len(h.sent[1].body()["messages"]) == len(h.sent[0].body()["messages"]) + 1


@pytest.mark.asyncio
async def test_ai_gateway_over_budget_never_sends():
    h = Harness()
    h.count = TokenCount(950, "exact")
    with pytest.raises(ContextError, match="context_budget_exceeded"):
        await h.run()
    assert not h.sent


@pytest.mark.asyncio
async def test_ai_gateway_rejects_heuristic_counts():
    h = Harness()
    h.count = TokenCount(100, "characters_divided_by_four")
    with pytest.raises(ContextError, match="unverified_token_count"):
        await h.run()
    assert not h.sent


@pytest.mark.asyncio
async def test_ai_gateway_reauthorization_after_awaiting_count():
    h = Harness()
    h.mutate_on_count = True
    with pytest.raises(ContextError, match="evidence_not_authorized"):
        await h.run()
    assert not h.sent


@pytest.mark.asyncio
async def test_ai_gateway_rejects_result_after_state_changed():
    h = Harness()
    h.mutate_on_send = True
    with pytest.raises(ContextError, match="stale_snapshot"):
        await h.run()
    assert len(h.sent) == 1


@pytest.mark.asyncio
async def test_ai_gateway_domain_rejection_not_retried_or_committed():
    h = Harness()
    h.reject = True
    with pytest.raises(ContextError, match="proposal_domain_rejected"):
        await h.run()
    assert len(h.sent) == 1


@pytest.mark.asyncio
async def test_ai_gateway_timeout_and_cancellation():
    h = Harness()
    h.delay = 1
    with pytest.raises(ContextError, match="model_stage_timeout"):
        await h.run(ExecutionBudget(1000, 100, timeout_seconds=.001))
    task = asyncio.create_task(h.run())
    await asyncio.sleep(.001)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_ai_gateway_provider_error_redacted():
    h = Harness()
    h.raise_secret = True
    with pytest.raises(ContextError) as exc:
        await h.run()
    assert str(exc.value) == "model_stage_failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ['{"action":"x","action":"y"}', '```json\n{}\n```', '[]'])
async def test_ai_gateway_rejects_invalid_json_and_bounded_retries(text):
    h = Harness([ModelReply(text)] * 3)
    with pytest.raises(ContextError, match="proposal_schema_rejected"):
        await h.run()
    assert len(h.sent) == 2


@pytest.mark.asyncio
async def test_ai_gateway_output_size_limit():
    h = Harness([ModelReply('{"action":"way too long"}')])
    with pytest.raises(ContextError, match="reply_size_exceeded"):
        await h.run(ExecutionBudget(1000, 100, max_reply_bytes=10))


@pytest.mark.asyncio
async def test_ai_gateway_schema_refs_never_fetch_network():
    h = Harness()
    h.profile = replace(h.profile, schema_json='{"$ref":"https://example.invalid/private"}')
    with pytest.raises(ContextError, match="output_schema_must_be_resolved"):
        await h.run()
    assert not h.sent


@pytest.mark.asyncio
async def test_ai_gateway_adapter_target_binding():
    h = Harness()
    gateway = h.gateway()
    with pytest.raises(ContextError, match="executor_target_mismatch"):
        await gateway.execute(h.request, h.profile, replace(h.target, endpoint_id="another"), ExecutionBudget(1000,100))
    assert not h.sent


@pytest.mark.parametrize("kwargs", [{"schema_retries":3},{"timeout_seconds":float("nan")},{"max_reply_bytes":0}])
def test_ai_gateway_invalid_budget(kwargs):
    with pytest.raises(ValueError):
        ExecutionBudget(1000,100,**kwargs)


@pytest.mark.asyncio
async def test_ai_gateway_failed_schema_attempt_usage_is_observed():
    h = Harness([ModelReply('{"wrong":true}', {"prompt_tokens":10,"prompt_tokens_details":{"cached_tokens":5}}),
                 ModelReply('{"action":"wait"}')])
    gateway = h.gateway()
    observations = []
    gateway.observe_attempt = observations.append
    result = await gateway.execute(h.request,h.profile,h.target,ExecutionBudget(1000,100))
    assert len(observations) == result.attempts == 2
    assert observations[0].status == "schema_rejected"
    assert observations[0].usage.cache_read == 5
    assert observations[1].status == "accepted_proposal"
    assert "wrong" not in repr(observations)


@pytest.mark.asyncio
async def test_ai_gateway_stale_response_usage_is_not_lost():
    h = Harness([ModelReply('{"action":"wait"}', {"prompt_tokens":100,"prompt_tokens_details":{"cached_tokens":80}})])
    h.mutate_on_send = True
    gateway = h.gateway()
    observations = []
    gateway.observe_attempt = observations.append
    with pytest.raises(ContextError,match="stale_snapshot"):
        await gateway.execute(h.request,h.profile,h.target,ExecutionBudget(1000,100))
    assert observations[0].status == "freshness_rejected"
    assert observations[0].usage.total_input == 100


@pytest.mark.asyncio
async def test_ai_gateway_telemetry_failure_never_retries_proposal():
    h = Harness()
    gateway = h.gateway()
    def broken_sink(observation):
        raise RuntimeError("sink unavailable")
    gateway.observe_attempt = broken_sink
    await gateway.execute(h.request,h.profile,h.target,ExecutionBudget(1000,100))
    assert len(h.sent) == 1
