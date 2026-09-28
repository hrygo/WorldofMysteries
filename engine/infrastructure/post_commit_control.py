"""Public read-only projection and explicit retry for post-COMMIT work.

``work.get`` is a pure read. It never claims a job, never rewrites durable
state, never seals audio and never calls a provider. Its only refinement over
the database-only projection is the audio handoff verdict, which requires the
persisted sealed result *and* a live unit in the current Engine registry.

``work.retry`` is an idempotent work acceptance. It never re-submits player
input, never re-runs the resolver and never rewrites a committed Domain turn.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from application.speech_unit import SealedSpeechUnit
from application.story_expression import (
    StoryExpressionError,
    StoryExpressionQueryService,
    StoryExpressionResponse,
)

from .audio.sealed_unit_codec import SealedSpeechUnitCodec, SealedSpeechUnitCodecError
from .audio.voice_runtime import SealedSpeechUnitRegistry, VoiceRenderRuntimeError
from .database_manager import DatabaseManager
from .post_commit_job_repository import (
    AudioPublicState,
    NarrativePublicState,
    PostCommitJobConflict,
    PostCommitPublicStatus,
    SQLitePostCommitJobRepository,
    SettlementPublicState,
)

SCHEMA_VERSION = "1.0"

WORK_KINDS = ("episode_finalize", "narrative_publish", "audio_prepare")

#: Durable audio success whose in-memory handoff this layer may still verify.
HANDOFF_UNVERIFIED = "handoff_unverified"
#: The sealed result is durable but its registry entry is gone.
HANDOFF_EXPIRED = "handoff_expired"
#: No audio job was ever scheduled for this turn.
AUDIO_NOT_SCHEDULED = "audio_not_scheduled"
#: Durable narrative success without a disclosed artifact to show for it.
NARRATIVE_ARTIFACT_UNAVAILABLE = "narrative_artifact_unavailable"

#: Durable job states an explicit retry may act on.
_RETRYABLE = frozenset({"retry_wait", "blocked"})


class PostCommitControlError(RuntimeError):
    """A public, stable refusal code for a post-COMMIT control request."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class WorkGetView:
    """Public projection matching ``work_get_response``."""

    session_id: str
    turn_id: str
    settlement_state: str
    narrative_state: str
    narrative_segments: tuple[Mapping[str, object], ...]
    audio_state: str
    settlement_reason: str | None = None
    narrative_reason: str | None = None
    audio_reason: str | None = None
    delivery: Mapping[str, object] | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "settlement_state": self.settlement_state,
            "narrative_state": self.narrative_state,
            "narrative_segments": [dict(segment) for segment in self.narrative_segments],
            "audio_state": self.audio_state,
        }
        if self.settlement_reason is not None:
            payload["settlement_reason"] = self.settlement_reason
        if self.narrative_reason is not None:
            payload["narrative_reason"] = self.narrative_reason
        if self.audio_reason is not None:
            payload["audio_reason"] = self.audio_reason
        if self.delivery is not None:
            payload["delivery"] = dict(self.delivery)
        return payload


@dataclass(frozen=True, slots=True)
class WorkRetryView:
    """Idempotent acknowledgement matching ``work_retry_response``."""

    session_id: str
    turn_id: str
    kind: str
    retry_request_id: str
    accepted: bool
    replayed: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "kind": self.kind,
            "retry_request_id": self.retry_request_id,
            "accepted": self.accepted,
            "replayed": self.replayed,
        }


