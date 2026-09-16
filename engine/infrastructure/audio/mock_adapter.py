"""Mock Audio Adapter for offline unit tests and deterministic Golden Scenarios."""

from typing import Optional
from domain.audio_voice import ASRProviderProtocol, ASRResult, SpeechResult, TTSProviderProtocol


class MockAudioAdapter(ASRProviderProtocol, TTSProviderProtocol):
    """Deterministic Mock Adapter for speech transcription and synthesis."""

    def __init__(
        self,
        mock_transcript: str = "这是一个已转录的玩家建议测试音频",
        mock_audio_bytes: bytes = b"MOCK_MP3_AUDIO_HEADER_AND_FRAMES",
    ) -> None:
        self.mock_transcript = mock_transcript
        self.mock_audio_bytes = mock_audio_bytes
        self.transcribe_call_count = 0
        self.synthesize_call_count = 0

    async def transcribe(
        self,
        audio_data: bytes,
        filename: str = "audio.wav",
        language: Optional[str] = None,
    ) -> ASRResult:
        self.transcribe_call_count += 1
        return ASRResult(
            transcript=self.mock_transcript,
            confidence=0.99,
            duration_seconds=2.5,
            language=language or "zh",
        )

    async def synthesize(
        self,
        text: str,
        voice: str,
        response_format: str = "mp3",
        speed: float = 1.0,
    ) -> SpeechResult:
        self.synthesize_call_count += 1
        return SpeechResult(
            audio_bytes=self.mock_audio_bytes,
            format=response_format,
            duration_seconds=float(len(text)) * 0.2,
        )
