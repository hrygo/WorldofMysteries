"""Test suite for Audio Voice Engine OpenAI SDK Adapter & SpeechRail integration."""

import asyncio
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.audio_voice import ASRProviderProtocol, ASRResult, SpeechResult, TTSProviderProtocol
from infrastructure.audio import (
    AudioProviderConfig,
    MEDIA_MAX_HEADER_BYTES,
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
