"""Test suite for Audio Voice Engine OpenAI SDK Adapter & SpeechRail integration."""

import asyncio
import base64
import hashlib
import json
import os
import struct
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.audio_voice import ASRProviderProtocol, ASRResult, SpeechResult, TTSProviderProtocol
from infrastructure.audio import (
    AudioProviderConfig,
    MEDIA_MAX_HEADER_BYTES,
    MediaCancelHeader,
    MediaChunkHeader,
    MediaCreditHeader,
    MediaCreditWindow,
    MediaEndHeader,
    MediaFormat,
    MediaGrantStore,
    MediaOpenHeader,
    MediaProtocolError,
    MediaReceiveState,
    MockAudioAdapter,
    OpenAIAudioAdapter,
    encode_media_frame,
    parse_media_header,
    read_media_frame,
    ProbeHttpResponse,
    EngineRealtimeTTSMediaStream,
    REALTIME_TTS_SAMPLE_RATE,
    RealtimeTTSChunk,
    RealtimeTTSMediaBridgeError,
    RealtimeTTSRequest,
    RealtimeTTSTerminal,
    render_realtime_tts_to_media,
    SpeechRailRealtimeTTSAdapter,
    SpeechRailRealtimeTTSError,
    StdlibJSONWebSocketTransport,
    create_realtime_tts_adapter,
    create_audio_adapter,
    probe_audio_capabilities,
)


def test_audio_provider_config_default_speechrail():
    """Verify default config points to the current local SpeechRail endpoint."""
    with patch.dict(os.environ, {}, clear=True):
        config = AudioProviderConfig.from_env()
        assert config.provider_name == "speechrail"
        assert config.base_url == "http://127.0.0.1:8201/v1"
        assert config.api_key == "speechrail-local"
        assert config.asr_model == "whisper-1"
        assert config.tts_model == "tts-1"


def test_audio_provider_config_hot_swap_to_third_party():
    """Verify hot-swapping to third-party OpenAI-compatible provider via environment."""
    env_override = {
        "AUDIO_PROVIDER_NAME": "groq",
        "OPENAI_AUDIO_BASE_URL": "https://api.groq.com/openai/v1",
        "OPENAI_AUDIO_API_KEY": "gsk_test_secret_key_12345",
        "OPENAI_AUDIO_ASR_MODEL": "whisper-large-v3",
        "OPENAI_AUDIO_TTS_MODEL": "tts-custom",
        "OPENAI_AUDIO_DEFAULT_VOICE": "playwright",
    }
    with patch.dict(os.environ, env_override, clear=True):
        config = AudioProviderConfig.from_env()
        assert config.provider_name == "groq"
        assert config.base_url == "https://api.groq.com/openai/v1"
        assert config.api_key == "gsk_test_secret_key_12345"
        assert config.asr_model == "whisper-large-v3"
        assert config.tts_model == "tts-custom"
        assert config.default_voice == "playwright"


def test_audio_provider_config_keeps_explicit_speechrail_override():
    """A configured SpeechRail endpoint wins over the local default."""
    with patch.dict(
        os.environ,
        {"SPEECHRAIL_BASE_URL": "http://127.0.0.1:9000/v1"},
        clear=True,
    ):
        config = AudioProviderConfig.from_env()
        assert config.base_url == "http://127.0.0.1:9000/v1"


def test_asr_result_confidence_defaults_to_unknown():
    """Missing confidence evidence must remain unknown."""
    result = ASRResult(transcript="测试")
    assert result.confidence is None


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_asr_result_rejects_out_of_range_confidence(value):
    with pytest.raises(ValueError, match="ASR confidence"):
        ASRResult(transcript="测试", confidence=value)


def test_openai_audio_adapter_conforms_to_domain_protocols():
    """Verify OpenAIAudioAdapter implements pure domain protocols."""
    adapter = create_audio_adapter()
    assert isinstance(adapter, ASRProviderProtocol)
    assert isinstance(adapter, TTSProviderProtocol)
    assert adapter.provider_name == "speechrail"


@pytest.mark.asyncio
async def test_openai_audio_adapter_transcribe_mocked():
    """Verify transcribe forwards to OpenAI audio.transcriptions.create."""
    adapter = create_audio_adapter()

    mock_response = MagicMock()
    mock_response.text = "我想先看看医生的反应。"
    mock_response.confidence = None

    with patch.object(
        adapter._client.audio.transcriptions,
        "create",
        new=AsyncMock(return_value=mock_response),
    ) as mock_create:
        dummy_audio = b"FAKE_WAV_HEADER_AND_PCM_DATA"
        result = await adapter.transcribe(
            audio_data=dummy_audio,
            filename="advice.wav",
            language="zh",
        )

        assert isinstance(result, ASRResult)
        assert result.transcript == "我想先看看医生的反应。"
        assert result.confidence is None
        assert result.language == "zh"
        mock_create.assert_awaited_once_with(
            model="whisper-1",
            file=("advice.wav", dummy_audio),
            language="zh",
        )


