"""Session Orchestrator Interface. Coordinates user input, AI reasoning, and state commit."""
from typing import Protocol


class SessionOrchestratorProtocol(Protocol):
    """Abstract orchestrator for end-to-end interactive narrative turns."""
