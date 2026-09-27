"""Authorized recall of a subject's committed Episode memory.

Semantic authorization comes first (invariant 7): a fresh Domain-issued grant is
built from the committed world.db Episode bundle for exactly one subject, and the
Context Compiler consumes only that pre-authorized set. Recall never widens
visibility from similarity or ranking, and a hidden fact that is not part of the
committed, subject-visible memory is never granted — so any attempt to smuggle it
into the request is rejected as unauthorized evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .context_compiler import CacheAwareContextCompiler
from .context_plan import (
    AuthorizationView,
    ContextError,
    ContextInput,
    ContextScope,
    Evidence,
    Layer,
    PromptPlan,
    WorkerProfile,
    canonical_json,
)


class EpisodeReadPort(Protocol):
    async def load_by_session(self, session_id: str): ...


@dataclass(frozen=True, slots=True)
class MemoryRecallCommand:
    session_id: str
    subject_id: str
    owner_id: str
    world_revision: int
    story_revision: int
    world_tick: int
    epoch_id: str
    policy_revision: str = "policy1"
    lineage_digest: str = "lineage1"
    consumer: str = "memory_distiller"
    prompt_revision: str = "v1"
    task_json: str = '{"task":"recall"}'
    request_id: str = "req-recall"


@dataclass(frozen=True, slots=True)
class AuthorizedRecallResult:
    plan: PromptPlan
    view: AuthorizationView
    evidence: tuple[Evidence, ...]


class EpisodeMemoryRecallService:
    """Assemble the authorized context for a subject from committed Episode memory."""

    _INSTRUCTIONS = "Recall only the authorized committed Episode memory for this subject."
    _SCHEMA = (
        '{"type":"object","properties":{"summary":{"type":"string"}},'
        '"required":["summary"],"additionalProperties":false}'
    )

    def __init__(self, *, episodes: EpisodeReadPort) -> None:
        self._episodes = episodes
        self._compiler = CacheAwareContextCompiler()

    async def recall(self, command: MemoryRecallCommand) -> AuthorizedRecallResult:
        if not isinstance(command, MemoryRecallCommand):
            raise ContextError("invalid_recall_command")
        bundle = await self._episodes.load_by_session(command.session_id)
        episode = bundle.episode
        # Only the requesting subject's own committed episode memories are eligible.
        memories = [
            memory
            for memory in bundle.artifacts.memories
            if memory.get("character_id") == command.subject_id
        ]
        scope = ContextScope(
            command.owner_id,
            episode.world_id,
            episode.worldline_id,
            command.consumer,
            command.subject_id,
            command.session_id,
            command.policy_revision,
            command.lineage_digest,
        )
        evidence = tuple(
            Evidence(
                source_id=memory["id"],
                source_revision=1,
                kind="memory",
                layer=Layer.HISTORY,
                content_json=canonical_json(memory),
                world_id=episode.world_id,
                worldline_id=episode.worldline_id,
                subject_id=memory["character_id"],
                committed_revision=bundle.store_revision,
                sequence=ordinal,
            )
            for ordinal, memory in enumerate(memories, start=1)
        )
        # Fresh Domain-issued eligible set: exactly the committed, subject-visible
        # memory and nothing else. No candidate can authorize itself.
        view = AuthorizationView(
            scope,
            command.world_revision,
            command.story_revision,
            command.world_tick,
            frozenset(item.fingerprint for item in evidence),
        )
        request = ContextInput(
            scope,
            command.world_revision,
            command.story_revision,
            command.epoch_id,
            evidence,
            command.task_json,
            command.request_id,
        )
        profile = WorkerProfile(
            command.consumer, command.prompt_revision, self._INSTRUCTIONS, self._SCHEMA
        )
        plan = self._compiler.compile(request, view, profile)
        return AuthorizedRecallResult(plan=plan, view=view, evidence=evidence)
