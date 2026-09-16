"""Database Manager Interface (Invariant 10 & 11: Multi-model SQLite architecture)."""
from typing import Protocol


class DatabaseManagerProtocol(Protocol):
    """
    Manages connections to:
    - canon.db: Read-only established history.
    - world.db: Authoritative mutable user world state.
    - retrieval.db: 100% idempotently rebuildable async projection.
    - runtime.db: Ephemeral session caches and execution logs.
    """