@pytest.mark.asyncio
async def test_openai_audio_adapter_preserves_reported_confidence():
    """Compatible providers may expose an explicit calibrated confidence."""
    adapter = create_audio_adapter()

    mock_response = MagicMock()
    mock_response.text = "保持观察。"
    mock_response.confidence = 0.87

    with patch.object(
        adapter._client.audio.transcriptions,
        "create",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await adapter.transcribe(b"audio")
        assert result.confidence == pytest.approx(0.87)


@pytest.mark.asyncio
async def test_openai_audio_adapter_ignores_invalid_reported_confidence():
    """Invalid provider metadata is not promoted into domain evidence."""
    adapter = create_audio_adapter()

    mock_response = MagicMock()
    mock_response.text = "保持观察。"
    mock_response.confidence = 7.0

    with patch.object(
        adapter._client.audio.transcriptions,
        "create",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await adapter.transcribe(b"audio")
        assert result.confidence is None


@pytest.mark.asyncio
async def test_openai_audio_adapter_synthesize_mocked():
    """Verify synthesize forwards to OpenAI audio.speech.create."""
    adapter = create_audio_adapter()

    mock_response = AsyncMock()
    mock_response.aread = AsyncMock(return_value=b"SYNTHESIZED_MP3_PAYLOAD")

    with patch.object(
        adapter._client.audio.speech,
        "create",
        new=AsyncMock(return_value=mock_response),
    ) as mock_create:
        result = await adapter.synthesize(
            text="傍晚的浓雾笼罩着东区的街巷。",
            voice="narrator_mystic",
            response_format="mp3",
        )

        assert isinstance(result, SpeechResult)
        assert result.audio_bytes == b"SYNTHESIZED_MP3_PAYLOAD"
        assert result.format == "mp3"
        mock_create.assert_awaited_once_with(
            model="tts-1",
            voice="narrator_mystic",
            input="傍晚的浓雾笼罩着东区的街巷。",
            response_format="mp3",
            speed=1.0,
        )


@pytest.mark.asyncio
async def test_mock_audio_adapter_deterministic():
    """Verify MockAudioAdapter operates deterministically without network."""
    mock_adapter = MockAudioAdapter(mock_transcript="占卜家序列九")
    asr_res = await mock_adapter.transcribe(b"bytes")
    assert asr_res.transcript == "占卜家序列九"
    assert asr_res.confidence == pytest.approx(0.99)
    assert mock_adapter.transcribe_call_count == 1

    tts_res = await mock_adapter.synthesize("文字", voice="test")
    assert tts_res.audio_bytes == b"MOCK_MP3_AUDIO_HEADER_AND_FRAMES"
    assert mock_adapter.synthesize_call_count == 1


@pytest.mark.asyncio
async def test_speechrail_capability_probe_consumes_one_atomic_safe_snapshot():
    config = AudioProviderConfig()
    calls: list[tuple[str, dict[str, str]]] = []
    revision = "vr_" + "a" * 32

    async def fetch(url: str, timeout: float, headers) -> ProbeHttpResponse:
        assert timeout == config.timeout_seconds
        calls.append((url, dict(headers)))
        return ProbeHttpResponse(
            200,
            {
                "schema_version": "effective_capabilities_v1",
                "service_instance_epoch": "epoch-1",
                "catalog_revision": "catalog-1",
                "snapshot_id": "snapshot-1",
                "profile": "quality",
                "models": {
                    "asr": {"source_model": "speechrail/qwen3-asr-1.7b"},
                    "tts": {"source_model": "speechrail/qwen3-tts-1.7b"},
                },
                "realtime": {
                    "orchestration": "caller",
                    "server_llm": False,
                    "conversation_state": False,
                    "websocket_path": "/v1/realtime",
                    "mcp_realtime": False,
                },
                "voices": [{
                    "id": "serena",
                    "available": True,
                    "variant": "custom_voice",
                    "mode": "system",
                    "voice_revision": revision,
                    "voice_identity_assurance": "content_addressed",
                    "production_ready": True,
                    "operations": {
                        "http_speech": {
                            "parameters": {"instructions": {"status": "unsupported"}}
                        }
                    },
                    "ref_text": "must never be consumed",
                    "audio_path": "/private/must-not-escape.wav",
                }],
                "operations": {"tts_text_planner": {"version": "tts_bounded_v1"}},
                "guarantees": {
                    "inference_version_pin": False,
                    "admission_reserved": False,
                },
            },
            etag='"snapshot-etag"',
        )

    result = await probe_audio_capabilities(config, fetch_json=fetch)
    assert result.status == "ready"
    assert result.assurance == "effective_capabilities_v1"
    assert result.ready is None
    assert result.service_instance_epoch == "epoch-1"
    assert result.catalog_revision == "catalog-1"
    assert result.snapshot_id == "snapshot-1"
    assert result.etag == '"snapshot-etag"'
    assert result.profile == "quality"
    assert result.model_ids == (
        "speechrail/qwen3-asr-1.7b",
        "speechrail/qwen3-tts-1.7b",
    )
    voice = result.voices[0]
    assert voice.voice_id == "serena"
    assert voice.voice_revision == revision
    assert voice.voice_identity_assurance == "content_addressed"
    assert voice.production_ready is True
    assert voice.supports_instruction is False
    assert voice.supports_speaker is None
    assert calls == [(
        "http://127.0.0.1:8201/v1/speechrail/capabilities",
        {"Authorization": "Bearer speechrail-local"},
    )]


@pytest.mark.asyncio
async def test_speechrail_capability_probe_uses_etag_304_only_with_verified_cache():
    config = AudioProviderConfig()

    async def first_fetch(url: str, timeout: float, headers) -> ProbeHttpResponse:
        del url, timeout, headers
        return ProbeHttpResponse(200, {
            "schema_version": "effective_capabilities_v1",
            "service_instance_epoch": "epoch",
            "catalog_revision": "catalog",
            "snapshot_id": "snapshot",
            "profile": "balanced",
            "models": {},
            "realtime": {},
            "voices": [],
            "operations": {},
            "guarantees": {},
        }, etag='"etag-1"')

    cached = await probe_audio_capabilities(config, fetch_json=first_fetch)

    async def unchanged(url: str, timeout: float, headers) -> ProbeHttpResponse:
        del url, timeout
        assert headers["If-None-Match"] == '"etag-1"'
        assert headers["Authorization"] == "Bearer speechrail-local"
        return ProbeHttpResponse(304, {})

    again = await probe_audio_capabilities(config, fetch_json=unchanged, cached=cached)
    assert again is cached


@pytest.mark.asyncio
async def test_speechrail_capability_probe_rejects_unknown_or_incomplete_schema():
    config = AudioProviderConfig()

    async def wrong_schema(url: str, timeout: float, headers) -> ProbeHttpResponse:
        del url, timeout, headers
        return ProbeHttpResponse(200, {"schema_version": "future_capabilities_v9"})

    result = await probe_audio_capabilities(config, fetch_json=wrong_schema)
    assert result.status == "degraded"
    assert result.assurance == "unknown"
    assert result.errors == ("capabilities_schema_unsupported",)

    async def invalid_snapshot(url: str, timeout: float, headers) -> ProbeHttpResponse:
        del url, timeout, headers
        return ProbeHttpResponse(200, {
            "schema_version": "effective_capabilities_v1",
            "service_instance_epoch": "epoch",
        })

    result = await probe_audio_capabilities(config, fetch_json=invalid_snapshot)
    assert result.status == "degraded"
    assert result.errors == ("capabilities_invalid",)


@pytest.mark.asyncio
async def test_speechrail_capability_probe_preserves_not_ready_and_transport_evidence():
    config = AudioProviderConfig()

    async def unavailable(url: str, timeout: float, headers) -> ProbeHttpResponse:
        del url, timeout, headers
        return ProbeHttpResponse(503, {})

    result = await probe_audio_capabilities(config, fetch_json=unavailable)
    assert result.status == "not_ready"
    assert result.assurance == "unknown"
    assert result.errors == ("capabilities_http_503",)

    async def broken(url: str, timeout: float, headers) -> ProbeHttpResponse:
        del url, timeout, headers
        raise OSError("offline")

    result = await probe_audio_capabilities(config, fetch_json=broken)
    assert result.status == "unreachable"
    assert result.errors == ("capabilities_transport_error",)

@pytest.mark.asyncio
async def test_capability_probe_does_not_apply_speechrail_private_contract_to_third_party():
    config = AudioProviderConfig(
        provider_name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key="test",
    )
    called = False

    async def fetch(url: str, timeout: float, headers) -> ProbeHttpResponse:
        nonlocal called
        called = True
        del headers
        raise AssertionError((url, timeout))

    result = await probe_audio_capabilities(config, fetch_json=fetch)

    assert result.status == "not_applicable"
    assert result.assurance == "not_applicable"
    assert called is False


@pytest.mark.asyncio
async def test_speechrail_capability_probe_rejects_ambiguous_base_path_without_network():
    config = AudioProviderConfig(base_url="http://127.0.0.1:8201/api")
    called = False

    async def fetch(url: str, timeout: float, headers) -> ProbeHttpResponse:
        nonlocal called
        called = True
        del headers
        raise AssertionError((url, timeout))

    result = await probe_audio_capabilities(config, fetch_json=fetch)

    assert result.status == "invalid_config"
    assert result.errors == ("base_url_invalid",)
    assert called is False


@pytest.mark.asyncio
async def test_openai_audio_adapter_exposes_capability_probe_on_same_config():
    config = AudioProviderConfig(base_url="http://127.0.0.1:9000/v1")
    adapter = create_audio_adapter(config)

    async def fetch(url: str, timeout: float, headers) -> ProbeHttpResponse:
        assert timeout == config.timeout_seconds
        assert url == "http://127.0.0.1:9000/v1/speechrail/capabilities"
        assert headers["Authorization"] == "Bearer speechrail-local"
        return ProbeHttpResponse(
            200,
            {
                "schema_version": "effective_capabilities_v1",
                "service_instance_epoch": "epoch-adapter",
                "catalog_revision": "catalog-adapter",
                "snapshot_id": "snapshot-adapter",
                "profile": "quality",
                "models": {},
                "realtime": {},
                "voices": [],
                "operations": {},
                "guarantees": {},
            },
            etag='"adapter-etag"',
        )

    result = await adapter.probe_capabilities(fetch_json=fetch)

    assert result.status == "ready"
    assert result.assurance == "effective_capabilities_v1"
    assert result.snapshot_id == "snapshot-adapter"


@pytest.mark.asyncio
async def test_speechrail_capability_probe_reports_all_transport_failures_as_unreachable():
    config = AudioProviderConfig()

    async def fetch(url: str, timeout: float, headers) -> ProbeHttpResponse:
        del url, timeout, headers
        raise OSError("offline")

    result = await probe_audio_capabilities(config, fetch_json=fetch)

    assert result.status == "unreachable"
    assert result.ready is None
    assert result.errors == ("capabilities_transport_error",)


@pytest.mark.asyncio
async def test_speechrail_capability_probe_reports_partial_discovery_as_degraded():
    config = AudioProviderConfig()

    async def fetch(url: str, timeout: float, headers) -> ProbeHttpResponse:
        del timeout, headers
        assert url.endswith("/v1/speechrail/capabilities")
        return ProbeHttpResponse(
            200,
            {
                "schema_version": "effective_capabilities_v1",
                "service_instance_epoch": "epoch",
                "catalog_revision": "catalog",
                "snapshot_id": "snapshot",
                "models": "not-a-mapping",
                "voices": [],
                "operations": {},
                "guarantees": {},
            },
        )

    result = await probe_audio_capabilities(config, fetch_json=fetch)

    assert result.status == "degraded"
    assert result.ready is None
    assert result.model_ids == ()
    assert result.errors == ("capabilities_invalid",)


MEDIA_FIXTURES = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "fixtures"
        / "media"
        / "headers.json"
    ).read_text(encoding="utf-8")
)


