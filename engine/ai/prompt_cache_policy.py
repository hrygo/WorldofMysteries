"""Explicit per-endpoint capabilities; no guessing from 'OpenAI-compatible'."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from typing import Any

from engine.application.context_plan import ContextError, canonical_json, identifier, parse_json
from .prompt_renderer import RenderedPrompt


class Protocol(str, Enum):
    CHAT = "chat_completions"
    RESPONSES = "responses"
    CLAUDE = "claude_messages"


class CacheMode(str, Enum):
    AUTO = "automatic_or_unspecified"
    OPENAI_EXPLICIT = "openai_explicit"
    CLAUDE_EXPLICIT = "claude_explicit"


@dataclass(frozen=True)
class ProviderProfile:
    """Application configuration, bound to an actual credential/endpoint elsewhere.

    Selecting explicit mode is an operator capability assertion, NOT auto-detection
    of endpoint support. Pin exact supported models; an empty allowlist fails.
    No model calls are made merely by constructing or rendering this profile.
    """
    endpoint_id: str
    model: str
    protocol: Protocol
    mode: CacheMode = CacheMode.AUTO
    supported_models: tuple[str, ...] = ()
    ttl: str | None = None
    usage_format: str = "unknown"
    revision: str = "v1"
    chat_output_limit_field: str = "max_tokens"
    routing_key_supported: bool = False

    def __post_init__(self) -> None:
        for value in (self.endpoint_id, self.model, self.revision):
            identifier(value)
        if not isinstance(self.protocol, Protocol) or not isinstance(self.mode, CacheMode):
            raise ContextError("invalid_provider_profile")
        object.__setattr__(self, "supported_models", tuple(self.supported_models))
        if self.chat_output_limit_field not in {"max_tokens", "max_completion_tokens"} or type(self.routing_key_supported) is not bool:
            raise ContextError("invalid_wire_capability")
        if self.usage_format not in {"unknown", "openai_chat", "openai_responses", "claude", "deepseek"}:
            raise ContextError("unknown_usage_format")
        if self.mode != CacheMode.AUTO and self.model not in self.supported_models:
            raise ContextError("cache_model_not_declared_supported")
        if self.mode == CacheMode.OPENAI_EXPLICIT:
            if self.protocol not in {Protocol.CHAT, Protocol.RESPONSES} or self.ttl not in (None, "30m"):
                raise ContextError("invalid_openai_cache_capability")
        elif self.mode == CacheMode.CLAUDE_EXPLICIT:
            if self.protocol != Protocol.CLAUDE or self.ttl not in (None, "5m", "1h"):
                raise ContextError("invalid_claude_cache_capability")
        elif self.ttl is not None:
            raise ContextError("ttl_requires_verified_explicit_mode")


@dataclass(frozen=True, repr=False)
class WireRequest:
    target: ProviderProfile
    body_json: str = field(repr=False)
    prefix_fingerprint: str
    cache_key: str

    def body(self) -> dict[str, Any]:
        return parse_json(self.body_json)


def render_wire(prompt: RenderedPrompt, target: ProviderProfile, output_tokens: int,
                repair: bool = False) -> WireRequest:
    if type(output_tokens) is not int or output_tokens < 1:
        raise ContextError("invalid_output_budget")
    messages = prompt.messages()
    if repair:
        # No raw validation errors, previous private result or changing IDs in the prefix.
        messages.append({"role": "user", "content": "Return one valid JSON object matching the output schema. No markdown or extra keys."})
    # Provider/model/render dialect are part of cache identity, never only the text.
    binding = canonical_json({"key": prompt.cache_key, "endpoint": target.endpoint_id,
                              "model": target.model, "protocol": target.protocol.value,
                              "capability_revision": target.revision})
    key = hashlib.sha256(binding.encode()).hexdigest()
    body: dict[str, Any] = {"model": target.model}
    tools = parse_json(prompt.tools_json)
    # v1 supports structured single-call workers. Bounded Director tool loops need
    # their own tool/result/authorization contract; do not silently pretend support.
    if tools:
        raise ContextError("tool_loop_not_supported_by_structured_gateway")
    end = prompt.stable_message_count - 1
    if target.protocol == Protocol.CLAUDE:
        body["max_tokens"] = output_tokens
        system = [{"type": "text", "text": messages[0]["content"]}]
        blocks = [{"type": "text", "text": m["content"]} for m in messages[1:]]
        if target.mode == CacheMode.CLAUDE_EXPLICIT:
            mark = {"type": "ephemeral", "ttl": target.ttl or "5m"}
            system[0]["cache_control"] = dict(mark)
            # Four total breakpoints at most: root plus latest three windows.
            # Explicit root remains a cold-fallback anchor after a large append.
            for index in (end - 1, end - 21, end - 41):
                if index >= 0:
                    blocks[index]["cache_control"] = dict(mark)
        body["system"] = system
        body["messages"] = [{"role": "user", "content": blocks}]
    else:
        content_type = "input_text" if target.protocol == Protocol.RESPONSES else "text"
        converted = [{"role": m["role"], "content": [{"type": content_type, "text": m["content"]}]} for m in messages]
        if target.routing_key_supported:
            body["prompt_cache_key"] = key
        if target.mode == CacheMode.OPENAI_EXPLICIT:
            body["prompt_cache_options"] = {"mode": "explicit", "ttl": target.ttl or "30m"}
            body["prompt_cache_key"] = key
            # Retain earlier explicit boundaries so append-only calls can read the
            # last cached prefix. OpenAI limits new writes to the latest four and
            # read lookup to fifty breakpoints, per the verified API contract.
            indices = sorted({0, *range(max(1, end - 48), end + 1)})
            for index in indices:
                converted[index]["content"][0]["prompt_cache_breakpoint"] = {"mode": "explicit"}
        if target.protocol == Protocol.RESPONSES:
            body["input"], body["max_output_tokens"] = converted, output_tokens
            body["store"] = False
        else:
            body["messages"], body[target.chat_output_limit_field] = converted, output_tokens
    prefix = hashlib.sha256((binding + prompt.prefix_fingerprint).encode()).hexdigest()
    return WireRequest(target, canonical_json(body), prefix, key)
