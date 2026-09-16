"""AgentScope Adapter Interface (Invariant 5: AI produces proposals only)."""
from typing import Protocol


class AgentScopeAdapterProtocol(Protocol):
    """Adapter bridging bounded AgentScope workers to produce typed domain proposals."""
