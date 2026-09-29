"""Bounded OpenAI-compatible chat transport for a live local model endpoint.

This module owns exactly one thing: turning a rendered
``prompt_cache_policy.WireRequest`` into a validated ``gateway.ModelReply`` over
an OpenAI-compatible ``POST {base_url}/chat/completions``.

It deliberately does not own prompt content, Domain authorization, token
accounting, or commit capability.  Two boundaries are load bearing:

* **No fabricated token counts.**  ``CacheAwareGateway`` demands an ``exact`` or
  ``certified_upper_bound`` counter because it makes cache-hit accounting
  claims.  This endpoint exposes no such proof, so live structured workers call
  :meth:`OpenAICompatibleChatTransport.send` directly instead of claiming cache
  accounting they cannot support.
* **No silent degradation.**  An unreachable endpoint, a non-JSON reply, an
  empty choice list or an oversized body all raise ``ModelTransportError``.
  Nothing here ever falls back to a canned narrative.

Credentials are read from the environment into ``ModelEndpointConfig`` and are
never logged, echoed into a ``WireRequest``, or retained in a repr.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .gateway import ModelReply, PreparedTransport
from .prompt_cache_policy import ProviderProfile, Protocol, WireRequest


class ModelTransportError(RuntimeError):
    """The live model endpoint failed or violated its bounded contract."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_MAX_REPLY_BYTES = 262_144
_MAX_MESSAGES = 64
_MAX_MESSAGE_CHARS = 32_768
_DEFAULT_TIMEOUT_SECONDS = 60.0
_MAX_TIMEOUT_SECONDS = 600.0


@dataclass(frozen=True, slots=True)
class ModelEndpointConfig:
    """One explicitly configured OpenAI-compatible chat endpoint.

    Nothing is auto-detected: an endpoint is used only when an operator names
    it.  A missing base URL or model is a configuration error, not a reason to
    silently keep a previous model.
    """

    base_url: str
    api_key: str = field(repr=False)
    model: str
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
    extra_body: Mapping[str, Any] = field(default_factory=dict, repr=False)
    provider_id: str = "wom-local-model"

    def __post_init__(self) -> None:
        for value in (self.base_url, self.model, self.provider_id):
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > 512
                or "\x00" in value
            ):
                raise ModelTransportError("invalid_model_endpoint")
        if not isinstance(self.api_key, str) or "\x00" in self.api_key:
            raise ModelTransportError("invalid_model_endpoint")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not 0 < float(self.timeout_seconds) <= _MAX_TIMEOUT_SECONDS
        ):
            raise ModelTransportError("invalid_model_endpoint")
        if not isinstance(self.extra_body, Mapping):
            raise ModelTransportError("invalid_model_endpoint")
        try:
            json.dumps(dict(self.extra_body), allow_nan=False)
        except (TypeError, ValueError):
            raise ModelTransportError("invalid_model_endpoint") from None

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    def provider_profile(self) -> ProviderProfile:
        """Project the endpoint onto the existing per-provider capability record."""
        return ProviderProfile(
            endpoint_id=self.provider_id,
            model=self.model,
            protocol=Protocol.CHAT,
            supported_models=(self.model,),
            usage_format="openai_chat",
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ModelEndpointConfig | None:
        """Read an explicitly configured endpoint, or ``None`` when unnamed.

        Returning ``None`` is the honest signal for "this deployment has no live
        model"; callers must then keep ``model_ready`` false rather than
        pretending a model exists.
        """
        source = os.environ if env is None else env
        base_url = (source.get("WOM_MODEL_BASE_URL") or "").strip()
        model = (source.get("WOM_MODEL_NAME") or "").strip()
        if not base_url or not model:
            return None
        raw_extra = (source.get("WOM_MODEL_EXTRA_BODY") or "").strip()
        extra: dict[str, Any] = {}
        if raw_extra:
            try:
                parsed = json.loads(raw_extra)
            except json.JSONDecodeError:
                raise ModelTransportError("invalid_model_endpoint") from None
            if not isinstance(parsed, dict):
                raise ModelTransportError("invalid_model_endpoint")
            extra = parsed
        raw_timeout = (source.get("WOM_MODEL_TIMEOUT") or "").strip()
        timeout = _DEFAULT_TIMEOUT_SECONDS
        if raw_timeout:
            try:
                timeout = float(raw_timeout)
            except ValueError:
                raise ModelTransportError("invalid_model_endpoint") from None
        return cls(
            base_url=base_url,
            api_key=source.get("WOM_MODEL_API_KEY") or "",
            model=model,
            timeout_seconds=timeout,
            extra_body=extra,
            provider_id=(source.get("WOM_MODEL_PROVIDER_ID") or "wom-local-model").strip(),
        )


def chat_wire(
    messages: Sequence[Mapping[str, str]],
    *,
    target: ProviderProfile,
    output_tokens: int,
    json_mode: bool = True,
    repair_hint: str | None = None,
    response_schema: Mapping[str, Any] | None = None,
) -> WireRequest:
    """Build one bounded chat body without inventing cache-accounting claims.

    ``prefix_fingerprint`` and ``cache_key`` are content digests of the exact
    wire body so a caller can correlate two identical calls, but no
    provider-side cache directive is emitted: this path makes no claim about
    prompt caching.
    """
    if (
        not isinstance(messages, Sequence)
        or isinstance(messages, (str, bytes))
        or not 1 <= len(messages) <= _MAX_MESSAGES
    ):
        raise ModelTransportError("invalid_model_prompt")
    rendered: list[dict[str, str]] = []
    for message in messages:
        if not isinstance(message, Mapping):
            raise ModelTransportError("invalid_model_prompt")
        role = message.get("role")
        content = message.get("content")
        if role not in {"system", "user", "assistant"}:
            raise ModelTransportError("invalid_model_prompt")
        if (
            not isinstance(content, str)
            or not content.strip()
            or len(content) > _MAX_MESSAGE_CHARS
            or "\x00" in content
        ):
            raise ModelTransportError("invalid_model_prompt")
        rendered.append({"role": role, "content": content})
    if type(output_tokens) is not int or not 1 <= output_tokens <= 8192:
        raise ModelTransportError("invalid_model_prompt")
    if rendered[-1]["role"] != "user":
        raise ModelTransportError("invalid_model_prompt")

    body: dict[str, Any] = {
        "model": target.model,
        "messages": rendered,
        "max_tokens": output_tokens,
        "temperature": 0.0,
        "stream": False,
    }
    if response_schema is not None:
        if not isinstance(response_schema, Mapping) or not response_schema:
            raise ModelTransportError("invalid_model_prompt")
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "structured_output",
                "strict": True,
                "schema": dict(response_schema),
            },
        }
    elif json_mode:
        body["response_format"] = {"type": "json_object"}
    if repair_hint is not None:
        if not isinstance(repair_hint, str) or not repair_hint.strip():
            raise ModelTransportError("invalid_model_prompt")
        body["messages"] = [*rendered, {"role": "user", "content": repair_hint}]

    body_json = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    digest = hashlib.sha256(body_json.encode("utf-8")).hexdigest()
    return WireRequest(
        target=target,
        body_json=body_json,
        prefix_fingerprint=digest,
        cache_key=digest,
    )


