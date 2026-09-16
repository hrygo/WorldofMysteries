"""Story Engine Interface (Invariant 13 & 15: No background MMO sim, explicit worldline forks)."""
from typing import Protocol


class StoryEngineProtocol(Protocol):
    """Abstract protocol for story sessions, beat plans, and episode progression."""
