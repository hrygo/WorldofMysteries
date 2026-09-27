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
from .story_turn_commit import StoryTurnCommitResult
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


class StoryFirstTurnPort(Protocol):
    @property
    def max_turn(self) -> int: ...

    def expected_input(
        self, bootstrap: StorySessionBootstrap, turn_number: int
    ) -> str: ...

    def interpreter_for(
        self, bootstrap: StorySessionBootstrap, turn_number: int
    ): ...

    def proposer_for(
        self, bootstrap: StorySessionBootstrap, turn_number: int
    ): ...

    def policy_for_turn(
        self, bootstrap: StorySessionBootstrap, turn_number: int
    ): ...

    def domain_validation_for(
        self, bootstrap: StorySessionBootstrap, turn_number: int
    ): ...


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
        after_commit: AfterCommitHook | None = None,
    ) -> None:
        self._initialization = initialization
        self._open_sessions = open_sessions
        self._query = query
        self._intake = intake
        self._advice = advice
        self._story = story
        self._first_turn = first_turn
        self._projector = projector or StoryPublicViewProjector()
        self._after_commit = after_commit
        self._session_read = _SessionReadAdapter(query)
        self._locks: dict[str, asyncio.Lock] = {}

    async def entry(self, scenario_id: str) -> StoryEntryView:
        _scenario(scenario_id)
        snapshot = await self._query.entry(scenario_id)
        session_view = None
        supported_advice = list(snapshot.supported_advice)
        if snapshot.session is not None:
            session_view = self._project_record(
                snapshot.session,
                pending=snapshot.session.pending_input_turn_id is not None
                or snapshot.pending_input_turn_id is not None,
            )
            # Expose the current turn's expected advice so the client can drive
            # every remaining fixed turn (and can resume a pending submit with
            # the same advice). Once the final turn has committed, no further
            # advice is accepted.
            next_turn = snapshot.session.session.story_state.turn + 1
            if next_turn <= self._first_turn.max_turn:
                supported_advice = [
                    self._first_turn.expected_input(
                        snapshot.session.bootstrap, next_turn
                    )
                ]
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
        """Frozen Golden 001 submission: only the authored advice is accepted."""
        return await self._submit_turn(command, deterministic=True)

    async def submit_live(self, command: SubmitAdviceCommand) -> AdviceSubmitView:
        """Submit whatever the player actually said, typed or spoken.

        This is additive to :meth:`submit`, not a relaxation of it.  The frozen
        fixture keeps its exact-template guard; a live turn instead routes
        through the configured model workers, so a SpeechRail transcript becomes
        durable ``PlayerAdvice`` on the same pre-COMMIT path.
        """
        return await self._submit_turn(command, deterministic=False)

    async def _submit_turn(
        self, command: SubmitAdviceCommand, *, deterministic: bool
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
            else:
                snapshot = await self._query.session(command.session_id)
                turn_number = snapshot.session.story_state.turn + 1
                self._validate_new(
                    command, snapshot, turn_number, deterministic=deterministic
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
            interpretation = PlayerAdviceInterpretationService(
                durable=self._advice,
                interpreter=self._first_turn.interpreter_for(
                    snapshot.bootstrap, turn_number
                ),
            )
            proposal = AdviceActionIntentService(
                durable=self._advice,
                sessions=self._session_read,
                proposer=self._first_turn.proposer_for(
                    snapshot.bootstrap, turn_number
                ),
            )
            commit = AdviceCommitService(
                durable=self._advice,
                proposal=proposal,
                story=self._story,
                resolver=DeterministicOutcomeResolver(),
                domain_context=lambda number: self._first_turn.domain_validation_for(
                    snapshot.bootstrap, number
                ),
            )
            await interpretation.interpret(command.input_turn_id)
            result = await commit.commit(
                command.input_turn_id,
                policy=self._first_turn.policy_for_turn(
                    snapshot.bootstrap, turn_number
                ),
                store_expected_revision=command.expected_store_revision,
                request_id=command.request_id,
                trace_id=command.trace_id,
            )
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
    ) -> PublicStorySessionView:
        try:
            return self._projector.project(
                session=record.session,
                bootstrap=record.bootstrap,
                observed_store_revision=record.observed_store_revision,
                has_pending_input=pending,
                max_turn=self._first_turn.max_turn,
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
        deterministic: bool,
    ) -> None:
        session = snapshot.session
        if session.id != command.session_id:
            raise StoryFacadeError("authorization_denied")
        if session.status is not StorySessionStatus.ACTIVE:
            raise StoryFacadeError("story_session_not_active")
        if snapshot.pending_input_turn_id is not None:
            raise StoryFacadeError("pending_turn_exists")
        if (
            turn_number != session.story_state.turn + 1
            or session.story_state.revision != turn_number - 1
            or turn_number > self._first_turn.max_turn
        ):
            raise StoryFacadeError("iteration_limit_reached")
        if (
            command.expected_story_revision != session.story_state.revision
            or command.expected_store_revision != snapshot.observed_store_revision
        ):
            raise StoryFacadeError("revision_conflict")
        if not deterministic:
            # A live turn is bounded by the durable revision guards above, not
            # by an authored string. The resolver and validators still own
            # every committed effect; the model only supplies semantics.
            return
        supported = self._first_turn.expected_input(
            snapshot.bootstrap, turn_number
        )
        if command.raw_input != supported:
            raise StoryFacadeError("deterministic_input_unsupported")

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
