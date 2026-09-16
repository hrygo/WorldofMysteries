"""Lore Engine Interface (Invariant 3 & 10: Canon constrains history, user world never pollutes canon)."""
from typing import Protocol


class LoreEngineProtocol(Protocol):
    """Abstract protocol for Canon facts, pathway sequences, abilities, and spoiler boundaries."""
