"""Voice Foundry orchestration: the only component that drives a supply task.

Every external side effect is bracketed the same way:

1. persist an intent naming the operation, its attempt identity and its exact
   request, then release the writer;
2. call the provider outside the writer;
3. come back and confirm the result against the same operation id.

The bracket is what makes a crash survivable. If the process dies between
(2) and (3) the operation stays ``unknown`` rather than being lost, and the
resume path *asks the provider what happened* instead of minting a second
candidate. That distinction is the whole point: re-running a create under a
fresh identity would silently double-cast a character.

Retries are deliberately narrow. Only an indeterminate transport failure is
retried, at most ``max_attempts`` times, with backoff bounded by an overall
deadline, and every attempt reuses one operation identity. A semantic
rejection is an answer, not an interruption, so it is never retried.

Tasks parked on a human — awaiting a selection or an audition verdict —
report ``slot_consumed=False`` so the scheduler can spend its slot
elsewhere.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from infrastructure.voice_foundry_repository import (
    VoiceCandidateRecord,
    VoiceEvidenceSnapshot,
)
from application.voice_foundry_ports import (
    AssetRequest,
    ConfirmRequest,
    CreateRequest,
    PreviewRequest,
    VoiceFoundryPortError,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from infrastructure.voice_foundry_repository import (
        SQLiteVoiceFoundryRepository,
        VoiceFoundryOperationRecord,
        VoiceFoundryTaskRecord,
    )

#: Candidate slots minted per task. The provider runs one at a time; a failing
#: candidate never overwrites its siblings.
MAX_CANDIDATES = 4

#: The tier a published voice must be proven at. Previews may be rendered
#: cheaply, but the evidence we bind to a voice has to cover the tier the game
#: will actually render at, or publication would vouch for a configuration
#: nobody ever heard.
PRODUCTION_CAPABILITY_KEY = "quality.render"

#: The only failure worth retrying: the call may or may not have landed.
INDETERMINATE_CODES = frozenset({"foundry_transient"})

#: Stages that are waiting on a person. They consume no worker slot and no
#: execution deadline, because a human is not a stalled worker.
HUMAN_STAGES = frozenset({"awaiting_selection", "awaiting_review"})


@dataclass(frozen=True, slots=True)
class FoundryRetryPolicy:
    """Bounded retry shape. Defaults are an implementation choice, not a
    measured performance figure."""

    max_attempts: int = 3
    backoff_seconds: tuple[float, ...] = (1.0, 2.0, 4.0)
    deadline_seconds: float = 120.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("foundry retry policy needs at least one attempt")
        if any(value < 0 for value in self.backoff_seconds):
            raise ValueError("foundry backoff must not be negative")


@dataclass(frozen=True, slots=True)
class WorkerStep:
    """What one advance did, and whether it was worth a worker slot."""

    record: "VoiceFoundryTaskRecord"
    slot_consumed: bool


def _candidate_key(task_id: str, index: int) -> str:
    return f"{task_id}:candidate:{index}"


def _discriminator_of(operation_id: str) -> int:
    tail = operation_id.rsplit(":", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def _voice_id_for(task: "VoiceFoundryTaskRecord") -> str:
    """A stable, provider-legal voice id derived from the task identity."""
    raw = hashlib.sha256(
        f"{task.scope.world_id}|{task.scope.presentation_identity}|{task.persona_revision}".encode(
            "utf-8"
        )
    ).hexdigest()[:16]
    return f"wom-{raw}"


def _digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class VoiceFoundryWorker:
    """Drive supply tasks forward, resumably, without ever double-casting."""

    def __init__(
        self,
        repository: "SQLiteVoiceFoundryRepository",
        port: object,
        *,
        policy: FoundryRetryPolicy | None = None,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._repository = repository
        self._port = port
        self._policy = policy or FoundryRetryPolicy()
        self._sleep = sleeper or asyncio.sleep
        self._clock = clock or time.monotonic

    # -- public surface --------------------------------------------------

    async def advance(self, task_id: str) -> WorkerStep:
        """Move one task forward by at most one durable step."""
        task = await self._repository.load_task(task_id)
        if task.cancel_requested or task.stage == "cancelled":
            if task.stage != "cancelled":
                task = await self._repository.set_stage(
                    task_id,
                    expected_revision=task.task_revision,
                    stage="cancelled",
                    operation_status=task.operation_status,
                    required_actions=(),
                )
            return WorkerStep(record=task, slot_consumed=False)
        if task.stage in HUMAN_STAGES:
            return WorkerStep(record=task, slot_consumed=False)
        deadline_at = self._clock() + self._policy.deadline_seconds
        if task.stage in {"requested", "previewing"}:
            task = await self._preview_one(task, deadline_at)
        elif task.stage == "provisioning":
            task = await self._provision_one(task, deadline_at)
        elif task.stage == "validating":
            task = await self._validate_one(task, deadline_at)
        else:
            # ready / published / failed need an explicit human or client
            # action; the worker must not improvise one.
            return WorkerStep(record=task, slot_consumed=False)
        return WorkerStep(record=task, slot_consumed=True)

    async def reconcile(self, task_id: str) -> int:
        """Settle every unknown operation on a task by asking the provider.

        Reconciliation replays the original request under its original
        idempotency key rather than issuing a new one. That is what makes it
        safe: if the first call landed, the provider replays the original
        candidate; if it did not, the replay creates it once. Either way
        exactly one candidate exists for this task, and no second voice is
        ever minted for the same identity.

        Returns how many operations were settled.
        """
        settled = 0
        task = await self._repository.load_task(task_id)
        for operation_id in self._operation_ids(task_id):
            try:
                record = await self._repository.load_operation(operation_id)
            except Exception:  # noqa: BLE001 - absent operation is not an error
                continue
            if record.status != "unknown" or record.stage != "create":
                continue
            replayed = CreateRequest(
                voice_id=str(record.payload["voice_id"]),
                name=task.scope.presentation_identity,
                instruction=task.voice_description,
                reference_text=task.reference_text,
                seed=int(record.payload.get("seed", 0)),
                provider_locale=self._port.locale_map.resolve(task.scope.locale)
                or "",
                idempotency_key=str(record.payload["idempotency_key"]),
            )
            state = await self._perform(
                task,
                stage="create",
                discriminator=_discriminator_of(operation_id),
                payload=dict(record.payload),
                call=lambda: self._port.create(replayed),
                result_ref=lambda outcome: outcome.candidate_id,
                deadline_at=self._clock() + self._policy.deadline_seconds,
                settle_unknown=True,
            )
            await self._repository.confirm_operation(
                operation_id,
                expected_status="unknown",
                provider_result_ref=state.candidate_id,
            )
            settled += 1
        return settled

    async def publish_and_bind(self, task_id: str, *, binding_id: str) -> WorkerStep:
        """Publish the reviewed voice and bind it, in one client-triggered step.

        Publication and binding belong together because the binding is what
        carries the evidence forward. Publishing first and binding later would
        leave a published voice with no binding, and binding first would bind a
        voice nobody ever published.

        Still a client action rather than something the worker improvises: a
        listener approved this exact candidate revision, and only the client
        knows that approval is what it is waiting on.
        """
        task = await self._repository.load_task(task_id)
        if task.stage != "published":
            return WorkerStep(record=task, slot_consumed=False)
        candidate = await self._repository.load_candidate(
            task_id, _candidate_key(task_id, 0)
        )
        if candidate.provider_candidate_revision is None:
            raise VoiceFoundryPortError("foundry_outcome_unknown")

        deadline_at = self._clock() + self._policy.deadline_seconds
        result = await self._perform(
            task,
            stage="publish",
            discriminator=0,
            payload={
                "candidate_id": candidate.provider_candidate_id,
                "candidate_revision": candidate.provider_candidate_revision,
            },
            call=lambda: self._port.publish(
                candidate.provider_candidate_id,
                expected_candidate_revision=candidate.provider_candidate_revision,
            ),
            result_ref=lambda outcome: outcome.candidate_revision,
            deadline_at=deadline_at,
        )
        task = await self._repository.load_task(task_id)
        committed = await self._repository.commit_ready_binding(
            task_id,
            expected_task_revision=task.task_revision,
            evidence=VoiceEvidenceSnapshot(
                provider_instance=task.provider_instance,
                evidence_id=result.evidence.evidence_id,
                evidence_digest=result.evidence.evidence_digest,
                voice_id=result.voice_id,
                voice_revision=result.voice_revision,
                snapshot={
                    "execution": dict(result.evidence.execution),
                    "reference": dict(result.evidence.reference),
                    "output": dict(result.evidence.output),
                    "human": dict(result.evidence.human),
                    "publication": dict(result.evidence.publication),
                    "rights": dict(result.evidence.rights),
                },
            ),
            binding_id=binding_id,
        )
        return WorkerStep(record=committed, slot_consumed=True)

    # -- steps -----------------------------------------------------------

    async def _preview_one(
        self, task: "VoiceFoundryTaskRecord", deadline_at: float
    ) -> "VoiceFoundryTaskRecord":
        if task.stage == "requested":
            task = await self._repository.set_stage(
                task.task_id,
                expected_revision=task.task_revision,
                stage="previewing",
                operation_status="prepared",
                required_actions=(),
            )
        request = PreviewRequest(
            game_locale=task.scope.locale,
            voice_description=task.voice_description,
            reference_text=task.reference_text,
            seed=0,
        )
        result = await self._perform(
            task,
            stage="preview",
            discriminator=0,
            payload={
                "game_locale": request.game_locale,
                "seed": request.seed,
                "reference_text_digest": hashlib.sha256(
                    request.reference_text.encode("utf-8")
                ).hexdigest(),
            },
            call=lambda: self._port.preview(request),
            result_ref=lambda outcome: outcome.preview_id,
            deadline_at=deadline_at,
        )
        task = await self._repository.add_candidate(
            task.task_id,
            expected_revision=task.task_revision,
            candidate=VoiceCandidateRecord(
                candidate_id=_candidate_key(task.task_id, 0),
                slot=1,
                seed=request.seed,
                state="ready",
                preview_audio_digest=result.audio_digest,
                recipe=result.recipe,
                recipe_digest=result.recipe_digest,
            ),
        )
        return await self._repository.set_stage(
            task.task_id,
            expected_revision=task.task_revision,
            stage="awaiting_selection",
            operation_status="confirmed",
            required_actions=("select_candidate",),
        )

    async def _provision_one(
        self, task: "VoiceFoundryTaskRecord", deadline_at: float
    ) -> "VoiceFoundryTaskRecord":
        candidate = await self._repository.load_candidate(
            task.task_id, _candidate_key(task.task_id, 0)
        )
        if candidate.provider_candidate_id is None:
            # A human picks the candidate before anything is minted for it.
            await self._advance_candidate(task, candidate.candidate_id, "selected")
            task = await self._repository.load_task(task.task_id)
            candidate = await self._advance_candidate(task, candidate.candidate_id, "provisioning")
            task = await self._repository.load_task(task.task_id)
            request = CreateRequest(
                voice_id=_voice_id_for(task),
                name=task.scope.presentation_identity,
                instruction=task.voice_description,
                reference_text=task.reference_text,
                seed=candidate.seed,
                provider_locale=self._port.locale_map.resolve(task.scope.locale) or "",
                idempotency_key=f"{task.task_id}:create:0",
            )
            state = await self._perform(
                task,
                stage="create",
                discriminator=0,
                payload={
                    "voice_id": request.voice_id,
                    "idempotency_key": request.idempotency_key,
                    "seed": request.seed,
                    "reference_text_digest": hashlib.sha256(
                        request.reference_text.encode("utf-8")
                    ).hexdigest(),
                },
                call=lambda: self._port.create(request),
                result_ref=lambda outcome: outcome.candidate_id,
                deadline_at=deadline_at,
            )
            task = await self._repository.load_task(task.task_id)
            await self._repository.update_candidate(
                task.task_id,
                expected_revision=task.task_revision,
                candidate_id=candidate.candidate_id,
                provider_candidate_id=state.candidate_id,
                provider_candidate_revision=state.candidate_revision,
            )
            # Recording the provider identity advanced the task revision, so the
            # stage move below has to speak for the revision that now exists.
            # Carrying the pre-write revision made every first-time creation
            # fail its way out of provisioning, and a task that failed here
            # could never be resumed into validation.
            task = await self._repository.load_task(task.task_id)
        return await self._repository.set_stage(
            task.task_id,
            expected_revision=task.task_revision,
            stage="validating",
            operation_status="confirmed",
            required_actions=(),
        )

    async def _advance_candidate(self, task, candidate_id: str, state: str):
        return await self._repository.update_candidate(
            task.task_id,
            expected_revision=task.task_revision,
            candidate_id=candidate_id,
            state=state,
        )

    async def _validate_one(
        self, task: "VoiceFoundryTaskRecord", deadline_at: float
    ) -> "VoiceFoundryTaskRecord":
        """Bind the reference, then prove the voice on text it has not heard.

        This is the half of supply that runs without a person. It used to have
        no driver at all: provisioning left the task ``validating`` and nothing
        advanced it, so a task that had been selected waited there forever.

        Both provider calls sit inside the same persist-call-confirm bracket as
        creation. A crash between them leaves an ``unknown`` operation that a
        resume reconciles, instead of a voice confirmed or validated twice.
        """
        candidate = await self._repository.load_candidate(
            task.task_id, _candidate_key(task.task_id, 0)
        )
        provider_candidate_id = candidate.provider_candidate_id
        if provider_candidate_id is None:
            raise VoiceFoundryPortError("foundry_outcome_unknown")

        reference_text_digest = hashlib.sha256(
            task.reference_text.encode("utf-8")
        ).hexdigest()
        await self._perform(
            task,
            stage="confirm",
            discriminator=0,
            payload={
                "candidate_id": provider_candidate_id,
                "reference_text_digest": reference_text_digest,
            },
            call=lambda: self._port.confirm(
                provider_candidate_id,
                ConfirmRequest(reference_text=task.reference_text),
            ),
            result_ref=lambda outcome: outcome.candidate_revision,
            deadline_at=deadline_at,
        )

        # The audition the listener will judge is a real asset, so its digest is
        # read back from the provider rather than assumed from the call that
        # produced it. A promise of an audio file is not evidence of one.
        reference_asset = await self._port.read_asset(
            AssetRequest(candidate_id=provider_candidate_id)
        )
        await self._repository.update_candidate(
            task.task_id,
            expected_revision=task.task_revision,
            candidate_id=candidate.candidate_id,
            state="validating",
            reference_audio_digest=reference_asset.audio_digest,
            reference_text_digest=reference_text_digest,
        )
        task = await self._repository.load_task(task.task_id)

        validation = await self._perform(
            task,
            stage="validate",
            discriminator=0,
            payload={
                "candidate_id": provider_candidate_id,
                "capability_key": PRODUCTION_CAPABILITY_KEY,
                "test_text_digest": hashlib.sha256(
                    task.validation_text.encode("utf-8")
                ).hexdigest(),
            },
            call=lambda: self._port.validate(
                provider_candidate_id,
                test_text=task.validation_text,
                capability_key=PRODUCTION_CAPABILITY_KEY,
            ),
            result_ref=lambda outcome: outcome.validation_id,
            deadline_at=deadline_at,
        )

        if not validation.passed:
            # A cross-text failure is not a candidate a listener should be asked
            # to judge. Ending here keeps an unproven voice away from a human's
            # signature instead of spending their attention on it.
            await self._repository.update_candidate(
                task.task_id,
                expected_revision=task.task_revision,
                candidate_id=candidate.candidate_id,
                state="failed",
            )
            task = await self._repository.load_task(task.task_id)
            return await self._repository.set_stage(
                task.task_id,
                expected_revision=task.task_revision,
                stage="failed",
                operation_status="rejected",
                required_actions=(),
                reason_code="machine_validation_failed",
            )

        await self._repository.update_candidate(
            task.task_id,
            expected_revision=task.task_revision,
            candidate_id=candidate.candidate_id,
            state="reviewing",
            validation_audio_digest=validation.audio_digest,
            validation_text_digest=validation.text_digest,
        )
        task = await self._repository.load_task(task.task_id)
        return await self._repository.set_stage(
            task.task_id,
            expected_revision=task.task_revision,
            stage="awaiting_review",
            operation_status="confirmed",
            required_actions=("listen_reference", "listen_validation", "review"),
        )

    # -- the side-effect bracket -----------------------------------------

    async def _perform(
        self,
        task: "VoiceFoundryTaskRecord",
        *,
        stage: str,
        discriminator: int,
        payload: Mapping[str, object],
        call: Callable[[], Awaitable[object]],
        result_ref: Callable[[object], str],
        deadline_at: float,
        settle_unknown: bool = False,
    ):
        from infrastructure.voice_foundry_repository import (
            VoiceFoundryOperationIntent,
        )

        intent = VoiceFoundryOperationIntent(
            operation_id=f"{stage}:{task.task_id}:{discriminator}",
            task_id=task.task_id,
            stage=stage,
            # One attempt identity per logical operation: retries and resumes
            # must not look like a new operation to the provider.
            attempt_identity=f"{stage}:{task.task_id}",
            idempotency_key=f"{task.task_id}:{stage}:{discriminator}",
            payload=payload,
            payload_digest=_digest(payload),
        )
        record = await self._repository.record_operation(intent)
        if record.status == "confirmed":
            return record
        if record.status == "unknown" and not settle_unknown:
            raise VoiceFoundryPortError("foundry_outcome_unknown")
        try:
            outcome = await self._call_with_retry(call, deadline_at)
        except VoiceFoundryPortError as exc:
            if exc.code in INDETERMINATE_CODES:
                # The call may or may not have landed upstream. Record that
                # honestly so a resume reconciles instead of re-casting.
                await self._repository.mark_operation_unknown(intent.operation_id)
            raise
        reference = result_ref(outcome)
        await self._repository.confirm_operation(
            intent.operation_id,
            expected_status="unknown" if settle_unknown else "prepared",
            provider_result_ref=reference,
        )
        return outcome

    async def _call_with_retry(self, call, deadline_at: float):
        attempt = 0
        while True:
            attempt += 1
            try:
                return await call()
            except VoiceFoundryPortError as exc:
                retryable = exc.code in INDETERMINATE_CODES and attempt < self._policy.max_attempts
                if not retryable:
                    raise
                backoff = self._backoff(attempt)
                if self._clock() + backoff > deadline_at:
                    # Sleeping would cross the budget; stop rather than run
                    # past a deadline we already told the caller about.
                    raise
                await self._sleep(backoff)

    def _backoff(self, attempt: int) -> float:
        schedule = self._policy.backoff_seconds
        if not schedule:
            return 0.0
        index = min(attempt - 1, len(schedule) - 1)
        return schedule[index]

    def _operation_ids(self, task_id: str) -> tuple[str, ...]:
        return (
            f"preview:{task_id}:0",
            *(f"create:{task_id}:{slot}" for slot in range(MAX_CANDIDATES)),
        )


__all__ = [
    "HUMAN_STAGES",
    "INDETERMINATE_CODES",
    "MAX_CANDIDATES",
    "FoundryRetryPolicy",
    "VoiceFoundryWorker",
    "WorkerStep",
]
