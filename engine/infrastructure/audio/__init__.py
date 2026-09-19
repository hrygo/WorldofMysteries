"""Audio Infrastructure Package (OpenAI SDK & SpeechRail Integration)."""

from .capabilities import (
    AudioCapabilityObservation,
    ProbeHttpResponse,
    VoiceCapabilityObservation,
    probe_audio_capabilities,
)
from .config import AudioProviderConfig
from .mock_adapter import MockAudioAdapter
from .openai_adapter import OpenAIAudioAdapter, create_audio_adapter

__all__ = [
    "AudioCapabilityObservation",
    "AudioProviderConfig",
    "MockAudioAdapter",
    "OpenAIAudioAdapter",
    "ProbeHttpResponse",
    "VoiceCapabilityObservation",
    "create_audio_adapter",
    "probe_audio_capabilities",
]
