"""Test suite for Audio Voice Engine OpenAI SDK Adapter & SpeechRail integration."""

import asyncio
import base64
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
    REALTIME_TTS_SAMPLE_RATE,
    RealtimeTTSRequest,
    SpeechRailRealtimeTTSAdapter,
    SpeechRailRealtimeTTSError,
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
async def test_speechrail_capability_probe_observes_only_safe_routing_fields():
    config = AudioProviderConfig()
    seen_urls: list[str] = []

    async def fetch(url: str, timeout: float) -> ProbeHttpResponse:
        assert timeout == config.timeout_seconds
        seen_urls.append(url)
        payloads = {
            "http://127.0.0.1:8201/health": {
                "version": "2.4.0",
                "profile": "quality",
                "asr_ready": True,
                "tts_ready": True,
            },
            "http://127.0.0.1:8201/readyz": {"ready": True},
            "http://127.0.0.1:8201/v1/models": {
                "object": "list",
                "data": [{"id": "whisper-1"}, {"id": "tts-1"}],
            },
            "http://127.0.0.1:8201/v1/voices": {
                "object": "list",
                "data": [
                    {
                        "id": "serena",
                        "available": True,
                        "variant": "custom_voice",
                        "capabilities": {
                            "supports_speaker": True,
                            "supports_instruction": False,
                            "supports_clone": False,
                        },
                        "ref_text": "private reference text must not escape the probe",
                        "audio_path": "/private/reference.wav",
                    }
                ],
            },
        }
        return ProbeHttpResponse(200, payloads[url])

    result = await probe_audio_capabilities(config, fetch_json=fetch)

    assert result.status == "ready"
    assert result.assurance == "legacy_observed"
    assert result.ready is True
    assert result.service_version == "2.4.0"
    assert result.profile == "quality"
    assert result.asr_ready is True
    assert result.tts_ready is True
    assert result.model_ids == ("tts-1", "whisper-1")
    assert len(result.voices) == 1
    voice = result.voices[0]
    assert voice.voice_id == "serena"
    assert voice.available is True
    assert voice.variant == "custom_voice"
    assert voice.supports_speaker is True
    assert voice.supports_instruction is False
    assert voice.supports_clone is False
    assert not hasattr(voice, "ref_text")
    assert not hasattr(voice, "audio_path")
    assert result.errors == ()
    assert set(seen_urls) == {
        "http://127.0.0.1:8201/health",
        "http://127.0.0.1:8201/readyz",
        "http://127.0.0.1:8201/v1/models",
        "http://127.0.0.1:8201/v1/voices",
    }


@pytest.mark.asyncio
async def test_speechrail_capability_probe_keeps_missing_fields_unknown():
    config = AudioProviderConfig()

    async def fetch(url: str, timeout: float) -> ProbeHttpResponse:
        del timeout
        if url.endswith("/health"):
            return ProbeHttpResponse(200, {})
        if url.endswith("/readyz"):
            return ProbeHttpResponse(200, {"ready": True})
        if url.endswith("/models"):
            return ProbeHttpResponse(200, {"data": []})
        return ProbeHttpResponse(
            200,
            {"data": [{"id": "legacy_voice", "capabilities": {}}]},
        )

    result = await probe_audio_capabilities(config, fetch_json=fetch)

    assert result.status == "ready"
    assert result.service_version is None
    assert result.profile is None
    assert result.asr_ready is None
    assert result.tts_ready is None
    assert result.voices[0].available is None
    assert result.voices[0].variant is None
    assert result.voices[0].supports_instruction is None


