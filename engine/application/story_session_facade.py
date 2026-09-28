"""Public trusted first-turn facade composed from existing durable services."""
from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from contracts import InputMode, StorySession, StorySessionStatus
from domain.resolver import DeterministicOutcomeResolver

from .advice_action import AdviceActionError, AdviceActionIntentService
from .advice_commit import AdviceCommitError, AdviceCommitService
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
from .story_initialization import (
    StoryInitializationService,
    StorySessionBootstrap,
)
from .story_public_view import (
    PublicStorySessionView,
    StoryPublicViewError,
    StoryPublicViewProjector,
)
from .story_session_open import (
    OpenStorySessionCommand,
    StorySessionOpenService,
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


class StoryFacadeError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class StoryEntryView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    scenario_id: str = "golden_001"
    mode: str = "golden_deterministic"
    supported_advice: list[str]
    observed_store_revision: int = Field(ge=0)
    session: PublicStorySessionView | None = None
    pending_input_turn_id: str | None = Field(default=None, min_length=1, max_length=256)


class StoryOpenView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    session: PublicStorySessionView
    opened_store_revision: int = Field(ge=0)
    replayed: bool


class StorySessionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    session: PublicStorySessionView


class AdviceReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_turn_id: str = Field(min_length=1, max_length=256)
    session_id: str = Field(min_length=1, max_length=256)
    turn_id: str = Field(min_length=1, max_length=256)
    status: str
    committed_store_revision: int | None = Field(default=None, ge=0)
    committed_story_revision: int | None = Field(default=None, ge=0)


class TurnDeliveryView(BaseModel):
    """Post-COMMIT expression state for one committed turn.

    ``unavailable`` never means the turn was lost.  The Domain commit already
    succeeded and stays durable; only the audible rendering is missing, which is
    exactly the separation invariant 9 requires.
    """

    model_config = ConfigDict(extra="forbid")

    state: Literal["ready", "unavailable"]
    narrative_block_id: str | None = None
    speech_unit_id: str | None = None
    spoken_text: str | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=128)
    # The exact sealed render recipe. The App replays it verbatim into
    # ``voice.render``; the Engine rejects any drift, so a client can never
    # choose the voice, the revision or the speed for a committed turn.
    render_recipe: dict[str, object] | None = None


class AdviceSubmitView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    receipt: AdviceReceiptView
    session: PublicStorySessionView
    replayed: bool
    delivery: TurnDeliveryView | None = None


class AdviceGetView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    found: bool
    receipt: AdviceReceiptView | None = None
    session: PublicStorySessionView | None = None
    replayed: bool


@dataclass(frozen=True, slots=True)
class SubmitAdviceCommand:
    session_id: str
    input_turn_id: str
    raw_input: str
    expected_story_revision: int
    expected_store_revision: int
    request_id: str
    trace_id: str
    # ``text`` is the historical default.  ``voice`` marks a SpeechRail
    # transcript; the durable receipt records the mode so a replayed turn can
    # never be reinterpreted as typed text.
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


@dataclass(frozen=True, slots=True)
class StoryEntrySnapshot:
    supported_advice: tuple[str, ...]
    observed_store_revision: int
    session: StorySessionSnapshotRecord | None = None
    pending_input_turn_id: str | None = None


class StorySessionQueryPort(Protocol):
    async def entry(self, scenario_id: str) -> StoryEntrySnapshot: ...

    async def session(self, session_id: str) -> StorySessionSnapshotRecord: ...

    async def input(
        self, session_id: str, input_turn_id: str
    ) -> StoredInputRecord | None: ...


AfterCommitHook = Callable[
    [SubmitAdviceCommand, StoryTurnCommitResult, PublicStorySessionView],
    Awaitable[TurnDeliveryView],
]


class _SessionReadAdapter:
    def __init__(self, query: StorySessionQueryPort) -> None:
        self._query = query

    async def load_session(self, session_id: str) -> StorySession:
        return (await self._query.session(session_id)).session


