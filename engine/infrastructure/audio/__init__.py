"""Audio Infrastructure Package (OpenAI SDK & SpeechRail Integration)."""

from .config import AudioProviderConfig
from .mock_adapter import MockAudioAdapter
from .openai_adapter import OpenAIAudioAdapter, create_audio_adapter

__all__ = [
    "AudioProviderConfig",
    "OpenAIAudioAdapter",
    "MockAudioAdapter",
    "create_audio_adapter",
]
