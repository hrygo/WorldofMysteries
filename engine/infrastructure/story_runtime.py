"""Composition root for the trusted product runtime.

The runtime binds the frozen content artifact (read-only canon role), the
engineering world database under an explicit persistent data root, the
application services and the public story control handlers.  It never creates an
empty canon database and never learns storage paths from IPC payloads.

Two capabilities are optional and are reported honestly in ``system.health``:

``model``
    Configured only when ``WOM_MODEL_BASE_URL`` and ``WOM_MODEL_NAME`` name an
    endpoint.  Without them the runtime keeps the frozen Golden 001 fixture and
    reports ``model_ready: false``.

``voice``
    Configured only when a SpeechRail endpoint is reachable *and* the named
    voice is content-addressed.  Capability discovery is a startup probe, not an
    assumption, so ``voice_ready`` tracks what was actually proven.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ai.golden_five_turn import GoldenFiveTurnCatalog, GoldenFiveTurnFactory
from ai.live_turn_workers import LiveFirstTurnFactory
from ai.openai_compatible import ModelEndpointConfig, ModelTransportError
from application.audio_disclosure import AudioDisclosureAuthorizer
from application.narrative_publication import (
    CommittedNarrativeService,
    CommittedNarrativeSource,
    NarrativeCandidate,
    NarrativePublicationError,
)
from application.post_commit_expression import PostCommitExpressionService
from application.scenario_policy import TurnWorkerFactory
from application.speech_unit import SpeechUnitSealingService
from application.story_expression import StoryExpressionQueryService
from application.story_initialization import (
    GOLDEN_SCENARIO_ID,
    StoryInitializationService,
    TrustedScenarioBundle,
)
from application.story_session_facade import (
    PublicStorySessionView,
    StorySessionFacade,
    SubmitAdviceCommand,
    TurnDeliveryView,
)
from application.story_session_open import StorySessionOpenService
from application.story_turn_commit import StoryTurnCommitResult

from .audio.config import AudioProviderConfig
from .audio.voice_delivery import (
    TurnDeliveryError,
    TurnDeliveryOutcome,
    TurnDeliveryPipeline,
)
from .audio.voice_runtime import SealedSpeechUnitRegistry, VoiceRenderRuntime
from .beat_plan_repository import SQLiteBeatPlanRepository
from .database_manager import DatabaseManager, DatabasePaths
from .episode_finalization_repository import SQLiteEpisodeFinalizationRepository
from .episode_settlement import (
    ScenarioSettlement,
    SettlingCommitPort,
    _SettlementBeatPlanPort,
)
from .narrative_block_repository import SQLiteNarrativeBlockRepository
from .outbox import OutboxProjector
from .player_advice_repository import SQLitePlayerAdviceRepository
from .post_commit_control import (
    PostCommitControlError,
    PostCommitControlService,
)
from .post_commit_job_repository import SQLitePostCommitJobRepository
from .post_commit_reconciliation import PostCommitReconciler
from .post_commit_worker import PostCommitWorker
from .scenarios.golden_policy import GoldenScenarioPolicy, GoldenScenarioWorkers
from .scenarios.post_commit_handlers import (
    ScenarioAudioPrepareHandler,
    ScenarioEpisodeFinalizeHandler,
    ScenarioNarrativePublishHandler,
)
from .scenarios.post_commit_planning import ScenarioPostCommitJobPlanner
from .story_bootstrap_repository import SQLiteStoryBootstrapRepository
from .story_content_repository import SQLiteStoryContentRepository
from .story_control import StoryRequestHandler, story_control_handlers
from .story_expression_control import (
    SQLiteNarrativePublicIdentityReader,
    story_expression_control_handlers,
)
from .story_session_open_repository import SQLiteStorySessionOpenPort
from .story_session_query import SQLiteStorySessionQuery
from .story_session_repository import SQLiteStorySessionCommitPort
from .turn_intake_repository import SQLiteTurnInputCommandPort
from .voice_binding_repository import SQLiteVoiceBindingRepository
from .voice_binding_resolver import (
    VoiceBindingResolutionError,
    resolve_voice_runtime,
)

ENGINEERING_WORLD_ID = "engineering-golden001"
CONTENT_ARTIFACT_NAME = "canon.db"
FIVE_TURN_DIRNAME = "five_turn"
DICTIONARY_REVISION = "wom-zh-cn-v1"


def default_content_path() -> Path:
    """Locate the packaged content artifact relative to the installed module."""
    return Path(__file__).resolve().parent / "story_content" / CONTENT_ARTIFACT_NAME


def load_five_turn_catalog(
    content_path: Path, seed: dict
) -> GoldenFiveTurnCatalog:
    """Load the frozen five-turn catalog from the module-relative content dir.

    The packaged runtime resolves the catalog next to the content artifact, never
    from a repository directory or environment variable, so the shipped App can
    complete all five fixed turns without the source tree.
    """
    base = Path(content_path).parent / FIVE_TURN_DIRNAME
    return GoldenFiveTurnCatalog.from_directory(
        base / "turns", base / "mock", seed=seed
    )


def _post_commit_control_handlers(
    service: PostCommitControlService,
) -> dict[str, StoryRequestHandler]:
    """Expose the durable work projection and explicit retry at the IPC edge."""

    async def get_work(
        _context: Mapping[str, object], payload: Mapping[str, object]
    ) -> tuple[dict[str, object] | None, str | None, bool]:
        try:
            result = await service.get_work(
                session_id=cast(str, payload.get("session_id")),
                turn_id=cast(str, payload.get("turn_id")),
            )
        except PostCommitControlError as exc:
            return None, exc.code, False
        return result.to_payload(), None, False

    async def retry_work(
        _context: Mapping[str, object], payload: Mapping[str, object]
    ) -> tuple[dict[str, object] | None, str | None, bool]:
        try:
            result = await service.retry_work(
                session_id=cast(str, payload.get("session_id")),
                turn_id=cast(str, payload.get("turn_id")),
                kind=cast(str, payload.get("kind")),
                retry_request_id=cast(str, payload.get("retry_request_id")),
            )
        except PostCommitControlError as exc:
            return None, exc.code, False
        return result.to_payload(), None, False

    return {
        "story.turn.work.get": get_work,
        "story.turn.work.retry": retry_work,
    }


@dataclass(frozen=True, slots=True)
class StoryRuntimeConfig:
    """Explicit storage configuration; never inferred from cwd or environment."""

    data_root: Path
    content_path: Path
    world_id: str = ENGINEERING_WORLD_ID
    voice_id: str | None = None

    @classmethod
    def for_data_root(
        cls,
        data_root: Path,
        *,
        content_path: Path | None = None,
        world_id: str = ENGINEERING_WORLD_ID,
        voice_id: str | None = None,
    ) -> StoryRuntimeConfig:
        return cls(
            data_root=Path(data_root),
            content_path=Path(content_path) if content_path else default_content_path(),
            world_id=world_id,
            voice_id=voice_id,
        )

    def paths(self) -> DatabasePaths:
        derived = DatabasePaths.for_world(self.data_root, self.world_id)
        # Keep the shared DatabasePaths rule for writable roles and replace only
        # the read-only canon role with the build-time content artifact.
        return DatabasePaths(
            canon=self.content_path,
            world=derived.world,
            retrieval=derived.retrieval,
            runtime=derived.runtime,
        )


class StoryRuntime:
    """Owns the story database handle and the public handler registry."""

    def __init__(
        self,
        *,
        database: DatabaseManager,
        facade: StorySessionFacade,
        content: TrustedScenarioBundle,
        model_ready: bool,
        voice: VoiceRenderRuntime | None,
        post_commit_worker: PostCommitWorker | None,
        durable_post_commit: bool,
    ) -> None:
        self._database = database
        self._facade = facade
        self._content = content
        # Durable capabilities reachable from the composition root. Frozen
        # expression (BeatPlan), Story Book restart reads and the rebuildable
        # retrieval projection. The five-turn catalog is resolved from the
        # module-relative packaged content, so the App can run all five turns.
        self._beat_plans = SQLiteBeatPlanRepository(database)
        self._episodes = SQLiteEpisodeFinalizationRepository(database)
        self._projector = OutboxProjector(database)
        self._model_ready = model_ready
        self._voice = voice
        self._post_commit_worker = post_commit_worker
        narrative_port = SQLiteNarrativeBlockRepository(database)
        expression = StoryExpressionQueryService(
            reads=narrative_port,
            disclosure=AudioDisclosureAuthorizer(narrative_port),
            identities=SQLiteNarrativePublicIdentityReader(
                SQLiteStoryBootstrapRepository(database)
            ),
        )
        story_handlers = story_control_handlers(facade)
        if durable_post_commit:
            story_handlers["story.advice.submit.v2"] = story_handlers.pop(
                "story.advice.submit"
            )
            story_handlers["story.turn.submit.v2"] = story_handlers.pop(
                "story.turn.submit"
            )
            post_commit_control = PostCommitControlService(
                database=database,
                jobs=SQLitePostCommitJobRepository(database),
                expression=expression,
                registry=(
                    self._voice.sealed_units
                    if self._voice is not None
                    else SealedSpeechUnitRegistry()
                ),
            )
            story_handlers.update(
                _post_commit_control_handlers(post_commit_control)
            )
        self._handlers = {
            **story_handlers,
            **story_expression_control_handlers(expression),
        }

    @classmethod
    async def open(
        cls,
        config: StoryRuntimeConfig,
        *,
        expected_sqlite_version: str | None = None,
        fault_hook: Callable[[str], None] | None = None,
        model_endpoint: ModelEndpointConfig | None = None,
        audio_config: AudioProviderConfig | None = None,
        fetch_json=None,
        durable_post_commit: bool = False,
    ) -> StoryRuntime:
        if type(durable_post_commit) is not bool:
            raise ValueError("durable_post_commit_must_be_boolean")
        content_repository = SQLiteStoryContentRepository(config.content_path)
        content = await content_repository.load(GOLDEN_SCENARIO_ID)
        catalog = load_five_turn_catalog(config.content_path, content.seed)
        database = await DatabaseManager.open(
            config.paths(),
            expected_sqlite_version=expected_sqlite_version,
            fault_hook=fault_hook,
        )
        voice = None
        post_commit_worker = None
        try:
            voice = cls._open_voice(audio_config)
            facade, post_commit_worker = await cls._build_facade(
                database,
                content_repository,
                content,
                catalog,
                config.content_path,
                config=config,
                model_endpoint=model_endpoint,
                voice=voice,
                audio_config=audio_config,
                fetch_json=fetch_json,
                durable_post_commit=durable_post_commit,
            )
            if durable_post_commit:
                await PostCommitReconciler(database).reconcile()
            if post_commit_worker is not None:
                await post_commit_worker.start()
        except BaseException:
            if post_commit_worker is not None:
                await post_commit_worker.stop()
            if voice is not None:
                await voice.aclose()
            await database.close()
            raise
        return cls(
            database=database,
            facade=facade,
            content=content,
            model_ready=model_endpoint is not None,
            voice=voice,
            post_commit_worker=post_commit_worker,
            durable_post_commit=durable_post_commit,
        )

    @staticmethod
    def _open_voice(audio_config: AudioProviderConfig | None) -> VoiceRenderRuntime | None:
        """Build the render runtime only for a named SpeechRail provider."""
        if audio_config is None:
            return None
        if audio_config.provider_name.casefold() != "speechrail":
            return None
        return VoiceRenderRuntime(provider_instance=audio_config.provider_name)

    @classmethod
    async def _build_facade(
        cls,
        database: DatabaseManager,
        content_repository: SQLiteStoryContentRepository,
        content: TrustedScenarioBundle,
        catalog: GoldenFiveTurnCatalog,
        content_path: Path,
        *,
        config: StoryRuntimeConfig,
        model_endpoint: ModelEndpointConfig | None,
        voice: VoiceRenderRuntime | None,
        audio_config: AudioProviderConfig | None,
        fetch_json,
        durable_post_commit: bool = False,
    ) -> tuple[StorySessionFacade, PostCommitWorker | None]:
        golden = GoldenFiveTurnFactory(catalog)
        scenario = GoldenScenarioPolicy(golden)
        # Validate the packaged bundle before exposing a runtime. Persisted
        # sessions repeat this check against their frozen bootstrap on reads.
        identity = scenario.identity(content)
        # AO-03: the committed turn registers its own post-COMMIT intents in the
        # same transaction, so the minimal job graph is decided by the same
        # frozen scenario the turn was played under. A voice runtime without
        # provider configuration still counts as "voice not configured": the
        # audio job starts blocked and never holds back text or the Episode.
        planner = (
            ScenarioPostCommitJobPlanner(
                scenario=scenario,
                identity=identity,
                story_seed_id=str(content.seed["id"]),
                max_turn=golden.max_turn,
                voice_configured=voice is not None and audio_config is not None,
            )
            if durable_post_commit
            else None
        )
        workers = (
            LiveFirstTurnFactory.from_config(model_endpoint)
            if model_endpoint is not None
            else GoldenScenarioWorkers(golden)
        )
        expression = PostCommitExpressionService(
            templates=golden.expression_templates,
            beats=_SettlementBeatPlanPort(
                SQLiteBeatPlanRepository(database), database
            ),
            narratives=SQLiteNarrativeBlockRepository(database),
        )
        settlement = ScenarioSettlement(
            database=database,
            scenario=scenario,
            expression=expression,
            content_path=content_path,
            # With a live model the post-COMMIT narrative service publishes its
            # disclosed model expression; frozen templates would be a second
            # writer for the same narrative slot. Without a model the authored
            # frozen path is unchanged.
            frozen_expression=model_endpoint is None,
        )
        query = SQLiteStorySessionQuery(
            database,
            supported_advice=(content.advice_template.raw_input,),
        )
        narrative_port = SQLiteNarrativeBlockRepository(database)
        bindings = SQLiteVoiceBindingRepository(database)
        delivery = _DeliveryCoordinator(
            query=query,
            narratives=narrative_port,
            bindings=bindings,
            voice=voice,
            audio_config=audio_config,
            voice_id=config.voice_id,
            workers=workers,
            fetch_json=fetch_json,
        )
        story_port = SQLiteStorySessionCommitPort(database, planner=planner)
        story = (
            story_port
            if durable_post_commit
            else SettlingCommitPort(story_port, settlement)
        )
        facade = StorySessionFacade(
            initialization=StoryInitializationService(content_repository),
            open_sessions=StorySessionOpenService(SQLiteStorySessionOpenPort(database)),
            query=query,
            intake=SQLiteTurnInputCommandPort(database),
            advice=SQLitePlayerAdviceRepository(database),
            story=story,
            scenario=scenario,
            workers=workers,
            after_commit=None if durable_post_commit else delivery.after_commit,
        )
        post_commit_worker = None
        if durable_post_commit:
            assert planner is not None
            read_story = SQLiteStorySessionCommitPort(database)
            bootstraps = SQLiteStoryBootstrapRepository(database)
            narratives = SQLiteNarrativeBlockRepository(database)
            bindings = SQLiteVoiceBindingRepository(database)
            post_commit_worker = PostCommitWorker(
                database=database,
                repository=SQLitePostCommitJobRepository(database),
                narrative_handler=ScenarioNarrativePublishHandler(
                    database=database,
                    story=read_story,
                    bootstraps=bootstraps,
                    advice=SQLitePlayerAdviceRepository(database),
                    narratives=narratives,
                    beat_plans=SQLiteBeatPlanRepository(database),
                    expression=expression,
                    workers=workers,
                    frozen_expression=model_endpoint is None,
                ),
                episode_finalize_handler=ScenarioEpisodeFinalizeHandler(
                    database=database,
                    story=read_story,
                    bootstraps=bootstraps,
                    settlement=settlement,
                ),
                audio_prepare_handler=ScenarioAudioPrepareHandler(
                    database=database,
                    story=read_story,
                    bootstraps=bootstraps,
                    narratives=narratives,
                    bindings=bindings,
                    voice=voice,
                    audio_config=audio_config,
                    voice_id=config.voice_id,
                    dictionary_revision=DICTIONARY_REVISION,
                    fetch_json=fetch_json,
                ),
                supported_recipes=planner.supported_recipes,
            )
        return facade, post_commit_worker

    @property
    def request_handlers(self) -> dict[str, StoryRequestHandler]:
        return dict(self._handlers)

    @property
    def control_handlers(self) -> dict[str, Callable[[Mapping[str, object]], Awaitable[tuple[dict[str, object] | None, str | None]]]]:
        if self._voice is None:
            return {}
        return {"voice.render": self._voice.handle_control}

    @property
    def media_session_handler(self):
        return None if self._voice is None else self._voice.media_handler

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    @property
    def beat_plans(self) -> SQLiteBeatPlanRepository:
        return self._beat_plans

    @property
    def episodes(self) -> SQLiteEpisodeFinalizationRepository:
        return self._episodes

    async def rebuild_retrieval_projection(self):
        """Idempotently rebuild the disposable retrieval projection from world.db."""
        return await self._projector.rebuild()

    @property
    def scenario_id(self) -> str:
        return self._content.scenario_id

    def health(self) -> dict[str, bool]:
        # Readiness is what was actually proven at startup, never an aspiration.
        # The frozen Golden 001 proposer is not a live model, and a render
        # runtime that was never built cannot serve audio.
        return {
            "transport_ready": True,
            "world_ready": True,
            "model_ready": self._model_ready,
            "voice_ready": self._voice is not None,
        }

    async def close(self) -> None:
        if self._post_commit_worker is not None:
            try:
                await self._post_commit_worker.stop()
            except asyncio.CancelledError:
                # A handler cancellation may already have terminated the worker
                # loop while leaving its durable claim for the next Engine. Close
                # can proceed only after that task is actually gone; cancellation
                # of this close caller while the worker is still draining propagates.
                if self._post_commit_worker.is_running:
                    raise
        if self._voice is not None:
            await self._voice.aclose()
        await self._database.close()


class _DeliveryCoordinator:
    """Publish durable text before resolving or attempting its optional audio."""

    def __init__(
        self,
        *,
        query: SQLiteStorySessionQuery,
        narratives: SQLiteNarrativeBlockRepository,
        bindings: SQLiteVoiceBindingRepository,
        voice: VoiceRenderRuntime | None,
        audio_config: AudioProviderConfig | None,
        voice_id: str | None,
        workers: TurnWorkerFactory,
        fetch_json,
    ) -> None:
        self._query = query
        self._narratives = narratives
        self._bindings = bindings
        self._voice = voice
        self._audio = audio_config
        self._voice_id = voice_id
        self._workers = workers
        self._fetch_json = fetch_json

    async def after_commit(
        self,
        command: SubmitAdviceCommand,
        result: StoryTurnCommitResult,
        view: PublicStorySessionView,
    ) -> TurnDeliveryView:
        """Post-COMMIT expression.  A failure here never touches Domain state."""
        try:
            snapshot = await self._query.session(command.session_id)
        except Exception:  # noqa: BLE001 - a read failure cannot unwind COMMIT
            return TurnDeliveryView(state="unavailable", reason="session_unavailable")

        source: CommittedNarrativeSource | None = None
        try:
            compiler = self._workers.narrative_compiler(snapshot.bootstrap)
            if compiler is not None:
                story_revision = result.turn.committed_story_revision
                if story_revision is None:
                    raise NarrativePublicationError(
                        "committed_story_revision_missing"
                    )
                source = CommittedNarrativeSource(
                    turn_id=result.turn.id,
                    session_id=result.turn.session_id,
                    story_revision=story_revision,
                    state_delta_id=result.delta.id,
                    state_delta=result.delta,
                    scene_id=result.delta.story_delta.scene_id,
                    protagonist_id=result.session.protagonist_id,
                    disclosed_facts=(
                        f"{_outcome_summary(result, snapshot.bootstrap)}\n"
                        f"玩家原话：{command.raw_input}"
                    ),
                )
            else:
                # Frozen turns publish their authored NarrativeBlock during
                # settlement. The service reads it first and will not invoke
                # this sentinel unless that post-COMMIT artifact is unavailable.
                compiler = _UnavailableNarrativeCompiler()
        except Exception as exc:  # noqa: BLE001 - expression failure is post-COMMIT
            return TurnDeliveryView(
                state="unavailable",
                reason=_delivery_failure_code(exc, "narrative_unavailable"),
            )

        publication = CommittedNarrativeService(
            reads=self._narratives,
            publisher=self._narratives,
            compiler=compiler,
        )
        try:
            narrative = await publication.ensure(
                turn_id=result.turn.id,
                source=source,
            )
        except Exception as exc:  # noqa: BLE001 - preserve the committed Domain result
            return TurnDeliveryView(
                state="unavailable",
                reason=_delivery_failure_code(exc, "narrative_unavailable"),
            )

        story_revision = result.turn.committed_story_revision
        if story_revision is None:
            return TurnDeliveryView(
                state="unavailable",
                reason="committed_story_revision_missing",
            )

        if self._voice is None or self._audio is None or not self._voice_id:
            return TurnDeliveryView(state="unavailable", reason="voice_not_configured")

        segment_index = next(
            (
                index
                for index, segment in enumerate(narrative.segments)
                if segment.type == "character"
                and segment.speaker_id == result.session.protagonist_id
            ),
            None,
        )
        if segment_index is None:
            return TurnDeliveryView(
                state="unavailable",
                reason="narrative_has_no_character_segment",
            )

        try:
            resolved = await resolve_voice_runtime(
                repository=self._bindings,
                session=snapshot.session,
                config=self._audio,
                voice_id=self._voice_id,
                fetch_json=self._fetch_json,
            )
        except VoiceBindingResolutionError as exc:
            return TurnDeliveryView(state="unavailable", reason=exc.code)
        except Exception:  # noqa: BLE001 - hide provider details after text publication
            return TurnDeliveryView(
                state="unavailable",
                reason="voice_runtime_unavailable",
            )

        pipeline = TurnDeliveryPipeline(
            sealing=SpeechUnitSealingService(
                disclosure=AudioDisclosureAuthorizer(self._narratives),
                bindings=self._bindings,
            ),
            voice=self._voice,
            binding_scope=resolved.scope,
            expected_binding_revision=resolved.binding.binding_revision,
            execution_model_id=resolved.execution_model_id,
            dictionary_revision=DICTIONARY_REVISION,
            seal_arguments={
                "semantic_anchors": (),
                "pronunciation_rules": (),
                "desired_performance": resolved.performance,
                "performance_capabilities": resolved.capabilities,
            },
        )
        try:
            receipt = await pipeline.deliver(
                TurnDeliveryOutcome(
                    turn_id=result.turn.id,
                    session_id=command.session_id,
                    story_revision=story_revision,
                    state_delta_id=result.delta.id,
                    narrative=narrative,
                    segment_index=segment_index,
                )
            )
            if receipt is None:
                return TurnDeliveryView(
                    state="unavailable",
                    reason="narrative_has_no_character_segment",
                )
        except TurnDeliveryError as exc:
            return TurnDeliveryView(state="unavailable", reason=exc.code)
        except Exception:  # noqa: BLE001 - audio failures cannot unwind COMMIT
            return TurnDeliveryView(
                state="unavailable",
                reason="voice_delivery_unavailable",
            )
        return TurnDeliveryView(
            state="ready",
            narrative_block_id=receipt.narrative_block_id,
            speech_unit_id=receipt.speech_unit_id,
            spoken_text=receipt.spoken_text,
            render_recipe=receipt.render_recipe,
        )


class _UnavailableNarrativeCompiler:
    async def compile(self, *, committed: str) -> NarrativeCandidate:
        del committed
        raise NarrativePublicationError("narrative_compiler_unavailable")


def _delivery_failure_code(error: Exception, fallback: str) -> str:
    code = getattr(error, "code", None)
    if (
        isinstance(code, str)
        and code
        and len(code) <= 128
        and code.isascii()
        and all(char.islower() or char.isdigit() or char == "_" for char in code)
    ):
        return code
    return fallback


def _outcome_summary(result: StoryTurnCommitResult, bootstrap) -> str:
    """Describe only committed, already-disclosed facts.

    Clue identifiers are rendered through the scenario's display-name table, so
    the narrator never receives a canonical or hidden identifier.
    """
    names = bootstrap.presentation.clue_display_names
    delta = result.delta
    added = [names.get(cid, cid) for cid in (delta.story_delta.clue_ids_add or ())]
    parts = [f"结果判定：{delta.outcome}"]
    if added:
        parts.append("玩家发现了：" + "、".join(added))
    story = delta.story_delta
    if story.scene_id:
        parts.append(f"场景转为：{story.scene_id}")
    if story.world_time_delta_minutes:
        parts.append(f"世界时间推进：{story.world_time_delta_minutes} 分钟")
    return "\n".join(parts)


__all__ = [
    "DICTIONARY_REVISION",
    "ENGINEERING_WORLD_ID",
    "ModelTransportError",
    "StoryRuntime",
    "StoryRuntimeConfig",
    "default_content_path",
]
