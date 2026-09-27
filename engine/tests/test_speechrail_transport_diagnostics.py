"""Transport-level failure classification for the local SpeechRail wire.

A rejection that happens before the WebSocket upgrade completes never produces
a close code, so the HTTP status is the only evidence available. These tests pin
that the status is classified *before* the accept token is inspected — otherwise
every rejection collapses into "invalid protocol" and the real cause is lost.
"""

from __future__ import annotations

import asyncio
import struct

import pytest

from infrastructure.audio.websocket_transport import (
    JSONWebSocketTransportError,
    StdlibJSONWebSocketTransport,
    classify_handshake_status,
    redact_reason,
)


class _RawServer:
    """A one-shot TCP server that replays a fixed HTTP response."""

    def __init__(self, response: bytes) -> None:
        self._response = response
        self._server: asyncio.AbstractServer | None = None
        self.port = 0

    async def __aenter__(self) -> "_RawServer":
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            await reader.readuntil(b"\r\n\r\n")
            writer.write(self._response)
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()


def _http(status: str, reason: str, extra_headers: str = "") -> bytes:
    return (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"{extra_headers}"
        "Content-Length: 0\r\n"
        "\r\n"
    ).encode("ascii")


# --------------------------------------------------------------------------
# Status classification


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "websocket_unauthorized"),
        (403, "websocket_forbidden"),
        (426, "websocket_upgrade_required"),
        (404, "websocket_endpoint_missing"),
        (405, "websocket_endpoint_missing"),
        (502, "websocket_backend_not_ready"),
        (503, "websocket_backend_not_ready"),
        (504, "websocket_backend_not_ready"),
        # A status with no specific evidence keeps the generic rejection rather
        # than inventing a cause.
        (400, "websocket_handshake_rejected"),
        (418, "websocket_handshake_rejected"),
        (500, "websocket_handshake_rejected"),
    ],
)
def test_handshake_status_maps_to_a_specific_code(status: int, expected: str):
    assert classify_handshake_status(status) == expected


@pytest.mark.parametrize("status", [401, 403, 503])
async def test_rejected_upgrade_reports_the_status_not_a_protocol_error(status: int):
    reason = {401: "Unauthorized", 403: "Forbidden", 503: "Service Unavailable"}[status]
    async with _RawServer(_http(str(status), reason)) as server:
        transport = StdlibJSONWebSocketTransport(timeout_seconds=5.0)
        with pytest.raises(JSONWebSocketTransportError) as caught:
            await transport.open(
                f"ws://127.0.0.1:{server.port}/v1/realtime", {"Authorization": "Bearer k"}
            )
    # The old order checked sec-websocket-accept first, so a rejection without
    # an accept header was reported as an invalid handshake.
    assert caught.value.code == classify_handshake_status(status)
    assert caught.value.status == status


async def test_a_403_does_not_claim_the_credential_was_invalid():
    async with _RawServer(_http("403", "Forbidden")) as server:
        transport = StdlibJSONWebSocketTransport(timeout_seconds=5.0)
        with pytest.raises(JSONWebSocketTransportError) as caught:
            await transport.open(f"ws://127.0.0.1:{server.port}/v1/realtime", {})
    # A proxy can refuse an upgrade for reasons unrelated to credentials, so the
    # code must not be an authentication verdict.
    assert caught.value.code == "websocket_forbidden"
    assert caught.value.code != "websocket_unauthorized"


async def test_a_101_without_a_valid_accept_token_is_a_protocol_error():
    async with _RawServer(_http("101", "Switching Protocols", "Upgrade: websocket\r\n")) as server:
        transport = StdlibJSONWebSocketTransport(timeout_seconds=5.0)
        with pytest.raises(JSONWebSocketTransportError) as caught:
            await transport.open(f"ws://127.0.0.1:{server.port}/v1/realtime", {})
    assert caught.value.code == "websocket_handshake_invalid"
    assert caught.value.status == 101


# --------------------------------------------------------------------------
# Close frame


def test_close_frame_1008_is_authentication_evidence():
    code, reason = StdlibJSONWebSocketTransport._parse_close(
        struct.pack("!H", 1008) + b"policy violation"
    )
    assert code == 1008
    assert reason == "policy violation"


def test_close_frame_1000_is_not_authentication_evidence():
    code, reason = StdlibJSONWebSocketTransport._parse_close(
        struct.pack("!H", 1000) + b"bye"
    )
    assert code == 1000
    assert reason == "bye"


@pytest.mark.parametrize("wire_code", [1005, 1006])
def test_reserved_close_codes_carry_no_reason(wire_code: int):
    code, reason = StdlibJSONWebSocketTransport._parse_close(
        struct.pack("!H", wire_code) + b"ignored"
    )
    assert code == wire_code
    assert reason is None


def test_close_frame_without_a_payload_has_no_code():
    assert StdlibJSONWebSocketTransport._parse_close(b"") == (None, None)


def test_close_frame_with_an_undecodable_reason_keeps_the_code():
    code, reason = StdlibJSONWebSocketTransport._parse_close(
        struct.pack("!H", 1008) + b"\xff\xfe"
    )
    assert code == 1008
    assert reason is None


# --------------------------------------------------------------------------
# Redaction


def test_close_reason_is_length_bounded():
    redacted = redact_reason("x" * 5_000)
    assert len(redacted) <= 120


def test_close_reason_strips_newlines():
    assert redact_reason("a\r\nb") == "a  b"


@pytest.mark.parametrize(
    "reason",
    [
        "Authorization: Bearer sk-abcdef123456",
        "token=abcdef123456",
        "bearer abcdef123456",
    ],
)
def test_close_reason_redacts_credential_shaped_text(reason: str):
    redacted = redact_reason(reason)
    assert "abcdef123456" not in redacted
    assert "sk-abcdef123456" not in redacted


# --------------------------------------------------------------------------
# Cancellation


async def test_capability_probe_propagates_cancellation():
    """A cancelled probe must not answer a live voice request with "unreachable"."""
    from infrastructure.audio import AudioProviderConfig
    from infrastructure.audio.capabilities import probe_audio_capabilities

    async def cancelled_fetch(url, timeout, headers):
        raise asyncio.CancelledError()

    config = AudioProviderConfig(
        provider_name="speechrail",
        base_url="http://127.0.0.1:8201/v1",
        api_key="",
    )
    with pytest.raises(asyncio.CancelledError):
        await probe_audio_capabilities(config, fetch_json=cancelled_fetch)


async def test_capability_probe_still_reports_an_ordinary_transport_error():
    from infrastructure.audio import AudioProviderConfig
    from infrastructure.audio.capabilities import probe_audio_capabilities

    async def failing_fetch(url, timeout, headers):
        raise OSError("connection refused")

    config = AudioProviderConfig(
        provider_name="speechrail",
        base_url="http://127.0.0.1:8201/v1",
        api_key="",
    )
    observation = await probe_audio_capabilities(config, fetch_json=failing_fetch)
    assert observation.status == "unreachable"
    assert observation.errors == ("capabilities_transport_error",)
