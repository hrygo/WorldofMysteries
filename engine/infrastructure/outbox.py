"""Transactional Outbox Interface (Invariant 9: Reliable asynchronous event propagation)."""
from typing import Protocol


class TransactionalOutboxProtocol(Protocol):
    """Guarantees reliable emission of domain events post-commit."""
