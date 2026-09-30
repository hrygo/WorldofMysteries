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
    FoundryReviewVerdict,
    PreviewRequest,
    review_verdict_is_accepted,
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

#: Largest audition asset this engine will hand to a client. The bound is the
#: wire's, not the provider's: 589824 bytes encodes to 786432 base64 bytes,
#: which fits the 1 MiB IPC frame with room for the envelope, and it is stated
#: in ``contracts/protocol/voice_foundry_control.schema.json`` so a client can
#: rely on it. An asset above it is refused rather than truncated — a WAV cut
#: short still plays and still sounds like a voice, and a listener would judge
#: it while the evidence kept describing bytes they never heard.
MAX_AUDITION_ASSET_BYTES = 589_824

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


@dataclass(frozen=True, slots=True)
class AuditionAsset:
    """One audition asset, with the facts that make it checkable.

    A human verdict is about particular audio. Carrying the bytes next to the
    revision, the validation identity and the digest is what lets the review
    that follows be checked against exactly what a listener heard, instead of
    against a claim that some audio existed somewhere.
    """

    candidate_id: str
    kind: str
    candidate_revision: str
    validation_id: str | None
    audio: bytes
    audio_digest: str


def _candidate_key(task_id: str, index: int) -> str:
    return f"{task_id}:candidate:{index}"


