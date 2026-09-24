"""Voice render runtime seals control identity before provider execution."""
from __future__ import annotations

import asyncio
import hashlib

import pytest

from application.audio_disclosure import SpokenSpanMapping
from application.performance_compiler import (
    DesiredPerformance,
    EffectiveBackendPerformance,
    EffectivePlaybackPerformance,
)
from application.speech_unit import SealedSpeechUnit
from infrastructure.audio.media_protocol import (
    MediaFormat,
    MediaOpenHeader,
    read_media_frame,
)
from infrastructure.audio.realtime_tts import (
    RealtimeTTSChunk,
    RealtimeTTSTerminal,
)
from infrastructure.audio.voice_runtime import (
    SealedSpeechUnitRegistry,
    VoiceRenderRuntime,
)
from infrastructure.ipc_framing import read_frame, write_frame
from infrastructure.ipc_server import LocalIPCServer


class MemoryMediaWriter:
    def __init__(self) -> None:
        self.data = bytearray()

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        return None


class FakeRuntimeAdapter:
    def __init__(self) -> None:
        self.connected_model_id = None
        self.connected_model_revision = None
        self.closed = False
        self.requests = []

    async def connect(
        self,
        *,
        expected_model_id=None,
        expected_model_revision=None,
        enable_render_receipts=True,
    ):
        assert enable_render_receipts is True
        self.connected_model_id = expected_model_id
        self.connected_model_revision = expected_model_revision

    async def render(self, request, on_chunk):
        self.requests.append(request)
        pcm = b"\x01\x00\x02\x00"
        await on_chunk(
            RealtimeTTSChunk(
                response_id="resp-runtime",
                item_id="item-runtime",
                sequence=1,
                offset_frames=0,
                frame_count=2,
                pcm16=pcm,
            )
        )
        return RealtimeTTSTerminal(
            request_id=request.request_id,
            response_id="resp-runtime",
            status="completed",
            total_frames=2,
            total_bytes=len(pcm),
            pcm_sha256=hashlib.sha256(pcm).hexdigest(),
            voice_revision=request.expected_voice_revision,
            receipt_id="receipt-runtime",
        )

    async def cancel_active(self):
        return None

    async def close(self):
        self.closed = True


def sealed_unit() -> SealedSpeechUnit:
    return SealedSpeechUnit(
        unit_id="speech_" + "a" * 32,
        turn_id="turn-1",
        story_session_id="session-1",
        story_revision=7,
        narrative_block_id="narrative-1",
        segment_index=0,
        presentation_identity="klein-visible",
        binding_id="binding-1",
        binding_revision=2,
        logical_voice_id="voice-klein",
        persona_revision="persona-r1",
        provider_instance="speechrail-local",
        voice_id="klein-approved",
        voice_revision="voice-" + "b" * 40,
        model_id="speechrail/qwen3-tts",
        model_revision="c" * 40,
        language="zh-CN",
        performance_plan_id="perf_" + "d" * 24,
        display_text="克莱恩没有开门。",
        spoken_text="克莱恩没有开门。",
        pronunciation_revision="pron-v1",
        pronunciation_mappings=(),
        desired=DesiredPerformance(),
        backend=EffectiveBackendPerformance(speed=1.0),
        playback=EffectivePlaybackPerformance(
            volume="normal",
            pause_before_ms=0,
        ),
        unsupported=(),
        degradation=(),
    )


def request_payload(unit: SealedSpeechUnit, **overrides):
    payload = {
        "schema_version": "1.0",
        **unit.render_recipe(),
        "media_stream_id": "media-runtime",
        "generation": 4,
    }
    payload.update(overrides)
    return payload


def opened(*, generation=4):
    return MediaOpenHeader(
        stream_id="media-runtime",
        trace_id="trace-runtime",
        engine_epoch="engine-runtime",
        generation=generation,
        ticket="e" * 64,
        direction="engine_to_app",
        format=MediaFormat(sample_rate=24_000),
        max_payload_bytes=4096,
        initial_credit_bytes=4096,
    )


async def decode_frames(data: bytes, count: int):
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return [await read_media_frame(reader) for _ in range(count)]


