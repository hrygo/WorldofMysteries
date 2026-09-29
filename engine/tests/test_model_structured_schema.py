"""Decode-time output contracts for model calls.

The profile schema is only ever validated locally after the model answers, so a
model that does not feel bound by the prompt produces a well-formed JSON object
that violates the contract. These tests pin the structural alternative: the same
schema is handed to the provider as a decode-time constraint, and an endpoint
that cannot honour it degrades to the previous behaviour instead of failing.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from ai.authorized_live_execution import constrain_output_schema
from ai.openai_compatible import (
    ModelEndpointConfig,
    ModelTransportError,
    OpenAICompatibleChatTransport,
    chat_wire,
)

PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "minLength": 1, "maxLength": 128},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"type": {"type": "string"}},
            },
        },
    },
}


def _config() -> ModelEndpointConfig:
    return ModelEndpointConfig(
        base_url="http://127.0.0.1:1",
        api_key="test-only",
        model="test-model",
    )


def _wire(response_schema: dict | None):
    return chat_wire(
        [{"role": "user", "content": "hello"}],
        target=_config().provider_profile(),
        output_tokens=64,
        json_mode=True,
        response_schema=response_schema,
    )


def _response_format(wire) -> dict:
    return json.loads(wire.body_json)["response_format"]


def test_wire_carries_the_schema_as_a_decode_time_constraint() -> None:
    wire = _wire(PROFILE_SCHEMA)

    response_format = _response_format(wire)

    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["schema"] == PROFILE_SCHEMA
    assert response_format["json_schema"]["strict"] is True


def test_wire_keeps_plain_json_mode_when_no_schema_is_supplied() -> None:
    """The previous behaviour must survive untouched for unconstrained calls."""
    assert _response_format(_wire(None)) == {"type": "json_object"}


def test_constrain_narrows_the_profile_schema_to_the_allowed_signatures() -> None:
    constrained = constrain_output_schema(
        PROFILE_SCHEMA,
        {
            "properties.intent": {"enum": ["observe_subject"]},
            "properties.actions.items.properties.type": {
                "enum": ["continue_conversation"]
            },
        },
    )

    assert constrained["properties"]["intent"]["enum"] == ["observe_subject"]
    action_type = constrained["properties"]["actions"]["items"]["properties"]["type"]
    assert action_type["enum"] == ["continue_conversation"]
    # The source schema is never mutated: it is shared per profile.
    assert "enum" not in PROFILE_SCHEMA["properties"]["intent"]


def test_constrain_can_state_a_bound_the_provider_must_also_enforce() -> None:
    """A bound the profile already states is repeated to the provider."""
    schema = {
        "type": "object",
        "properties": {"speech": {"type": "string", "maxLength": 600}},
    }

    constrained = constrain_output_schema(
        schema, {"properties.speech": {"minLength": 1}}
    )

    assert constrained["properties"]["speech"]["minLength"] == 1
    # Existing bounds survive the merge.
    assert constrained["properties"]["speech"]["maxLength"] == 600
    assert "minLength" not in schema["properties"]["speech"]


def test_constrain_rejects_a_path_the_schema_does_not_expose() -> None:
    with pytest.raises(ValueError):
        constrain_output_schema(PROFILE_SCHEMA, {"nonexistent": {"minLength": 1}})


class _FakeCompletions:
    def __init__(self, *, reject_schema: bool) -> None:
        self.reject_schema = reject_schema
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        response_format = kwargs.get("extra_body", {}).get("response_format", {})
        if self.reject_schema and response_format.get("type") == "json_schema":
            raise RuntimeError("unsupported response_format")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"intent":"x"}'))],
            usage=None,
        )


def _transport(fake: _FakeCompletions) -> OpenAICompatibleChatTransport:
    transport = OpenAICompatibleChatTransport(_config())
    transport._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return transport


@pytest.mark.asyncio
async def test_provider_without_schema_support_degrades_instead_of_failing() -> None:
    fake = _FakeCompletions(reject_schema=True)
    transport = _transport(fake)

    reply = await transport.send(_wire(PROFILE_SCHEMA))

    assert reply.text == '{"intent":"x"}'
    # Retried once without the constraint rather than surfacing an outage.
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_degraded_provider_is_not_offered_the_constraint_again() -> None:
    """Capability is learned once; later turns must not pay a failed call each."""
    fake = _FakeCompletions(reject_schema=True)
    transport = _transport(fake)

    await transport.send(_wire(PROFILE_SCHEMA))
    await transport.send(_wire(PROFILE_SCHEMA))

    # 2 calls for the first send (try + degrade), 1 for the second.
    assert len(fake.calls) == 3


@pytest.mark.asyncio
async def test_schema_capable_provider_is_sent_the_constraint() -> None:
    fake = _FakeCompletions(reject_schema=False)
    transport = _transport(fake)

    await transport.send(_wire(PROFILE_SCHEMA))

    assert len(fake.calls) == 1
    response_format = fake.calls[0]["extra_body"]["response_format"]
    assert response_format["type"] == "json_schema"


@pytest.mark.asyncio
async def test_a_genuinely_unreachable_endpoint_still_reports_an_outage() -> None:
    class _Dead:
        async def create(self, **kwargs):
            raise RuntimeError("connection refused")

    transport = OpenAICompatibleChatTransport(_config())
    transport._client = SimpleNamespace(chat=SimpleNamespace(completions=_Dead()))

    with pytest.raises(ModelTransportError):
        await transport.send(_wire(PROFILE_SCHEMA))
