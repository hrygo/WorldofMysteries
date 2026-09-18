"""Session Orchestrator interfaces. Coordinates user input, AI reasoning and commit.

The concrete orchestrator can bind GameplayContextCoordinator as its read-only AI
context port.  Domain transactions remain outside the context/cache subsystem.
"""
from typing import Protocol

from .gameplay_context import GameplayCall, PreparedGameplayContext


class GameplayContextPort(Protocol):
    async def prepare(self, call: GameplayCall) -> PreparedGameplayContext: ...


class SessionOrchestratorProtocol(Protocol):
    """End-to-end turn control plane; context preparation is a pre-model read stage."""
    async def prepare_ai_context(self, call: GameplayCall) -> PreparedGameplayContext: ...
