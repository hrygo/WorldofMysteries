"""The human spine of voice supply: choose, review, bind.

Every command names an id the caller controls, and that id is the idempotency
key. Replaying it returns the current answer without acting twice; reusing it
for different input is refused. The durable revision CAS backs this up — a
command arriving without a receipt still cannot overwrite newer state — but
the receipt is what makes a repeat *answerable* rather than merely safe.

These three verbs are where a person meets the supply loop. Everything between
them belongs to the worker or the provider: this module starts the machine,
records what the listener decided, and commits the published voice.

**A verdict is not a formality.** Only ``PASS`` publishes. ``WARN`` has no
lossless representation in the shipped evidence contract and ``NOT_REVIEWED``
is the absence of a decision, so both are refused here rather than folded into
anything. Folding them in is precisely how audio nobody approved reaches a
player, and it is the failure this whole supply chain exists to prevent.

Repository errors are deliberately not wrapped. They are already typed and
already say what went wrong; a command layer that re-coded them would only add
a translation to get wrong.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from application.voice_foundry_ports import (
    VoiceSupplyDriver,
)
from application.voice_foundry_service import (
    VoiceSupplyResult,
    VoiceSupplyService,
)
from infrastructure.voice_foundry_repository import (
    SQLiteVoiceFoundryRepository,
    VoiceCommandAck,
    VoiceEvidenceSnapshot,
    VoiceFoundryStage,
    VoiceFoundryTaskRecord,
)


class VoiceFoundryCommandError(RuntimeError):
    """A command cannot be applied to the task in its current state."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _stage_value(stage: object) -> str:
    """The stage as a plain string.

    Both ``infrastructure.x`` and ``engine.infrastructure.x`` are importable
    here, so the same enum can arrive from either module copy and ``is`` would
    miss. Value comparison is what the worker and the supply service rely on.
    """
    return str(getattr(stage, "value", stage))


def _digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


#: Past the point where a provider voice exists. A cancel here would be a
#: claim that something was withdrawn that in fact was published, so these
#: stages are refused instead.
_PUBLISHED_STAGES = frozenset({"published", "binding", "ready"})

#: Stages where a person, not the machine, owes the next move. Mirrors
#: ``HUMAN_STAGES`` in the worker: a retry here would race the very decision
#: the task is waiting on.
_HUMAN_STAGES = frozenset({"awaiting_selection", "awaiting_review"})

#: Stages with nothing left for the machine half to drive.
_SETTLED_STAGES = frozenset({"published", "binding", "ready", "failed"})


