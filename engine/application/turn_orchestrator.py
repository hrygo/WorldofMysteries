"""Application orchestration for one durable Story turn.

This is the sole owner of pre-COMMIT turn ordering and per-session admission.
Concrete persistence and worker implementations remain behind the injected
application ports; the facade only normalizes commands and projects results.
"""
from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol

from contracts import InputMode, StorySession, StorySessionStatus
from domain.resolver import DeterministicOutcomeResolver

from .advice_action import AdviceActionError, AdviceActionIntentService
from .advice_commit import (
    AdviceCommitError,
    AdviceCommitService,
    StoryTurnCommitPort,
)
from .advice_interpretation import (
    AdviceInterpretationError,
    DurableAdvicePort,
    PlayerAdviceInterpretationService,
)
from .scenario_policy import (
    ActionSignature,
    ScenarioIdentity,
    ScenarioPolicyError,
    ScenarioPolicyPort,
    TurnPolicyDecision,
    TurnWorkerFactory,
)
from .story_initialization import StorySessionBootstrap
from .story_public_view import (
    PublicStorySessionView,
    StoryPublicProjectionFacts,
    StoryPublicViewError,
)
from .story_turn_commit import StoryTurnCommitResult
from .turn_context_binding import TurnContextBindingPort
from .turn_input import (
    DurableTurnIntakePort,
    FinalizedStoryInput,
    StoryTurnInputService,
    TurnInputReceipt,
    TurnInputStatus,
)


