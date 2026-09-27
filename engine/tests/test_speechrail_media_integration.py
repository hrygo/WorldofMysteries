"""Offline integration across the real 4.0 adapter and the real media bridge.

The unit suites drive each half with a fake of the other. This file wires the
**production** adapter to the **production** ``render_realtime_tts_to_media``
bridge and only fakes the two network edges: the SpeechRail WebSocket peer and
the app-side media socket. What it proves is the seam — that a 4.0 render
reaches the media stream as PCM, that CREDIT bounds it, and that a failed
receipt can never become a media END.

Cancellation while the render is parked on credit is covered separately in
``test_audio_adapter.py`` with a provider fake that stays blocked; this file
deliberately does not re-model it, because a peer that has already queued its
whole render leaves the adapter with nothing active to cancel.
"""

from __future__ import annotations

import asyncio
import hashlib

import pytest
from test_audio_adapter import (
    _FakeRealtimeTTSTransport,
    _MemoryMediaWriter,
    _ScriptedReceiptReader,
    _tts_media_open,
)

from infrastructure.audio import AudioProviderConfig
from infrastructure.audio.media_bridge import render_realtime_tts_to_media
from infrastructure.audio.media_protocol import (
    MediaCancelHeader,
    MediaProtocolError,
    encode_media_frame,
    read_media_frame,
)
from infrastructure.audio.realtime_tts import (
    RealtimeTTSRequest,
    SpeechRailRealtimeTTSAdapter,
)


def _adapter(transport, **kwargs):
    return SpeechRailRealtimeTTSAdapter(
        AudioProviderConfig(default_voice="serena", api_key="sr-local-key"),
        transport,
        receipt_reader=_ScriptedReceiptReader(transport),
        **kwargs,
    )


def _request(request_id: str = "wom-turn-1-sentence-1") -> RealtimeTTSRequest:
    return RealtimeTTSRequest(
        text="向前走。",
        voice="serena",
        request_id=request_id,
    )


async def _drain(data: bytes) -> list[tuple]:
    """Decode every complete frame in ``data``; stop at the first partial one."""
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    frames = []
    while True:
        try:
            frames.append(
                await asyncio.wait_for(read_media_frame(reader), timeout=0.2)
            )
        except (
            asyncio.TimeoutError,
            asyncio.IncompleteReadError,
            EOFError,
            MediaProtocolError,
        ):
            return frames


@pytest.mark.asyncio
async def test_real_adapter_and_bridge_deliver_pcm_then_end():
    """A completed 4.0 render becomes chunk frames followed by exactly one END."""
    transport = _FakeRealtimeTTSTransport(chunks=(b"\x01\x00\x02\x00", b"\x03\x00"))
    adapter = _adapter(transport)
    await adapter.connect(expected_model_revision="b" * 40)

    reader = asyncio.StreamReader()
    writer = _MemoryMediaWriter()
    opened = _tts_media_open(credit=64, max_payload=64)

    terminal = await asyncio.wait_for(
        render_realtime_tts_to_media(adapter, _request(), opened, reader, writer),
        timeout=5,
    )
    assert terminal.status == "completed"

    frames = await _drain(bytes(writer.data))
    kinds = [h.kind for h, _ in frames]
    assert kinds[-1] == "end", f"END must be the last frame, got {kinds}"
    assert "error" not in kinds

    chunks = [f for f in frames if f[0].kind == "chunk"]
    assert [h.sequence for h, _ in chunks] == list(range(len(chunks)))
    pcm = b"".join(p for _, p in chunks)
    assert pcm == b"\x01\x00\x02\x00\x03\x00"

    end = frames[-1][0]
    assert end.total_bytes == len(pcm)
    assert end.total_frames == len(pcm) // 2
    # The media END digest covers exactly what crossed the media socket.
    assert end.sha256 == hashlib.sha256(pcm).hexdigest()


@pytest.mark.asyncio
async def test_credit_bounds_the_audio_and_a_late_grant_lets_it_finish():
    """With only two bytes of credit the bridge must stop, not overrun."""
    chunks = (b"\x01\x00\x02\x00", b"\x03\x00\x04\x00")
    transport = _FakeRealtimeTTSTransport(chunks=chunks)
    adapter = _adapter(transport)
    await adapter.connect(expected_model_revision="b" * 40)

    reader = asyncio.StreamReader()
    writer = _MemoryMediaWriter()
    opened = _tts_media_open(credit=2, max_payload=2)

    task = asyncio.create_task(
        render_realtime_tts_to_media(adapter, _request(), opened, reader, writer)
    )

    # Nothing may be written beyond the granted credit.
    await asyncio.sleep(0.05)
    blocked = await _drain(bytes(writer.data))
    assert [h.kind for h, _ in blocked] == ["chunk"]
    assert not task.done()

    from infrastructure.audio.media_protocol import MediaCreditHeader

    reader.feed_data(
        encode_media_frame(
            MediaCreditHeader(
                stream_id="tts-media",
                generation=3,
                credit_bytes=64,
            )
        )
    )
    terminal = await asyncio.wait_for(task, timeout=5)
    assert terminal.status == "completed"

    frames = await _drain(bytes(writer.data))
    kinds = [h.kind for h, _ in frames]
    assert kinds.count("chunk") == 4
    assert kinds[-1] == "end"
    pcm = b"".join(p for h, p in frames if h.kind == "chunk")
    assert pcm == b"".join(chunks)


@pytest.mark.asyncio
async def test_a_rejected_receipt_never_becomes_a_media_end():
    """Receipt evidence is the only proof of a completed render."""
    transport = _FakeRealtimeTTSTransport(
        chunks=(b"\x01\x00\x02\x00",),
        receipt_overrides={"audio": {"integrity_boundary": "pcm16_after_websocket_send"}},
    )
    adapter = _adapter(transport)
    await adapter.connect(expected_model_revision="b" * 40)

    reader = asyncio.StreamReader()
    writer = _MemoryMediaWriter()
    opened = _tts_media_open(credit=64, max_payload=64)

    with pytest.raises(Exception) as caught:
        await asyncio.wait_for(
            render_realtime_tts_to_media(adapter, _request(), opened, reader, writer),
            timeout=5,
        )
    assert "receipt" in str(caught.value).lower() or "integrity" in str(
        caught.value
    ).lower()

    kinds = [h.kind for h, _ in await _drain(bytes(writer.data))]
    assert "end" not in kinds, "an unproven render must not publish a media END"