async def test_runtime_registers_only_exact_sealed_recipe():
    adapter = FakeRuntimeAdapter()
    runtime = VoiceRenderRuntime(
        provider_instance="speechrail-local",
        adapter_factory=lambda: adapter,
    )
    unit = sealed_unit()
    runtime.publish(unit)

    accepted, error = await runtime.handle_control(request_payload(unit))
    assert error is None
    assert accepted is not None
    assert accepted["speech_unit_id"] == unit.unit_id
    assert accepted["media_stream_id"] == "media-runtime"

    duplicate, duplicate_error = await runtime.handle_control(
        request_payload(unit, media_stream_id="media-second")
    )
    assert duplicate is None
    assert duplicate_error == "voice_render_unit_already_reserved"


async def test_runtime_rejects_app_text_or_voice_drift_without_consuming_unit():
    runtime = VoiceRenderRuntime(provider_instance="speechrail-local")
    unit = sealed_unit()
    runtime.publish(unit)

    accepted, error = await runtime.handle_control(
        request_payload(unit, spoken_text="篡改文本")
    )
    assert accepted is None
    assert error == "voice_render_recipe_mismatch"
    assert runtime.sealed_units.peek(unit.unit_id) == unit


async def test_runtime_media_consumes_once_and_streams_pcm_end():
    adapter = FakeRuntimeAdapter()
    runtime = VoiceRenderRuntime(
        provider_instance="speechrail-local",
        adapter_factory=lambda: adapter,
    )
    unit = sealed_unit()
    runtime.publish(unit)
    accepted, error = await runtime.handle_control(request_payload(unit))
    assert accepted is not None and error is None

    reader = asyncio.StreamReader()
    writer = MemoryMediaWriter()
    await runtime.media_handler(
        opened(),
        reader,
        writer,  # type: ignore[arg-type]
    )

    frames = await decode_frames(bytes(writer.data), 2)
    assert [header.kind for header, _ in frames] == ["chunk", "end"]
    assert adapter.connected_model_id == "speechrail/qwen3-tts"
    assert adapter.connected_model_revision == "c" * 40
    assert adapter.requests[0].text == unit.spoken_text
    assert adapter.requests[0].voice == unit.voice_id
    assert adapter.requests[0].expected_voice_revision == unit.voice_revision
    assert adapter.closed
    assert len(runtime.sealed_units) == 0


async def test_runtime_generation_mismatch_fails_before_provider_and_allows_reseal_retry():
    adapters = []
    runtime = VoiceRenderRuntime(
        provider_instance="speechrail-local",
        adapter_factory=lambda: adapters.append(FakeRuntimeAdapter()) or adapters[-1],
    )
    unit = sealed_unit()
    runtime.publish(unit)
    accepted, error = await runtime.handle_control(request_payload(unit))
    assert accepted is not None and error is None

    reader = asyncio.StreamReader()
    writer = MemoryMediaWriter()
    await runtime.media_handler(
        opened(generation=5),
        reader,
        writer,  # type: ignore[arg-type]
    )
    frames = await decode_frames(bytes(writer.data), 1)
    assert frames[0][0].kind == "error"
    assert frames[0][0].code == "voice_render_generation_mismatch"
    assert adapters == []
    assert runtime.sealed_units.peek(unit.unit_id) == unit

    retried, retry_error = await runtime.handle_control(
        request_payload(unit, media_stream_id="media-retry", generation=6)
    )
    assert retried is not None
    assert retry_error is None


async def test_runtime_unregistered_media_never_opens_provider():
    adapters = []
    runtime = VoiceRenderRuntime(
        provider_instance="speechrail-local",
        adapter_factory=lambda: adapters.append(FakeRuntimeAdapter()) or adapters[-1],
    )
    writer = MemoryMediaWriter()
    await runtime.media_handler(
        opened(),
        asyncio.StreamReader(),
        writer,  # type: ignore[arg-type]
    )
    frames = await decode_frames(bytes(writer.data), 1)
    assert frames[0][0].kind == "error"
    assert frames[0][0].code == "voice_render_not_found"
    assert adapters == []


