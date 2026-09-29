"""Optional prepared-call seam for a future AgentScope integration.

The current ``StoryRuntime`` uses ``OpenAICompatibleChatTransport`` and does not
construct this adapter. A future host integration can supply its concrete
AgentScope model executor and credentials without leaking SDK types into the app.
This adapter accepts only an executor bound to the same provider profile and
forwards the exact prepared body once. It does not create an Agent, memory, tools,
or provider session. Actual SDK wiring still requires a fixed-version wire-capture
integration test; providing an arbitrary callable is not proof of AgentScope SDK
compatibility.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from application.context_plan import ContextError

from .gateway import ModelReply
from .prompt_cache_policy import ProviderProfile, WireRequest


class AgentScopeAdapterProtocol(Protocol):
    async def send(self, request: WireRequest) -> ModelReply: ...


class PreparedAgentScopeAdapter:
    def __init__(self, target: ProviderProfile,
                 executor: Callable[[WireRequest], Awaitable[ModelReply]]):
        self._target, self._executor = target, executor

    async def send(self, request: WireRequest) -> ModelReply:
        if request.target != self._target:
            raise ContextError("executor_target_mismatch")
        result = await self._executor(request)
        if not isinstance(result, ModelReply):
            raise ContextError("invalid_executor_reply")
        return result
