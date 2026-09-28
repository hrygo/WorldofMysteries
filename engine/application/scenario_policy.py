"""Application ports for trusted scenario rules and per-turn workers.

Scenario rules are selected from the frozen bootstrap and committed Domain
state. Worker factories only create executors; they do not choose whether a
turn is allowed or what the resolver may commit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from contracts import StorySession
from domain.resolution_policy import ResolutionPolicy

from .advice_action import ActionIntentProposerPort
from .advice_interpretation import AdviceInterpreterPort
from .narrative_publication import NarrativeCompilerPort
from .story_initialization import StorySessionBootstrap
from .story_turn_commit import DomainValidationContext

type ActionSignature = tuple[str, tuple[str, ...]]
type CommittedEvidence = frozenset[str]

_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MAX_IDENTITY_TEXT = 256


class ScenarioPolicyError(RuntimeError):
    """A stored or requested scenario identity cannot be trusted."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ScenarioIdentity:
    """Trusted content and rule revision bound to an opened session."""

    scenario_id: str
    content_digest: str
    rules_revision: str

    def __post_init__(self) -> None:
        for value, field in (
            (self.scenario_id, "scenario_id"),
            (self.rules_revision, "rules_revision"),
        ):
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > _MAX_IDENTITY_TEXT
                or "\x00" in value
            ):
                raise ValueError(f"invalid_{field}")
        if (
            not isinstance(self.content_digest, str)
            or _HEX_DIGEST.fullmatch(self.content_digest) is None
        ):
            raise ValueError("invalid_content_digest")


@dataclass(frozen=True, slots=True)
class TurnPolicyDecision:
    """Scenario-owned decision about continuing or ending a StorySession."""

    allowed_to_submit: bool
    terminal: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.allowed_to_submit, bool) or not isinstance(
            self.terminal, bool
        ):
            raise TypeError("invalid_turn_policy_decision")
        if self.terminal and self.allowed_to_submit:
            raise ValueError("terminal_scenario_cannot_accept_input")
        if self.reason is not None and (
            not isinstance(self.reason, str)
            or not self.reason.strip()
            or len(self.reason) > _MAX_IDENTITY_TEXT
            or "\x00" in self.reason
        ):
            raise ValueError("invalid_turn_policy_reason")
        if self.terminal and self.reason is None:
            raise ValueError("terminal_scenario_requires_reason")


@dataclass(frozen=True, slots=True)
class FinalizationRecipe:
    """Scenario-owned names for its immutable finalization content."""

    episode_filename: str
    memory_filename: str

    def __post_init__(self) -> None:
        for filename, field in (
            (self.episode_filename, "episode_filename"),
            (self.memory_filename, "memory_filename"),
        ):
            if (
                not isinstance(filename, str)
                or not filename
                or len(filename) > 128
                or filename in {".", ".."}
                or "/" in filename
                or "\\" in filename
                or "\x00" in filename
            ):
                raise ValueError(f"invalid_{field}")


class ScenarioPolicyPort(Protocol):
    """Read-only rules selected for one trusted, frozen scenario."""

    def identity(self, bootstrap: StorySessionBootstrap) -> ScenarioIdentity: ...

    def decision(
        self,
        session: StorySession,
        committed_evidence: CommittedEvidence,
    ) -> TurnPolicyDecision: ...

    def expected_input(
        self,
        bootstrap: StorySessionBootstrap,
        session: StorySession,
    ) -> str | None: ...

    def resolution_policy(
        self,
        bootstrap: StorySessionBootstrap,
        session: StorySession,
    ) -> ResolutionPolicy: ...

    def validation_context(
        self,
        bootstrap: StorySessionBootstrap,
        session: StorySession,
    ) -> DomainValidationContext: ...

    def finalization_recipe(
        self,
        bootstrap: StorySessionBootstrap,
        committed_session: StorySession,
    ) -> FinalizationRecipe | None: ...


class TurnWorkerFactory(Protocol):
    """Creates executors without taking ownership of scenario decisions."""

    @property
    def supports_live_input(self) -> bool: ...

    def interpreter_for(
        self,
        bootstrap: StorySessionBootstrap,
        turn_number: int,
    ) -> AdviceInterpreterPort: ...

    def proposer_for(
        self,
        bootstrap: StorySessionBootstrap,
        turn_number: int,
        allowed_signatures: tuple[ActionSignature, ...],
    ) -> ActionIntentProposerPort: ...

    def narrative_compiler(
        self,
        bootstrap: StorySessionBootstrap,
    ) -> NarrativeCompilerPort | None: ...


__all__ = [
    "ActionSignature",
    "CommittedEvidence",
    "FinalizationRecipe",
    "ScenarioIdentity",
    "ScenarioPolicyError",
    "ScenarioPolicyPort",
    "TurnPolicyDecision",
    "TurnWorkerFactory",
]
