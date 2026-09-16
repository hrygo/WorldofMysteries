"""OpenAI SDK-compatible Audio Adapter for SpeechRail & Third-Party Voice Services."""

from typing import Optional
from openai import AsyncOpenAI
from domain.audio_voice import ASRProviderProtocol, ASRResult, SpeechResult, TTSProviderProtocol
from .config import AudioProviderConfig


class OpenAIAudioAdapter(ASRProviderProtocol, TTSProviderProtocol):
    """Audio Adapter implementing OpenAI Audio API Specification.

    Connects to SpeechRail by default, and can be seamlessly switched to any
    OpenAI-compatible speech provider (OpenAI, Azure, Groq, ElevenLabs proxy, LocalAI, etc.)
    by adjusting the base_url, api_key, and models.
    """

    def __init__(self, config: Optional[AudioProviderConfig] = None) -> None:
        self.config = config or AudioProviderConfig.from_env()
        self._client = AsyncOpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            timeout=self.config.timeout_seconds,
        )

    @property
    def provider_name(self) -> str:
        return self.config.provider_name

    @property
    def base_url(self) -> str:
        return self.config.base_url

    async def transcribe(
        self,
        audio_data: bytes,
        filename: str = "audio.wav",
        language: Optional[str] = None,
    ) -> ASRResult:
        """Transcribe speech audio bytes using OpenAI-compatible transcription API."""
        kwargs = {
            "model": self.config.asr_model,
            "file": (filename, audio_data),
        }
        if language:
            kwargs["language"] = language

        response = await self._client.audio.transcriptions.create(**kwargs)
        transcript = response.text if hasattr(response, "text") else str(response)

        return ASRResult(
            transcript=transcript.strip(),
            confidence=1.0,
            language=language,
        )

    async def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        response_format: str = "mp3",
        speed: float = 1.0,
    ) -> SpeechResult:
        """Synthesize text into speech using OpenAI-compatible speech synthesis API."""
        target_voice = voice or self.config.default_voice

        response = await self._client.audio.speech.create(
            model=self.config.tts_model,
            voice=target_voice,
            input=text,
            response_format=response_format,
            speed=speed,
        )

        if hasattr(response, "aread"):
            audio_bytes = await response.aread()
        elif hasattr(response, "content"):
            audio_bytes = response.content
        else:
            audio_bytes = bytes(response)

        return SpeechResult(
            audio_bytes=audio_bytes,
            format=response_format,
        )


def create_audio_adapter(config: Optional[AudioProviderConfig] = None) -> OpenAIAudioAdapter:
    """Factory creating an OpenAIAudioAdapter instance."""
    return OpenAIAudioAdapter(config=config)