@pytest.mark.parametrize(
    "case",
    MEDIA_FIXTURES,
    ids=lambda case: f"python_{case['id']}",
)
def test_media_header_python_parity_with_contract_fixtures(case):
    if case["valid"]:
        parsed = parse_media_header(case["header"])
        assert parsed.kind == case["header"]["kind"]
    else:
        # Some invalid fixtures are schema-valid headers with invalid framing.
        # The encode path performs both checks.
        try:
            parsed = parse_media_header(case["header"])
        except MediaProtocolError:
            return
        payload = b"\x00" * case["payload_length"]
        with pytest.raises(MediaProtocolError):
            encode_media_frame(parsed, payload)


@pytest.mark.asyncio
async def test_media_frame_roundtrip_is_raw_pcm_not_base64():
    payload = (b"\x01\x02" * 960)
    header = MediaChunkHeader(
        stream_id="stream_1",
        generation=4,
        sequence=0,
        offset_frames=0,
        frame_count=960,
        payload_bytes=len(payload),
    )
    wire = encode_media_frame(header, payload)
    assert payload in wire

    reader = asyncio.StreamReader()
    reader.feed_data(wire)
    reader.feed_eof()
    decoded, decoded_payload = await read_media_frame(reader)

    assert decoded == header
    assert decoded_payload == payload


