"""Public trusted first-turn facade composed from existing durable services."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from contracts import InputMode, StorySession, StorySessionStatus
from domain.resolution_policy import ResolutionPolicy, ResolutionRule, StoryEffect
from domain.resolver import DeterministicOutcomeResolver

from .advice_action import AdviceActionIntentService
from .advice_commit import AdviceCommitService
from .advice_interpretation import (
    DurableAdvicePort,
    PlayerAdviceInterpretationService,
)
from .story_initialization import (
    GOLDEN_SCENARIO_ID,
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


class AdviceSubmitView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    receipt: AdviceReceiptView
    session: PublicStorySessionView
    replayed: bool


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


class StoryFirstTurnPort(Protocol):
    def interpreter_for(self, bootstrap: StorySessionBootstrap): ...

    def proposer_for(self, bootstrap: StorySessionBootstrap): ...


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
        first_turn: StoryFirstTurnPort,
        projector: StoryPublicViewProjector | None = None,
    ) -> None:
        self._initialization = initialization
        self._open_sessions = open_sessions
        self._query = query
        self._intake = intake
        self._advice = advice
        self._story = story
        self._first_turn = first_turn
        self._projector = projector or StoryPublicViewProjector()
        self._session_read = _SessionReadAdapter(query)
        self._locks: dict[str, asyncio.Lock] = {}

    async def entry(self, scenario_id: str) -> StoryEntryView:
        _scenario(scenario_id)
        snapshot = await self._query.entry(scenario_id)
        session_view = None
        if snapshot.session is not None:
            session_view = self._project_record(
                snapshot.session,
                pending=snapshot.session.pending_input_turn_id is not None
                or snapshot.pending_input_turn_id is not None,
            )
        elif snapshot.pending_input_turn_id is not None:
            raise StoryFacadeError("recovery_required")
        return StoryEntryView(
            scenario_id=scenario_id,
            supported_advice=list(snapshot.supported_advice),
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
        _scenario(scenario_id)
        _request_identity(open_request_id, "invalid_open_identity")
        _request_identity(request_id, "invalid_request_identity")
        _request_identity(trace_id, "invalid_trace_identity")
        _revision(expected_store_revision, "invalid_store_expected_revision", upper=False)

        initialized = await self._initialization.initialize(
            scenario_id=scenario_id,
            open_request_id=open_request_id,
        )
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
            else:
                snapshot = await self._query.session(command.session_id)
                self._validate_new(command, snapshot)
                receipt = await StoryTurnInputService(
                    sessions=self._session_read,
                    intake=self._intake,
                ).receive(
                    FinalizedStoryInput(
                        input_turn_id=command.input_turn_id,
                        session_id=command.session_id,
                        input_mode=InputMode.TEXT,
                        raw_input=command.raw_input,
                        public_expected_store_revision=command.expected_store_revision,
                    )
                )
                if receipt.status is TurnInputStatus.CANCELLED:
                    raise StoryFacadeError("input_turn_cancelled")

            interpretation = PlayerAdviceInterpretationService(
                durable=self._advice,
                interpreter=self._first_turn.interpreter_for(snapshot.bootstrap),
            )
            proposal = AdviceActionIntentService(
                durable=self._advice,
                sessions=self._session_read,
                proposer=self._first_turn.proposer_for(snapshot.bootstrap),
            )
            commit = AdviceCommitService(
                durable=self._advice,
                proposal=proposal,
                story=self._story,
                resolver=DeterministicOutcomeResolver(),
            )
            await interpretation.interpret(command.input_turn_id)
            result = await commit.commit(
                command.input_turn_id,
                policy=_opening_policy(snapshot.bootstrap),
                store_expected_revision=command.expected_store_revision,
                request_id=command.request_id,
                trace_id=command.trace_id,
            )
            if result.turn.committed_story_revision is None:
                raise StoryFacadeError("committed_turn_missing_story_revision")
            snapshot = await self._query.session(command.session_id)
            return AdviceSubmitView(
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
    ) -> PublicStorySessionView:
        try:
            return self._projector.project(
                session=record.session,
                bootstrap=record.bootstrap,
                observed_store_revision=record.observed_store_revision,
                has_pending_input=pending,
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
            or receipt.input_mode.value != "text"
            or receipt.public_expected_store_revision
            != command.expected_store_revision
            or receipt.base_revisions.story != command.expected_story_revision
        ):
            raise StoryFacadeError("input_turn_identity_conflict")

    @staticmethod
    def _validate_new(
        command: SubmitAdviceCommand,
        snapshot: StorySessionSnapshotRecord,
    ) -> None:
        session = snapshot.session
        if session.id != command.session_id:
            raise StoryFacadeError("authorization_denied")
        if session.status is not StorySessionStatus.ACTIVE:
            raise StoryFacadeError("story_session_not_active")
        if snapshot.pending_input_turn_id is not None:
            raise StoryFacadeError("pending_turn_exists")
        if session.story_state.turn != 0 or session.story_state.revision != 0:
            raise StoryFacadeError("iteration_limit_reached")
        if (
            command.expected_story_revision != session.story_state.revision
            or command.expected_store_revision != snapshot.observed_store_revision
        ):
            raise StoryFacadeError("revision_conflict")
        supported = snapshot.bootstrap.advice_template["raw_input"]
        if command.raw_input != supported:
            raise StoryFacadeError("deterministic_input_unsupported")

    def _lock(self, session_id: str) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())


def _opening_policy(bootstrap: StorySessionBootstrap):
    return ResolutionPolicy.from_story_seed(
        bootstrap.seed,
        [
            ResolutionRule(
                rule_id="observe-morris-reaction",
                intent="observe_subject",
                action_types=("continue_conversation",),
                effect=StoryEffect(
                    outcome="partial_success",
                    clue_ids_add=("clue_doctor_pause",),
                    pressure_delta=(("doctor_suspicion", 0),),
                ),
                evidence_ids=("policy.golden001.opening",),
            )
        ],
        policy_id="golden001-opening-policy",
    )


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


def _scenario(value: object) -> None:
    if value != GOLDEN_SCENARIO_ID:
        raise StoryFacadeError("unsupported_scenario")


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
