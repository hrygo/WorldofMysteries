"""Durable presentation-side persistence for Voice Foundry supply work."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import json

from domain.voice_identity import (
    ProviderVoiceRevision,
    VoiceBindingScope,
    VoiceIdentityAssurance,
    VoiceIdentityError,
)

from .database_manager import DatabaseManager, StorageError, VoiceFoundryTransaction


class VoiceFoundryConflict(StorageError):
    """A durable Foundry identity or revision is bound to different input."""


class VoiceFoundryCancelled(StorageError):
    """A cancelled task cannot advance into a new binding or provider action."""


class VoiceFoundryStage(StrEnum):
    REQUESTED = "requested"
    PREVIEWING = "previewing"
    AWAITING_SELECTION = "awaiting_selection"
    PROVISIONING = "provisioning"
    VALIDATING = "validating"
    AWAITING_REVIEW = "awaiting_review"
    PUBLISHED = "published"
    BINDING = "binding"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


_OPERATION_STATUSES = frozenset({"prepared", "unknown", "confirmed", "rejected"})
_TERMINAL_STAGES = frozenset({VoiceFoundryStage.FAILED, VoiceFoundryStage.CANCELLED})

# A candidate walks this ladder exactly once. The order encodes the real supply
# sequence, so no caller can shortcut "ready" straight to "published" and call
# it done; the two off-ladder states are terminal.
_CANDIDATE_STATE_ORDER = {
    "previewing": 0,
    "ready": 1,
    "selected": 2,
    "provisioning": 3,
    "validating": 4,
    "reviewing": 5,
    "published": 6,
}
_CANDIDATE_TERMINAL_STATES = frozenset({"failed", "cancelled"})
_CANDIDATE_STATES = frozenset(_CANDIDATE_STATE_ORDER) | _CANDIDATE_TERMINAL_STATES


def _require_forward_state(current: str, target: str) -> None:
    """Allow only a no-op, the single next rung, or a terminal exit.

    Skipping is refused as firmly as going backwards: a candidate that could
    jump from "ready" to "published" would let a caller claim publication
    without ever having been provisioned, validated or reviewed.
    """
    if current in _CANDIDATE_TERMINAL_STATES:
        raise VoiceFoundryConflict(
            "Terminal Voice Foundry candidate cannot change state"
        )
    if target in _CANDIDATE_TERMINAL_STATES:
        return
    if target == current:
        return
    if _CANDIDATE_STATE_ORDER[target] != _CANDIDATE_STATE_ORDER[current] + 1:
        raise VoiceFoundryConflict(
            "Voice Foundry candidate state must advance one step at a time"
        )


def _identifier(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 256
        or "\x00" in value
    ):
        raise StorageError(f"Invalid Voice Foundry {field}")
    return value


def _digest(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise StorageError(f"Invalid Voice Foundry {field}")
    return value


def _revision(value: int, field: str) -> int:
    if type(value) is not int or value < 1 or value >= 2**63:
        raise StorageError(f"Invalid Voice Foundry {field}")
    return value


def _text(value: str, field: str, *, minimum: int = 1, maximum: int = 256) -> str:
    _identifier(value, field)
    if not minimum <= len(value) <= maximum:
        raise StorageError(f"Invalid Voice Foundry {field}")
    return value


def _json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        raise StorageError("Voice Foundry JSON payload is invalid") from None


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _validate_scope(scope: VoiceBindingScope) -> VoiceBindingScope:
    if not isinstance(scope, VoiceBindingScope):
        raise StorageError("Voice Foundry task requires a typed scope")
    return scope


@dataclass(frozen=True, slots=True)
class VoiceExecutionScope:
    """What the requester asked to be rendered by, when it said.

    ``model_id`` and ``model_artifact_revision`` are nullable because the
    contract makes them nullable: "whatever this provider serves" is an
    expressible request, and for a deployment that has not pinned a model it
    is the honest answer. Recording the absence is what lets a later step
    tell "unpinned" apart from "pinned to something we have forgotten".
    """

    variant: str = "default"
    model_id: str | None = None
    model_artifact_revision: str | None = None


@dataclass(frozen=True, slots=True)
class VoiceCastBudget:
    """The limits one casting request set for itself.

    Stored rather than assumed, so a caller is never told a budget was
    honoured when nothing read it. The defaults are what this engine was
    already doing unasked, so a row written before the budget existed keeps
    describing itself truthfully.
    """

    candidate_count: int = 4
    timeout_ms: int = 120_000
    max_audio_bytes: int = 16 * 1024 * 1024


#: What an undeclared request looks like once it is durable.
DEFAULT_EXECUTION_SCOPE = VoiceExecutionScope()
DEFAULT_CAST_BUDGET = VoiceCastBudget()


@dataclass(frozen=True, slots=True)
class VoiceFoundryTaskSpec:
    task_id: str
    request_id: str
    request_digest: str
    authorization_ref: str
    scope: VoiceBindingScope
    persona_revision: str
    usage: str
    provider_instance: str
    public_traits: tuple[str, ...]
    voice_description: str
    reference_text: str
    validation_text: str
    origin_kind: str
    origin_ref: str
    origin_revision: int
    execution_scope: VoiceExecutionScope = DEFAULT_EXECUTION_SCOPE
    budget: VoiceCastBudget = DEFAULT_CAST_BUDGET

    def validated(self) -> "VoiceFoundryTaskSpec":
        scope = _validate_scope(self.scope)
        usage = _text(self.usage, "usage", maximum=16).casefold()
        origin_kind = _text(self.origin_kind, "origin kind", maximum=16).casefold()
        if usage not in {"dialogue", "narration"}:
            raise StorageError("Invalid Voice Foundry usage")
        if origin_kind not in {"content", "scene"}:
            raise StorageError("Invalid Voice Foundry origin kind")
        _validate_execution_scope(self.execution_scope)
        _validate_budget(self.budget)
        traits = tuple(
            _text(item, "public trait", maximum=64) for item in self.public_traits
        )
        if len(traits) > 32 or len(set(traits)) != len(traits):
            raise StorageError("Invalid Voice Foundry public traits")
        reference = _text(
            self.reference_text, "reference text", minimum=20, maximum=240
        )
        validation = _text(
            self.validation_text, "validation text", minimum=20, maximum=240
        )
        if reference == validation:
            raise StorageError("Voice Foundry validation text must differ from reference")
        origin_revision = self.origin_revision
        if type(origin_revision) is not int or origin_revision < 0:
            raise StorageError("Invalid Voice Foundry origin revision")
        return VoiceFoundryTaskSpec(
            task_id=_identifier(self.task_id, "task id"),
            request_id=_identifier(self.request_id, "request id"),
            request_digest=_digest(self.request_digest, "request digest"),
            authorization_ref=_identifier(
                self.authorization_ref, "authorization reference"
            ),
            scope=scope,
            persona_revision=_identifier(
                self.persona_revision, "persona revision"
            ),
            usage=usage,
            provider_instance=_identifier(
                self.provider_instance, "provider instance"
            ),
            public_traits=traits,
            voice_description=_text(
                self.voice_description,
                "voice description",
                maximum=1000,
            ),
            reference_text=reference,
            validation_text=validation,
            origin_kind=origin_kind,
            origin_ref=_identifier(self.origin_ref, "origin reference"),
            origin_revision=origin_revision,
            execution_scope=_execution_scope_of(self.execution_scope),
            budget=_budget_of(self.budget),
        )


def _execution_scope_of(value: object) -> VoiceExecutionScope:
    if not isinstance(value, VoiceExecutionScope):
        raise StorageError("Voice Foundry task requires a typed execution scope")
    variant = _text(value.variant, "execution variant", maximum=256)
    return VoiceExecutionScope(
        variant=variant,
        model_id=(
            None
            if value.model_id is None
            else _identifier(value.model_id, "execution model id")
        ),
        model_artifact_revision=(
            None
            if value.model_artifact_revision is None
            else _identifier(
                value.model_artifact_revision, "execution model artifact revision"
            )
        ),
    )


def _budget_of(value: object) -> VoiceCastBudget:
    if not isinstance(value, VoiceCastBudget):
        raise StorageError("Voice Foundry task requires a typed budget")
    if type(value.candidate_count) is not int or not 1 <= value.candidate_count <= 4:
        raise StorageError("Invalid Voice Foundry candidate count")
    if type(value.timeout_ms) is not int or not 1000 <= value.timeout_ms <= 3600000:
        raise StorageError("Invalid Voice Foundry timeout")
    if (
        type(value.max_audio_bytes) is not int
        or not 1 <= value.max_audio_bytes <= 134217728
    ):
        raise StorageError("Invalid Voice Foundry audio budget")
    return value


def _validate_execution_scope(value: object) -> None:
    _execution_scope_of(value)


def _validate_budget(value: object) -> None:
    _budget_of(value)


@dataclass(frozen=True, slots=True)
class VoiceFoundryTaskRecord:
    task_id: str
    request_id: str
    request_digest: str
    authorization_ref: str
    scope: VoiceBindingScope
    persona_revision: str
    usage: str
    provider_instance: str
    public_traits: tuple[str, ...]
    voice_description: str
    reference_text: str
    validation_text: str
    origin_kind: str
    origin_ref: str
    origin_revision: int
    stage: VoiceFoundryStage
    task_revision: int
    cancel_requested: bool
    operation_status: str
    required_actions: tuple[str, ...]
    reason_code: str | None
    created_at: str
    updated_at: str
    execution_scope: VoiceExecutionScope = DEFAULT_EXECUTION_SCOPE
    budget: VoiceCastBudget = DEFAULT_CAST_BUDGET


@dataclass(frozen=True, slots=True)
class VoiceCandidateRecord:
    candidate_id: str
    slot: int
    seed: int
    state: str
    preview_audio_digest: str
    recipe: Mapping[str, object]
    recipe_digest: str
    provider_candidate_id: str | None = None
    provider_candidate_revision: str | None = None
    reference_audio_digest: str | None = None
    reference_text_digest: str | None = None
    validation_audio_digest: str | None = None
    validation_text_digest: str | None = None


@dataclass(frozen=True, slots=True)
class VoiceFoundryOperationIntent:
    operation_id: str
    task_id: str
    stage: str
    attempt_identity: str
    idempotency_key: str
    payload: Mapping[str, object]
    payload_digest: str


@dataclass(frozen=True, slots=True)
class VoiceFoundryOperationRecord:
    operation_id: str
    task_id: str
    stage: str
    attempt_identity: str
    idempotency_key: str
    payload: Mapping[str, object]
    payload_digest: str
    status: str
    provider_result_ref: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class VoiceCommandAck:
    command_id: str
    task_id: str
    payload_digest: str
    accepted_result: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class VoiceEvidenceSnapshot:
    provider_instance: str
    evidence_id: str
    evidence_digest: str
    voice_id: str
    voice_revision: str
    snapshot: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class VoiceBindingRevisionRecord:
    binding_id: str
    binding_revision: int
    scope: VoiceBindingScope
    logical_voice_id: str
    persona_revision: str
    provider_instance: str
    provider_voice_id: str
    voice_revision: str
    model_catalog_revision: str | None
    evidence_id: str | None
    evidence_digest: str | None
    qualification: str
    status: str
    reserved_at_world_revision: int
    recorded_at: str


def _task_from_row(row: dict) -> VoiceFoundryTaskRecord:
    return VoiceFoundryTaskRecord(
        task_id=row["task_id"],
        request_id=row["request_id"],
        request_digest=row["request_digest"],
        authorization_ref=row["authorization_ref"],
        scope=VoiceBindingScope(
            owner_id=row["owner_id"],
            world_id=row["world_id"],
            worldline_id=row["worldline_id"],
            presentation_identity=row["presentation_identity"],
            phase=row["phase"],
            locale=row["locale"],
        ),
        persona_revision=row["persona_revision"],
        usage=row["usage"],
        provider_instance=row["provider_instance"],
        public_traits=tuple(json.loads(row["public_traits_json"])),
        voice_description=row["voice_description"],
        reference_text=row["reference_text"],
        validation_text=row["validation_text"],
        origin_kind=row["origin_kind"],
        origin_ref=row["origin_ref"],
        origin_revision=row["origin_revision"],
        stage=VoiceFoundryStage(row["stage"]),
        task_revision=row["task_revision"],
        cancel_requested=bool(row["cancel_requested"]),
        operation_status=row["operation_status"],
        required_actions=tuple(json.loads(row["required_actions_json"])),
        reason_code=row["reason_code"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        execution_scope=VoiceExecutionScope(
            variant=row["execution_variant"],
            model_id=row["execution_model_id"],
            model_artifact_revision=row["execution_model_artifact_revision"],
        ),
        budget=VoiceCastBudget(
            candidate_count=row["budget_candidate_count"],
            timeout_ms=row["budget_timeout_ms"],
            max_audio_bytes=row["budget_max_audio_bytes"],
        ),
    )


def _candidate_from_row(row: dict) -> VoiceCandidateRecord:
    return VoiceCandidateRecord(
        candidate_id=row["candidate_id"],
        slot=row["slot"],
        seed=row["seed"],
        state=row["state"],
        preview_audio_digest=row["preview_audio_digest"],
        recipe=json.loads(row["recipe_json"]),
        recipe_digest=row["recipe_digest"],
        provider_candidate_id=row["provider_candidate_id"],
        provider_candidate_revision=row["provider_candidate_revision"],
        reference_audio_digest=row["reference_audio_digest"],
        reference_text_digest=row["reference_text_digest"],
        validation_audio_digest=row["validation_audio_digest"],
        validation_text_digest=row["validation_text_digest"],
    )


def _operation_from_row(row: dict) -> VoiceFoundryOperationRecord:
    return VoiceFoundryOperationRecord(
        operation_id=row["operation_id"],
        task_id=row["task_id"],
        stage=row["stage"],
        attempt_identity=row["attempt_identity"],
        idempotency_key=row["idempotency_key"],
        payload=json.loads(row["payload_json"]),
        payload_digest=row["payload_digest"],
        status=row["status"],
        provider_result_ref=row["provider_result_ref"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _binding_from_row(row: dict) -> VoiceBindingRevisionRecord:
    return VoiceBindingRevisionRecord(
        binding_id=row["binding_id"],
        binding_revision=row["binding_revision"],
        scope=VoiceBindingScope(
            owner_id=row["owner_id"],
            world_id=row["world_id"],
            worldline_id=row["worldline_id"],
            presentation_identity=row["presentation_identity"],
            phase=row["phase"],
            locale=row["locale"],
        ),
        logical_voice_id=row["logical_voice_id"],
        persona_revision=row["persona_revision"],
        provider_instance=row["provider_instance"],
        provider_voice_id=row["provider_voice_id"],
        voice_revision=row["voice_revision"],
        model_catalog_revision=row["model_catalog_revision"],
        evidence_id=row["evidence_id"],
        evidence_digest=row["evidence_digest"],
        qualification=row["qualification"],
        status=row["status"],
        reserved_at_world_revision=row["reserved_at_world_revision"],
        recorded_at=row["recorded_at"],
    )


def _task_values(spec: VoiceFoundryTaskSpec, *, now: str) -> tuple:
    scope = spec.scope
    return (
        spec.task_id,
        spec.request_id,
        spec.request_digest,
        spec.authorization_ref,
        scope.owner_id,
        scope.world_id,
        scope.worldline_id,
        scope.presentation_identity,
        scope.phase,
        scope.locale,
        spec.persona_revision,
        spec.usage,
        spec.provider_instance,
        _json(list(spec.public_traits)),
        spec.voice_description,
        spec.reference_text,
        spec.validation_text,
        spec.origin_kind,
        spec.origin_ref,
        spec.origin_revision,
        VoiceFoundryStage.REQUESTED.value,
        1,
        0,
        "prepared",
        "[]",
        None,
        now,
        now,
        spec.execution_scope.variant,
        spec.execution_scope.model_id,
        spec.execution_scope.model_artifact_revision,
        spec.budget.candidate_count,
        spec.budget.timeout_ms,
        spec.budget.max_audio_bytes,
    )


class SQLiteVoiceFoundryRepository:
    """Single-writer repository for durable, non-domain voice supply state."""

    def __init__(self, database: DatabaseManager):
        self.database = database

    async def register_task(
        self, spec: VoiceFoundryTaskSpec
    ) -> VoiceFoundryTaskRecord:
        validated = spec.validated()

        def apply(tx: VoiceFoundryTransaction):
            existing = tx.execute(
                "SELECT * FROM voice_foundry_tasks WHERE request_id=?",
                (validated.request_id,),
            )
            if existing:
                if (
                    len(existing) != 1
                    or existing[0]["request_digest"] != validated.request_digest
                ):
                    raise VoiceFoundryConflict(
                        "Voice Foundry request id is bound to different input"
                    )
                return _task_from_row(existing[0])

            scope = validated.scope
            active = tx.execute(
                "SELECT * FROM voice_foundry_tasks "
                "WHERE owner_id=? AND world_id=? AND worldline_id=? "
                "AND presentation_identity=? AND phase=? AND locale=? "
                "AND persona_revision=? AND request_digest=? AND provider_instance=? "
                "AND stage NOT IN ('failed','cancelled')",
                (
                    scope.owner_id,
                    scope.world_id,
                    scope.worldline_id,
                    scope.presentation_identity,
                    scope.phase,
                    scope.locale,
                    validated.persona_revision,
                    validated.request_digest,
                    validated.provider_instance,
                ),
            )
            if active:
                if len(active) != 1:
                    raise VoiceFoundryConflict(
                        "Voice Foundry active scope is ambiguous"
                    )
                return _task_from_row(active[0])

            now = _now()
            tx.execute(
                "INSERT INTO voice_foundry_tasks("
                "task_id,request_id,request_digest,authorization_ref,owner_id,world_id,"
                "worldline_id,presentation_identity,phase,locale,persona_revision,usage,"
                "provider_instance,public_traits_json,voice_description,reference_text,"
                "validation_text,origin_kind,origin_ref,origin_revision,stage,task_revision,"
                "cancel_requested,operation_status,required_actions_json,reason_code,"
                "created_at,updated_at,execution_variant,execution_model_id,"
                "execution_model_artifact_revision,budget_candidate_count,"
                "budget_timeout_ms,budget_max_audio_bytes"
                ") VALUES (" + ",".join("?" * 34) + ")",
                _task_values(validated, now=now),
            )
            rows = tx.execute(
                "SELECT * FROM voice_foundry_tasks WHERE task_id=?",
                (validated.task_id,),
            )
            return _task_from_row(rows[0])

        return await self.database.voice_foundry_write(apply)

    async def load_task(self, task_id: str) -> VoiceFoundryTaskRecord:
        rows = await self.database.read_world(
            "SELECT * FROM voice_foundry_tasks WHERE task_id=?",
            (_identifier(task_id, "task id"),),
        )
        if len(rows) != 1:
            raise StorageError("Voice Foundry task not found")
        return _task_from_row(rows[0])

    async def set_stage(
        self,
        task_id: str,
        *,
        expected_revision: int,
        stage: VoiceFoundryStage,
        operation_status: str,
        required_actions: Sequence[str],
        reason_code: str | None = None,
    ) -> VoiceFoundryTaskRecord:
        task_id = _identifier(task_id, "task id")
        expected_revision = _revision(expected_revision, "expected task revision")
        stage = VoiceFoundryStage(stage)
        if operation_status not in _OPERATION_STATUSES:
            raise StorageError("Invalid Voice Foundry operation status")
        actions = tuple(
            _text(action, "required action", maximum=64) for action in required_actions
        )
        if len(actions) > 8 or len(set(actions)) != len(actions):
            raise StorageError("Invalid Voice Foundry required actions")
        if reason_code is not None:
            reason_code = _text(reason_code, "reason code", maximum=128)

        def apply(tx: VoiceFoundryTransaction):
            current = self._require_task(tx, task_id)
            self._require_revision(current, expected_revision)
            if current.cancel_requested and stage is not VoiceFoundryStage.CANCELLED:
                raise VoiceFoundryCancelled(
                    "Voice Foundry task was cancelled before the stage change"
                )
            updated_at = _now()
            tx.execute(
                "UPDATE voice_foundry_tasks SET stage=?,task_revision=?,"
                "operation_status=?,required_actions_json=?,reason_code=?,updated_at=? "
                "WHERE task_id=? AND task_revision=?",
                (
                    stage.value,
                    expected_revision + 1,
                    operation_status,
                    _json(list(actions)),
                    reason_code,
                    updated_at,
                    task_id,
                    expected_revision,
                ),
            )
            return self._require_task(tx, task_id)

        return await self.database.voice_foundry_write(apply)

    async def request_cancel(
        self,
        task_id: str,
        *,
        expected_revision: int,
        reason_code: str | None = None,
    ) -> VoiceFoundryTaskRecord:
        task_id = _identifier(task_id, "task id")
        expected_revision = _revision(expected_revision, "expected task revision")

        def apply(tx: VoiceFoundryTransaction):
            current = self._require_task(tx, task_id)
            if current.cancel_requested:
                return current
            self._require_revision(current, expected_revision)
            tx.execute(
                "UPDATE voice_foundry_tasks SET stage=?,task_revision=?,"
                "cancel_requested=1,operation_status='rejected',required_actions_json='[]',"
                "reason_code=?,updated_at=? WHERE task_id=? AND task_revision=?",
                (
                    VoiceFoundryStage.CANCELLED.value,
                    expected_revision + 1,
                    reason_code,
                    _now(),
                    task_id,
                    expected_revision,
                ),
            )
            return self._require_task(tx, task_id)

        return await self.database.voice_foundry_write(apply)

    async def add_candidate(
        self,
        task_id: str,
        *,
        expected_revision: int,
        candidate: VoiceCandidateRecord,
    ) -> VoiceFoundryTaskRecord:
        task_id = _identifier(task_id, "task id")
        expected_revision = _revision(expected_revision, "expected task revision")
        self._validate_candidate(candidate)

        def apply(tx: VoiceFoundryTransaction):
            current = self._require_task(tx, task_id)
            self._require_revision(current, expected_revision)
            existing = tx.execute(
                "SELECT * FROM voice_foundry_candidates "
                "WHERE task_id=? AND candidate_id=?",
                (task_id, candidate.candidate_id),
            )
            if existing:
                if _candidate_from_row(existing[0]) != candidate:
                    raise VoiceFoundryConflict(
                        "Voice Foundry candidate id is bound to different content"
                    )
                return current
            now = _now()
            tx.execute(
                "INSERT INTO voice_foundry_candidates("
                "task_id,candidate_id,slot,seed,state,preview_audio_digest,recipe_json,"
                "recipe_digest,provider_candidate_id,provider_candidate_revision,"
                "reference_audio_digest,reference_text_digest,validation_audio_digest,"
                "validation_text_digest,created_at,updated_at"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    task_id,
                    candidate.candidate_id,
                    candidate.slot,
                    candidate.seed,
                    candidate.state,
                    candidate.preview_audio_digest,
                    _json(dict(candidate.recipe)),
                    candidate.recipe_digest,
                    candidate.provider_candidate_id,
                    candidate.provider_candidate_revision,
                    candidate.reference_audio_digest,
                    candidate.reference_text_digest,
                    candidate.validation_audio_digest,
                    candidate.validation_text_digest,
                    now,
                    now,
                ),
            )
            tx.execute(
                "UPDATE voice_foundry_tasks SET task_revision=?,updated_at=? "
                "WHERE task_id=? AND task_revision=?",
                (expected_revision + 1, now, task_id, expected_revision),
            )
            return self._require_task(tx, task_id)

        return await self.database.voice_foundry_write(apply)

    async def load_candidate(
        self, task_id: str, candidate_id: str
    ) -> VoiceCandidateRecord:
        rows = await self.database.read_world(
            "SELECT * FROM voice_foundry_candidates "
            "WHERE task_id=? AND candidate_id=?",
            (
                _identifier(task_id, "task id"),
                _identifier(candidate_id, "candidate id"),
            ),
        )
        if len(rows) != 1:
            raise StorageError("Voice Foundry candidate not found")
        return _candidate_from_row(rows[0])

    async def load_candidates(self, task_id: str) -> tuple[VoiceCandidateRecord, ...]:
        """Every candidate minted for one task, in slot order.

        A task holds at most ``MAX_CANDIDATES`` slots, so the whole set is one
        small read.  Ordering by slot is what makes the public projection
        stable: the same task always presents its candidates in the same
        sequence, whichever order they finished previewing in.
        """
        rows = await self.database.read_world(
            "SELECT * FROM voice_foundry_candidates WHERE task_id=? ORDER BY slot ASC",
            (_identifier(task_id, "task id"),),
        )
        return tuple(_candidate_from_row(row) for row in rows)

    async def load_scope_tasks(
        self, scope: VoiceBindingScope
    ) -> tuple[VoiceFoundryTaskRecord, ...]:
        """Every supply task ever opened for one presentation scope.

        Pre-warming a scene asks what each identity already has before it asks
        for anything new, so this has to include finished and abandoned tasks,
        not just the live one — otherwise a scope that failed once looks like a
        scope that was never asked.  Ordered by creation so a caller reading
        the list sees the same history every time.
        """
        checked = _validate_scope(scope)
        rows = await self.database.read_world(
            "SELECT * FROM voice_foundry_tasks "
            "WHERE owner_id=? AND world_id=? AND worldline_id=? "
            "AND presentation_identity=? AND phase=? AND locale=? "
            "ORDER BY created_at ASC, task_id ASC",
            (
                checked.owner_id,
                checked.world_id,
                checked.worldline_id,
                checked.presentation_identity,
                checked.phase,
                checked.locale,
            ),
        )
        return tuple(_task_from_row(row) for row in rows)

    async def load_tasks_page(
        self,
        *,
        page_size: int,
        after_created_at: str | None = None,
        after_task_id: str | None = None,
        stage: str | None = None,
    ) -> tuple[VoiceFoundryTaskRecord, ...]:
        """One keyset page of this world's supply tasks, oldest first.

        The window is anchored on ``(created_at, task_id)`` rather than an
        offset so a task registered or cancelled while a caller pages cannot
        slide a row into or out of the page it is reading. ``stage`` filters
        server-side, and the engine serves a single world, so no owner or
        world predicate is applied here.
        """
        if type(page_size) is not int or not 1 <= page_size <= 100:
            raise StorageError("Invalid Voice Foundry page size")
        clauses: list[str] = []
        params: list[object] = []
        if stage is not None:
            clauses.append("stage=?")
            params.append(_text(stage, "stage", maximum=32))
        if after_created_at is not None and after_task_id is not None:
            clauses.append("(created_at>? OR (created_at=? AND task_id>?))")
            params.extend([after_created_at, after_created_at, after_task_id])
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(page_size)
        rows = await self.database.read_world(
            "SELECT * FROM voice_foundry_tasks"
            f"{where} ORDER BY created_at ASC, task_id ASC LIMIT ?",
            tuple(params),
        )
        return tuple(_task_from_row(row) for row in rows)

    async def update_candidate(
        self,
        task_id: str,
        *,
        expected_revision: int,
        candidate_id: str,
        state: str | None = None,
        provider_candidate_id: str | None = None,
        provider_candidate_revision: str | None = None,
        reference_audio_digest: str | None = None,
        reference_text_digest: str | None = None,
        validation_audio_digest: str | None = None,
        validation_text_digest: str | None = None,
    ) -> VoiceCandidateRecord:
        """Attach provider-owned facts to a candidate that already exists.

        Only the fields the provider actually reported may be patched, and the
        task revision is the CAS guard. Two rules make this safe to resume:

        * A provider identity, once written, is immutable. Re-pointing a slot
          at a different provider candidate would be a silent re-cast, so it
          is refused rather than applied.
        * Candidate state only moves forward, and a terminal state is final.
          A failed candidate cannot quietly re-enter review.
        """
        task_id = _identifier(task_id, "task id")
        expected_revision = _revision(expected_revision, "expected task revision")
        candidate_id = _identifier(candidate_id, "candidate id")
        patches: dict[str, str] = {}
        for column, value in (
            ("provider_candidate_id", provider_candidate_id),
            ("provider_candidate_revision", provider_candidate_revision),
            ("reference_audio_digest", reference_audio_digest),
            ("reference_text_digest", reference_text_digest),
            ("validation_audio_digest", validation_audio_digest),
            ("validation_text_digest", validation_text_digest),
        ):
            if value is None:
                continue
            if column.endswith("digest"):
                patches[column] = _digest(value, column)
            else:
                patches[column] = _identifier(value, column)
        if state is not None:
            if state not in _CANDIDATE_STATES:
                raise StorageError("Invalid Voice Foundry candidate state")
            patches["state"] = state
        if not patches:
            raise StorageError("Voice Foundry candidate update changes nothing")

        def apply(tx: VoiceFoundryTransaction):
            current_task = self._require_task(tx, task_id)
            self._require_revision(current_task, expected_revision)
            rows = tx.execute(
                "SELECT * FROM voice_foundry_candidates "
                "WHERE task_id=? AND candidate_id=?",
                (task_id, candidate_id),
            )
            if len(rows) != 1:
                raise StorageError("Voice Foundry candidate not found")
            current = _candidate_from_row(rows[0])
            if (
                current.provider_candidate_id is not None
                and "provider_candidate_id" in patches
                and patches["provider_candidate_id"] != current.provider_candidate_id
            ):
                raise VoiceFoundryConflict(
                    "Voice Foundry candidate identity is already bound"
                )
            if (
                current.provider_candidate_revision is not None
                and
                "provider_candidate_revision" in patches
                and patches["provider_candidate_revision"]
                != current.provider_candidate_revision
            ):
                # A candidate's *identity* is immutable; its revision is not.
                # The provider moves the revision as the design is confirmed,
                # validated and published, and ``publish`` is conditional on
                # the revision that exists then — so freezing the one create
                # handed out makes publication impossible against a real
                # provider. What may not happen is a re-point at a revision
                # nobody ever reported, so a new value has to be one this
                # engine durably recorded from the provider.
                reported = tx.execute(
                    "SELECT 1 FROM voice_foundry_operations "
                    "WHERE task_id=? AND provider_result_ref=? "
                    "AND status='confirmed' LIMIT 1",
                    (task_id, patches["provider_candidate_revision"]),
                )
                if not reported:
                    raise VoiceFoundryConflict(
                        "Voice Foundry candidate revision was never reported"
                    )
            if "state" in patches:
                _require_forward_state(current.state, patches["state"])
            now = _now()
            assignments = ",".join(f"{column}=?" for column in patches)
            tx.execute(
                f"UPDATE voice_foundry_candidates SET {assignments},updated_at=? "
                f"WHERE task_id=? AND candidate_id=?",
                (*patches.values(), now, task_id, candidate_id),
            )
            tx.execute(
                "UPDATE voice_foundry_tasks SET task_revision=?,updated_at=? "
                "WHERE task_id=? AND task_revision=?",
                (expected_revision + 1, now, task_id, expected_revision),
            )
            return _candidate_from_row(
                tx.execute(
                    "SELECT * FROM voice_foundry_candidates "
                    "WHERE task_id=? AND candidate_id=?",
                    (task_id, candidate_id),
                )[0]
            )

        return await self.database.voice_foundry_write(apply)

    async def adopt_published_candidate(
        self,
        task_id: str,
        *,
        expected_revision: int,
        candidate_id: str,
        provider_candidate_id: str,
        provider_candidate_revision: str,
    ) -> VoiceCandidateRecord:
        """Park a candidate on a voice the provider published in an earlier run.

        This is the one door out of the candidate ladder that does not walk it.
        ``_require_forward_state`` exists so nobody can claim publication for a
        voice that was never provisioned, validated and reviewed, and that
        objection is correct for every caller that walks the ladder itself.
        Reuse is the case it cannot see: the provisioning, the cross-text
        validation and the human verdict all happened — upstream, before this
        task existed, and the published evidence says so. So the skip is not a
        loosened rule but a named operation with its own preconditions, which
        is why it cannot be reached by passing a state to
        :meth:`update_candidate`.

        What it still refuses, because none of it is part of the exception:

        * a candidate that is not mid-provisioning — adoption names the moment
          it is meant to happen, and any other moment is a different claim;
        * a candidate already bound to a provider identity — a re-adoption
          under a different design would be a silent re-cast;
        * a task whose revision has moved, which is the usual CAS guard.
        """
        task_id = _identifier(task_id, "task id")
        expected_revision = _revision(expected_revision, "expected task revision")
        candidate_id = _identifier(candidate_id, "candidate id")
        provider_candidate_id = _identifier(
            provider_candidate_id, "provider candidate id"
        )
        provider_candidate_revision = _identifier(
            provider_candidate_revision, "provider candidate revision"
        )

        def apply(tx: VoiceFoundryTransaction):
            current_task = self._require_task(tx, task_id)
            self._require_revision(current_task, expected_revision)
            rows = tx.execute(
                "SELECT * FROM voice_foundry_candidates "
                "WHERE task_id=? AND candidate_id=?",
                (task_id, candidate_id),
            )
            if len(rows) != 1:
                raise StorageError("Voice Foundry candidate not found")
            current = _candidate_from_row(rows[0])
            if current.state != "provisioning":
                raise VoiceFoundryConflict(
                    "Voice Foundry candidate is not awaiting adoption"
                )
            if current.provider_candidate_id is not None:
                raise VoiceFoundryConflict(
                    "Voice Foundry candidate identity is already bound"
                )
            now = _now()
            tx.execute(
                "UPDATE voice_foundry_candidates SET state='published',"
                "provider_candidate_id=?,provider_candidate_revision=?,"
                "updated_at=? WHERE task_id=? AND candidate_id=?",
                (
                    provider_candidate_id,
                    provider_candidate_revision,
                    now,
                    task_id,
                    candidate_id,
                ),
            )
            tx.execute(
                "UPDATE voice_foundry_tasks SET task_revision=?,updated_at=? "
                "WHERE task_id=? AND task_revision=?",
                (expected_revision + 1, now, task_id, expected_revision),
            )
            return _candidate_from_row(
                tx.execute(
                    "SELECT * FROM voice_foundry_candidates "
                    "WHERE task_id=? AND candidate_id=?",
                    (task_id, candidate_id),
                )[0]
            )

        return await self.database.voice_foundry_write(apply)

    async def record_operation(
        self, intent: VoiceFoundryOperationIntent
    ) -> VoiceFoundryOperationRecord:
        if not isinstance(intent, VoiceFoundryOperationIntent):
            raise StorageError("Voice Foundry operation requires a typed intent")
        operation_id = _identifier(intent.operation_id, "operation id")
        task_id = _identifier(intent.task_id, "task id")
        stage = _text(intent.stage, "operation stage", maximum=64)
        attempt_identity = _identifier(
            intent.attempt_identity, "attempt identity"
        )
        idempotency_key = _identifier(
            intent.idempotency_key, "idempotency key"
        )
        payload_digest = _digest(intent.payload_digest, "operation payload digest")
        payload_json = _json(dict(intent.payload))

        def apply(tx: VoiceFoundryTransaction):
            existing = tx.execute(
                "SELECT * FROM voice_foundry_operations WHERE operation_id=?",
                (operation_id,),
            )
            if existing:
                current = _operation_from_row(existing[0])
                if (
                    current.task_id != task_id
                    or current.stage != stage
                    or current.attempt_identity != attempt_identity
                    or current.idempotency_key != idempotency_key
                    or current.payload_digest != payload_digest
                    or current.payload != dict(intent.payload)
                ):
                    raise VoiceFoundryConflict(
                        "Voice Foundry operation id is bound to different input"
                    )
                return current
            now = _now()
            tx.execute(
                "INSERT INTO voice_foundry_operations("
                "operation_id,task_id,stage,attempt_identity,idempotency_key,"
                "payload_json,payload_digest,status,provider_result_ref,created_at,updated_at"
                ") VALUES (?,?,?,?,?,?,?,'prepared',NULL,?,?)",
                (
                    operation_id,
                    task_id,
                    stage,
                    attempt_identity,
                    idempotency_key,
                    payload_json,
                    payload_digest,
                    now,
                    now,
                ),
            )
            return _operation_from_row(
                tx.execute(
                    "SELECT * FROM voice_foundry_operations WHERE operation_id=?",
                    (operation_id,),
                )[0]
            )

        return await self.database.voice_foundry_write(apply)

    async def mark_operation_unknown(
        self, operation_id: str
    ) -> VoiceFoundryOperationRecord:
        operation_id = _identifier(operation_id, "operation id")

        def apply(tx: VoiceFoundryTransaction):
            current = self._require_operation(tx, operation_id)
            if current.status == "unknown":
                return current
            if current.status != "prepared":
                raise VoiceFoundryConflict(
                    "Only a prepared Voice Foundry operation can become unknown"
                )
            tx.execute(
                "UPDATE voice_foundry_operations SET status='unknown',updated_at=? "
                "WHERE operation_id=?",
                (_now(), operation_id),
            )
            return self._require_operation(tx, operation_id)

        return await self.database.voice_foundry_write(apply)

    async def confirm_operation(
        self,
        operation_id: str,
        *,
        expected_status: str,
        provider_result_ref: str,
    ) -> VoiceFoundryOperationRecord:
        operation_id = _identifier(operation_id, "operation id")
        if expected_status not in _OPERATION_STATUSES:
            raise StorageError("Invalid Voice Foundry operation status")
        provider_result_ref = _identifier(
            provider_result_ref, "provider result reference"
        )

        def apply(tx: VoiceFoundryTransaction):
            current = self._require_operation(tx, operation_id)
            if current.status == "confirmed":
                if current.provider_result_ref == provider_result_ref:
                    return current
                raise VoiceFoundryConflict(
                    "Confirmed Voice Foundry operation result changed"
                )
            if current.status != expected_status:
                raise VoiceFoundryConflict(
                    "Voice Foundry operation status does not match"
                )
            tx.execute(
                "UPDATE voice_foundry_operations SET status='confirmed',"
                "provider_result_ref=?,updated_at=? WHERE operation_id=?",
                (provider_result_ref, _now(), operation_id),
            )
            return self._require_operation(tx, operation_id)

        return await self.database.voice_foundry_write(apply)

    async def load_operation(
        self, operation_id: str
    ) -> VoiceFoundryOperationRecord:
        rows = await self.database.read_world(
            "SELECT * FROM voice_foundry_operations WHERE operation_id=?",
            (_identifier(operation_id, "operation id"),),
        )
        if len(rows) != 1:
            raise StorageError("Voice Foundry operation not found")
        return _operation_from_row(rows[0])

    async def accept_command(
        self, command: VoiceCommandAck
    ) -> VoiceCommandAck:
        if not isinstance(command, VoiceCommandAck):
            raise StorageError("Voice Foundry command requires a typed value")
        command_id = _identifier(command.command_id, "command id")
        task_id = _identifier(command.task_id, "task id")
        payload_digest = _digest(command.payload_digest, "command payload digest")
        result_json = _json(dict(command.accepted_result))

        def apply(tx: VoiceFoundryTransaction):
            existing = tx.execute(
                "SELECT * FROM voice_foundry_commands WHERE command_id=?",
                (command_id,),
            )
            if existing:
                if (
                    existing[0]["task_id"] != task_id
                    or existing[0]["payload_digest"] != payload_digest
                    or existing[0]["accepted_result_json"] != result_json
                ):
                    raise VoiceFoundryConflict(
                        "Voice Foundry command id is bound to different input"
                    )
                return VoiceCommandAck(
                    command_id=command_id,
                    task_id=task_id,
                    payload_digest=payload_digest,
                    accepted_result=json.loads(existing[0]["accepted_result_json"]),
                )
            tx.execute(
                "INSERT INTO voice_foundry_commands("
                "command_id,task_id,payload_digest,accepted_result_json,created_at"
                ") VALUES (?,?,?,?,?)",
                (command_id, task_id, payload_digest, result_json, _now()),
            )
            return command

        return await self.database.voice_foundry_write(apply)

    async def load_command(self, command_id: str) -> VoiceCommandAck | None:
        """The receipt for one command id, or ``None`` if it never ran.

        A command id is the caller's idempotency key. Recording a receipt
        without ever reading one back makes a replay indistinguishable from a
        first attempt, so the caller could only answer a repeat by colliding
        with the revision its own first attempt already moved. This is what
        lets a repeated command return its original answer instead.
        """
        rows = await self.database.read_world(
            "SELECT command_id,task_id,payload_digest,accepted_result_json "
            "FROM voice_foundry_commands WHERE command_id=?",
            (_identifier(command_id, "command id"),),
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise StorageError("Voice Foundry command receipt is duplicated")
        return VoiceCommandAck(
            command_id=rows[0]["command_id"],
            task_id=rows[0]["task_id"],
            payload_digest=rows[0]["payload_digest"],
            accepted_result=json.loads(rows[0]["accepted_result_json"]),
        )

    async def load_evidence(
        self, provider_instance: str, evidence_id: str
    ) -> VoiceEvidenceSnapshot:
        rows = await self.database.read_world(
            "SELECT * FROM voice_evidence_snapshots "
            "WHERE provider_instance=? AND evidence_id=? "
            "ORDER BY created_at DESC LIMIT 1",
            (
                _identifier(provider_instance, "provider instance"),
                _identifier(evidence_id, "evidence id"),
            ),
        )
        if len(rows) != 1:
            raise StorageError("Voice Foundry evidence not found")
        row = rows[0]
        return VoiceEvidenceSnapshot(
            provider_instance=row["provider_instance"],
            evidence_id=row["evidence_id"],
            evidence_digest=row["evidence_digest"],
            voice_id=row["voice_id"],
            voice_revision=row["voice_revision"],
            snapshot=json.loads(row["snapshot_json"]),
        )

    async def commit_ready_binding(
        self,
        task_id: str,
        *,
        expected_task_revision: int,
        evidence: VoiceEvidenceSnapshot,
        binding_id: str,
    ) -> VoiceFoundryTaskRecord:
        task_id = _identifier(task_id, "task id")
        expected_task_revision = _revision(
            expected_task_revision, "expected task revision"
        )
        binding_id = _identifier(binding_id, "binding id")
        if not isinstance(evidence, VoiceEvidenceSnapshot):
            raise StorageError("Voice Foundry binding requires typed evidence")
        provider_instance = _identifier(
            evidence.provider_instance, "provider instance"
        )
        evidence_id = _identifier(evidence.evidence_id, "evidence id")
        evidence_digest = _digest(evidence.evidence_digest, "evidence digest")
        voice_id = _identifier(evidence.voice_id, "voice id")
        voice_revision = _identifier(evidence.voice_revision, "voice revision")
        snapshot_json = _json(dict(evidence.snapshot))

        def apply(tx: VoiceFoundryTransaction):
            task = self._require_task(tx, task_id)
            if task.cancel_requested:
                raise VoiceFoundryCancelled(
                    "Cancelled Voice Foundry task cannot bind a voice"
                )
            self._require_revision(task, expected_task_revision)
            if task.stage not in {
                VoiceFoundryStage.PUBLISHED,
                VoiceFoundryStage.BINDING,
            }:
                raise VoiceFoundryConflict(
                    "Voice Foundry task is not ready to bind"
                )
            if evidence.provider_instance != task.provider_instance:
                raise VoiceFoundryConflict(
                    "Voice Foundry evidence provider does not match the task"
                )

            snapshot = evidence.snapshot.get("execution")
            if not isinstance(snapshot, Mapping):
                raise StorageError("Voice Foundry evidence execution scope is missing")
            # The artifact revision is required by the evidence contract, and it
            # is written onto the binding as one third of its review. Leaving it
            # out produced a binding that could not be read back at all: its
            # review was an incomplete triple, so loading it raised instead of
            # rendering. Refusing here keeps a published voice from being
            # stranded one layer down.
            model_artifact_revision = _identifier(
                snapshot.get("model_artifact_revision"), "model artifact revision"
            )
            # The catalogue revision is a sealed-render pin, but the evidence
            # contract does not carry one — a bundle that satisfies the contract
            # has no such field to give. It stays optional here and is required
            # where it actually matters: a render without it is refused, and
            # says so.
            raw_catalog_revision = snapshot.get("model_catalog_revision")
            model_catalog_revision = (
                _identifier(raw_catalog_revision, "model catalog revision")
                if raw_catalog_revision is not None
                else None
            )
            try:
                addressable = ProviderVoiceRevision(
                    provider_instance=provider_instance,
                    voice_id=voice_id,
                    assurance=VoiceIdentityAssurance.CONTENT_ADDRESSED,
                    voice_revision=voice_revision,
                    model_catalog_revision=model_catalog_revision,
                    revoked=False,
                )
            except VoiceIdentityError as exc:
                raise StorageError(
                    "Voice Foundry evidence does not address a renderable voice"
                ) from exc

            existing_evidence = tx.execute(
                "SELECT snapshot_json FROM voice_evidence_snapshots "
                "WHERE provider_instance=? AND evidence_id=? AND evidence_digest=?",
                (provider_instance, evidence_id, evidence_digest),
            )
            if existing_evidence:
                if existing_evidence[0]["snapshot_json"] != snapshot_json:
                    raise VoiceFoundryConflict(
                        "Voice Foundry evidence digest is bound to different content"
                    )
            else:
                tx.execute(
                    "INSERT INTO voice_evidence_snapshots("
                    "provider_instance,evidence_id,evidence_digest,voice_id,"
                    "voice_revision,snapshot_json,created_at"
                    ") VALUES (?,?,?,?,?,?,?)",
                    (
                        provider_instance,
                        evidence_id,
                        evidence_digest,
                        voice_id,
                        voice_revision,
                        snapshot_json,
                        _now(),
                    ),
                )

            scope = task.scope
            # The row key and the row's scope have to be the same fact.
            # Both uniqueness checks below would pass for a key borrowed from
            # another scope: the borrowed key is either unused, or it belongs
            # to a scope this task is not. The row would satisfy the
            # constraint and still be unreachable, because everything that
            # renders a voice looks it up by scope.
            if binding_id != scope.binding_identity:
                raise VoiceFoundryConflict(
                    "Voice Foundry binding id does not match the task scope"
                )
            scope_rows = tx.execute(
                "SELECT binding_id FROM voice_bindings WHERE owner_id=? AND world_id=? "
                "AND worldline_id=? AND presentation_identity=? AND phase=? AND locale=?",
                (
                    scope.owner_id,
                    scope.world_id,
                    scope.worldline_id,
                    scope.presentation_identity,
                    scope.phase,
                    scope.locale,
                ),
            )
            if scope_rows:
                raise VoiceFoundryConflict(
                    "Voice Foundry scope already has a current binding"
                )
            binding_id_rows = tx.execute(
                "SELECT binding_id FROM voice_bindings WHERE binding_id=?",
                (binding_id,),
            )
            if binding_id_rows:
                raise VoiceFoundryConflict(
                    "Voice Foundry binding id is already in use"
                )

            world_revision = tx.execute(
                "SELECT revision FROM world_meta WHERE singleton=1"
            )[0]["revision"]
            recorded_at = _now()
            tx.execute(
                "INSERT INTO voice_bindings("
                "binding_id,owner_id,world_id,worldline_id,presentation_identity,"
                "phase,locale,logical_voice_id,persona_revision,provider_instance,"
                "provider_voice_id,assurance,voice_revision,model_catalog_revision,"
                "provider_revoked,binding_revision,status,reserved_at_world_revision,"
                "evidence_id,evidence_digest,model_artifact_revision"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,1,'reserved',?,?,?,?)",
                (
                    binding_id,
                    scope.owner_id,
                    scope.world_id,
                    scope.worldline_id,
                    scope.presentation_identity,
                    scope.phase,
                    scope.locale,
                    voice_id,
                    task.persona_revision,
                    provider_instance,
                    voice_id,
                    "content_addressed",
                    voice_revision,
                    addressable.model_catalog_revision,
                    world_revision,
                    evidence_id,
                    evidence_digest,
                    model_artifact_revision,
                ),
            )
            self._insert_binding_revision(
                tx,
                task=task,
                binding_id=binding_id,
                binding_revision=1,
                logical_voice_id=voice_id,
                provider_instance=provider_instance,
                provider_voice_id=voice_id,
                voice_revision=voice_revision,
                model_catalog_revision=model_catalog_revision,
                evidence_id=evidence_id,
                evidence_digest=evidence_digest,
                status="reserved",
                world_revision=world_revision,
                recorded_at=recorded_at,
            )
            tx.execute(
                "UPDATE voice_bindings SET binding_revision=2,status='active' "
                "WHERE binding_id=? AND binding_revision=1",
                (binding_id,),
            )
            self._insert_binding_revision(
                tx,
                task=task,
                binding_id=binding_id,
                binding_revision=2,
                logical_voice_id=voice_id,
                provider_instance=provider_instance,
                provider_voice_id=voice_id,
                voice_revision=voice_revision,
                model_catalog_revision=model_catalog_revision,
                evidence_id=evidence_id,
                evidence_digest=evidence_digest,
                status="active",
                world_revision=world_revision,
                recorded_at=recorded_at,
            )
            tx.execute(
                "UPDATE voice_foundry_tasks SET stage=?,task_revision=?,"
                "operation_status='confirmed',required_actions_json='[]',"
                "reason_code=NULL,updated_at=? WHERE task_id=? AND task_revision=?",
                (
                    VoiceFoundryStage.READY.value,
                    expected_task_revision + 1,
                    recorded_at,
                    task_id,
                    expected_task_revision,
                ),
            )
            return self._require_task(tx, task_id)

        return await self.database.voice_foundry_write(apply)

    async def load_binding_history(
        self, binding_id: str
    ) -> tuple[VoiceBindingRevisionRecord, ...]:
        rows = await self.database.read_world(
            "SELECT * FROM voice_binding_revisions "
            "WHERE binding_id=? ORDER BY binding_revision",
            (_identifier(binding_id, "binding id"),),
        )
        if not rows:
            raise StorageError("Voice Foundry binding history not found")
        return tuple(_binding_from_row(row) for row in rows)

    @staticmethod
    def _require_task(
        tx: VoiceFoundryTransaction, task_id: str
    ) -> VoiceFoundryTaskRecord:
        rows = tx.execute(
            "SELECT * FROM voice_foundry_tasks WHERE task_id=?", (task_id,)
        )
        if len(rows) != 1:
            raise StorageError("Voice Foundry task not found")
        return _task_from_row(rows[0])

    @staticmethod
    def _require_operation(
        tx: VoiceFoundryTransaction, operation_id: str
    ) -> VoiceFoundryOperationRecord:
        rows = tx.execute(
            "SELECT * FROM voice_foundry_operations WHERE operation_id=?",
            (operation_id,),
        )
        if len(rows) != 1:
            raise StorageError("Voice Foundry operation not found")
        return _operation_from_row(rows[0])

    @staticmethod
    def _require_revision(
        current: VoiceFoundryTaskRecord, expected_revision: int
    ) -> None:
        if current.task_revision != expected_revision:
            raise VoiceFoundryConflict(
                "Expected Voice Foundry task revision does not match"
            )

    @staticmethod
    def _validate_candidate(candidate: VoiceCandidateRecord) -> None:
        if not isinstance(candidate, VoiceCandidateRecord):
            raise StorageError("Voice Foundry candidate requires a typed record")
        _identifier(candidate.candidate_id, "candidate id")
        if type(candidate.slot) is not int or not 1 <= candidate.slot <= 4:
            raise StorageError("Invalid Voice Foundry candidate slot")
        if (
            type(candidate.seed) is not int
            or candidate.seed < 0
            or candidate.seed > 4294967295
        ):
            raise StorageError("Invalid Voice Foundry candidate seed")
        _digest(candidate.preview_audio_digest, "preview audio digest")
        _digest(candidate.recipe_digest, "recipe digest")
        _json(dict(candidate.recipe))
        for field, value in (
            ("provider candidate id", candidate.provider_candidate_id),
            (
                "provider candidate revision",
                candidate.provider_candidate_revision,
            ),
            ("reference audio digest", candidate.reference_audio_digest),
            ("reference text digest", candidate.reference_text_digest),
            ("validation audio digest", candidate.validation_audio_digest),
            ("validation text digest", candidate.validation_text_digest),
        ):
            if value is not None:
                if field.endswith("digest"):
                    _digest(value, field)
                else:
                    _identifier(value, field)

    @staticmethod
    def _insert_binding_revision(
        tx: VoiceFoundryTransaction,
        *,
        task: VoiceFoundryTaskRecord,
        binding_id: str,
        binding_revision: int,
        logical_voice_id: str,
        provider_instance: str,
        provider_voice_id: str,
        voice_revision: str,
        model_catalog_revision: str | None,
        evidence_id: str,
        evidence_digest: str,
        status: str,
        world_revision: int,
        recorded_at: str,
    ) -> None:
        scope = task.scope
        tx.execute(
            "INSERT INTO voice_binding_revisions("
            "binding_id,binding_revision,owner_id,world_id,worldline_id,"
            "presentation_identity,phase,locale,logical_voice_id,persona_revision,"
            "provider_instance,provider_voice_id,voice_revision,model_catalog_revision,"
            "evidence_id,evidence_digest,qualification,status,"
            "reserved_at_world_revision,recorded_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                binding_id,
                binding_revision,
                scope.owner_id,
                scope.world_id,
                scope.worldline_id,
                scope.presentation_identity,
                scope.phase,
                scope.locale,
                logical_voice_id,
                task.persona_revision,
                provider_instance,
                provider_voice_id,
                voice_revision,
                model_catalog_revision,
                evidence_id,
                evidence_digest,
                "qualified",
                status,
                world_revision,
                recorded_at,
            ),
        )


__all__ = [
    "SQLiteVoiceFoundryRepository",
    "VoiceBindingRevisionRecord",
    "VoiceCandidateRecord",
    "VoiceCommandAck",
    "VoiceEvidenceSnapshot",
    "VoiceFoundryCancelled",
    "VoiceFoundryConflict",
    "VoiceFoundryOperationIntent",
    "VoiceFoundryOperationRecord",
    "VoiceFoundryStage",
    "VoiceFoundryTaskRecord",
    "VoiceCastBudget",
    "VoiceExecutionScope",
    "VoiceFoundryTaskSpec",
]
