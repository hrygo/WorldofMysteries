"""Supply orchestration: what a presentation identity still needs a voice for.

The durable task, its candidates and the worker that drives them all exist.
What was missing was the layer that answers the only question a caller
actually has — *can this identity speak right now, and if not, what is it
waiting on* — and that turns that answer into the public
``voice_foundry_state`` projection the App renders.

Three rules shape this layer.

**Reuse before recast.** A scope whose persona revision is already bound to a
voice a human approved does not get a second voice minted for it. Asking again
is not free: it spends provider budget, it puts a second candidate in front of
the same listener, and the two would then compete for one binding.

**The projection never guesses.** Every field is read from the durable record.
Where ADR-005 D6 asks for ``provider_unavailable`` and ``policy_blocked`` to be
distinguished, this layer reports ``failed`` instead, because a task record
carries no evidence of *which* of the two happened — the worker re-raises the
provider's own code rather than writing a reason. Classifying it here would
mean inventing a distinction the data does not carry, and a supply status that
lies is worse than one that is coarse. The distinction belongs where the
provider call is answered.

**A pre-check reads history.** Scene pre-warming asks what every identity
already has before it asks for anything, so ``precheck`` reports the live task
for a scope and treats "asked and abandoned" differently from "never asked".
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from domain.voice_identity import VoiceBinding, VoiceBindingScope
from infrastructure.voice_foundry_repository import (
    SQLiteVoiceFoundryRepository,
    VoiceFoundryStage,
    VoiceFoundryTaskRecord,
    VoiceFoundryTaskSpec,
)


class VoiceSupplyOutcome(StrEnum):
    """What a caller may do about one identity's voice right now."""

    #: A reviewed voice is bound and may render new audio.
    READY = "ready"
    #: Supply is under way; no human decision is being waited on.
    SUPPLY_REQUIRED = "supply_required"
    #: A person is the bottleneck: choose a candidate, or listen and review.
    PENDING_REVIEW = "pending_review"
    #: Supply stopped and will not resume on its own.
    FAILED = "failed"
    #: The task was withdrawn.
    CANCELLED = "cancelled"


#: Keyed by the stage's string value — see ``_stage_value`` for why.
_OUTCOME_BY_STAGE = {
    "ready": VoiceSupplyOutcome.READY,
    "awaiting_selection": VoiceSupplyOutcome.PENDING_REVIEW,
    "awaiting_review": VoiceSupplyOutcome.PENDING_REVIEW,
    "failed": VoiceSupplyOutcome.FAILED,
    "cancelled": VoiceSupplyOutcome.CANCELLED,
}

_TERMINAL_STAGES = frozenset({"failed", "cancelled"})


@dataclass(frozen=True, slots=True)
class VoiceCandidateProjection:
    """One candidate as ``voice_foundry_state`` states it."""

    candidate_id: str
    slot: int
    seed: int
    state: str
    preview_audio_digest: str
    provider_candidate_id: str | None
    provider_candidate_revision: str | None
    #: Not part of the public contract; the App needs them to fetch audio.
    reference_audio_digest: str | None = None
    validation_audio_digest: str | None = None

    def to_contract(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "slot": self.slot,
            "seed": self.seed,
            "state": self.state,
            "preview_audio_digest": self.preview_audio_digest,
            "provider_candidate_id": self.provider_candidate_id,
            "provider_candidate_revision": self.provider_candidate_revision,
        }


@dataclass(frozen=True, slots=True)
class VoiceFoundryProjection:
    """The public projection of one supply task.

    ``to_contract`` emits exactly the fields
    ``contracts/schemas/voice_foundry_state.schema.json`` declares, so the
    projection cannot drift into a shape the contract would reject.
    """

    task_id: str
    request_id: str
    request_digest: str
    scope: VoiceBindingScope
    stage: str
    task_revision: int
    cancel_requested: bool
    operation_status: str
    required_actions: tuple[str, ...]
    reason_code: str | None
    candidates: tuple[VoiceCandidateProjection, ...]

    def to_contract(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "task_id": self.task_id,
            "request_id": self.request_id,
            "request_digest": self.request_digest,
            "scope": {
                "owner_id": self.scope.owner_id,
                "world_id": self.scope.world_id,
                "worldline_id": self.scope.worldline_id,
                "presentation_identity": self.scope.presentation_identity,
                "phase": self.scope.phase,
                "locale": self.scope.locale,
            },
            "stage": self.stage,
            "task_revision": self.task_revision,
            "cancel_requested": self.cancel_requested,
            "operation_status": self.operation_status,
            "required_actions": list(self.required_actions),
            "reason_code": self.reason_code,
            "candidates": [item.to_contract() for item in self.candidates],
        }


@dataclass(frozen=True, slots=True)
class VoiceSupplyResult:
    """The answer to "can this identity speak, and if not, why not"."""

    outcome: VoiceSupplyOutcome
    #: ``None`` when the answer came from an existing binding rather than a
    #: supply task — a scope that was served without ever being asked.
    state: VoiceFoundryProjection | None = None
    #: The binding that authorizes rendering, when one exists.
    binding_id: str | None = None
    reason_code: str | None = None


