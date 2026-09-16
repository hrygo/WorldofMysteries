"""Audio / Voice Engine Domain Protocols (Invariant 9: Narrative & audio strictly follow commit).

Pure domain layer - no external cloud SDK dependencies.
"""

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class ASRResult:
    """Domain representation of speech-to-text transcript output."""

    transcript: str
    confidence: float = 1.0
    duration_seconds: Optional[float] = None
    language: Optional[str] = None


@dataclass(frozen=True)
class SpeechResult:
    """Domain representation of text-to-speech synthesized audio output."""

    audio_bytes: bytes
    format: str = "mp3"
    duration_seconds: Optional[float] = None


@runtime_checkable
class ASRProviderProtocol(Protocol):
    """Abstract provider protocol for Automatic Speech Recognition."""

    async def transcribe(
        self,
        audio_data: bytes,
        filename: str = "audio.wav",
        language: Optional[str] = None,
    ) -> ASRResult:
        """Transcribe speech audio bytes into text."""
        ...


@runtime_checkable
class TTSProviderProtocol(Protocol):
    """Abstract provider protocol for Text-to-Speech synthesis."""

    async def synthesize(
        self,
        text: str,
        voice: str,
        response_format: str = "mp3",
        speed: float = 1.0,
    ) -> SpeechResult:
        """Synthesize text into speech audio bytes."""
        ...


@runtime_checkable
class AudioVoiceEngineProtocol(Protocol):
    """Abstract protocol for Audio/Voice orchestration, ducking, and timeline rendering."""

    async def process_user_speech(self, audio_data: bytes) -> ASRResult:
        """Process incoming player speech into authorized transcript."""
        ...

    async def render_narrative_speech(self, text: str, voice: str) -> SpeechResult:
        """Render committed narrative block into voice performance."""
        ...
