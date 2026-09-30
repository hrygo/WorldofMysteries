"""Artifact-first handlers for the Golden scenario's durable post-COMMIT jobs."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from application.audio_disclosure import AudioDisclosureAuthorizer
from application.narrative_publication import (
    CommittedNarrativeService,
    CommittedNarrativeSource,
    NarrativePublicationError,
)
from application.post_commit_expression import (
    CommittedExpressionInput,
    PostCommitExpressionService,
)
from application.post_commit_work import (
    PostCommitKind,
    PostCommitResult,
    PostCommitResultState,
    PostCommitWorkSource,
)
from application.speech_unit import SealedSpeechUnit, SpeechUnitSealingService
from application.story_initialization import StorySessionBootstrap
from application.story_turn_commit import StoryTurnCommitResult
from application.turn_context_binding import TurnContextBindingPort
from application.voice_evidence import load_evidence_record, render_execution
from contracts import NarrativeBlock, TurnStatus

from ..audio.config import AudioProviderConfig
from ..audio.foundry_policy import DEFAULT_VARIANT
from ..audio.sealed_unit_codec import SealedSpeechUnitCodec, SealedSpeechUnitCodecError
from ..audio.voice_delivery import TurnDeliveryError
from ..audio.voice_runtime import VoiceRenderRuntime, VoiceRenderRuntimeError
from ..beat_plan_repository import SQLiteBeatPlanRepository
from ..database_manager import DatabaseManager, PostCommitJobTransaction
from ..database_schema import StorageError
from ..episode_settlement import ScenarioSettlement, ScenarioSettlementFailure
from ..narrative_block_repository import SQLiteNarrativeBlockRepository
from ..player_advice_repository import SQLitePlayerAdviceRepository
from ..story_bootstrap_repository import SQLiteStoryBootstrapRepository
from ..story_session_repository import SQLiteStorySessionCommitPort
from ..voice_binding_repository import SQLiteVoiceBindingRepository
from ..voice_binding_resolver import (
    NARRATION_PHASE,
    ResolvedVoiceRuntime,
    VoiceBindingResolutionError,
    resolve_voice_runtime,
    speaker_scope_for,
)
from ..voice_foundry_repository import SQLiteVoiceFoundryRepository
from domain.voice_identity import VoiceBindingScope

_SOURCE_MISMATCH = "work_unavailable"
_RESULT_CONFLICT = "sealed_result_conflict"


class VoiceSupplyTriggerPort(Protocol):
    """The one verb the audio job borrows, and the reason it may not fail.

    Structural rather than concrete so the audio path can be exercised
    without a catalog, a provider or a supply chain behind it.
    """

    async def ensure(self, scope: object) -> object: ...


@dataclass(frozen=True, slots=True)
class _CommittedTurn:
    turn: Any
    delta: Any
    bootstrap: StorySessionBootstrap


class _PostCommitSourceError(RuntimeError):
    def __init__(self, code: str = _SOURCE_MISMATCH) -> None:
        super().__init__(code)
        self.code = code


def _success(result_ref: str) -> PostCommitResult:
    return PostCommitResult(
        state=PostCommitResultState.SUCCEEDED,
        result_ref=result_ref,
    )


def _blocked(reason_code: str) -> PostCommitResult:
    return PostCommitResult(
        state=PostCommitResultState.BLOCKED,
        reason_code=reason_code,
    )


async def _load_committed_turn(
    *,
    database: DatabaseManager,
    story: SQLiteStorySessionCommitPort,
    bootstraps: SQLiteStoryBootstrapRepository,
    source: PostCommitWorkSource,
) -> _CommittedTurn:
    """Resolve a job only through its frozen turn identity, never latest scene state."""
    turn = await story.load_turn(source.turn_id)
    if (
        turn.id != source.turn_id
        or turn.session_id != source.session_id
        or turn.committed_story_revision != source.source_story_revision
        or not turn.state_delta_id
    ):
        raise _PostCommitSourceError()
    rows = await database.read_world(
        "SELECT committed_world_revision FROM turn_transactions WHERE id=? "
        "AND session_id=?",
        (source.turn_id, source.session_id),
    )
    if (
        len(rows) != 1
        or type(rows[0]["committed_world_revision"]) is not int
        or rows[0]["committed_world_revision"] != source.source_world_revision
    ):
        raise _PostCommitSourceError()
    delta = await story.load_delta(turn.state_delta_id)
    if delta.turn_id != source.turn_id:
        raise _PostCommitSourceError()
    bootstrap = await bootstraps.require(source.session_id)
    return _CommittedTurn(turn=turn, delta=delta, bootstrap=bootstrap)


def _validate_narrative(
    narrative: NarrativeBlock,
    *,
    source: PostCommitWorkSource,
    turn: Any,
) -> None:
    if (
        narrative.story_session_id != source.session_id
        or narrative.source_story_revision != source.source_story_revision
        or narrative.source_state_delta_id != turn.state_delta_id
    ):
        raise _PostCommitSourceError()


def _disclosed_facts(
    *,
    delta: Any,
    bootstrap: StorySessionBootstrap,
) -> str:
    """Rebuild only the committed, player-disclosable facts for this turn."""
    names = bootstrap.presentation.clue_display_names
    # This is a post-COMMIT expression path. A clue without an explicit
    # presentation label is omitted; expression failure must not unwind the
    # committed turn, and a canonical identifier must never reach the narrator.
    added = [
        name
        for clue_id in delta.story_delta.clue_ids_add or ()
        if (name := names.get(clue_id)) is not None
    ]
    parts = [f"结果判定：{delta.outcome}"]
    if added:
        parts.append("玩家发现了：" + "、".join(added))
    story_delta = delta.story_delta
    if story_delta.scene_id:
        parts.append(f"场景转为：{story_delta.scene_id}")
    if story_delta.world_time_delta_minutes:
        parts.append(f"世界时间推进：{story_delta.world_time_delta_minutes} 分钟")
    return "\n".join(parts)


class ScenarioNarrativePublishHandler:
    """Publish one frozen or live NarrativeBlock from its committed source."""

    def __init__(
        self,
        *,
        database: DatabaseManager,
        story: SQLiteStorySessionCommitPort,
        bootstraps: SQLiteStoryBootstrapRepository,
        advice: SQLitePlayerAdviceRepository,
        narratives: SQLiteNarrativeBlockRepository,
        beat_plans: SQLiteBeatPlanRepository,
        expression: PostCommitExpressionService,
        workers,
        frozen_expression: bool,
        context_bindings: TurnContextBindingPort | None = None,
    ) -> None:
        self._database = database
        self._story = story
        self._bootstraps = bootstraps
        self._advice = advice
        self._narratives = narratives
        self._beat_plans = beat_plans
        self._expression = expression
        self._workers = workers
        self._frozen_expression = frozen_expression
        self._context_bindings = context_bindings

    async def execute(self, source: PostCommitWorkSource) -> PostCommitResult:
        if source.kind is not PostCommitKind.NARRATIVE_PUBLISH:
            return _blocked("work_unavailable")
        try:
            committed = await _load_committed_turn(
                database=self._database,
                story=self._story,
                bootstraps=self._bootstraps,
                source=source,
            )
            turn = committed.turn
            if turn.narrative_block_id:
                existing = await self._narratives.load_narrative_block(
                    turn.narrative_block_id
                )
                _validate_narrative(existing, source=source, turn=turn)
                return _success(f"narrative:{existing.id}")
            if self._frozen_expression:
                beat = await self._beat_plans.load_turn_beat_plan(turn.id)
                if beat is not None and (
                    beat.story_session_id != source.session_id
                    or beat.source_story_revision != source.source_story_revision
                ):
                    return _blocked("work_unavailable")
                result = await self._expression.publish(
                    turn_number=source.source_story_revision,
                    commit=CommittedExpressionInput(
                        session_id=source.session_id,
                        turn_id=source.turn_id,
                        story_revision=source.source_story_revision,
                        state_delta_id=turn.state_delta_id,
                        turn_status=TurnStatus.COMMITTED,
                    ),
                )
                _validate_narrative(result.narrative, source=source, turn=turn)
                return _success(f"narrative:{result.narrative.id}")
            return await self._publish_live(source, committed)
        except _PostCommitSourceError as exc:
            return _blocked(exc.code)
        except (StorageError, NarrativePublicationError) as exc:
            code = getattr(exc, "code", None)
            return _blocked(code if isinstance(code, str) else "narrative_unavailable")

    async def _publish_live(
        self,
        source: PostCommitWorkSource,
        committed: _CommittedTurn,
    ) -> PostCommitResult:
        # The turn's idempotency_key is a derived ``turn-input:<digest>`` form,
        # so it can never satisfy a lookup keyed by input_turn_id. Post-COMMIT
        # work carries the turn, so resolve the pre-COMMIT input from it.
        frozen_input = await self._advice.load_input_for_turn(source.turn_id)
        if (
            frozen_input is None
            or frozen_input.session_id != source.session_id
            or frozen_input.turn_id != source.turn_id
        ):
            return _blocked("work_unavailable")
        compiler = self._workers.narrative_compiler(committed.bootstrap)
        if compiler is None:
            return _blocked("recipe_unavailable")
        delta = committed.delta
        story_delta = delta.story_delta
        narrative_source = CommittedNarrativeSource(
            turn_id=source.turn_id,
            session_id=source.session_id,
            story_revision=source.source_story_revision,
            state_delta_id=committed.turn.state_delta_id,
            state_delta=delta,
            scene_id=story_delta.scene_id,
            protagonist_id=committed.bootstrap.initial_session.protagonist_id,
            disclosed_facts=_disclosed_facts(
                delta=delta,
                bootstrap=committed.bootstrap,
            ),
            input_turn_id=frozen_input.input_turn_id,
            source_store_revision=source.source_world_revision,
        )
        publication = CommittedNarrativeService(
            reads=self._narratives,
            publisher=self._narratives,
            compiler=compiler,
            context_bindings=self._context_bindings,
        )
        narrative = await publication.ensure(
            turn_id=source.turn_id,
            source=narrative_source,
        )
        _validate_narrative(narrative, source=source, turn=committed.turn)
        return _success(f"narrative:{narrative.id}")


class ScenarioEpisodeFinalizeHandler:
    """Finalize terminal Golden sessions through the existing domain transaction."""

    def __init__(
        self,
        *,
        database: DatabaseManager,
        story: SQLiteStorySessionCommitPort,
        bootstraps: SQLiteStoryBootstrapRepository,
        settlement: ScenarioSettlement,
    ) -> None:
        self._database = database
        self._story = story
        self._bootstraps = bootstraps
        self._settlement = settlement

    async def execute(self, source: PostCommitWorkSource) -> PostCommitResult:
        if source.kind is not PostCommitKind.EPISODE_FINALIZE:
            return _blocked("work_unavailable")
        try:
            existing = await self._settlement.episodes.load_by_session(
                source.session_id
            )
        except StorageError:
            rows = await self._database.read_world(
                "SELECT id FROM episodes WHERE session_id=?",
                (source.session_id,),
            )
            if rows:
                return _blocked("episode_bundle_unavailable")
        else:
            if existing.episode.id != f"episode_{source.session_id}":
                return _blocked("work_unavailable")
            return _success(f"episode:{existing.episode.id}")

        try:
            committed = await _load_committed_turn(
                database=self._database,
                story=self._story,
                bootstraps=self._bootstraps,
                source=source,
            )
            session = await self._story.load_session(source.session_id)
            if session.story_state.revision != source.source_story_revision:
                return _blocked("session_advanced")
            await self._settlement.finalize_only(
                StoryTurnCommitResult(
                    store_revision=source.source_world_revision,
                    session=session,
                    turn=committed.turn,
                    delta=committed.delta,
                    replayed=True,
                )
            )
            finalized = await self._settlement.episodes.load_by_session(
                source.session_id
            )
            if finalized.episode.id != f"episode_{source.session_id}":
                return _blocked("work_unavailable")
            return _success(f"episode:{finalized.episode.id}")
        except ScenarioSettlementFailure as exc:
            return _blocked(exc.code)
        except _PostCommitSourceError as exc:
            return _blocked(exc.code)
        except StorageError:
            return _blocked("episode_finalize_failed")


class ScenarioAudioPrepareHandler:
    """Seal and durably hand off only an already-published narrative segment."""

    def __init__(
        self,
        *,
        database: DatabaseManager,
        story: SQLiteStorySessionCommitPort,
        bootstraps: SQLiteStoryBootstrapRepository,
        narratives: SQLiteNarrativeBlockRepository,
        bindings: SQLiteVoiceBindingRepository,
        voice: VoiceRenderRuntime | None,
        audio_config: AudioProviderConfig | None,
        voice_id: str | None,
        dictionary_revision: str,
        fetch_json,
        evidence_store: SQLiteVoiceFoundryRepository,
        codec: SealedSpeechUnitCodec | None = None,
        supply_trigger: VoiceSupplyTriggerPort | None = None,
    ) -> None:
        self._database = database
        self._story = story
        self._bootstraps = bootstraps
        self._narratives = narratives
        self._bindings = bindings
        self._voice = voice
        self._audio_config = audio_config
        self._voice_id = voice_id
        self._dictionary_revision = dictionary_revision
        self._fetch_json = fetch_json
        self._evidence_store = evidence_store
        self._codec = codec or SealedSpeechUnitCodec()
        self._supply_trigger = supply_trigger

    async def execute(self, source: PostCommitWorkSource) -> PostCommitResult:
        if source.kind is not PostCommitKind.AUDIO_PREPARE:
            return _blocked("work_unavailable")
        try:
            committed = await _load_committed_turn(
                database=self._database,
                story=self._story,
                bootstraps=self._bootstraps,
                source=source,
            )
            turn = committed.turn
            if not turn.narrative_block_id:
                return _blocked("dependency_unavailable")
            narrative = await self._narratives.load_narrative_block(
                turn.narrative_block_id
            )
            _validate_narrative(narrative, source=source, turn=turn)
            existing = await self._load_sealed_unit(
                source=source,
                narrative=narrative,
            )
            if self._voice is None or self._audio_config is None or not self._voice_id:
                return _blocked("voice_not_configured")
            session = await self._story.load_session(source.session_id)
            # The speaker is chosen before the voice is resolved, because the
            # scope *is* the speaker. Resolving first would mean asking the
            # repository for a voice before knowing whose voice was wanted.
            #
            # Only character segments are candidates here. The sealing
            # boundary refuses a speakerless narration on purpose — until a
            # NarrativeBlock carries an explicit narrator identity, letting a
            # caller name one would let it choose who narrates the game. So
            # narration leads every block but is not yet sealable, and
            # selecting it anyway cost this job both its audio and the cast
            # that would have supplied the character's voice.
            candidates = [
                (index, scope)
                for index, item in enumerate(narrative.segments)
                if item.type == "character"
                and (scope := speaker_scope_for(session, item)) is not None
            ]
            segment_index, scope = (
                candidates[0] if candidates else (None, None)
            )
            if segment_index is None or scope is None:
                return _blocked("narrative_has_no_character_segment")
            resolved = await resolve_voice_runtime(
                repository=self._bindings,
                session=session,
                config=self._audio_config,
                voice_id=self._voice_id,
                scope=scope,
                fetch_json=self._fetch_json,
            )
            if existing is not None:
                if not _same_voice_revision(existing, resolved):
                    return _blocked("voice_revision_unavailable")
                try:
                    self._voice.publish(existing)
                except VoiceRenderRuntimeError:
                    return _blocked("handoff_unavailable")
                return _success(f"sealed:{existing.unit_id}")
            execution = render_execution(
                provider_instance=resolved.provider_instance,
                voice_id=resolved.binding.provider.voice_id,
                voice_revision=resolved.binding.provider.conditional_pin,
                model_id=resolved.execution_model_id,
                model_artifact_revision=(
                    None
                    if resolved.binding.evidence is None
                    else resolved.binding.evidence.model_artifact_revision
                ),
                model_catalog_revision=resolved.model_catalog_revision,
                game_locale=resolved.scope.locale,
                phase=resolved.scope.phase,
                variant=DEFAULT_VARIANT,
            )
            if execution is None:
                return _blocked("voice_evidence_not_admitted")
            evidence = await load_evidence_record(
                self._evidence_store,
                resolved.provider_instance,
                resolved.binding.evidence.evidence_id,
            )
            if evidence is None:
                return _blocked("voice_evidence_not_admitted")
            sealing = SpeechUnitSealingService(
                disclosure=AudioDisclosureAuthorizer(self._narratives),
                bindings=self._bindings,
            )
            unit = await sealing.seal(
                turn_id=source.turn_id,
                expected_story_revision=source.source_story_revision,
                segment_index=segment_index,
                binding_scope=resolved.scope,
                expected_binding_revision=resolved.binding.binding_revision,
                execution_model_id=resolved.execution_model_id,
                execution=execution,
                evidence=evidence,
                dictionary_revision=self._dictionary_revision,
                semantic_anchors=(),
                pronunciation_rules=(),
                desired_performance=resolved.performance,
                performance_capabilities=resolved.capabilities,
            )
            if (
                unit.story_session_id != source.session_id
                or unit.narrative_block_id != narrative.id
            ):
                return _blocked("work_unavailable")
            await self._persist_sealed_result(source, unit)
            try:
                self._voice.publish(unit)
            except VoiceRenderRuntimeError:
                # Durable sealed state survives a failed in-memory handoff.
                return _blocked("handoff_unavailable")
            return _success(f"sealed:{unit.unit_id}")
        except _PostCommitSourceError as exc:
            return _blocked(exc.code)
        except SealedSpeechUnitCodecError:
            return _blocked("handoff_unverified")
        except VoiceBindingResolutionError as exc:
            # First appearance with no voice is when supply starts, and it
            # starts silently. The outcome returned below is exactly what it
            # would have been without this call: the text is already
            # published, and the segment falls back to a subtitle.
            await self._request_supply_quietly(
                source.session_id, committed.bootstrap, scope
            )
            return _blocked(exc.code)
        except (StorageError, TurnDeliveryError):
            return _blocked("audio_prepare_failed")

    async def _request_supply_quietly(
        self,
        session_id: str,
        bootstrap: StorySessionBootstrap,
        scope: VoiceBindingScope,
    ) -> None:
        """Ask supply to start casting this speaker, and fail at nothing.

        Everything this does is invisible to the caller by construction. It
        runs after the turn's text is committed and published, so opening a
        casting task, finding one already open, having no design for this
        character and outright failing all leave the job returning the same
        blocked audio result it always did. A supply problem is not allowed to
        become a story problem.

        The scope is the one whose voice was just found missing, not a
        re-derived guess: a turn whose narrator has no voice must ask the
        foundry for a narrator, and asking on the protagonist's behalf would
        cast a voice nobody is missing.
        """
        trigger = self._supply_trigger
        if trigger is None:
            return
        try:
            await trigger.ensure(
                scope,
                spoken_lines=await self._published_lines(session_id, scope),
                display_name=self._display_name(bootstrap),
            )
        except Exception:  # noqa: BLE001 - supply must never fail this job
            return

    async def _published_lines(
        self, session_id: str, scope: VoiceBindingScope
    ) -> tuple[str, ...]:
        """What this speaker has already said, as published.

        Read from the published narrative rather than from any dossier: a line
        the player has seen is public by construction, and a line they have not
        is not something a voice may be tuned against. Accumulated across the
        whole session, because one line per turn never reaches the two a
        cross-text check needs — the character simply is not cast yet, and is
        cast on the turn where they have finally said enough.

        The scope decides which lines count. Narration is published with no
        ``speaker_id`` at all, so a narrator's lines are found by their phase
        and a character's by their speaker — reading a narrator's text as
        though someone had said it aloud would tune the voice against lines no
        mouth ever moved on.
        """
        lines: list[str] = []
        rows = await self._database.read_world(
            "SELECT payload_json FROM narrative_blocks "
            "WHERE session_id=? ORDER BY source_story_revision",
            (session_id,),
        )
        narration = scope.phase == NARRATION_PHASE
        for row in rows:
            payload = json.loads(row["payload_json"])
            for segment in payload.get("segments", []):
                if (
                    (
                        segment.get("type") == "narration"
                        if narration
                        else segment.get("type") == "character"
                        and segment.get("speaker_id")
                        == scope.presentation_identity
                    )
                    and isinstance(segment.get("text"), str)
                    and segment["text"].strip()
                ):
                    lines.append(segment["text"].strip())
        return tuple(lines)

    @staticmethod
    def _display_name(bootstrap: StorySessionBootstrap) -> str:
        try:
            name = bootstrap.character["identity"]["display_name"]
        except (AttributeError, KeyError, TypeError):
            # A bootstrap without a character block is a content gap, not a
            # reason to fail an audio job; the composer falls back to the
            # identity itself.
            return ""
        return name if isinstance(name, str) else ""

    async def _load_sealed_unit(
        self,
        *,
        source: PostCommitWorkSource,
        narrative: NarrativeBlock,
    ) -> SealedSpeechUnit | None:
        rows = await self._database.read_world(
            "SELECT format_version,payload_json,payload_digest "
            "FROM post_commit_job_results WHERE job_id=?",
            (source.job_id,),
        )
        if not rows:
            return None
        if len(rows) != 1 or rows[0]["format_version"] != self._codec.format_version:
            raise SealedSpeechUnitCodecError("sealed_result_identity_mismatch")
        return self._codec.decode(
            rows[0]["payload_json"],
            rows[0]["payload_digest"],
            expected_turn_id=source.turn_id,
            expected_narrative_block_id=narrative.id,
        )

    async def _persist_sealed_result(
        self,
        source: PostCommitWorkSource,
        unit: SealedSpeechUnit,
    ) -> None:
        payload_json, payload_digest = self._codec.encode(unit)
        format_version = self._codec.format_version

        def apply(tx: PostCommitJobTransaction) -> None:
            rows = tx.execute(
                "SELECT format_version,payload_json,payload_digest "
                "FROM post_commit_job_results WHERE job_id=?",
                (source.job_id,),
            )
            if rows:
                current = rows[0]
                if (
                    current["format_version"] != format_version
                    or current["payload_json"] != payload_json
                    or current["payload_digest"] != payload_digest
                ):
                    raise StorageError(_RESULT_CONFLICT)
                return
            tx.execute(
                "INSERT INTO post_commit_job_results("
                "job_id,format_version,payload_json,payload_digest) "
                "VALUES (?,?,?,?)",
                (source.job_id, format_version, payload_json, payload_digest),
            )

        await self._database.post_commit_job_write(apply)


def _same_voice_revision(
    unit: SealedSpeechUnit,
    resolved: ResolvedVoiceRuntime,
) -> bool:
    binding = resolved.binding
    return (
        unit.provider_instance == resolved.provider_instance
        and unit.voice_id == binding.provider.voice_id
        and unit.voice_revision == binding.provider.voice_revision
        and unit.model_id == resolved.execution_model_id
        and unit.model_revision == resolved.model_catalog_revision
        and unit.binding_id == binding.binding_id
        and unit.presentation_identity == resolved.scope.presentation_identity
    )


__all__ = [
    "ScenarioAudioPrepareHandler",
    "ScenarioEpisodeFinalizeHandler",
    "ScenarioNarrativePublishHandler",
]
