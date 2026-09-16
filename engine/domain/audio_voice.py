"""Audio / Voice Engine Interface (Invariant 9: Narrative & audio strictly follow commit)."""
from typing import Protocol


class AudioVoiceEngineProtocol(Protocol):
    """Abstract protocol for narrative performance, TTS cue generation, and audio ducking states."""