def test_sealed_registry_is_bounded_and_content_identity_is_stable():
    now = [10.0]
    registry = SealedSpeechUnitRegistry(
        max_entries=1,
        ttl_seconds=5,
        clock=lambda: now[0],
    )
    unit = sealed_unit()
    registry.publish(unit)
    registry.publish(unit)
    assert len(registry) == 1

    other = sealed_unit()
    object.__setattr__(other, "unit_id", "speech_" + "f" * 32)
    with pytest.raises(Exception, match="voice_render_unit_registry_capacity"):
        registry.publish(other)

    now[0] = 16.0
    assert len(registry) == 0


async def test_runtime_executes_authenticated_control_to_media_uds_end_to_end():
    import tempfile
    from pathlib import Path

    adapter = FakeRuntimeAdapter()
    runtime = VoiceRenderRuntime(
        provider_instance="speechrail-local",
        adapter_factory=lambda: adapter,
    )
    unit = sealed_unit()
    runtime.publish(unit)

    with tempfile.TemporaryDirectory(prefix="wom-voice-runtime-") as directory:
        socket_path = Path(directory) / "engine.sock"
        server = LocalIPCServer(
            socket_path,
            "f" * 64,
            media_session_handler=runtime.media_handler,
            control_handlers={"voice.render": runtime.handle_control},
        )
        await server.start()
        try:
            control_reader, control_writer = await asyncio.open_unix_connection(
                socket_path
            )
            await write_frame(
                control_writer,
                {
                    "kind": "request",
                    "protocol_version": "1.0",
                    "request_id": "hello",
                    "trace_id": "trace-runtime",
                    "method": "system.handshake",
                    "payload": {
                        "app_version": "0.1.0",
                        "app_build": "test",
                        "supported_protocols": ["1.0"],
                        "session_token": "f" * 64,
                    },
                },
            )
            hello = await read_frame(control_reader)
            assert set(hello["payload"]["capabilities"]) == {
                "system.health",
                "system.shutdown",
                "voice.render",
                "media.open",
            }

            await write_frame(
                control_writer,
                {
                    "kind": "request",
                    "protocol_version": "1.0",
                    "request_id": "media-open",
                    "trace_id": "trace-runtime",
                    "method": "media.open",
                    "payload": {
                        "direction": "engine_to_app",
                        "generation": 4,
                        "format": {
                            "codec": "pcm_s16le",
                            "sample_rate": 24000,
                            "channels": 1,
                        },
                    },
                },
            )
            grant_reply = await read_frame(control_reader)
            grant = grant_reply["payload"]

            control_payload = request_payload(
                unit,
                media_stream_id=grant["stream_id"],
                generation=grant["generation"],
            )
            await write_frame(
                control_writer,
                {
                    "kind": "request",
                    "protocol_version": "1.0",
                    "request_id": "voice-render",
                    "trace_id": "trace-runtime",
                    "method": "voice.render",
                    "payload": control_payload,
                },
            )
            render_reply = await read_frame(control_reader)
            assert render_reply["status"] == "ok"
            assert render_reply["payload"]["speech_unit_id"] == unit.unit_id

            media_reader, media_writer = await asyncio.open_unix_connection(
                grant["socket_path"]
            )
            media_open = MediaOpenHeader(
                stream_id=grant["stream_id"],
                trace_id=grant["trace_id"],
                engine_epoch=grant["engine_epoch"],
                generation=grant["generation"],
                ticket=grant["ticket"],
                direction=grant["direction"],
                format=MediaFormat.model_validate(grant["format"]),
                max_payload_bytes=grant["max_payload_bytes"],
                initial_credit_bytes=grant["initial_credit_bytes"],
            )
            from infrastructure.audio.media_protocol import write_media_frame
            await write_media_frame(media_writer, media_open)

            first_header, first_payload = await read_media_frame(media_reader)
            terminal_header, terminal_payload = await read_media_frame(media_reader)
            assert first_header.kind == "chunk"
            assert first_payload == b"\x01\x00\x02\x00"
            assert terminal_header.kind == "end"
            assert terminal_payload == b""
            assert adapter.connected_model_revision == unit.model_revision

            media_writer.close()
            control_writer.close()
            await media_writer.wait_closed()
            await control_writer.wait_closed()
        finally:
            await server.close()
