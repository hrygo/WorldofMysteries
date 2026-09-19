"""Test suite for Audio Voice Engine OpenAI SDK Adapter & SpeechRail integration."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.audio_voice import ASRProviderProtocol, ASRResult, SpeechResult, TTSProviderProtocol
from infrastructure.audio import (
    AudioProviderConfig,
    MockAudioAdapter,
    OpenAIAudioAdapter,
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
