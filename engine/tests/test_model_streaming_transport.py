"""Server-sent-event aggregation on the OpenAI-compatible chat transport.

A narrative turn is one bounded structured call, so the caller still wants a
single ``ModelReply``.  What streaming buys is a lower time-to-first-byte on the
wire and a reply body assembled under the same byte ceiling the one-shot path
already enforced, instead of after it.

These tests pin the aggregate and the two capabilities that must be learned
without costing a failed call per turn: ``json_schema`` constraints and the
stream flag itself.  A provider that refuses either degrades exactly once.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from ai.openai_compatible import (
    ModelEndpointConfig,
    ModelTransportError,
    OpenAICompatibleChatTransport,
    chat_wire,
)

SCHEMA = {
    "type": "object",
    "properties": {"intent": {"type": "string", "minLength": 1}},
}


def _config(**overrides) -> ModelEndpointConfig:
    base = {
        "base_url": "http://127.0.0.1:1",
        "api_key": "test-only",
        "model": "test-model",
    }
    base.update(overrides)
    return ModelEndpointConfig(**base)


def _wire(*, stream: bool = False, response_schema: dict | None = SCHEMA):
    return chat_wire(
        [{"role": "user", "content": "hello"}],
        target=_config().provider_profile(),
        output_tokens=64,
        json_mode=True,
        response_schema=response_schema,
        stream=stream,
    )


def _body(wire) -> dict:
    return json.loads(wire.body_json)


def _delta(content, *, reasoning=None, finish=None):
    delta = SimpleNamespace(content=content, reasoning_content=reasoning)
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish)],
        usage=None,
    )


def _usage_chunk(prompt: int, completion: int):
    return SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        ),
    )


class _FakeStream:
    def __init__(self, chunks) -> None:
        self._chunks = list(chunks)
        self.closed = False

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for chunk in self._chunks:
            yield chunk

    async def close(self) -> None:
        self.closed = True


class _FakeCompletions:
    """A provider that can refuse ``stream`` and/or ``json_schema`` on demand."""

    def __init__(
        self,
        chunks=(),
        *,
        text='{"intent":"x"}',
        reject_stream: bool = False,
        reject_schema: bool = False,
        usage=(11, 7),
    ) -> None:
        self.chunks = list(chunks)
        self.text = text
        self.reject_stream = reject_stream
        self.reject_schema = reject_schema
        self.usage = usage
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        response_format = kwargs.get("extra_body", {}).get("response_format", {})
        if self.reject_schema and response_format.get("type") == "json_schema":
            raise RuntimeError("unsupported response_format")
        if kwargs.get("stream"):
            if self.reject_stream:
                raise RuntimeError("streaming is not supported")
            chunks = list(self.chunks)
            if self.usage is not None:
                chunks.append(_usage_chunk(*self.usage))
            return _FakeStream(chunks)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.text))],
            usage=None,
        )


def _transport(fake, **overrides) -> OpenAICompatibleChatTransport:
    transport = OpenAICompatibleChatTransport(_config(**overrides))
    transport._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return transport


def test_wire_asks_for_a_stream_and_its_usage_only_when_streaming() -> None:
    streaming = _body(_wire(stream=True))
    one_shot = _body(_wire(stream=False))

    assert streaming["stream"] is True
    assert streaming["stream_options"] == {"include_usage": True}
    # The one-shot body must stay byte-identical to what it was before.
    assert one_shot["stream"] is False
    assert "stream_options" not in one_shot


def test_the_wire_digest_covers_the_stream_flag() -> None:
    """Two bodies differing only in streaming must not share a cache identity."""
    assert _wire(stream=True).prefix_fingerprint != _wire(stream=False).prefix_fingerprint


@pytest.mark.asyncio
async def test_streamed_deltas_are_aggregated_into_one_reply() -> None:
    fake = _FakeCompletions(
        chunks=[_delta('{"intent"'), _delta(':"x"}', finish="stop")]
    )
    transport = _transport(fake)

    reply = await transport.send(_wire(stream=True))

    assert reply.text == '{"intent":"x"}'
    assert reply.usage == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
    assert fake.calls[0]["stream"] is True


@pytest.mark.asyncio
async def test_reasoning_deltas_are_never_aggregated_into_the_reply() -> None:
    """Thinking tokens are the model's private scratch, not the player's text."""
    fake = _FakeCompletions(
        chunks=[
            _delta(None, reasoning="the player wants to "),
            _delta('{"intent":"x"}', reasoning="answer with x"),
        ]
    )
    transport = _transport(fake)

    reply = await transport.send(_wire(stream=True))

    assert reply.text == '{"intent":"x"}'


@pytest.mark.asyncio
async def test_a_stream_that_only_thinks_produces_no_reply() -> None:
    fake = _FakeCompletions(chunks=[_delta(None, reasoning="hmm")])
    transport = _transport(fake)

    with pytest.raises(ModelTransportError) as excinfo:
        await transport.send(_wire(stream=True))

    assert excinfo.value.code == "model_reply_empty"


@pytest.mark.asyncio
async def test_an_oversized_stream_is_cut_off_rather_than_buffered() -> None:
    fake = _FakeCompletions(chunks=[_delta("x" * 4096) for _ in range(200)], usage=None)
    transport = _transport(fake)

    with pytest.raises(ModelTransportError) as excinfo:
        await transport.send(_wire(stream=True))

    assert excinfo.value.code == "model_reply_too_large"


@pytest.mark.asyncio
async def test_a_provider_without_stream_support_degrades_instead_of_failing() -> None:
    fake = _FakeCompletions(reject_stream=True)
    transport = _transport(fake)

    reply = await transport.send(_wire(stream=True))

    assert reply.text == '{"intent":"x"}'
    # Retried once as a one-shot call rather than surfacing an outage.
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_a_degraded_provider_is_not_offered_streaming_again() -> None:
    """Capability is learned once; later turns must not pay a failed call each."""
    fake = _FakeCompletions(reject_stream=True)
    transport = _transport(fake)

    await transport.send(_wire(stream=True))
    await transport.send(_wire(stream=True))

    # 2 calls for the first send (try + degrade), 1 for the second.
    assert len(fake.calls) == 3


@pytest.mark.asyncio
async def test_streaming_and_schema_capability_are_learned_independently() -> None:
    """A provider that refuses both must not cost a rejected call per capability."""
    fake = _FakeCompletions(reject_stream=True, reject_schema=True)
    transport = _transport(fake)

    reply = await transport.send(_wire(stream=True))

    assert reply.text == '{"intent":"x"}'
    # stream attempt, then a one-shot attempt that still carries the constraint
    # and therefore costs the schema degrade too.
    assert len(fake.calls) == 3


@pytest.mark.asyncio
async def test_streaming_can_be_declined_by_the_deployment() -> None:
    """An operator can pin the one-shot path without editing code."""
    fake = _FakeCompletions(chunks=[_delta('{"intent":"x"}')])
    transport = _transport(fake, stream=False)

    reply = await transport.send(_wire(stream=False))

    assert reply.text == '{"intent":"x"}'
    assert not fake.calls[0].get("stream")


@pytest.mark.asyncio
async def test_a_genuinely_unreachable_endpoint_still_reports_an_outage() -> None:
    class _Dead:
        async def create(self, **kwargs):
            raise RuntimeError("connection refused")

    transport = OpenAICompatibleChatTransport(_config())
    transport._client = SimpleNamespace(chat=SimpleNamespace(completions=_Dead()))

    with pytest.raises(ModelTransportError) as excinfo:
        await transport.send(_wire(stream=True))

    assert excinfo.value.code == "model_endpoint_unreachable"