class OpenAICompatibleChatTransport(PreparedTransport):
    """Execute one rendered chat body against a named local endpoint."""

    def __init__(self, config: ModelEndpointConfig) -> None:
        if not isinstance(config, ModelEndpointConfig):
            raise ModelTransportError("invalid_model_endpoint")
        self._config = config
        self._client: Any | None = None
        self._lock = asyncio.Lock()
        # None until an endpoint has been asked for a decode-time constraint.
        self._structured_output: bool | None = None

    @property
    def config(self) -> ModelEndpointConfig:
        return self._config

    async def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        async with self._lock:
            if self._client is not None:
                return self._client
            try:
                from openai import AsyncOpenAI
            except ImportError:  # pragma: no cover - dependency is declared
                raise ModelTransportError("model_client_unavailable") from None
            self._client = AsyncOpenAI(
                base_url=self._config.base_url.rstrip("/") + "/",
                api_key=self._config.api_key or "not-required",
                timeout=float(self._config.timeout_seconds),
                max_retries=0,
            )
            return self._client

    async def send(self, request: WireRequest) -> ModelReply:
        if not isinstance(request, WireRequest):
            raise ModelTransportError("invalid_model_request")
        client = await self._ensure_client()
        body = request.body()
        extra = dict(self._config.extra_body)
        # ``response_format`` and chat-template switches are provider extensions
        # on an OpenAI-compatible surface; they travel in extra_body so a server
        # that rejects them fails loudly instead of silently changing behaviour.
        if "response_format" in body:
            extra.setdefault("response_format", body.pop("response_format"))
        body.pop("stream", None)
        constrained = (
            isinstance(extra.get("response_format"), Mapping)
            and extra["response_format"].get("type") == "json_schema"
        )
        if constrained and self._structured_output is False:
            extra["response_format"] = {"type": "json_object"}
            constrained = False
        try:
            completion = await client.chat.completions.create(
                **body, extra_body=extra or None
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            if not (constrained and self._structured_output is None):
                # Provider exceptions can embed the request body or the API key.
                raise ModelTransportError("model_endpoint_unreachable") from None
            # The endpoint refused the decode-time constraint. Learn that once and
            # degrade, so an OpenAI-compatible server without json_schema support
            # costs one rejected call instead of failing every later turn.
            self._structured_output = False
            extra["response_format"] = {"type": "json_object"}
            try:
                completion = await client.chat.completions.create(
                    **body, extra_body=extra or None
                )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - provider errors may embed request material
                raise ModelTransportError("model_endpoint_unreachable") from None
        else:
            if constrained:
                self._structured_output = True
        return self._to_reply(completion)

    @staticmethod
    def _to_reply(completion: Any) -> ModelReply:
        choices = getattr(completion, "choices", None)
        if not choices:
            raise ModelTransportError("model_reply_empty")
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise ModelTransportError("model_reply_empty")
        if len(content.encode("utf-8")) > _MAX_REPLY_BYTES:
            raise ModelTransportError("model_reply_too_large")
        usage_obj = getattr(completion, "usage", None)
        usage: Mapping[str, Any] | None = None
        if usage_obj is not None:
            usage = {
                "prompt_tokens": getattr(usage_obj, "prompt_tokens", None),
                "completion_tokens": getattr(usage_obj, "completion_tokens", None),
                "total_tokens": getattr(usage_obj, "total_tokens", None),
            }
        return ModelReply(text=content, usage=usage)

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass


__all__ = [
    "ModelEndpointConfig",
    "ModelTransportError",
    "OpenAICompatibleChatTransport",
    "chat_wire",
]