class StorySessionFacade:
    def __init__(
        self,
        *,
        initialization: StoryInitializationService,
        open_sessions: StorySessionOpenService,
        query: StorySessionQueryPort,
        intake: DurableTurnIntakePort,
        advice: DurableAdvicePort,
        story: object,
        scenario: ScenarioPolicyPort,
        workers: TurnWorkerFactory,
        projector: StoryPublicViewProjector | None = None,
        after_commit: AfterCommitHook | None = None,
        context_bindings: TurnContextBindingPort | None = None,
    ) -> None:
        self._initialization = initialization
        self._open_sessions = open_sessions
        self._query = query
        self._intake = intake
        self._advice = advice
        self._story = story
        self._scenario = scenario
        self._workers = workers
        self._projector = projector or StoryPublicViewProjector()
        self._after_commit = after_commit
        self._context_bindings = context_bindings
        self._session_read = _SessionReadAdapter(query)
        self._locks: dict[str, asyncio.Lock] = {}

    async def entry(self, scenario_id: str) -> StoryEntryView:
        snapshot = await self._query.entry(scenario_id)
        session_view = None
        supported_advice = list(snapshot.supported_advice)
        if snapshot.session is not None:
            record = snapshot.session
            self._ensure_scenario_identity(record.bootstrap)
            policy_decision = self._decision(record.session)
            session_view = self._project_record(
                record,
                pending=record.pending_input_turn_id is not None
                or snapshot.pending_input_turn_id is not None,
                policy_decision=policy_decision,
            )
            if policy_decision.allowed_to_submit:
                expected = self._scenario.expected_input(
                    record.bootstrap, record.session
                )
                supported_advice = [] if expected is None else [expected]
            else:
                supported_advice = []
        elif snapshot.pending_input_turn_id is not None:
            raise StoryFacadeError("recovery_required")
        return StoryEntryView(
            scenario_id=scenario_id,
            supported_advice=supported_advice,
            observed_store_revision=snapshot.observed_store_revision,
            session=session_view,
            pending_input_turn_id=snapshot.pending_input_turn_id,
        )

    async def open(
        self,
        *,
        scenario_id: str,
        open_request_id: str,
        expected_store_revision: int,
        request_id: str,
        trace_id: str,
    ) -> StoryOpenView:
        _request_identity(open_request_id, "invalid_open_identity")
        _request_identity(request_id, "invalid_request_identity")
        _request_identity(trace_id, "invalid_trace_identity")
        _revision(expected_store_revision, "invalid_store_expected_revision", upper=False)

        initialized = await self._initialization.initialize(
            scenario_id=scenario_id,
            open_request_id=open_request_id,
        )
        self._ensure_scenario_identity(initialized.bootstrap)
        result = await self._open_sessions.open(
            OpenStorySessionCommand(
                initial_session=initialized.initial_session,
                open_request_id=open_request_id,
                store_expected_revision=expected_store_revision,
                request_id=request_id,
                trace_id=trace_id,
                bootstrap=initialized.bootstrap,
            )
        )
        snapshot = await self._query.session(result.snapshot.session.id)
        return StoryOpenView(
            session=self._project_record(snapshot, pending=False),
            opened_store_revision=result.opened_store_revision,
            replayed=result.replayed,
        )

    async def get(self, session_id: str) -> StorySessionView:
        _request_identity(session_id, "invalid_session_id")
        snapshot = await self._query.session(session_id)
        return StorySessionView(
            session=self._project_record(
                snapshot,
                pending=snapshot.pending_input_turn_id is not None,
            )
        )

    async def submit(self, command: SubmitAdviceCommand) -> AdviceSubmitView:
        """Submit only the exact fixed input authorized by the scenario."""
        return await self._submit_turn(command, input_method="fixed")

    async def submit_live(self, command: SubmitAdviceCommand) -> AdviceSubmitView:
        """Submit whatever the player actually said, typed or spoken.

        A free utterance is accepted only when the configured worker factory
        declares a live-input capability. Scenario resolution and validation
        remain the same as for a fixed-input turn.
        """
        return await self._submit_turn(command, input_method="live")

    async def _submit_turn(
        self,
        command: SubmitAdviceCommand,
        *,
        input_method: Literal["fixed", "live"],
    ) -> AdviceSubmitView:
        _submit(command)
        async with self._lock(command.session_id):
            existing = await self._query.input(
                command.session_id,
                command.input_turn_id,
            )
            if existing is not None:
                self._validate_existing(command, existing)
                if existing.receipt.status is TurnInputStatus.COMMITTED:
                    if existing.committed_story_revision is None:
                        raise StoryFacadeError("committed_turn_missing_story_revision")
                    snapshot = await self._query.session(command.session_id)
                    return AdviceSubmitView(
                        receipt=_receipt_from_record(existing),
                        session=self._project_record(snapshot, pending=False),
                        replayed=True,
                    )
                if existing.receipt.status is TurnInputStatus.CANCELLED:
                    raise StoryFacadeError("input_turn_cancelled")
                snapshot = await self._query.session(command.session_id)
                if (
                    existing.receipt.base_revisions.story
                    != command.expected_story_revision
                ):
                    raise StoryFacadeError("revision_conflict")
                turn_number = snapshot.session.story_state.turn + 1
                self._validate_new(
                    command,
                    snapshot,
                    turn_number,
                    input_method=input_method,
                    resuming_input=True,
                )
            else:
                snapshot = await self._query.session(command.session_id)
                turn_number = snapshot.session.story_state.turn + 1
                self._validate_new(
                    command, snapshot, turn_number, input_method=input_method
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
                    raise StoryFacadeError("input_turn_cancelled")

            turn_number = snapshot.session.story_state.turn + 1
            policy = self._scenario.resolution_policy(
                snapshot.bootstrap, snapshot.session
            )
            validation_context = self._scenario.validation_context(
                snapshot.bootstrap, snapshot.session
            )
            allowed_signatures: tuple[ActionSignature, ...] = tuple(
                rule.signature for rule in policy.rules
            )
            interpretation = PlayerAdviceInterpretationService(
                durable=self._advice,
                interpreter=self._workers.interpreter_for(
                    snapshot.bootstrap, turn_number
                ),
            )
            proposal = AdviceActionIntentService(
                durable=self._advice,
                sessions=self._session_read,
                proposer=self._workers.proposer_for(
                    snapshot.bootstrap, turn_number, allowed_signatures
                ),
                context_bindings=self._context_bindings,
            )
            commit = AdviceCommitService(
                durable=self._advice,
                proposal=proposal,
                story=self._story,
                resolver=DeterministicOutcomeResolver(),
                domain_context=lambda _number: validation_context,
                context_bindings=self._context_bindings,
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
                    raise StoryFacadeError("revision_conflict") from exc
                if exc.code == "legacy_context_unbound":
                    raise StoryFacadeError("recovery_required") from exc
                raise
            if result.turn.committed_story_revision is None:
                raise StoryFacadeError("committed_turn_missing_story_revision")
            snapshot = await self._query.session(command.session_id)
            view = AdviceSubmitView(
                receipt=AdviceReceiptView(
                    input_turn_id=command.input_turn_id,
                    session_id=command.session_id,
                    turn_id=result.turn.id,
                    status="committed",
                    committed_store_revision=result.store_revision,
                    committed_story_revision=result.turn.committed_story_revision,
                ),
                session=self._project_record(snapshot, pending=False),
                replayed=result.replayed,
            )
            if self._after_commit is not None and not result.replayed:
                view = view.model_copy(
                    update={
                        "delivery": await self._after_commit(command, result, view.session)
                    }
                )
            return view

    async def get_advice(
        self, session_id: str, input_turn_id: str
    ) -> AdviceGetView:
        _request_identity(session_id, "invalid_session_id")
        _request_identity(input_turn_id, "invalid_input_turn_id")
        record = await self._query.input(session_id, input_turn_id)
        if record is None:
            return AdviceGetView(found=False, replayed=False)
        if record.receipt.session_id != session_id:
            raise StoryFacadeError("authorization_denied")
        snapshot = await self._query.session(session_id)
        return AdviceGetView(
            found=True,
            receipt=_receipt_from_record(record),
            session=self._project_record(
                snapshot,
                pending=record.receipt.status is TurnInputStatus.RECEIVED,
            ),
            replayed=True,
        )

    def _project_record(
        self,
        record: StorySessionSnapshotRecord,
        *,
        pending: bool,
        policy_decision: TurnPolicyDecision | None = None,
    ) -> PublicStorySessionView:
        self._ensure_scenario_identity(record.bootstrap)
        try:
            return self._projector.project(
                session=record.session,
                bootstrap=record.bootstrap,
                observed_store_revision=record.observed_store_revision,
                has_pending_input=pending,
                policy_decision=(
                    policy_decision
                    if policy_decision is not None
                    else self._decision(record.session)
                ),
            )
        except StoryPublicViewError as exc:
            raise StoryFacadeError(exc.code) from None

    @staticmethod
    def _validate_existing(
        command: SubmitAdviceCommand, record: StoredInputRecord
    ) -> None:
        receipt = record.receipt
        if receipt.session_id != command.session_id:
            raise StoryFacadeError("authorization_denied")
        if (
            receipt.input_sha256
            != hashlib.sha256(command.raw_input.encode("utf-8")).hexdigest()
            or receipt.input_mode is not command.input_mode
            or receipt.public_expected_store_revision
            != command.expected_store_revision
            or receipt.base_revisions.story != command.expected_story_revision
        ):
            raise StoryFacadeError("input_turn_identity_conflict")

    def _validate_new(
        self,
        command: SubmitAdviceCommand,
        snapshot: StorySessionSnapshotRecord,
        turn_number: int,
        *,
        input_method: Literal["fixed", "live"],
        resuming_input: bool = False,
    ) -> None:
        session = snapshot.session
        self._ensure_scenario_identity(snapshot.bootstrap)
        if session.id != command.session_id:
            raise StoryFacadeError("authorization_denied")
        if session.status is not StorySessionStatus.ACTIVE:
            raise StoryFacadeError("story_session_not_active")
        if snapshot.pending_input_turn_id is not None and not (
            resuming_input
            and snapshot.pending_input_turn_id == command.input_turn_id
        ):
            raise StoryFacadeError("pending_turn_exists")
        if (
            turn_number != session.story_state.turn + 1
            or session.story_state.revision != turn_number - 1
        ):
            raise StoryFacadeError("iteration_limit_reached")
        if (
            command.expected_story_revision != session.story_state.revision
            or command.expected_store_revision != snapshot.observed_store_revision
        ):
            raise StoryFacadeError("revision_conflict")
        decision = self._decision(session)
        if not decision.allowed_to_submit:
            raise StoryFacadeError(
                decision.reason or "scenario_submission_not_allowed"
            )
        if input_method == "live":
            if not self._workers.supports_live_input:
                raise StoryFacadeError("live_worker_unavailable")
            return
        supported = self._scenario.expected_input(
            snapshot.bootstrap, session
        )
        if supported is None:
            raise StoryFacadeError("fixed_input_unsupported")
        if command.raw_input != supported:
            raise StoryFacadeError("deterministic_input_unsupported")

    def _decision(self, session: StorySession) -> TurnPolicyDecision:
        committed_evidence = frozenset(
            session.story_state.discovered_clue_ids or ()
        )
        return self._scenario.decision(session, committed_evidence)

    def _ensure_scenario_identity(self, bootstrap: StorySessionBootstrap) -> None:
        try:
            identity = self._scenario.identity(bootstrap)
        except ScenarioPolicyError as exc:
            raise StoryFacadeError(exc.code) from None
        if not isinstance(identity, ScenarioIdentity) or identity != ScenarioIdentity(
            scenario_id=bootstrap.scenario_id,
            content_digest=bootstrap.content_digest,
            rules_revision=bootstrap.policy_version,
        ):
            raise StoryFacadeError("scenario_identity_mismatch")

    def _lock(self, session_id: str) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())


def _receipt_from_record(record: StoredInputRecord) -> AdviceReceiptView:
    receipt = record.receipt
    if receipt.status is TurnInputStatus.COMMITTED:
        if (
            receipt.committed_world_revision is None
            or record.committed_story_revision is None
        ):
            raise StoryFacadeError("committed_turn_missing_revision")
        return AdviceReceiptView(
            input_turn_id=receipt.input_turn_id,
            session_id=receipt.session_id,
            turn_id=receipt.turn_id,
            status="committed",
            committed_store_revision=receipt.committed_world_revision,
            committed_story_revision=record.committed_story_revision,
        )
    return AdviceReceiptView(
        input_turn_id=receipt.input_turn_id,
        session_id=receipt.session_id,
        turn_id=receipt.turn_id,
        status=receipt.status.value,
    )


def _submit(command: SubmitAdviceCommand) -> None:
    if not isinstance(command, SubmitAdviceCommand):
        raise StoryFacadeError("invalid_submit_command")
    _request_identity(command.session_id, "invalid_session_id")
    _request_identity(command.input_turn_id, "invalid_input_turn_id")
    _request_identity(command.request_id, "invalid_request_identity")
    _request_identity(command.trace_id, "invalid_trace_identity")
    if (
        not isinstance(command.raw_input, str)
        or not command.raw_input.strip()
        or len(command.raw_input) > 16_384
        or "\x00" in command.raw_input
    ):
        raise StoryFacadeError("deterministic_input_unsupported")
    _revision(command.expected_story_revision, "invalid_story_revision", upper=False)
    _revision(command.expected_store_revision, "invalid_store_revision", upper=False)


def _request_identity(value: object, code: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 256
        or "\x00" in value
    ):
        raise StoryFacadeError(code)
    return value


def _revision(value: object, code: str, *, upper: bool) -> int:
    maximum = (2**63 - 1) if upper else (2**63 - 2)
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= maximum
    ):
        raise StoryFacadeError(code)
    return value
