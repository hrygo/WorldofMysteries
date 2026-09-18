"""Framing assertions use real bytes/readers, not mocked envelope results."""
import asyncio
import struct

import pytest

from infrastructure.ipc_framing import FrameError, decode_payload, encode_frame, read_frame


@pytest.mark.parametrize("value", [{}, {"中文": [1, True, None]}, {"nested": {"ok": "yes"}}])
def test_encode_decode(value):
    data = encode_frame(value)
    assert struct.unpack("!I", data[:4])[0] == len(data) - 4
    assert decode_payload(data[4:]) == value


@pytest.mark.parametrize("payload", [b'{"x":1,"x":2}', b'{"a":{"x":1,"x":2}}',
    b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}', b'[]', b'null', b'1', b'"text"',
    b'\xff', b'{', b'{}{}', b'{"a":' + b'[' * 1500 + b'0' + b']' * 1500 + b'}'])
def test_reject_bad_json_without_echo(payload):
    with pytest.raises(FrameError) as exc:
        decode_payload(payload)
    assert str(exc.value) == "Invalid JSON frame"


@pytest.mark.parametrize("value", [{"x": float("nan")}, {"x": float("inf")},
                                  {"x": object()}, {"x": "\ud800"}])
def test_reject_invalid_output(value):
    with pytest.raises(FrameError):
        encode_frame(value)


def test_bound_output():
    with pytest.raises(FrameError):
        encode_frame({"big": "x" * 50}, max_bytes=20)


@pytest.mark.parametrize("raw", [struct.pack("!I", 0), struct.pack("!I", 1024 * 1024 + 1),
                                b'\x00\x00', struct.pack("!I", 4) + b'{'])
async def test_invalid_length_and_truncation(raw):
    reader = asyncio.StreamReader()
    reader.feed_data(raw)
    reader.feed_eof()
    with pytest.raises(FrameError):
        await read_frame(reader)


async def test_clean_eof():
    reader = asyncio.StreamReader()
    reader.feed_eof()
    with pytest.raises(EOFError):
        await read_frame(reader)


async def test_partial_header_deadline():
    reader = asyncio.StreamReader()
    reader.feed_data(b'\x00')
    with pytest.raises(TimeoutError):
        await read_frame(reader, timeout=0.03)


async def test_fragmented_and_coalesced_frames():
    reader = asyncio.StreamReader()
    encoded = encode_frame({"value": "中文"})
    task = asyncio.create_task(read_frame(reader))
    for byte in encoded:
        reader.feed_data(bytes([byte]))
        await asyncio.sleep(0)
    assert await task == {"value": "中文"}
    reader.feed_data(encode_frame({"n": 1}) + encode_frame({"n": 2}))
    assert await read_frame(reader) == {"n": 1}
    assert await read_frame(reader) == {"n": 2}


def test_braces_and_escaped_quotes_inside_strings_are_not_depth():
    value = {"text": "[" * 1000 + '\\"' + "}" * 1000}
    assert decode_payload(encode_frame(value)[4:]) == value


def test_nonobject_output_rejected():
    with pytest.raises(FrameError):
        encode_frame([])


def test_excessive_output_depth_rejected():
    value = {}
    for _ in range(100):
        value = {"nested": value}
    with pytest.raises(FrameError):
        encode_frame(value)