@pytest.mark.asyncio
async def test_media_reader_rejects_oversize_header_before_body_allocation():
    reader = asyncio.StreamReader()
    reader.feed_data((MEDIA_MAX_HEADER_BYTES + 1).to_bytes(4, "big") + (0).to_bytes(4, "big"))
    reader.feed_eof()

    with pytest.raises(MediaProtocolError, match="media_header_too_large"):
        await read_media_frame(reader)


def test_media_grant_is_one_time_bound_and_does_not_retain_ticket_plaintext():
    now = 100.0
    store = MediaGrantStore(clock=lambda: now)
    fmt = MediaFormat(sample_rate=24000)
    ticket, grant = store.mint(
        stream_id="tts_1",
        trace_id="trace_1",
        engine_epoch="epoch_1",
        generation=9,
        direction="engine_to_app",
        format=fmt,
    )
    assert ticket not in repr(store)
    assert ticket not in repr(grant)

    opened = MediaOpenHeader(
        stream_id=grant.stream_id,
        trace_id=grant.trace_id,
        engine_epoch=grant.engine_epoch,
        generation=grant.generation,
        ticket=ticket,
        direction=grant.direction,
        format=grant.format,
        max_payload_bytes=grant.max_payload_bytes,
        initial_credit_bytes=grant.initial_credit_bytes,
    )
    assert store.consume(opened) == grant
    with pytest.raises(MediaProtocolError, match="media_ticket_invalid"):
        store.consume(opened)


def test_media_grant_mismatch_burns_ticket():
    store = MediaGrantStore()
    fmt = MediaFormat(sample_rate=16000)
    ticket, grant = store.mint(
        stream_id="asr_1",
        trace_id="trace_2",
        engine_epoch="epoch_2",
        generation=1,
        direction="app_to_engine",
        format=fmt,
    )
    wrong = MediaOpenHeader(
        stream_id=grant.stream_id,
        trace_id=grant.trace_id,
        engine_epoch=grant.engine_epoch,
        generation=2,
        ticket=ticket,
        direction=grant.direction,
        format=grant.format,
        max_payload_bytes=grant.max_payload_bytes,
        initial_credit_bytes=grant.initial_credit_bytes,
    )
    with pytest.raises(MediaProtocolError, match="media_grant_mismatch"):
        store.consume(wrong)
    with pytest.raises(MediaProtocolError, match="media_ticket_invalid"):
        store.consume(wrong)


def test_media_credit_window_is_bounded():
    credit = MediaCreditWindow(4096)
    credit.consume(2048)
    assert credit.available_bytes == 2048
    credit.grant(1024)
    assert credit.available_bytes == 3072
    with pytest.raises(MediaProtocolError, match="media_credit_exhausted"):
        credit.consume(4096)


def test_media_receive_state_validates_sequence_offsets_totals_and_digest():
    opened = MediaOpenHeader(
        stream_id="tts_1",
        trace_id="trace_1",
        engine_epoch="epoch_1",
        generation=3,
        ticket="a" * 64,
        direction="engine_to_app",
        format=MediaFormat(sample_rate=24000),
        max_payload_bytes=4096,
        initial_credit_bytes=4096,
    )
    state = MediaReceiveState(opened)
    p0 = b"\x00\x01" * 100
    p1 = b"\x02\x03" * 50
    state.accept_chunk(
        MediaChunkHeader(
            stream_id="tts_1",
            generation=3,
            sequence=0,
            offset_frames=0,
            frame_count=100,
            payload_bytes=len(p0),
        ),
        p0,
    )
    state.accept_chunk(
        MediaChunkHeader(
            stream_id="tts_1",
            generation=3,
            sequence=1,
            offset_frames=100,
            frame_count=50,
            payload_bytes=len(p1),
        ),
        p1,
    )
    digest = hashlib.sha256(p0 + p1).hexdigest()
    state.accept_end(
        MediaEndHeader(
            stream_id="tts_1",
            generation=3,
            total_frames=150,
            total_bytes=300,
            sha256=digest,
        )
    )
    assert state.total_frames == 150
    assert state.total_bytes == 300


