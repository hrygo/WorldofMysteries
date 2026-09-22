"""Small dependency-free RFC 6455 JSON transport for local SpeechRail.

The Engine intentionally keeps this transport narrow: one JSON text message at
a time, no extensions/subprotocols, bounded messages, strict server framing and
mandatory client masking.  It is sufficient for SpeechRail's current-only
Realtime speech plane without adding an undeclared transitive dependency.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import os
import ssl
import struct
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit


_WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_RESERVED_REQUEST_HEADERS = {
    "connection",
    "host",
    "sec-websocket-key",
    "sec-websocket-version",
    "upgrade",
}


class JSONWebSocketTransportError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class StdlibJSONWebSocketTransport:
    """Bounded RFC 6455 client for JSON text events."""

    maximum_http_header_bytes = 16 * 1024
    maximum_message_bytes = 1024 * 1024

    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._timeout_seconds = timeout_seconds
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._send_lock = asyncio.Lock()
        self._close_sent = False

    async def open(self, url: str, headers: Mapping[str, str]) -> None:
        if self._reader is not None or self._writer is not None:
            raise JSONWebSocketTransportError("websocket_invalid_state")
        parsed = urlsplit(url)
        if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
            raise JSONWebSocketTransportError("websocket_invalid_url")
        if parsed.username is not None or parsed.password is not None or parsed.fragment:
            raise JSONWebSocketTransportError("websocket_invalid_url")
        for name, value in headers.items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise JSONWebSocketTransportError("websocket_invalid_header")
            if name.lower() in _RESERVED_REQUEST_HEADERS or "\r" in value or "\n" in value:
                raise JSONWebSocketTransportError("websocket_invalid_header")

        secure = parsed.scheme == "wss"
        port = parsed.port or (443 if secure else 80)
        ssl_context = ssl.create_default_context() if secure else None
        server_hostname = parsed.hostname if secure else None
        writer: asyncio.StreamWriter | None = None
        try:
            async with asyncio.timeout(self._timeout_seconds):
                reader, writer = await asyncio.open_connection(
                    parsed.hostname,
                    port,
                    ssl=ssl_context,
                    server_hostname=server_hostname,
                )
                key = base64.b64encode(os.urandom(16)).decode("ascii")
                path = parsed.path or "/"
                if parsed.query:
                    path += f"?{parsed.query}"
                host = self._host_header(parsed.hostname, port, secure=secure)
                request_lines = [
                    f"GET {path} HTTP/1.1",
                    f"Host: {host}",
                    "Upgrade: websocket",
                    "Connection: Upgrade",
                    f"Sec-WebSocket-Key: {key}",
                    "Sec-WebSocket-Version: 13",
                ]
                request_lines.extend(f"{name}: {value}" for name, value in headers.items())
                request = "\r\n".join(request_lines) + "\r\n\r\n"
                writer.write(request.encode("ascii"))
                await writer.drain()
                raw_headers = await reader.readuntil(b"\r\n\r\n")
                if len(raw_headers) > self.maximum_http_header_bytes:
                    raise JSONWebSocketTransportError("websocket_handshake_too_large")
                response_headers = self._parse_handshake(raw_headers)
                expected_accept = base64.b64encode(
                    hashlib.sha1((key + _WEBSOCKET_GUID).encode("ascii")).digest()
                ).decode("ascii")
                if response_headers.get("sec-websocket-accept") != expected_accept:
                    raise JSONWebSocketTransportError("websocket_handshake_invalid")
                if response_headers.get(":status") != "101":
                    raise JSONWebSocketTransportError("websocket_handshake_rejected")
                if response_headers.get("upgrade", "").lower() != "websocket":
                    raise JSONWebSocketTransportError("websocket_handshake_invalid")
                connection_tokens = {
                    token.strip().lower()
                    for token in response_headers.get("connection", "").split(",")
                }
                if "upgrade" not in connection_tokens:
                    raise JSONWebSocketTransportError("websocket_handshake_invalid")
            self._reader = reader
            self._writer = writer
            self._close_sent = False
        except BaseException:
            if writer is not None:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()
            raise

    async def send_json(self, payload: Mapping[str, object]) -> None:
        try:
            text = json.dumps(
                dict(payload),
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError):
            raise JSONWebSocketTransportError("websocket_json_invalid") from None
        encoded = text.encode("utf-8")
        if len(encoded) > self.maximum_message_bytes:
            raise JSONWebSocketTransportError("websocket_message_too_large")
        await self._send_frame(0x1, encoded)

    async def receive_json(self) -> Mapping[str, object]:
        fragments = bytearray()
        fragmented = False
        while True:
            fin, opcode, payload = await self._read_frame()
            if opcode == 0x8:  # close
                if len(payload) == 1:
                    raise JSONWebSocketTransportError("websocket_close_invalid")
                if not self._close_sent:
                    await self._send_frame(0x8, payload[:125])
                    self._close_sent = True
                raise JSONWebSocketTransportError("websocket_closed")
            if opcode == 0x9:  # ping
                await self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:  # pong
                continue
            if opcode == 0x2:
                raise JSONWebSocketTransportError("websocket_binary_unsupported")
            if opcode == 0x1:
                if fragmented:
                    raise JSONWebSocketTransportError("websocket_fragment_invalid")
                fragments.extend(payload)
                fragmented = not fin
            elif opcode == 0x0:
                if not fragmented:
                    raise JSONWebSocketTransportError("websocket_fragment_invalid")
                fragments.extend(payload)
                fragmented = not fin
            else:
                raise JSONWebSocketTransportError("websocket_opcode_unsupported")

            if len(fragments) > self.maximum_message_bytes:
                raise JSONWebSocketTransportError("websocket_message_too_large")
            if fragmented:
                continue
            try:
                decoded = fragments.decode("utf-8")
                value: Any = json.loads(decoded)
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise JSONWebSocketTransportError("websocket_json_invalid") from None
            if not isinstance(value, dict):
                raise JSONWebSocketTransportError("websocket_json_invalid")
            return value

    async def close(self) -> None:
        writer = self._writer
        if writer is None:
            self._reader = None
            return
        if not self._close_sent:
            with contextlib.suppress(Exception):
                await self._send_frame(0x8, struct.pack("!H", 1000))
            self._close_sent = True
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
        self._reader = None
        self._writer = None

    async def _send_frame(self, opcode: int, payload: bytes) -> None:
        writer = self._writer
        if writer is None:
            raise JSONWebSocketTransportError("websocket_not_connected")
        if opcode >= 0x8 and len(payload) > 125:
            raise JSONWebSocketTransportError("websocket_control_too_large")
        if len(payload) > self.maximum_message_bytes:
            raise JSONWebSocketTransportError("websocket_message_too_large")

        first = 0x80 | opcode
        length = len(payload)
        if length <= 125:
            length_field = bytes([0x80 | length])
        elif length <= 0xFFFF:
            length_field = bytes([0x80 | 126]) + struct.pack("!H", length)
        else:
            length_field = bytes([0x80 | 127]) + struct.pack("!Q", length)
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        frame = bytes([first]) + length_field + mask + masked
        async with self._send_lock:
            try:
                async with asyncio.timeout(self._timeout_seconds):
                    writer.write(frame)
                    await writer.drain()
            except (TimeoutError, ConnectionError, OSError):
                raise JSONWebSocketTransportError("websocket_send_failed") from None

    async def _read_frame(self) -> tuple[bool, int, bytes]:
        reader = self._reader
        if reader is None:
            raise JSONWebSocketTransportError("websocket_not_connected")
        try:
            async with asyncio.timeout(self._timeout_seconds):
                prefix = await reader.readexactly(2)
                first, second = prefix
                fin = bool(first & 0x80)
                if first & 0x70:
                    raise JSONWebSocketTransportError("websocket_extension_unsupported")
                opcode = first & 0x0F
                if second & 0x80:
                    raise JSONWebSocketTransportError("websocket_server_masked")
                length = second & 0x7F
                if length == 126:
                    length = struct.unpack("!H", await reader.readexactly(2))[0]
                elif length == 127:
                    raw_length = await reader.readexactly(8)
                    length = struct.unpack("!Q", raw_length)[0]
                    if length & (1 << 63):
                        raise JSONWebSocketTransportError("websocket_frame_invalid")
                if opcode >= 0x8:
                    if not fin or length > 125:
                        raise JSONWebSocketTransportError("websocket_control_invalid")
                if length > self.maximum_message_bytes:
                    raise JSONWebSocketTransportError("websocket_message_too_large")
                payload = await reader.readexactly(length)
                return fin, opcode, payload
        except JSONWebSocketTransportError:
            raise
        except TimeoutError:
            raise JSONWebSocketTransportError("websocket_receive_timeout") from None
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            raise JSONWebSocketTransportError("websocket_receive_failed") from None

    @classmethod
    def _parse_handshake(cls, raw: bytes) -> dict[str, str]:
        try:
            text = raw.decode("iso-8859-1")
        except UnicodeDecodeError:
            raise JSONWebSocketTransportError("websocket_handshake_invalid") from None
        lines = text.split("\r\n")
        if not lines or not lines[0].startswith("HTTP/1.1 "):
            raise JSONWebSocketTransportError("websocket_handshake_invalid")
        parts = lines[0].split(" ", 2)
        if len(parts) < 2 or not parts[1].isdigit():
            raise JSONWebSocketTransportError("websocket_handshake_invalid")
        headers: dict[str, str] = {":status": parts[1]}
        for line in lines[1:]:
            if not line:
                continue
            if ":" not in line:
                raise JSONWebSocketTransportError("websocket_handshake_invalid")
            name, value = line.split(":", 1)
            key = name.strip().lower()
            if not key or key in headers:
                raise JSONWebSocketTransportError("websocket_handshake_invalid")
            headers[key] = value.strip()
        return headers

    @staticmethod
    def _host_header(hostname: str, port: int, *, secure: bool) -> str:
        host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
        default_port = 443 if secure else 80
        return host if port == default_port else f"{host}:{port}"