class VoiceFoundryCommandService:
    """Apply one caller-named decision to one supply task, at most once."""

    def __init__(
        self,
        *,
        repository: SQLiteVoiceFoundryRepository,
        supply: VoiceSupplyService,
        driver: VoiceSupplyDriver,
    ) -> None:
        self._repository = repository
        self._supply = supply
        self._driver = driver

    # -- public surface --------------------------------------------------

    async def select_candidate(
        self, *, command_id: str, task_id: str, candidate_id: str
    ) -> VoiceSupplyResult:
        """Choose the candidate to carry forward, and start provisioning it.

        Selection is the point of no return for the other candidates: they are
        left exactly as they were rather than cancelled, so a later decision
        can still be explained from the durable record.
        """
        payload = {
            "verb": "select_candidate",
            "task_id": task_id,
            "candidate_id": candidate_id,
        }
        if await self._replayed(command_id, task_id, payload):
            return await self._supply.get(task_id)

        task = await self._require_stage(task_id, "awaiting_selection")
        candidate = await self._repository.load_candidate(task_id, candidate_id)
        if candidate.state != "ready":
            raise VoiceFoundryCommandError("candidate_not_selectable")

        await self._repository.update_candidate(
            task_id,
            expected_revision=task.task_revision,
            candidate_id=candidate_id,
            state="selected",
        )
        await self._repository.set_stage(
            task_id,
            expected_revision=task.task_revision + 1,
            stage=VoiceFoundryStage.PROVISIONING,
            operation_status="confirmed",
            required_actions=(),
        )
        return await self._record(
            command_id, task_id, payload, {"candidate_id": candidate_id}
        )

    async def bind(
        self,
        *,
        command_id: str,
        task_id: str,
        evidence: VoiceEvidenceSnapshot,
        binding_id: str,
    ) -> VoiceSupplyResult:
        """Commit the published voice as this identity's binding, atomically.

        The evidence and the binding land in one write, so a task can never
        read ``ready`` while the binding it names is absent or unreadable.
        """
        payload = {
            "verb": "bind",
            "task_id": task_id,
            "evidence_id": evidence.evidence_id,
            "evidence_digest": evidence.evidence_digest,
            "binding_id": binding_id,
        }
        if await self._replayed(command_id, task_id, payload):
            return await self._supply.get(task_id)
        task = await self._require_stage(task_id, "published")

        await self._repository.commit_ready_binding(
            task_id,
            expected_task_revision=task.task_revision,
            evidence=evidence,
            binding_id=binding_id,
        )
        return await self._record(
            command_id, task_id, payload, {"binding_id": binding_id}
        )

    async def cancel(
        self,
        *,
        command_id: str,
        task_id: str,
        reason_code: str | None = None,
    ) -> VoiceSupplyResult:
        """Withdraw a supply task that has not published anything yet.

        Cancellation stops this game's side of the task: the worker refuses to
        take another step and no binding follows. It does not un-publish a
        provider voice, and it refuses to pretend it did — once a voice is
        published the task is a record of a real thing that happened, so the
        audit trail has to keep it. Revoking a published voice is a different
        command with different evidence.
        """
        payload = {
            "verb": "cancel",
            "task_id": task_id,
            "reason_code": reason_code,
        }
        if await self._replayed(command_id, task_id, payload):
            return await self._supply.get(task_id)

        task = await self._repository.load_task(task_id)
        stage = _stage_value(task.stage)
        if stage in _PUBLISHED_STAGES:
            raise VoiceFoundryCommandError("published_voice_cannot_be_cancelled")
        if task.cancel_requested or stage == "cancelled":
            # Already withdrawn. Re-recording the same withdrawal is what
            # makes a retried cancel converge instead of erroring.
            return await self._record(command_id, task_id, payload, {})

        await self._repository.request_cancel(
            task_id,
            expected_revision=task.task_revision,
            reason_code=reason_code,
        )
        return await self._record(command_id, task_id, payload, {})

    async def retry(
        self, *, command_id: str, task_id: str
    ) -> VoiceSupplyResult:
        """Settle an unknown provider outcome, then resume the same task.

        Retry is deliberately not a state edit. When a call's result is
        unknown, ADR-005 D9 requires asking the provider under the original
        idempotency key and resuming the original request — reopening the task
        instead would leave a half-created voice unaccounted for and mint a
        second one. So a retry on a task with nothing unknown is refused
        rather than treated as a fresh start.

        What makes a task retryable is that the machine half still owes it a
        step: it is not withdrawn, not waiting on a person, and not already
        finished. The driver reconciles any operation whose outcome is unknown
        under its original key, then advances at most one durable step.
        """
        payload = {"verb": "retry", "task_id": task_id}
        if await self._replayed(command_id, task_id, payload):
            return await self._supply.get(task_id)

        task = await self._repository.load_task(task_id)
        stage = _stage_value(task.stage)
        if task.cancel_requested or stage == "cancelled":
            raise VoiceFoundryCommandError("cancelled_task_cannot_be_retried")
        if stage in _HUMAN_STAGES:
            # A person is the bottleneck; a background retry would race the
            # decision they are being asked for, not help it along.
            raise VoiceFoundryCommandError("task_awaits_a_human_decision")
        if stage in _SETTLED_STAGES:
            # ``published`` still owes the publish step, but that is the
            # publish action's job, driven by a reviewer who approved it.
            raise VoiceFoundryCommandError("task_is_not_retryable")

        settled = await self._driver.reconcile(task_id)
        step = await self._driver.advance(task_id)
        return await self._record(
            command_id,
            task_id,
            payload,
            {
                "settled_operations": settled,
                "slot_consumed": bool(getattr(step, "slot_consumed", False)),
            },
        )

    # -- internals -------------------------------------------------------

    async def _require_stage(
        self, task_id: str, expected: str
    ) -> VoiceFoundryTaskRecord:
        task = await self._repository.load_task(task_id)
        if _stage_value(task.stage) != expected:
            raise VoiceFoundryCommandError(f"task_not_{expected}")
        return task

    async def _replayed(
        self, command_id: str, task_id: str, payload: Mapping[str, object]
    ) -> bool:
        receipt = await self._repository.load_command(command_id)
        if receipt is None:
            return False
        if receipt.task_id != task_id or receipt.payload_digest != _digest(payload):
            raise VoiceFoundryCommandError("command_id_rebound_to_different_input")
        return True

    async def _record(
        self,
        command_id: str,
        task_id: str,
        payload: Mapping[str, object],
        accepted: Mapping[str, object],
    ) -> VoiceSupplyResult:
        await self._repository.accept_command(
            VoiceCommandAck(
                command_id=command_id,
                task_id=task_id,
                payload_digest=_digest(payload),
                accepted_result={"verb": payload["verb"], **dict(accepted)},
            )
        )
        return await self._supply.get(task_id)


__all__ = ["VoiceFoundryCommandError", "VoiceFoundryCommandService"]