def test_media_receive_state_rejects_late_generation_and_gap():
    opened = MediaOpenHeader(
        stream_id="tts_1",
        trace_id="trace_1",
        engine_epoch="epoch_1",
        generation=8,
        ticket="b" * 64,
        direction="engine_to_app",
        format=MediaFormat(sample_rate=24000),
        max_payload_bytes=4096,
        initial_credit_bytes=4096,
    )
    state = MediaReceiveState(opened)
    with pytest.raises(MediaProtocolError, match="media_stream_identity_mismatch"):
        state.accept_chunk(
            MediaChunkHeader(
                stream_id="tts_1",
                generation=7,
                sequence=0,
                offset_frames=0,
                frame_count=1,
                payload_bytes=2,
            ),
            b"\x00\x00",
        )
    with pytest.raises(MediaProtocolError, match="media_chunk_sequence_mismatch"):
        state.accept_chunk(
            MediaChunkHeader(
                stream_id="tts_1",
                generation=8,
                sequence=1,
                offset_frames=0,
                frame_count=1,
                payload_bytes=2,
            ),
            b"\x00\x00",
        )


def test_media_control_frames_reject_binary_payload():
    header = MediaCreditHeader(
        stream_id="tts_1",
        generation=1,
        credit_bytes=1024,
    )
    with pytest.raises(MediaProtocolError, match="media_control_payload_forbidden"):
        encode_media_frame(header, b"\x00\x00")


class _FakeRealtimeTTSTransport:
    def __init__(self) -> None:
        self.opened: list[tuple[str, dict[str, str]]] = []
        self.sent: list[dict[str, object]] = []
        self.closed = False
        self.session_id = "sess-tts-1"
        self.sequence = 0
        self.inbound: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        self.script_on_create = None

    async def open(self, url, headers):
        self.opened.append((url, dict(headers)))
        await self.emit(
            {
                "type": "session.created",
                "session": {
                    "id": self.session_id,
                    "type": "transcription",
                    "input_audio_format": "pcm16",
                    "speechrail": {"tts": {"enabled": False}},
                },
            }
        )

    async def send_json(self, payload):
        message = dict(payload)
        self.sent.append(message)
        if message["type"] == "transcription_session.update":
            session = message["session"]
            speechrail = session["speechrail"]
            await self.emit(
                {
                    "type": "transcription_session.updated",
                    "session": {
                        "id": self.session_id,
                        "type": "transcription",
                        "input_audio_format": "pcm16",
                        "input_audio_transcription": {"model": "whisper-1"},
                        "turn_detection": None,
                        "speechrail": {
                            "tts": {"enabled": True},
                            "render_receipts": {
                                "enabled": bool(
                                    speechrail.get("render_receipts", {}).get("enabled")
                                )
                            },
                        },
                    },
                }
            )
        elif message["type"] == "speechrail.tts.create" and self.script_on_create:
            await self.script_on_create(self, message)
        elif message["type"] == "speechrail.tts.cancel":
            await self.emit(
                {
                    "type": "response.done",
                    "response": {
                        "id": message.get("response_id", "resp-cancel"),
                        "object": "realtime.response",
                        "status": "cancelled",
                        "output": [],
                    },
                    "speechrail": {
                        "kind": "tts",
                        "orchestration": "caller",
                        "request_id": message["request_id"],
                    },
                }
            )

    async def receive_json(self):
        return await self.inbound.get()

    async def close(self):
        self.closed = True

    async def emit(self, payload):
        self.sequence += 1
        event = dict(payload)
        event.setdefault("event_id", f"srv-{self.sequence}")
        event.setdefault("session_id", self.session_id)
        event.setdefault("sequence", self.sequence)
        await self.inbound.put(event)


def _receipt(*, request_id, response_id, pcm, voice="serena"):
    return {
        "receipt_id": "rr_" + "a" * 32,
        "request_id": request_id,
        "response_id": response_id,
        "status": "completed",
        "voice": {"id": voice, "revision": "vr_test"},
        "model": {
            "artifact": "tts",
            "source_model": "speechrail/qwen3-tts",
            "variant": "base",
            "catalog_revision": "b" * 40,
            "runtime_revision": None,
        },
        "audio": {
            "format": "pcm16",
            "pcm_sample_rate": REALTIME_TTS_SAMPLE_RATE,
            "channels": 1,
            "integrity_boundary": "pcm16_after_websocket_send",
            "sample_count": len(pcm) // 2,
            "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
        },
        "error_code": None,
    }


async def _script_completed_tts(transport, message, chunks=(b"\x01\x00\x02\x00", b"\x03\x00")):
    response_id = "resp-1"
    item_id = "item-1"
    await transport.emit(
        {
            "type": "response.created",
            "response": {
                "id": response_id,
                "object": "realtime.response",
                "status": "in_progress",
                "output": [],
            },
        }
    )
    await transport.emit(
        {
            "type": "response.output_item.added",
            "response_id": response_id,
            "output_index": 0,
            "item": {
                "id": item_id,
                "object": "realtime.item",
                "type": "message",
                "role": "assistant",
                "content": [],
            },
        }
    )
    await transport.emit(
        {
            "type": "response.content_part.added",
            "response_id": response_id,
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
            "part": {"type": "audio"},
        }
    )
    for chunk in chunks:
        await transport.emit(
            {
                "type": "response.output_audio.delta",
                "response_id": response_id,
                "item_id": item_id,
                "output_index": 0,
                "content_index": 0,
                "delta": base64.b64encode(chunk).decode("ascii"),
            }
        )
    await transport.emit(
        {
            "type": "response.output_audio.done",
            "response_id": response_id,
            "item_id": item_id,
            "output_index": 0,
            "content_index": 0,
        }
    )
    await transport.emit(
        {
            "type": "response.output_item.done",
            "response_id": response_id,
            "output_index": 0,
            "item": {"id": item_id},
        }
    )
    pcm = b"".join(chunks)
    await transport.emit(
        {
            "type": "response.done",
            "response": {
                "id": response_id,
                "object": "realtime.response",
                "status": "completed",
                "output": [],
            },
            "speechrail": {
                "kind": "tts",
                "orchestration": "caller",
                "request_id": message["request_id"],
                "voice_revision": "vr_test",
                "render_receipt": _receipt(
                    request_id=message["request_id"], response_id=response_id, pcm=pcm
                ),
            },
        }
    )


