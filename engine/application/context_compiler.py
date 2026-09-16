"""Context Compiler Interface (Invariant 6 & 7: Semantic authorization precedes execution, zero leak)."""
from typing import Protocol


class ContextCompilerProtocol(Protocol):
    """Abstract compiler determining authorized context boundary for character reasoners."""
