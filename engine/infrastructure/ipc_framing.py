"""Bounded length-prefixed UTF-8 JSON framing; errors never include payload bytes."""
from __future__ import annotations

import asyncio
import json
import math
import struct
from typing import Any

MAX_FRAME_BYTES = 1024 * 1024
FRAME_TIMEOUT = 5.0
MAX_JSON_DEPTH = 64


class FrameError(ValueError):
    """Untrusted framing/JSON input. Close the connection without echoing its bytes."""


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FrameError("Duplicate JSON key")
        result[key] = value
    return result


def _number(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise FrameError("Nonfinite JSON number")
    return value


def _constant(_: str) -> None:
    raise FrameError("Invalid JSON constant")


def _check_depth(text: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise FrameError("JSON nesting exceeds limit")
        elif char in "]}":
            depth -= 1


def decode_payload(data: bytes) -> dict[str, Any]:
    try:
        if not data or len(data) > MAX_FRAME_BYTES:
            raise FrameError("Invalid frame length")
        text = data.decode("utf-8")
        _check_depth(text)
        value = json.loads(text, object_pairs_hook=_object,
                           parse_float=_number, parse_constant=_constant)
        if not isinstance(value, dict):
            raise FrameError("JSON envelope must be an object")
        return value
    except (UnicodeError, ValueError, RecursionError):
        raise FrameError("Invalid JSON frame") from None


def encode_frame(value: dict[str, Any], max_bytes: int = MAX_FRAME_BYTES) -> bytes:
    try:
        if not isinstance(value, dict):
            raise FrameError("JSON envelope must be an object")
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        _check_depth(text)
        data = text.encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise FrameError("Unencodable JSON frame") from None
    if not data or len(data) > max_bytes:
        raise FrameError("Frame exceeds size limit")
    return struct.pack("!I", len(data)) + data


async def read_frame(reader: asyncio.StreamReader, *, max_bytes: int = MAX_FRAME_BYTES,
                     timeout: float = FRAME_TIMEOUT) -> dict[str, Any]:
    # Authenticated idle connections need not poll or reconnect. Once a byte arrives,
    # the entire remaining header/body has one absolute deadline, not a per-byte timer.
    try:
        first = await reader.readexactly(1)
    except asyncio.IncompleteReadError:
        raise EOFError from None
    try:
        async with asyncio.timeout(timeout):
            header = first + await reader.readexactly(3)
            size = struct.unpack("!I", header)[0]
            if size == 0 or size > max_bytes:
                raise FrameError("Invalid frame length")
            return decode_payload(await reader.readexactly(size))
    except asyncio.IncompleteReadError:
        raise FrameError("Truncated frame") from None


async def write_frame(writer: asyncio.StreamWriter, value: dict[str, Any],
                      *, timeout: float = FRAME_TIMEOUT) -> None:
    writer.write(encode_frame(value))
    async with asyncio.timeout(timeout):
        await writer.drain()
