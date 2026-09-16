"""Audio Provider Configuration.

Supports default SpeechRail local service with seamless hot-swap to any OpenAI-compatible provider.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AudioProviderConfig:
    """Configuration for OpenAI-compatible ASR & TTS voice services."""

    provider_name: str = "speechrail"
    base_url: str = "http://localhost:8080/v1"
    api_key: str = "speechrail-local"
    asr_model: str = "whisper-1"
    tts_model: str = "tts-1"
    default_voice: str = "alloy"
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls, custom_provider: Optional[str] = None) -> "AudioProviderConfig":
        """Load configuration from environment with fallback defaults.

        Precedence:
        1. Explicit provider environment variables (e.g. OPENAI_AUDIO_*)
        2. SpeechRail specific environment variables (e.g. SPEECHRAIL_*)
        3. Local SpeechRail defaults
        """
        base_url = (
            os.getenv("OPENAI_AUDIO_BASE_URL")
            or os.getenv("SPEECHRAIL_BASE_URL")
            or "http://localhost:8080/v1"
        )
        api_key = (
            os.getenv("OPENAI_AUDIO_API_KEY")
            or os.getenv("SPEECHRAIL_API_KEY")
            or "speechrail-local"
        )
        asr_model = os.getenv("OPENAI_AUDIO_ASR_MODEL") or "whisper-1"
        tts_model = os.getenv("OPENAI_AUDIO_TTS_MODEL") or "tts-1"
        default_voice = os.getenv("OPENAI_AUDIO_DEFAULT_VOICE") or "alloy"
        timeout_str = os.getenv("OPENAI_AUDIO_TIMEOUT", "30.0")

        return cls(
            provider_name=custom_provider or os.getenv("AUDIO_PROVIDER_NAME", "speechrail"),
            base_url=base_url,
            api_key=api_key,
            asr_model=asr_model,
            tts_model=tts_model,
            default_voice=default_voice,
            timeout_seconds=float(timeout_str),
        )