def _operation_id(stage: str, task_id: str, discriminator: int) -> str:
    """The one place an operation's identity is spelled.

    ``_perform`` writes under this name and the client-triggered steps read
    it back. Building the string in both places is how a resume ends up
    looking for an operation that was filed under a slightly different name
    and silently minting a second one.
    """
    return f"{stage}:{task_id}:{discriminator}"


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

    async def confirm_reference_step(
        self,
        task_id: str,
        *,
        provider_candidate_revision: str,
        reference_text: str,
        reference_audio_digest: str,
    ) -> WorkerStep:
        """Bind the reference, then prove the caller means that binding.

        The control surface lets a client authorize this half on its own, so
        the three facts it brings back are checked against what this engine
        durably recorded rather than taken on trust. The text is refused
        before the provider is called, because a mismatch there costs nothing
        to detect; the revision and the audio digest can only be checked
        afterwards, because they are the provider's to answer.

        Asking twice is not a second binding. The confirm intent is settled by
        its operation identity, so a repeat reads the same answer back instead
        of binding the reference again.
        """
        task = await self._repository.load_task(task_id)
        if task.stage != "validating":
            return WorkerStep(record=task, slot_consumed=False)
        if reference_text != task.reference_text:
            raise VoiceFoundryPortError("confirm_reference_text_mismatch")

        task, candidate = await self._confirm_reference(
            task, self._clock() + self._policy.deadline_seconds
        )

        confirm = await self._repository.load_operation(
            _operation_id("confirm", task_id, 0)
        )
        if (
            confirm.status != "confirmed"
            or confirm.provider_result_ref != provider_candidate_revision
        ):
            raise VoiceFoundryPortError("confirm_reference_revision_mismatch")
        if candidate.reference_audio_digest != reference_audio_digest:
            raise VoiceFoundryPortError("confirm_reference_asset_mismatch")
        return WorkerStep(record=task, slot_consumed=True)

    async def validate_step(
        self,
        task_id: str,
        *,
        test_text: str,
        capability_key: str,
    ) -> WorkerStep:
        """Prove the confirmed voice on text it has not been read.

        Both inputs are refused before the provider is called when they are not
        the ones this task was authorized to use. What a listener signs
        afterwards is a verdict about *this* text at *this* tier, so a check
        run against anything else would produce evidence describing a
        different test than the one on the record.
        """
        task = await self._repository.load_task(task_id)
        if task.stage != "validating":
            return WorkerStep(record=task, slot_consumed=False)
        candidate = await self._repository.load_candidate(
            task_id, _candidate_key(task_id, 0)
        )
        if candidate.provider_candidate_id is None:
            raise VoiceFoundryPortError("foundry_outcome_unknown")
        if candidate.state != "validating":
            raise VoiceFoundryPortError("reference_not_confirmed")
        if capability_key != PRODUCTION_CAPABILITY_KEY:
            raise VoiceFoundryPortError("validation_capability_mismatch")
        if test_text != task.validation_text:
            raise VoiceFoundryPortError("validation_text_mismatch")

        task = await self._validate(
            task,
            candidate,
            self._clock() + self._policy.deadline_seconds,
            test_text=test_text,
            capability_key=capability_key,
        )
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

    async def submit_review(
        self,
        task_id: str,
        *,
        candidate_id: str,
        validation_id: str,
        reference_audio_digest: str,
        validation_audio_digest: str,
        identity: FoundryReviewVerdict,
        naturalness: FoundryReviewVerdict,
    ) -> WorkerStep:
        """Send one listener's verdict upstream, then record it locally.

        The provider only lets a voice be published once a human review has
        reached *it*. A verdict that stayed in this process would mark the
        task published while the provider still refuses the publication, so
        this is a worker step and not a local state edit: the port call and
        the state change sit in the same persist-call-confirm bracket, and a
        crash between them resumes rather than publishing an unheard voice.

        The digests are checked against what this engine durably read back
        from the provider, never taken on trust. A verdict attaches to the
        exact assets a person heard; if the reference or the cross-text audio
        was regenerated since they listened, their verdict describes audio
        that no longer exists and is refused rather than carried forward.
        """
        task = await self._repository.load_task(task_id)
        if task.stage != "awaiting_review":
            return WorkerStep(record=task, slot_consumed=False)
        candidate = await self._repository.load_candidate(task_id, candidate_id)
        if candidate.state != "reviewing":
            raise VoiceFoundryPortError("candidate_not_awaiting_review")
        if candidate.provider_candidate_id is None:
            raise VoiceFoundryPortError("foundry_outcome_unknown")

        # Refuse before spending the call. WARN has no lossless
        # representation in our evidence contract and NOT_REVIEWED is the
        # absence of a person, so neither may reach the provider and then be
        # dropped on the way back.
        for verdict in (identity, naturalness):
            if verdict is FoundryReviewVerdict.WARN:
                raise VoiceFoundryPortError(
                    "review_verdict_requires_explicit_handling"
                )
            if verdict is FoundryReviewVerdict.NOT_REVIEWED:
                raise VoiceFoundryPortError("review_verdict_absent")

        await self._require_auditioned_assets(
            task_id,
            candidate,
            validation_id=validation_id,
            reference_audio_digest=reference_audio_digest,
            validation_audio_digest=validation_audio_digest,
        )

        await self._perform(
            task,
            stage="review",
            discriminator=0,
            payload={
                "candidate_id": candidate.provider_candidate_id,
                "validation_id": validation_id,
                "reference_audio_digest": reference_audio_digest,
                "validation_audio_digest": validation_audio_digest,
                "identity": identity.value,
                "naturalness": naturalness.value,
            },
            call=lambda: self._port.review(
                candidate.provider_candidate_id,
                validation_id=validation_id,
                identity=identity,
                naturalness=naturalness,
                # The evidence has to name the audio this verdict is about.
                # It was checked against the record a moment ago, so this is
                # the digest of the asset the listener actually heard.
                validation_audio_digest=validation_audio_digest,
            ),
            result_ref=lambda outcome: outcome.evidence_id,
            deadline_at=self._clock() + self._policy.deadline_seconds,
        )

        # Acceptance is both questions answered yes. One "reject" is a
        # rejection: a voice the listener could not place, or would not sit
        # through a scene with, is not a casting they signed off on.
        accepted = review_verdict_is_accepted(
            identity
        ) and review_verdict_is_accepted(naturalness)
        task = await self._repository.load_task(task_id)
        await self._repository.update_candidate(
            task_id,
            expected_revision=task.task_revision,
            candidate_id=candidate_id,
            state="published" if accepted else "failed",
        )
        # Recording the candidate's fate advanced the task revision, so the
        # stage move has to speak for the revision that now exists.
        task = await self._repository.load_task(task_id)
        task = await self._repository.set_stage(
            task_id,
            expected_revision=task.task_revision,
            stage="published" if accepted else "failed",
            operation_status="confirmed",
            required_actions=(),
            reason_code=None if accepted else "human_review_rejected",
        )
        return WorkerStep(record=task, slot_consumed=True)

    async def audition_asset(
        self,
        task_id: str,
        *,
        candidate_id: str,
        kind: str,
    ) -> AuditionAsset:
        """Fetch one of a candidate's two audition assets, and say what it is.

        Reading is not the hard part of a human review; being able to prove
        what was heard is. Three facts travel with the bytes here, and each
        one closes a way the review that follows could be about the wrong
        thing:

        * the read names the candidate revision this engine recorded, so the
          audio belongs to the design whose evidence will be published;
        * the validation id comes from the operation journal, so a client can
          actually name the validation its verdict is about — it is the
          provider's answer to the validate call and lives nowhere else;
        * the digest is compared against the one recorded when the asset was
          first read. If the provider has moved since, the audio a listener
          would hear today is not the audio the evidence describes, and the
          read is refused instead of quietly auditioning something else.

        Nothing here is journalled. An audition changes no state, so a repeat
        costs one provider read and nothing else — there is no second casting
        to accidentally perform.
        """
        if kind not in ("reference", "validation"):
            raise VoiceFoundryPortError("audition_asset_kind_unknown")
        candidate = await self._repository.load_candidate(task_id, candidate_id)
        if (
            candidate.provider_candidate_id is None
            or candidate.provider_candidate_revision is None
        ):
            raise VoiceFoundryPortError("foundry_outcome_unknown")

        validation_id: str | None = None
        if kind == "validation":
            record = await self._repository.load_operation(
                _operation_id("validate", task_id, 0)
            )
            if record.status != "confirmed" or record.provider_result_ref is None:
                raise VoiceFoundryPortError("foundry_outcome_unknown")
            validation_id = record.provider_result_ref

        result = await self._port.read_asset(
            AssetRequest(
                candidate_id=candidate.provider_candidate_id,
                candidate_revision=candidate.provider_candidate_revision,
                validation_id=validation_id,
            )
        )
        recorded = (
            candidate.reference_audio_digest
            if kind == "reference"
            else candidate.validation_audio_digest
        )
        if recorded is None:
            raise VoiceFoundryPortError("audition_asset_not_recorded")
        if result.audio_digest != recorded:
            raise VoiceFoundryPortError("audition_asset_drifted")
        if not result.audio:
            raise VoiceFoundryPortError("audition_asset_empty")
        if len(result.audio) > MAX_AUDITION_ASSET_BYTES:
            raise VoiceFoundryPortError("audition_asset_too_large")
        return AuditionAsset(
            candidate_id=candidate.candidate_id,
            kind=kind,
            candidate_revision=candidate.provider_candidate_revision,
            validation_id=validation_id,
            audio=result.audio,
            audio_digest=result.audio_digest,
        )

    async def _require_auditioned_assets(
        self,
        task_id: str,
        candidate: VoiceCandidateRecord,
        *,
        validation_id: str,
        reference_audio_digest: str,
        validation_audio_digest: str,
    ) -> None:
        """Refuse a verdict that is not about the audio that exists now.

        The validation id is read back from the operation journal rather than
        from the candidate row, because it is the provider's answer to the
        validate call and that is where it is durably recorded.
        """
        record = await self._repository.load_operation(
            _operation_id("validate", task_id, 0)
        )
        if record.status != "confirmed" or record.provider_result_ref != validation_id:
            raise VoiceFoundryPortError("foundry_outcome_unknown")
        if (
            candidate.reference_audio_digest != reference_audio_digest
            or candidate.validation_audio_digest != validation_audio_digest
        ):
            raise VoiceFoundryPortError("review_asset_mismatch")

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

        It is the unattended path through the same two steps a client can
        authorize one at a time, so both routes run one implementation and
        cannot drift apart.
        """
        task, candidate = await self._confirm_reference(task, deadline_at)
        return await self._validate(
            task,
            candidate,
            deadline_at,
            test_text=task.validation_text,
            capability_key=PRODUCTION_CAPABILITY_KEY,
        )

    async def _confirm_reference(
        self, task: "VoiceFoundryTaskRecord", deadline_at: float
    ) -> tuple["VoiceFoundryTaskRecord", VoiceCandidateRecord]:
        """Bind the reference text and record the audio a listener will hear.

        The audition is a real asset, so its digest is read back from the
        provider rather than assumed from the call that promised it. A promise
        of an audio file is not evidence of one.
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

        # ``confirm`` is where the provider moves the design to a new
        # revision: its contract says editing the reference text produces a
        # new candidate revision and clears the old validations, so the
        # revision a caller may act on is never the one ``create`` handed
        # out. It is read back from the journal rather than from the call's
        # return, so a resume sees the same answer the first attempt did.
        confirm = await self._repository.load_operation(
            _operation_id("confirm", task.task_id, 0)
        )
        if confirm.status != "confirmed" or confirm.provider_result_ref is None:
            raise VoiceFoundryPortError("foundry_outcome_unknown")

        reference_asset = await self._port.read_asset(
            AssetRequest(
                candidate_id=provider_candidate_id,
                # The revision ``confirm`` just produced, not the one
                # ``create`` handed out: binding the reference is what moves
                # the design. Reading at the older revision would hand a
                # listener audio of a voice this engine never recorded.
                candidate_revision=confirm.provider_result_ref,
            )
        )
        candidate = await self._repository.update_candidate(
            task.task_id,
            expected_revision=task.task_revision,
            candidate_id=candidate.candidate_id,
            state="validating",
            provider_candidate_revision=confirm.provider_result_ref,
            reference_audio_digest=reference_asset.audio_digest,
            reference_text_digest=reference_text_digest,
        )
        # Writing the candidate moved the task revision, so the record handed
        # back has to be the one that now exists.
        task = await self._repository.load_task(task.task_id)
        return task, candidate

    async def _validate(
        self,
        task: "VoiceFoundryTaskRecord",
        candidate: VoiceCandidateRecord,
        deadline_at: float,
        *,
        test_text: str,
        capability_key: str,
    ) -> "VoiceFoundryTaskRecord":
        """Run the cross-text check and hand the result to a person or to a
        failure, never to both."""

        validation = await self._perform(
            task,
            stage="validate",
            discriminator=0,
            payload={
                "candidate_id": candidate.provider_candidate_id,
                "capability_key": capability_key,
                "test_text_digest": hashlib.sha256(
                    test_text.encode("utf-8")
                ).hexdigest(),
            },
            call=lambda: self._port.validate(
                candidate.provider_candidate_id,
                test_text=test_text,
                capability_key=capability_key,
            ),
            result_ref=lambda outcome: outcome.validation_id,
            deadline_at=deadline_at,
            # A settled intent still has to yield its answer. The provider
            # replays the same result under the same key, so re-reading is
            # how a resume recovers the outcome instead of assuming one.
            reread_confirmed=True,
        )

        # The provider is asked for the revision it is currently at, and it
        # answers with one. If that is not the revision this engine recorded
        # at ``confirm``, the design moved somewhere this engine has no
        # durable record of, and every later step — the audition a listener
        # judges, the evidence they sign — would describe a different voice.
        # Stopping here says so; carrying the stale revision forward would
        # not.
        if validation.candidate_revision != candidate.provider_candidate_revision:
            raise VoiceFoundryPortError("foundry_revision_advanced")

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

        # The provider publishes no digest for a validation, so the audio's
        # identity is established by reading the asset — the same rule, in the
        # same place, that ``_confirm_reference`` follows for the reference.
        # A promise that a cross-text check ran is not evidence that a file
        # exists, and an empty digest recorded here would travel all the way
        # to the repository, which refuses it as malformed without saying
        # which layer produced it.
        validation_asset = await self._port.read_asset(
            AssetRequest(
                candidate_id=candidate.provider_candidate_id,
                candidate_revision=candidate.provider_candidate_revision,
                validation_id=validation.validation_id,
            )
        )
        if not validation_asset.audio:
            raise VoiceFoundryPortError("validation_asset_empty")

        await self._repository.update_candidate(
            task.task_id,
            expected_revision=task.task_revision,
            candidate_id=candidate.candidate_id,
            state="reviewing",
            validation_audio_digest=validation_asset.audio_digest,
            # The digest of the text this engine asked the provider to speak,
            # computed here for the same reason: the provider records it but
            # does not publish it.
            validation_text_digest=hashlib.sha256(
                test_text.encode("utf-8")
            ).hexdigest(),
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
        reread_confirmed: bool = False,
    ):
        from infrastructure.voice_foundry_repository import (
            VoiceFoundryOperationIntent,
        )

        intent = VoiceFoundryOperationIntent(
            operation_id=_operation_id(stage, task.task_id, discriminator),
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
            if reread_confirmed:
                # The intent is already settled, so this is a read rather than
                # an action: the provider answers the same key with the same
                # object. Anything else means the provider and our own record
                # have parted ways, and picking either one silently is exactly
                # the kind of guess this bracket exists to prevent.
                outcome = await self._call_with_retry(call, deadline_at)
                if result_ref(outcome) != record.provider_result_ref:
                    raise VoiceFoundryPortError("foundry_outcome_diverged")
                return outcome
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
    "MAX_AUDITION_ASSET_BYTES",
    "AuditionAsset",
    "FoundryRetryPolicy",
    "VoiceFoundryWorker",
    "WorkerStep",
]