class TurnOrchestrationError(RuntimeError):
    """Stable application error raised while admitting or executing a turn."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SubmissionPolicy(StrEnum):
    FIXED = "fixed"
    LIVE = "live"


@dataclass(frozen=True, slots=True)
class SubmitAdviceCommand:
    session_id: str
    input_turn_id: str
    raw_input: str
    expected_story_revision: int
    expected_store_revision: int
    request_id: str
    trace_id: str
    input_mode: InputMode = InputMode.TEXT


@dataclass(frozen=True, slots=True)
class StorySessionSnapshotRecord:
    session: StorySession
    bootstrap: StorySessionBootstrap
    observed_store_revision: int
    pending_input_turn_id: str | None = None


@dataclass(frozen=True, slots=True)
class StoredInputRecord:
    receipt: TurnInputReceipt
    committed_story_revision: int | None


class StorySessionQueryPort(Protocol):
    async def entry(self, scenario_id: str): ...

    async def session(self, session_id: str) -> StorySessionSnapshotRecord: ...

    async def input(
        self, session_id: str, input_turn_id: str
    ) -> StoredInputRecord | None: ...


@dataclass(frozen=True, slots=True)
class CommittedTurnResult:
    """Internal commit receipt, trusted session, and safe projection facts."""

    input_turn_id: str
    session_id: str
    turn_id: str
    committed_store_revision: int
    committed_story_revision: int
    session: StorySession
    observed_store_revision: int
    projection_facts: StoryPublicProjectionFacts
    policy_decision: TurnPolicyDecision
    replayed: bool
    delivery: object | None = None


AfterCommitHook = Callable[
    [SubmitAdviceCommand, StoryTurnCommitResult, PublicStorySessionView | None],
    Awaitable[object],
]


class _SessionReadAdapter:
    def __init__(self, query: StorySessionQueryPort) -> None:
        self._query = query

    async def load_session(self, session_id: str) -> StorySession:
        return (await self._query.session(session_id)).session


class TurnOrchestrator:
    """Execute the durable input → proposal → resolver → COMMIT sequence."""

    def __init__(
        self,
        *,
        sessions: StorySessionQueryPort,
        intake: DurableTurnIntakePort,
        advice: DurableAdvicePort,
        story: StoryTurnCommitPort,
        scenario: ScenarioPolicyPort,
        workers: TurnWorkerFactory,
        context: TurnContextBindingPort | None = None,
        work: AfterCommitHook | None = None,
    ) -> None:
        self._sessions = sessions
        self._intake = intake
        self._advice = advice
        self._story = story
        self._scenario = scenario
        self._workers = workers
        self._context = context
        self._work = work
        self._session_read = _SessionReadAdapter(sessions)
        self._locks: dict[str, asyncio.Lock] = {}

    async def execute(
        self,
        command: SubmitAdviceCommand,
        submission_policy: SubmissionPolicy,
    ) -> CommittedTurnResult:
        if not isinstance(submission_policy, SubmissionPolicy):
            raise TurnOrchestrationError("invalid_submission_policy")

        async with self._lock(command.session_id):
            result, commit_result = await self._execute_admitted(
                command,
                submission_policy,
            )

        # Expression and audio are downstream of an already durable commit.
        # They run outside the admission lock and can never roll the commit back.
        if (
            commit_result is not None
            and self._work is not None
            and not result.replayed
        ):
            delivery = await self._work(command, commit_result, None)
            result = replace(result, delivery=delivery)
        return result

    async def _execute_admitted(
        self,
        command: SubmitAdviceCommand,
        submission_policy: SubmissionPolicy,
    ) -> tuple[CommittedTurnResult, StoryTurnCommitResult | None]:
        existing = await self._sessions.input(
            command.session_id,
            command.input_turn_id,
        )
        if existing is not None:
            self._validate_existing(command, existing)
            if existing.receipt.status is TurnInputStatus.COMMITTED:
                if existing.committed_story_revision is None:
                    raise TurnOrchestrationError(
                        "committed_turn_missing_story_revision"
                    )
                snapshot = await self._sessions.session(command.session_id)
                self._ensure_scenario_identity(snapshot.bootstrap)
                return (
                    CommittedTurnResult(
                        input_turn_id=command.input_turn_id,
                        session_id=command.session_id,
                        turn_id=existing.receipt.turn_id,
                        committed_store_revision=_required_revision(
                            existing.receipt.committed_world_revision,
                            "committed_turn_missing_revision",
                        ),
                        committed_story_revision=existing.committed_story_revision,
                        session=snapshot.session,
                        observed_store_revision=snapshot.observed_store_revision,
                        projection_facts=self._projection_facts(snapshot.bootstrap),
                        policy_decision=self._decision(snapshot.session),
                        replayed=True,
                    ),
                    None,
                )
            if existing.receipt.status is TurnInputStatus.CANCELLED:
                raise TurnOrchestrationError("input_turn_cancelled")
            snapshot = await self._sessions.session(command.session_id)
            if (
                existing.receipt.base_revisions.story
                != command.expected_story_revision
            ):
                raise TurnOrchestrationError("revision_conflict")
            turn_number = snapshot.session.story_state.turn + 1
            self._validate_new(
                command,
                snapshot,
                turn_number,
                submission_policy=submission_policy,
                resuming_input=True,
            )
        else:
            snapshot = await self._sessions.session(command.session_id)
            turn_number = snapshot.session.story_state.turn + 1
            self._validate_new(
                command,
                snapshot,
                turn_number,
                submission_policy=submission_policy,
            )
            receipt = await StoryTurnInputService(
                sessions=self._session_read,
                intake=self._intake,
            ).receive(
                FinalizedStoryInput(
                    input_turn_id=command.input_turn_id,
                    session_id=command.session_id,
                    input_mode=command.input_mode,
                    raw_input=command.raw_input,
                    public_expected_store_revision=command.expected_store_revision,
                )
            )
            if receipt.status is TurnInputStatus.CANCELLED:
                raise TurnOrchestrationError("input_turn_cancelled")

        turn_number = snapshot.session.story_state.turn + 1
        policy = self._scenario.resolution_policy(
            snapshot.bootstrap,
            snapshot.session,
        )
        validation_context = self._scenario.validation_context(
            snapshot.bootstrap,
            snapshot.session,
        )
        allowed_signatures: tuple[ActionSignature, ...] = tuple(
            rule.signature for rule in policy.rules
        )
        interpretation = PlayerAdviceInterpretationService(
            durable=self._advice,
            interpreter=self._workers.interpreter_for(
                snapshot.bootstrap,
                turn_number,
            ),
        )
        proposal = AdviceActionIntentService(
            durable=self._advice,
            sessions=self._session_read,
            proposer=self._workers.proposer_for(
                snapshot.bootstrap,
                turn_number,
                allowed_signatures,
            ),
            context_bindings=self._context,
        )
        commit = AdviceCommitService(
            durable=self._advice,
            proposal=proposal,
            story=self._story,
            resolver=DeterministicOutcomeResolver(),
            domain_context=lambda _number: validation_context,
            context_bindings=self._context,
        )
        try:
            await interpretation.interpret(command.input_turn_id)
            result = await commit.commit(
                command.input_turn_id,
                policy=policy,
                store_expected_revision=command.expected_store_revision,
                request_id=command.request_id,
                trace_id=command.trace_id,
            )
        except (AdviceInterpretationError, AdviceActionError, AdviceCommitError) as exc:
            if exc.code in {"context_stale", "revision_conflict"}:
                raise TurnOrchestrationError("revision_conflict") from exc
            if exc.code == "legacy_context_unbound":
                raise TurnOrchestrationError("recovery_required") from exc
            raise

        if result.turn.committed_story_revision is None:
            raise TurnOrchestrationError("committed_turn_missing_story_revision")
        committed_snapshot = await self._sessions.session(command.session_id)
        self._ensure_scenario_identity(committed_snapshot.bootstrap)
        return (
            CommittedTurnResult(
                input_turn_id=command.input_turn_id,
                session_id=command.session_id,
                turn_id=result.turn.id,
                committed_store_revision=result.store_revision,
                committed_story_revision=result.turn.committed_story_revision,
                session=committed_snapshot.session,
                observed_store_revision=(
                    committed_snapshot.observed_store_revision
                ),
                projection_facts=self._projection_facts(
                    committed_snapshot.bootstrap
                ),
                policy_decision=self._decision(committed_snapshot.session),
                replayed=result.replayed,
            ),
            result,
        )

    @staticmethod
    def _validate_existing(
        command: SubmitAdviceCommand,
        record: StoredInputRecord,
    ) -> None:
        receipt = record.receipt
        if receipt.session_id != command.session_id:
            raise TurnOrchestrationError("authorization_denied")
        if (
            receipt.input_sha256
            != hashlib.sha256(command.raw_input.encode("utf-8")).hexdigest()
            or receipt.input_mode is not command.input_mode
            or receipt.public_expected_store_revision
            != command.expected_store_revision
            or receipt.base_revisions.story != command.expected_story_revision
        ):
            raise TurnOrchestrationError("input_turn_identity_conflict")

    def _validate_new(
        self,
        command: SubmitAdviceCommand,
        snapshot: StorySessionSnapshotRecord,
        turn_number: int,
        *,
        submission_policy: SubmissionPolicy,
        resuming_input: bool = False,
    ) -> None:
        session = snapshot.session
        self._ensure_scenario_identity(snapshot.bootstrap)
        if session.id != command.session_id:
            raise TurnOrchestrationError("authorization_denied")
        if session.status is not StorySessionStatus.ACTIVE:
            raise TurnOrchestrationError("story_session_not_active")
        if snapshot.pending_input_turn_id is not None and not (
            resuming_input
            and snapshot.pending_input_turn_id == command.input_turn_id
        ):
            raise TurnOrchestrationError("pending_turn_exists")
        if (
            turn_number != session.story_state.turn + 1
            or session.story_state.revision != turn_number - 1
        ):
            raise TurnOrchestrationError("iteration_limit_reached")
        if (
            command.expected_story_revision != session.story_state.revision
            or command.expected_store_revision != snapshot.observed_store_revision
        ):
            raise TurnOrchestrationError("revision_conflict")
        decision = self._decision(session)
        if not decision.allowed_to_submit:
            raise TurnOrchestrationError(
                decision.reason or "scenario_submission_not_allowed"
            )
        if submission_policy is SubmissionPolicy.LIVE:
            if not self._workers.supports_live_input:
                raise TurnOrchestrationError("live_worker_unavailable")
            return
        supported = self._scenario.expected_input(snapshot.bootstrap, session)
        if supported is None:
            raise TurnOrchestrationError("fixed_input_unsupported")
        if command.raw_input != supported:
            raise TurnOrchestrationError("deterministic_input_unsupported")

    def _decision(self, session: StorySession) -> TurnPolicyDecision:
        committed_evidence = frozenset(
            session.story_state.discovered_clue_ids or ()
        )
        return self._scenario.decision(session, committed_evidence)

    def _ensure_scenario_identity(self, bootstrap: StorySessionBootstrap) -> None:
        try:
            identity = self._scenario.identity(bootstrap)
        except ScenarioPolicyError as exc:
            raise TurnOrchestrationError(exc.code) from None
        if not isinstance(identity, ScenarioIdentity) or identity != ScenarioIdentity(
            scenario_id=bootstrap.scenario_id,
            content_digest=bootstrap.content_digest,
            rules_revision=bootstrap.policy_version,
        ):
            raise TurnOrchestrationError("scenario_identity_mismatch")

    @staticmethod
    def _projection_facts(
        bootstrap: StorySessionBootstrap,
    ) -> StoryPublicProjectionFacts:
        try:
            return StoryPublicProjectionFacts.from_bootstrap(bootstrap)
        except StoryPublicViewError as exc:
            raise TurnOrchestrationError(exc.code) from None

    def _lock(self, session_id: str) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())


def _required_revision(value: int | None, error_code: str) -> int:
    if value is None:
        raise TurnOrchestrationError(error_code)
    return value


__all__ = [
    "CommittedTurnResult",
    "StoredInputRecord",
    "StorySessionQueryPort",
    "StorySessionSnapshotRecord",
    "SubmissionPolicy",
    "SubmitAdviceCommand",
    "TurnOrchestrationError",
    "TurnOrchestrator",
]