class VoiceBindingLookup(Protocol):
    """The one binding verb this layer needs."""

    async def load_scope(self, scope: VoiceBindingScope) -> VoiceBinding | None: ...


def _outcome_of(stage: VoiceFoundryStage) -> VoiceSupplyOutcome:
    """Map the durable stage onto the answer a caller acts on.

    A projection, not a policy: the stage is the fact, and this only says which
    fact the caller is looking at.
    """
    return _OUTCOME_BY_STAGE.get(
        _stage_value(stage), VoiceSupplyOutcome.SUPPLY_REQUIRED
    )


def _stage_value(stage: object) -> str:
    """The stage as a plain string, compared by value rather than identity.

    Both ``infrastructure.x`` and ``engine.infrastructure.x`` are importable
    here, so the same enum can arrive from either module copy and ``is`` would
    miss. Value comparison is what the worker already relies on.
    """
    return str(getattr(stage, "value", stage))


class VoiceSupplyService:
    """Decide what one presentation identity still needs, and say so."""

    def __init__(
        self,
        *,
        repository: SQLiteVoiceFoundryRepository,
        bindings: VoiceBindingLookup,
    ) -> None:
        self._repository = repository
        self._bindings = bindings

    async def request(self, spec: VoiceFoundryTaskSpec) -> VoiceSupplyResult:
        """Supply a voice for one identity, or report that it already has one.

        Registration is idempotent by request id and, for a scope already in
        flight, by digest — so a retried request resumes the same task instead
        of minting a second set of candidates for the same character.
        """
        bound = await self._renderable_binding(spec.scope, spec.persona_revision)
        if bound is not None:
            return VoiceSupplyResult(
                outcome=VoiceSupplyOutcome.READY,
                binding_id=bound.binding_id,
            )
        task = await self._repository.register_task(spec)
        return await self._result_of(task)

    async def get(self, task_id: str) -> VoiceSupplyResult:
        task = await self._repository.load_task(task_id)
        return await self._result_of(task)

    async def precheck(self, scope: VoiceBindingScope) -> VoiceSupplyResult:
        """Report one identity's readiness without asking for anything.

        Pre-warming a scene runs this for every identity it will need. It
        creates no task and calls no provider: a caller that only wanted to
        know must not, as a side effect, have started a cast.
        """
        bound = await self._renderable_binding(scope, None)
        if bound is not None:
            return VoiceSupplyResult(
                outcome=VoiceSupplyOutcome.READY,
                binding_id=bound.binding_id,
            )
        tasks = await self._repository.load_scope_tasks(scope)
        if not tasks:
            return VoiceSupplyResult(
                outcome=VoiceSupplyOutcome.SUPPLY_REQUIRED,
                reason_code="voice_never_requested",
            )
        live = [
            item
            for item in tasks
            if _stage_value(item.stage) not in _TERMINAL_STAGES
        ]
        # The newest live task is the one a caller would resume; when every
        # task is spent, the newest of those is what the scope ended on.
        return await self._result_of(live[-1] if live else tasks[-1])

    # -- internals -------------------------------------------------------

    async def _renderable_binding(
        self, scope: VoiceBindingScope, persona_revision: str | None
    ) -> VoiceBinding | None:
        """The binding that can actually render for this scope, if any.

        A binding that exists but was never reviewed is skipped: it is a
        claim, not a voice anybody may hear, and treating it as one would
        strand the scope with no supply at all.
        """
        bound = await self._bindings.load_scope(scope)
        if bound is None or not bound.permits_new_render:
            return None
        if persona_revision is not None and bound.persona.revision != persona_revision:
            # The same voice under a different persona revision is a different
            # casting decision, so the existing binding cannot answer for it.
            return None
        return bound

    async def _result_of(self, task: VoiceFoundryTaskRecord) -> VoiceSupplyResult:
        candidates = await self._repository.load_candidates(task.task_id)
        projection = VoiceFoundryProjection(
            task_id=task.task_id,
            request_id=task.request_id,
            request_digest=task.request_digest,
            scope=task.scope,
            stage=task.stage.value,
            task_revision=task.task_revision,
            cancel_requested=task.cancel_requested,
            operation_status=task.operation_status,
            # Read, never re-derived: whoever moved the task last decided what
            # a person owes next, and a second derivation here could disagree
            # with the durable record about the very buttons it publishes.
            required_actions=tuple(task.required_actions),
            reason_code=task.reason_code,
            candidates=tuple(
                VoiceCandidateProjection(
                    candidate_id=item.candidate_id,
                    slot=item.slot,
                    seed=item.seed,
                    state=item.state,
                    preview_audio_digest=item.preview_audio_digest,
                    provider_candidate_id=item.provider_candidate_id,
                    provider_candidate_revision=item.provider_candidate_revision,
                    reference_audio_digest=item.reference_audio_digest,
                    validation_audio_digest=item.validation_audio_digest,
                )
                for item in candidates
            ),
        )
        return VoiceSupplyResult(
            outcome=_outcome_of(task.stage),
            state=projection,
            reason_code=task.reason_code,
        )


__all__ = [
    "VoiceCandidateProjection",
    "VoiceFoundryProjection",
    "VoiceSupplyOutcome",
    "VoiceSupplyResult",
    "VoiceSupplyService",
]
