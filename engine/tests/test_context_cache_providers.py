from dataclasses import replace
import pytest

from engine.application.context_plan import ContextError
from engine.ai.cache_metrics import CacheUsage, aggregate_hit_rate, normalize_usage
from engine.ai.prompt_cache_policy import CacheMode, Protocol, ProviderProfile, render_wire
from engine.ai.prompt_renderer import PromptRenderer
from engine.tests.test_context_compiler import rendered
from engine.tests.test_context_epoch import plan_with_history


@pytest.mark.parametrize("protocol", [Protocol.CHAT, Protocol.RESPONSES])
def test_context_openai_explicit_marks_prefix_not_dynamic_tail(protocol):
    prompt = rendered()
    profile = ProviderProfile("test-endpoint", "tested-model", protocol, CacheMode.OPENAI_EXPLICIT,
                              ("tested-model",), "30m")
    wire = render_wire(prompt, profile, 128)
    body = wire.body()
    assert body["prompt_cache_options"] == {"mode": "explicit", "ttl": "30m"}
    messages = body["messages" if protocol == Protocol.CHAT else "input"]
    assert "prompt_cache_breakpoint" in messages[prompt.stable_message_count-1]["content"][0]
    assert all("prompt_cache_breakpoint" not in m["content"][0] for m in messages[prompt.stable_message_count:])
    assert body["prompt_cache_key"] == wire.cache_key


def test_context_openai_append_retains_previous_breakpoint():
    renderer = PromptRenderer(b"s"*32)
    a, b = renderer.render(plan_with_history(1)), renderer.render(plan_with_history(2))
    profile = ProviderProfile("test", "m", Protocol.RESPONSES, CacheMode.OPENAI_EXPLICIT, ("m",))
    first, second = render_wire(a, profile, 128).body(), render_wire(b, profile, 128).body()
    boundary = a.stable_message_count
    assert first["input"][:boundary] == second["input"][:boundary]


def test_context_claude_max_four_markers_and_no_dynamic_marker():
    plan = plan_with_history(60)
    prompt = PromptRenderer(b"s"*32).render(plan)
    profile = ProviderProfile("test", "m", Protocol.CLAUDE, CacheMode.CLAUDE_EXPLICIT, ("m",), "5m")
    body = render_wire(prompt, profile, 128).body()
    blocks = body["system"] + body["messages"][0]["content"]
    assert sum("cache_control" in b for b in blocks) == 4
    assert all("cache_control" not in b for b in blocks[prompt.stable_message_count:])


@pytest.mark.parametrize("kwargs", [
    {"mode": CacheMode.OPENAI_EXPLICIT},
    {"ttl": "1h"},
    {"mode": CacheMode.CLAUDE_EXPLICIT, "supported_models": ("m",)},
    {"mode": CacheMode.OPENAI_EXPLICIT, "supported_models": ("m",), "ttl": "1h"},
])
def test_context_undeclared_provider_features_fail(kwargs):
    with pytest.raises(ContextError):
        ProviderProfile("test", "m", Protocol.CHAT, **kwargs)


def test_context_generic_endpoint_gets_no_cache_parameters():
    body = render_wire(rendered(), ProviderProfile("local", "m", Protocol.CHAT), 20).body()
    assert "prompt_cache_key" not in body
    assert "prompt_cache_options" not in body
    assert "prompt_cache_breakpoint" not in str(body)
    assert body["max_tokens"] == 20


def test_context_verified_legacy_routing_key_and_limit():
    profile = ProviderProfile("test", "m", Protocol.CHAT, routing_key_supported=True,
                              chat_output_limit_field="max_completion_tokens")
    body = render_wire(rendered(), profile, 20).body()
    assert "prompt_cache_key" in body
    assert body["max_completion_tokens"] == 20
    assert "prompt_cache_options" not in body


def test_context_model_switch_changes_private_key():
    profile = ProviderProfile("test", "m1", Protocol.CHAT)
    assert render_wire(rendered(), profile, 20).cache_key != render_wire(rendered(), replace(profile, model="m2"), 20).cache_key


def test_context_usage_openai_counts_are_subsets():
    usage = normalize_usage({"prompt_tokens": 100, "prompt_tokens_details": {
        "cached_tokens": 50, "cache_write_tokens": 20}}, "openai_chat")
    assert usage == CacheUsage(100, 50, 20, 30)


def test_context_usage_claude_total_is_sum():
    usage = normalize_usage({"input_tokens": 30, "cache_read_input_tokens": 50,
                             "cache_creation_input_tokens": 20}, "claude")
    assert usage == CacheUsage(100, 50, 20, 30)


def test_context_usage_deepseek_does_not_fabricate_writes():
    usage = normalize_usage({"prompt_tokens": 100, "prompt_cache_hit_tokens": 70,
                            "prompt_cache_miss_tokens": 30}, "deepseek")
    assert usage == CacheUsage(100, 70, None, 30)


@pytest.mark.parametrize("value", [-1, True, 2.5, "8"])
def test_context_usage_invalid_not_zero(value):
    usage = normalize_usage({"prompt_tokens": 100, "prompt_tokens_details": {"cached_tokens": value}}, "openai_chat")
    assert not usage.valid and usage.hit_rate is None


def test_context_usage_unknown_and_inconsistent():
    assert normalize_usage(None, "unknown").hit_rate is None
    assert normalize_usage({"input_tokens": 20}, "claude").total_input is None
    assert not normalize_usage({"prompt_tokens": 5, "prompt_tokens_details": {"cached_tokens": 6}}, "openai_chat").valid
    assert not normalize_usage({"prompt_tokens": 5, "prompt_cache_hit_tokens": 2, "prompt_cache_miss_tokens": 4}, "deepseek").valid


def test_context_usage_weighted_aggregation_and_unknown_coverage():
    assert aggregate_hit_rate([CacheUsage(100, 80, 0, 20), CacheUsage(900, 0, 0, 900)]) == .08
    assert aggregate_hit_rate([CacheUsage(100, 80, 0, 20), CacheUsage(None, None, None, None)]) is None
