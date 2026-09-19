"""Audio Infrastructure Package (OpenAI SDK & SpeechRail Integration)."""

from .capabilities import (
    AudioCapabilityObservation,
    ProbeHttpResponse,
    VoiceCapabilityObservation,
    probe_audio_capabilities,
)
from .config import AudioProviderConfig
from .media_protocol import (
    MEDIA_MAX_HEADER_BYTES,
    MEDIA_MAX_PAYLOAD_BYTES,
    MediaChunkHeader,
    MediaCreditHeader,
    MediaCreditWindow,
    MediaEndHeader,
    MediaErrorHeader,
    MediaFormat,
    MediaGrant,
    MediaGrantStore,
    MediaOpenHeader,
    MediaProtocolError,
    MediaReceiveState,
    encode_media_frame,
    parse_media_header,
    read_media_frame,
    write_media_frame,
)
from .mock_adapter import MockAudioAdapter
from .openai_adapter import OpenAIAudioAdapter, create_audio_adapter

__all__ = [
    "AudioCapabilityObservation",
    "AudioProviderConfig",
    "MEDIA_MAX_HEADER_BYTES",
    "MEDIA_MAX_PAYLOAD_BYTES",
    "MediaChunkHeader",
    "MediaCreditHeader",
    "MediaCreditWindow",
    "MediaEndHeader",
    "MediaErrorHeader",
    "MediaFormat",
    "MediaGrant",
    "MediaGrantStore",
    "MediaOpenHeader",
    "MediaProtocolError",
    "MediaReceiveState",
    "MockAudioAdapter",
    "encode_media_frame",
    "parse_media_header",
    "read_media_frame",
    "write_media_frame",
    "OpenAIAudioAdapter",
    "ProbeHttpResponse",
    "VoiceCapabilityObservation",
    "create_audio_adapter",
    "probe_audio_capabilities",
]
