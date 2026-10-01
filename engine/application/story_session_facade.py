"""Public trusted first-turn facade composed from existing durable services."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts import StorySession

from .scenario_policy import (
    ScenarioIdentity,
    ScenarioPolicyError,
    ScenarioPolicyPort,
    TurnPolicyDecision,
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
from .turn_input import TurnInputStatus
from .turn_orchestrator import (
    CommittedTurnResult,
    StoredInputRecord,
    StorySessionQueryPort,
    StorySessionSnapshotRecord,
    SubmissionPolicy,
    SubmitAdviceCommand,
    TurnOrchestrationError,
    TurnOrchestrator,
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

    ``speech_units`` is the only view: one entry per character segment of the
    block, in block order.  The single-segment mirror that used to stand in for
    it is gone — a field that can only ever describe one of several voices is a
    field that will eventually describe the wrong one.
    """

    model_config = ConfigDict(extra="forbid")

    state: Literal["ready", "unavailable"]
    narrative_block_id: str | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=128)
    # One sealed render recipe per segment, carried inside its segment. The App
    # replays each verbatim into ``voice.render``; the Engine rejects any
    # drift, so a client can never choose the voice, the revision or the speed
    # for a committed turn.
    speech_units: tuple[SegmentDeliveryView, ...] = ()

    @model_validator(mode="after")
    def a_ready_turn_names_at_least_one_voice(self) -> TurnDeliveryView:
        """A turn with nothing sealed cannot claim to be ready.

        Asserting it here rather than trusting the coordinator means a future
        path that forgets to build the batch fails at the boundary instead of
        shipping a ``ready`` the player hears silence for.
        """
        if self.state == "ready" and not any(
            unit.state == "ready" for unit in self.speech_units
        ):
            raise ValueError("ready_delivery_requires_a_sealed_segment")
        return self


class SegmentDeliveryView(BaseModel):
    """One narrative segment's audio state.

    A segment that could not be voiced is reported rather than dropped.  That
    is the whole point of the batch: a missing voice must cost that segment its
    audio and nothing else, so the rest of the turn still plays and the player
    can see which line was lost and why.
    """

    model_config = ConfigDict(extra="forbid")

    segment_index: int = Field(ge=0, le=131071)
    state: Literal["ready", "unavailable"]
    speech_unit_id: str | None = None
    spoken_text: str | None = None
    render_recipe: dict[str, object] | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def ready_segments_carry_their_own_recipe(self) -> SegmentDeliveryView:
        if self.state == "ready":
            if self.reason is not None:
                raise ValueError("ready_segment_cannot_carry_a_reason")
            if (
                self.speech_unit_id is None
                or self.spoken_text is None
                or self.render_recipe is None
            ):
                raise ValueError("ready_segment_requires_its_own_recipe")
        elif self.reason is None:
            # An unavailable segment that does not say why is indistinguishable
            # from one the Engine forgot to look at.
            raise ValueError("unavailable_segment_requires_a_reason")
        return self


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
class StoryEntrySnapshot:
    supported_advice: tuple[str, ...]
    observed_store_revision: int
    session: StorySessionSnapshotRecord | None = None
    pending_input_turn_id: str | None = None


class StorySessionFacade:
    def __init__(
        self,
        *,
        initialization: StoryInitializationService,
        open_sessions: StorySessionOpenService,
        query: StorySessionQueryPort,
        scenario: ScenarioPolicyPort,
        turns: TurnOrchestrator,
        projector: StoryPublicViewProjector | None = None,
    ) -> None:
        self._initialization = initialization
        self._open_sessions = open_sessions
        self._query = query
        self._scenario = scenario
        self._turns = turns
        self._projector = projector or StoryPublicViewProjector()

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
        return await self._submit_turn(command, SubmissionPolicy.FIXED)

    async def submit_live(self, command: SubmitAdviceCommand) -> AdviceSubmitView:
        """Submit whatever the player actually said, typed or spoken.

        A free utterance is accepted only when the configured worker factory
        declares a live-input capability. Scenario resolution and validation
        remain the same as for a fixed-input turn.
        """
        return await self._submit_turn(command, SubmissionPolicy.LIVE)

    async def _submit_turn(
        self,
        command: SubmitAdviceCommand,
        submission_policy: SubmissionPolicy,
    ) -> AdviceSubmitView:
        _submit(command)
        try:
            result = await self._turns.execute(command, submission_policy)
        except TurnOrchestrationError as exc:
            raise StoryFacadeError(exc.code) from exc
        return self._project_committed_result(result)

    def _project_committed_result(
        self,
        result: CommittedTurnResult,
    ) -> AdviceSubmitView:
        try:
            session = self._projector.project_from_facts(
                session=result.session,
                facts=result.projection_facts,
                observed_store_revision=result.observed_store_revision,
                policy_decision=result.policy_decision,
                has_pending_input=False,
            )
        except StoryPublicViewError as exc:
            raise StoryFacadeError(exc.code) from None
        return AdviceSubmitView(
            receipt=AdviceReceiptView(
                input_turn_id=result.input_turn_id,
                session_id=result.session_id,
                turn_id=result.turn_id,
                status="committed",
                committed_store_revision=result.committed_store_revision,
                committed_story_revision=result.committed_story_revision,
            ),
            session=session,
            replayed=result.replayed,
            delivery=result.delivery,
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
