"""Test suite for Audio Voice Engine OpenAI SDK Adapter & SpeechRail integration."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.audio_voice import ASRProviderProtocol, ASRResult, SpeechResult, TTSProviderProtocol
from infrastructure.audio import (
    AudioProviderConfig,
    MockAudioAdapter,
    OpenAIAudioAdapter,
    create_audio_adapter,
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