@pytest.mark.asyncio
async def test_realtime_tts_uses_current_only_handshake_and_streams_verified_pcm():
    transport = _FakeRealtimeTTSTransport()
    transport.script_on_create = _script_completed_tts
    config = AudioProviderConfig(default_voice="serena")
    adapter = SpeechRailRealtimeTTSAdapter(config, transport)

    await adapter.connect(expected_model_revision="b" * 40)
    chunks = []

    async def collect(chunk):
        chunks.append(chunk)

    request = RealtimeTTSRequest(
        text="向前走。",
        voice="serena",
        request_id="wom-turn-1-sentence-1",
        expected_voice_revision="vr_test",
    )
    terminal = await adapter.render(request, collect)

    assert transport.opened == [
        (
            "ws://127.0.0.1:8201/v1/realtime?model=whisper-1",
            {"Authorization": "Bearer speechrail-local"},
        )
    ]
    session_update = transport.sent[0]
    assert session_update["type"] == "transcription_session.update"
    assert session_update["session"]["input_audio_format"] == "pcm16"
    assert session_update["session"]["speechrail"] == {
        "tts": {"enabled": True},
        "render_receipts": {"enabled": True},
        "model_revision": {"expected": "b" * 40},
    }
    create = transport.sent[1]
    assert create == {
        "type": "speechrail.tts.create",
        "request_id": "wom-turn-1-sentence-1",
        "text": "向前走。",
        "voice": "serena",
        "speed": 1.0,
        "expected_voice_revision": "vr_test",
    }
    assert [chunk.offset_frames for chunk in chunks] == [0, 2]
    assert [chunk.frame_count for chunk in chunks] == [2, 1]
    assert b"".join(chunk.pcm16 for chunk in chunks) == b"\x01\x00\x02\x00\x03\x00"
    assert terminal.status == "completed"
    assert terminal.total_frames == 3
    assert terminal.total_bytes == 6
    assert terminal.receipt_id == "rr_" + "a" * 32


@pytest.mark.asyncio
async def test_realtime_tts_fails_closed_when_receipt_disagrees_with_received_pcm():
    async def bad_receipt(transport, message):
        await _script_completed_tts(transport, message)
        events = []
        while not transport.inbound.empty():
            events.append(await transport.inbound.get())
        events[-1]["speechrail"]["render_receipt"]["audio"]["sample_count"] = 999
        for event in events:
            await transport.inbound.put(event)

    transport = _FakeRealtimeTTSTransport()
    transport.script_on_create = bad_receipt
    adapter = SpeechRailRealtimeTTSAdapter(AudioProviderConfig(default_voice="serena"), transport)
    await adapter.connect()

    with pytest.raises(SpeechRailRealtimeTTSError, match="render_receipt_mismatch"):
        await adapter.render(
            RealtimeTTSRequest(
                text="测试",
                voice="serena",
                request_id="req-bad-receipt",
            ),
            AsyncMock(),
        )


@pytest.mark.asyncio
async def test_realtime_tts_rejects_odd_pcm_before_it_reaches_media_sink():
    async def odd_audio(transport, message):
        await transport.emit(
            {
                "type": "response.created",
                "response": {"id": "resp-odd", "status": "in_progress"},
            }
        )
        await transport.emit(
            {
                "type": "response.output_item.added",
                "response_id": "resp-odd",
                "item": {"id": "item-odd"},
            }
        )
        await transport.emit(
            {
                "type": "response.output_audio.delta",
                "response_id": "resp-odd",
                "item_id": "item-odd",
                "delta": base64.b64encode(b"\x00").decode("ascii"),
            }
        )

    transport = _FakeRealtimeTTSTransport()
    transport.script_on_create = odd_audio
    adapter = SpeechRailRealtimeTTSAdapter(AudioProviderConfig(default_voice="serena"), transport)
    await adapter.connect()
    sink = AsyncMock()

    with pytest.raises(SpeechRailRealtimeTTSError, match="realtime_invalid_audio"):
        await adapter.render(
            RealtimeTTSRequest(text="测试", voice="serena", request_id="req-odd"),
            sink,
        )
    sink.assert_not_awaited()


@pytest.mark.asyncio
async def test_realtime_tts_cancel_uses_namespaced_cancel_and_terminal_is_cancelled():
    created = asyncio.Event()

    async def wait_for_cancel(transport, message):
        await transport.emit(
            {
                "type": "response.created",
                "response": {"id": "resp-cancel", "status": "in_progress"},
            }
        )
        await transport.emit(
            {
                "type": "response.output_item.added",
                "response_id": "resp-cancel",
                "item": {"id": "item-cancel"},
            }
        )
        created.set()

    transport = _FakeRealtimeTTSTransport()
    transport.script_on_create = wait_for_cancel
    adapter = SpeechRailRealtimeTTSAdapter(AudioProviderConfig(default_voice="serena"), transport)
    await adapter.connect()
    render_task = asyncio.create_task(
        adapter.render(
            RealtimeTTSRequest(text="停止前的句子", voice="serena", request_id="req-cancel"),
            AsyncMock(),
        )
    )
    await created.wait()
    await asyncio.sleep(0)
    await adapter.cancel_active()
    terminal = await render_task

    assert transport.sent[-1] == {
        "type": "speechrail.tts.cancel",
        "request_id": "req-cancel",
        "response_id": "resp-cancel",
    }
    assert terminal.status == "cancelled"
    assert terminal.total_frames == 0