def _identifier(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise PostCommitControlError(code)
    return value


class PostCommitControlService:
    """Project durable post-COMMIT work and accept explicit retries."""

    def __init__(
        self,
        *,
        database: DatabaseManager,
        jobs: SQLitePostCommitJobRepository,
        expression: StoryExpressionQueryService,
        registry: SealedSpeechUnitRegistry,
        sealed_results: SealedSpeechUnitCodec | None = None,
    ) -> None:
        self._database = database
        self._jobs = jobs
        self._expression = expression
        self._registry = registry
        self._codec = sealed_results or SealedSpeechUnitCodec()

    # ------------------------------------------------------------------ read

    async def get_work(self, *, session_id: str, turn_id: str) -> WorkGetView:
        """Read one committed turn's independent work projections."""
        session = _identifier(session_id, "invalid_session_id")
        turn = _identifier(turn_id, "invalid_turn_id")
        await self._require_owned_turn(session, turn)
        status = await self._jobs.get_status(session_id=session, turn_id=turn)
        expression = await self._read_expression(session, turn)
        narrative_state, segments, narrative_reason = self._narrative(
            status, expression
        )
        audio_state, audio_reason, delivery = await self._audio(session, turn, status)
        return WorkGetView(
            session_id=session,
            turn_id=turn,
            settlement_state=status.settlement.value,
            settlement_reason=self._settlement_reason(status),
            narrative_state=narrative_state,
            narrative_segments=segments,
            narrative_reason=narrative_reason,
            audio_state=audio_state,
            audio_reason=audio_reason,
            delivery=delivery,
        )

    async def _require_owned_turn(self, session_id: str, turn_id: str) -> None:
        """Refuse any turn that does not belong to the requested session."""
        rows = await self._database.read_world(
            "SELECT session_id FROM turn_transactions WHERE id=?", (turn_id,)
        )
        if not rows:
            raise PostCommitControlError("turn_not_found")
        if rows[0]["session_id"] != session_id:
            raise PostCommitControlError("turn_session_mismatch")

    async def _read_expression(
        self, session_id: str, turn_id: str
    ) -> StoryExpressionResponse | None:
        """Read disclosed narrative; never let a read failure invent a state."""
        try:
            return await self._expression.get(
                session_id=session_id, turn_id=turn_id
            )
        except StoryExpressionError as exc:
            if exc.code in {"turn_identity_mismatch", "turn_session_mismatch"}:
                raise PostCommitControlError(exc.code) from None
            return None
        except Exception:  # noqa: BLE001 - degrade to the durable lower bound
            return None

    @staticmethod
    def _settlement_reason(status: PostCommitPublicStatus) -> str | None:
        if status.settlement is not SettlementPublicState.BLOCKED:
            return None
        return status.settlement_reason or "settlement_blocked"

    @staticmethod
    def _narrative(
        status: PostCommitPublicStatus,
        expression: StoryExpressionResponse | None,
    ) -> tuple[str, tuple[Mapping[str, object], ...], str | None]:
        """Narrative is ready only alongside a non-empty disclosed artifact."""
        if expression is not None and expression.narrative_state == "ready":
            segments = tuple(
                segment.model_dump(mode="json", exclude_none=True)
                for segment in expression.segments
            )
            if segments:
                return NarrativePublicState.READY.value, segments, None
        if status.narrative is NarrativePublicState.READY:
            # Durable success with nothing disclosed: never report ready with
            # zero segments, because the wire contract forbids it.
            return (
                NarrativePublicState.BLOCKED.value,
                (),
                NARRATIVE_ARTIFACT_UNAVAILABLE,
            )
        if status.narrative is NarrativePublicState.BLOCKED:
            return (
                NarrativePublicState.BLOCKED.value,
                (),
                status.narrative_reason or "narrative_blocked",
            )
        return status.narrative.value, (), None

    async def _audio(
        self, session_id: str, turn_id: str, status: PostCommitPublicStatus
    ) -> tuple[str, str | None, Mapping[str, object] | None]:
        """Refine the durable lower bound with live registry evidence."""
        if status.audio is AudioPublicState.PENDING:
            return status.audio.value, None, None
        if status.audio is AudioPublicState.RUNNING:
            return status.audio.value, None, None
        if status.audio_reason != HANDOFF_UNVERIFIED:
            # Either blocked, or never scheduled; the durable reason stands.
            return (
                status.audio.value,
                status.audio_reason or AUDIO_NOT_SCHEDULED,
                None,
            )

        durable = await self._durable_audio_unit(session_id, turn_id)
        if durable is None:
            return AudioPublicState.UNAVAILABLE.value, HANDOFF_UNVERIFIED, None
        try:
            live = self._registry.peek(durable.unit_id)
        except VoiceRenderRuntimeError:
            # Expired, consumed, or lost to an Engine restart: the sealed result
            # stays durable, only the handoff is gone.
            return AudioPublicState.UNAVAILABLE.value, HANDOFF_EXPIRED, None
        if live != durable:
            return AudioPublicState.UNAVAILABLE.value, HANDOFF_UNVERIFIED, None
        return AudioPublicState.READY.value, None, self._delivery(live)

    async def _durable_audio_unit(
        self, session_id: str, turn_id: str
    ) -> SealedSpeechUnit | None:
        """Load and integrity-check the persisted sealed result, if any."""
        rows = await self._database.read_world(
            "SELECT r.payload_json AS payload_json,"
            "r.payload_digest AS payload_digest FROM post_commit_jobs AS j "
            "LEFT JOIN post_commit_job_results AS r ON r.job_id=j.job_id "
            "WHERE j.session_id=? AND j.turn_id=? AND j.kind='audio_prepare' "
            "ORDER BY j.recipe_revision",
            (session_id, turn_id),
        )
        for row in rows:
            if row["payload_json"] is None or row["payload_digest"] is None:
                continue
            try:
                return self._codec.decode(
                    row["payload_json"],
                    row["payload_digest"],
                    expected_turn_id=turn_id,
                )
            except SealedSpeechUnitCodecError:
                # An integrity failure is a lower bound, never a ready verdict.
                continue
        return None

    @staticmethod
    def _delivery(unit: SealedSpeechUnit) -> dict[str, object]:
        return {
            "state": "ready",
            "narrative_block_id": unit.narrative_block_id,
            "speech_unit_id": unit.unit_id,
            "spoken_text": unit.spoken_text,
            "render_recipe": unit.render_recipe(),
        }

    # ----------------------------------------------------------------- retry

    async def retry_work(
        self,
        *,
        session_id: str,
        turn_id: str,
        kind: str,
        retry_request_id: str,
    ) -> WorkRetryView:
        """Idempotently accept one eligible retry without touching the Domain."""
        session = _identifier(session_id, "invalid_session_id")
        turn = _identifier(turn_id, "invalid_turn_id")
        request = _identifier(retry_request_id, "invalid_retry_request_id")
        if kind not in WORK_KINDS:
            raise PostCommitControlError("invalid_work_kind")
        await self._require_owned_turn(session, turn)
        job = await self._find_job(session, turn, kind)
        if job is None:
            raise PostCommitControlError("work_not_found")
        # A replayed request id is answered from the durable binding before any
        # eligibility check: re-arming already moved the job to ``pending``, so
        # gating on eligibility first would reject a legitimate replay.
        bound = await self._retry_binding(request)
        if bound is not None:
            if bound != job["job_id"]:
                raise PostCommitControlError("work_retry_conflict")
            return WorkRetryView(
                session_id=session,
                turn_id=turn,
                kind=kind,
                retry_request_id=request,
                accepted=True,
                replayed=True,
            )
        if job["state"] in _RETRYABLE:
            return await self._retry_scheduling(session, turn, kind, request, job)
        if job["state"] == "succeeded" and kind == "audio_prepare":
            return await self._rebuild_handoff(session, turn, request)
        raise PostCommitControlError("work_not_eligible")

    async def _retry_scheduling(
        self,
        session: str,
        turn: str,
        kind: str,
        request: str,
        job: Mapping[str, object],
    ) -> WorkRetryView:
        """Re-arm a retryable job; the repository owns request idempotency."""
        try:
            result = await self._jobs.retry(job["job_id"], request_id=request)
        except PostCommitJobConflict as exc:
            raise PostCommitControlError("work_retry_conflict") from exc
        return WorkRetryView(
            session_id=session,
            turn_id=turn,
            kind=kind,
            retry_request_id=request,
            accepted=result.accepted,
            replayed=result.replayed,
        )

    async def _rebuild_handoff(
        self, session: str, turn: str, request: str
    ) -> WorkRetryView:
        """Re-publish the same sealed unit; never re-seal or re-narrate.

        Idempotency here is derived from observable handoff state rather than a
        request ledger: publishing the identical unit is itself idempotent, so
        a replayed call observes the unit already live and reports
        ``replayed=True``. This survives an Engine restart, which a durable
        request ledger would not be required to.
        """
        unit = await self._durable_audio_unit(session, turn)
        if unit is None:
            raise PostCommitControlError("audio_result_unavailable")
        try:
            live = self._registry.peek(unit.unit_id)
        except VoiceRenderRuntimeError:
            live = None
        if live is not None and live == unit:
            return WorkRetryView(
                session_id=session,
                turn_id=turn,
                kind="audio_prepare",
                retry_request_id=request,
                accepted=True,
                replayed=True,
            )
        try:
            self._registry.publish(unit)
        except VoiceRenderRuntimeError as exc:
            raise PostCommitControlError("audio_handoff_unavailable") from exc
        return WorkRetryView(
            session_id=session,
            turn_id=turn,
            kind="audio_prepare",
            retry_request_id=request,
            accepted=True,
            replayed=False,
        )

    async def _find_job(
        self, session_id: str, turn_id: str, kind: str
    ) -> Mapping[str, object] | None:
        rows = await self._database.read_world(
            "SELECT job_id,state FROM post_commit_jobs "
            "WHERE session_id=? AND turn_id=? AND kind=? "
            "ORDER BY recipe_revision",
            (session_id, turn_id, kind),
        )
        return rows[0] if rows else None

    async def _retry_binding(self, request_id: str) -> str | None:
        """Return the job a retry request id is already bound to, if any."""
        rows = await self._database.read_world(
            "SELECT job_id FROM post_commit_retry_requests WHERE request_id=?",
            (request_id,),
        )
        return rows[0]["job_id"] if rows else None