@pytest.mark.asyncio
async def test_speechrail_capability_probe_preserves_not_ready_and_catalog_evidence():
    config = AudioProviderConfig()

    async def fetch(url: str, timeout: float) -> ProbeHttpResponse:
        del timeout
        if url.endswith("/health"):
            return ProbeHttpResponse(
                200,
                {"version": "2.4.0", "asr_ready": False, "tts_ready": False},
            )
        if url.endswith("/readyz"):
            return ProbeHttpResponse(503, {"error": {"code": "backend_not_ready"}})
        if url.endswith("/models"):
            return ProbeHttpResponse(200, {"data": [{"id": "tts-1"}]})
        return ProbeHttpResponse(200, {"data": []})

    result = await probe_audio_capabilities(config, fetch_json=fetch)

    assert result.status == "not_ready"
    assert result.ready is False
    assert result.model_ids == ("tts-1",)
    assert "readyz_http_503" in result.errors


@pytest.mark.asyncio
async def test_capability_probe_does_not_apply_speechrail_private_contract_to_third_party():
    config = AudioProviderConfig(
        provider_name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key="test",
    )
    called = False

    async def fetch(url: str, timeout: float) -> ProbeHttpResponse:
        nonlocal called
        called = True
        raise AssertionError((url, timeout))

    result = await probe_audio_capabilities(config, fetch_json=fetch)

    assert result.status == "not_applicable"
    assert result.assurance == "not_applicable"
    assert called is False


@pytest.mark.asyncio
async def test_speechrail_capability_probe_rejects_ambiguous_base_path_without_network():
    config = AudioProviderConfig(base_url="http://127.0.0.1:8201/api")
    called = False

    async def fetch(url: str, timeout: float) -> ProbeHttpResponse:
        nonlocal called
        called = True
        raise AssertionError((url, timeout))

    result = await probe_audio_capabilities(config, fetch_json=fetch)

    assert result.status == "invalid_config"
    assert result.errors == ("base_url_invalid",)
    assert called is False


@pytest.mark.asyncio
async def test_openai_audio_adapter_exposes_capability_probe_on_same_config():
    config = AudioProviderConfig(base_url="http://127.0.0.1:9000/v1")
    adapter = create_audio_adapter(config)

    async def fetch(url: str, timeout: float) -> ProbeHttpResponse:
        assert timeout == config.timeout_seconds
        if url == "http://127.0.0.1:9000/health":
            return ProbeHttpResponse(
                200,
                {"version": "2.4.0", "asr_ready": True, "tts_ready": True},
            )
        if url == "http://127.0.0.1:9000/readyz":
            return ProbeHttpResponse(200, {"ready": True})
        return ProbeHttpResponse(200, {"data": []})

    result = await adapter.probe_capabilities(fetch_json=fetch)

    assert result.status == "ready"
    assert result.service_version == "2.4.0"


@pytest.mark.asyncio
async def test_speechrail_capability_probe_reports_all_transport_failures_as_unreachable():
    config = AudioProviderConfig()

    async def fetch(url: str, timeout: float) -> ProbeHttpResponse:
        del url, timeout
        raise OSError("offline")

    result = await probe_audio_capabilities(config, fetch_json=fetch)

    assert result.status == "unreachable"
    assert result.ready is None
    assert result.errors == (
        "health_transport_error",
        "models_transport_error",
        "readyz_transport_error",
        "voices_transport_error",
    )


@pytest.mark.asyncio
async def test_speechrail_capability_probe_reports_partial_discovery_as_degraded():
    config = AudioProviderConfig()

    async def fetch(url: str, timeout: float) -> ProbeHttpResponse:
        del timeout
        if url.endswith("/health"):
            return ProbeHttpResponse(
                200,
                {"version": "2.4.0", "asr_ready": True, "tts_ready": True},
            )
        if url.endswith("/readyz"):
            return ProbeHttpResponse(200, {"ready": True})
        if url.endswith("/models"):
            return ProbeHttpResponse(200, {"data": "not-a-list"})
        return ProbeHttpResponse(200, {"data": []})

    result = await probe_audio_capabilities(config, fetch_json=fetch)

    assert result.status == "degraded"
    assert result.ready is True
    assert result.model_ids == ()
    assert result.errors == ("models_invalid",)


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