def test_realtime_tts_rejects_plaintext_remote_endpoint():
    adapter = SpeechRailRealtimeTTSAdapter(
        AudioProviderConfig(base_url="http://speech.example.test:8201/v1"),
        _FakeRealtimeTTSTransport(),
    )
    with pytest.raises(SpeechRailRealtimeTTSError, match="realtime_insecure_remote_endpoint"):
        asyncio.run(adapter.connect())


async def _read_masked_client_websocket_frame(reader):
    first, second = await reader.readexactly(2)
    fin = bool(first & 0x80)
    opcode = first & 0x0F
    assert second & 0x80, "RFC 6455 clients must mask frames"
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", await reader.readexactly(8))[0]
    mask = await reader.readexactly(4)
    encoded = await reader.readexactly(length)
    payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(encoded))
    return fin, opcode, payload


def _server_websocket_frame(opcode, payload, *, fin=True):
    first = (0x80 if fin else 0) | opcode
    length = len(payload)
    if length <= 125:
        prefix = bytes([first, length])
    elif length <= 0xFFFF:
        prefix = bytes([first, 126]) + struct.pack("!H", length)
    else:
        prefix = bytes([first, 127]) + struct.pack("!Q", length)
    return prefix + payload


@pytest.mark.asyncio
async def test_stdlib_websocket_transport_performs_real_masked_current_wire_roundtrip():
    observed = {}
    server_done = asyncio.Event()

    async def handler(reader, writer):
        try:
            request = await reader.readuntil(b"\r\n\r\n")
            lines = request.decode("ascii").split("\r\n")
            observed["request_line"] = lines[0]
            headers = {}
            for line in lines[1:]:
                if ":" in line:
                    name, value = line.split(":", 1)
                    headers[name.lower()] = value.strip()
            observed["authorization"] = headers.get("authorization")
            accept = base64.b64encode(
                hashlib.sha1(
                    (
                        headers["sec-websocket-key"]
                        + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
                    ).encode("ascii")
                ).digest()
            ).decode("ascii")
            writer.write(
                (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
                ).encode("ascii")
            )
            await writer.drain()

            fin, opcode, payload = await _read_masked_client_websocket_frame(reader)
            assert fin and opcode == 0x1
            observed["client_json"] = json.loads(payload.decode("utf-8"))

            writer.write(_server_websocket_frame(0x9, b"ping"))
            await writer.drain()
            fin, opcode, payload = await _read_masked_client_websocket_frame(reader)
            observed["pong"] = (fin, opcode, payload)

            response = json.dumps(
                {"type": "server.test", "message": "你好"},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            split = len(response) // 2
            writer.write(_server_websocket_frame(0x1, response[:split], fin=False))
            writer.write(_server_websocket_frame(0x0, response[split:], fin=True))
            await writer.drain()

            fin, opcode, payload = await _read_masked_client_websocket_frame(reader)
            observed["close"] = (fin, opcode, payload)
        finally:
            writer.close()
            await writer.wait_closed()
            server_done.set()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    transport = StdlibJSONWebSocketTransport(timeout_seconds=2)
    async with server:
        await transport.open(
            f"ws://127.0.0.1:{port}/v1/realtime?model=whisper-1",
            {"Authorization": "Bearer test-secret"},
        )
        await transport.send_json({"type": "speechrail.tts.cancel", "request_id": "r1"})
        response = await transport.receive_json()
        await transport.close()
        await asyncio.wait_for(server_done.wait(), timeout=2)

    assert observed["request_line"] == "GET /v1/realtime?model=whisper-1 HTTP/1.1"
    assert observed["authorization"] == "Bearer test-secret"
    assert observed["client_json"] == {
        "type": "speechrail.tts.cancel",
        "request_id": "r1",
    }
    assert observed["pong"] == (True, 0xA, b"ping")
    assert response == {"type": "server.test", "message": "你好"}
    assert observed["close"][0:2] == (True, 0x8)


def test_realtime_tts_factory_has_dependency_free_production_transport():
    adapter = create_realtime_tts_adapter(AudioProviderConfig())
    assert isinstance(adapter, SpeechRailRealtimeTTSAdapter)


class _MemoryMediaWriter:
    def __init__(self) -> None:
        self.data = bytearray()

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        return None


def _tts_media_open(*, credit: int = 16, max_payload: int = 4) -> MediaOpenHeader:
    return MediaOpenHeader(
        stream_id="tts-media",
        trace_id="trace-media",
        engine_epoch="engine-media",
        generation=3,
        ticket="a" * 64,
        direction="engine_to_app",
        format=MediaFormat(sample_rate=24_000),
        max_payload_bytes=max_payload,
        initial_credit_bytes=credit,
    )


async def _decode_media_frames(data: bytes, count: int):
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return [await read_media_frame(reader) for _ in range(count)]


@pytest.mark.asyncio
async def test_realtime_tts_media_bridge_rechunks_and_finishes():
    reader = asyncio.StreamReader()
    writer = _MemoryMediaWriter()
    stream = EngineRealtimeTTSMediaStream(_tts_media_open(), reader, writer)  # type: ignore[arg-type]
    await stream.start()
    pcm = bytes([1, 0, 2, 0, 3, 0, 4, 0])
    await stream.push(
        RealtimeTTSChunk(
            response_id="resp",
            item_id="item",
            sequence=10,
            offset_frames=0,
            frame_count=4,
            pcm16=pcm,
        )
    )
    digest = hashlib.sha256(pcm).hexdigest()
    await stream.finish_completed(
        RealtimeTTSTerminal(
            request_id="req",
            response_id="resp",
            status="completed",
            total_frames=4,
            total_bytes=8,
            pcm_sha256=digest,
            voice_revision="vr_" + "a" * 40,
            receipt_id="receipt",
        )
    )
    frames = await _decode_media_frames(bytes(writer.data), 3)
    assert [header.kind for header, _ in frames] == ["chunk", "chunk", "end"]
    assert [header.offset_frames for header, _ in frames[:2]] == [0, 2]
    assert frames[-1][0].sha256 == digest
    await stream.close()


@pytest.mark.asyncio
async def test_realtime_tts_media_bridge_waits_for_full_chunk_credit():
    reader = asyncio.StreamReader()
    writer = _MemoryMediaWriter()
    stream = EngineRealtimeTTSMediaStream(
        _tts_media_open(credit=2, max_payload=4), reader, writer  # type: ignore[arg-type]
    )
    await stream.start()
    task = asyncio.create_task(
        stream.push(
            RealtimeTTSChunk(
                response_id="resp",
                item_id="item",
                sequence=1,
                offset_frames=0,
                frame_count=2,
                pcm16=bytes([1, 0, 2, 0]),
            )
        )
    )
    await asyncio.sleep(0.01)
    assert not task.done()
    assert writer.data == b""
    reader.feed_data(
        encode_media_frame(
            MediaCreditHeader(
                stream_id="tts-media",
                generation=3,
                credit_bytes=2,
            )
        )
    )
    await asyncio.wait_for(task, timeout=1)
    frames = await _decode_media_frames(bytes(writer.data), 1)
    assert len(frames[0][1]) == 4
    await stream.close()


@pytest.mark.asyncio
async def test_realtime_tts_media_bridge_peer_cancel_unblocks_backpressure():
    reader = asyncio.StreamReader()
    writer = _MemoryMediaWriter()
    stream = EngineRealtimeTTSMediaStream(
        _tts_media_open(credit=0, max_payload=4), reader, writer  # type: ignore[arg-type]
    )
    await stream.start()
    task = asyncio.create_task(
        stream.push(
            RealtimeTTSChunk(
                response_id="resp",
                item_id="item",
                sequence=1,
                offset_frames=0,
                frame_count=1,
                pcm16=b"\x00\x00",
            )
        )
    )
    await asyncio.sleep(0.01)
    reader.feed_data(
        encode_media_frame(
            MediaCancelHeader(
                stream_id="tts-media",
                generation=3,
                reason="user_stop",
            )
        )
    )
    with pytest.raises(RealtimeTTSMediaBridgeError, match="media_peer_cancelled"):
        await asyncio.wait_for(task, timeout=1)
    stop = await stream.wait_peer_stop()
    assert stop.kind == "cancel"
    assert stop.reason == "user_stop"
    await stream.close()


@pytest.mark.asyncio
async def test_realtime_tts_media_bridge_terminal_mismatch_never_emits_end():
    reader = asyncio.StreamReader()
    writer = _MemoryMediaWriter()
    stream = EngineRealtimeTTSMediaStream(_tts_media_open(), reader, writer)  # type: ignore[arg-type]
    await stream.start()
    await stream.push(
        RealtimeTTSChunk(
            response_id="resp",
            item_id="item",
            sequence=1,
            offset_frames=0,
            frame_count=1,
            pcm16=b"\x01\x00",
        )
    )
    with pytest.raises(RealtimeTTSMediaBridgeError, match="media_bridge_terminal_mismatch"):
        await stream.finish_completed(
            RealtimeTTSTerminal(
                request_id="req",
                response_id="resp",
                status="completed",
                total_frames=1,
                total_bytes=2,
                pcm_sha256="0" * 64,
                voice_revision=None,
                receipt_id=None,
            )
        )
    frames = await _decode_media_frames(bytes(writer.data), 1)
    assert frames[0][0].kind == "chunk"
    await stream.close()


class _BridgeCancelAdapter:
    def __init__(self) -> None:
        self.cancel_calls = 0
        self.chunk_started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def render(self, request, on_chunk):
        self.chunk_started.set()
        await on_chunk(
            RealtimeTTSChunk(
                response_id="resp-cancel-bridge",
                item_id="item-cancel-bridge",
                sequence=1,
                offset_frames=0,
                frame_count=1,
                pcm16=b"\x01\x00",
            )
        )
        await self.cancelled.wait()
        return RealtimeTTSTerminal(
            request_id=request.request_id,
            response_id="resp-cancel-bridge",
            status="cancelled",
            total_frames=0,
            total_bytes=0,
            pcm_sha256=hashlib.sha256(b"").hexdigest(),
            voice_revision=None,
            receipt_id=None,
        )

    async def cancel_active(self):
        self.cancel_calls += 1
        self.cancelled.set()


@pytest.mark.asyncio
async def test_realtime_tts_media_bridge_peer_cancel_reaches_provider_while_credit_blocked():
    reader = asyncio.StreamReader()
    writer = _MemoryMediaWriter()
    adapter = _BridgeCancelAdapter()
    opened = _tts_media_open(credit=0, max_payload=4)
    request = RealtimeTTSRequest(
        text="停止这句",
        voice="serena",
        request_id="req-cancel-bridge",
    )
    task = asyncio.create_task(
        render_realtime_tts_to_media(
            adapter,  # type: ignore[arg-type]
            request,
            opened,
            reader,
            writer,  # type: ignore[arg-type]
        )
    )
    await adapter.chunk_started.wait()
    await asyncio.sleep(0)
    reader.feed_data(
        encode_media_frame(
            MediaCancelHeader(
                stream_id="tts-media",
                generation=3,
                reason="user_stop",
            )
        )
    )

    terminal = await asyncio.wait_for(task, timeout=1)
    assert terminal.status == "cancelled"
    assert adapter.cancel_calls == 1
    assert writer.data == b""
