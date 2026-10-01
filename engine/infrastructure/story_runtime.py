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
import secrets
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol, cast

from contracts import NarrativeBlock

from ai.authorized_live_execution import AuthorizedLiveExecution
from ai.golden_five_turn import GoldenFiveTurnCatalog, GoldenFiveTurnFactory
from ai.live_turn_workers import LiveFirstTurnFactory, LiveTurnWorkerProfiles
from ai.openai_compatible import (
    ModelEndpointConfig,
    ModelTransportError,
    OpenAICompatibleChatTransport,
)
from ai.prompt_renderer import PromptRenderer
from application.audio_disclosure import AudioDisclosureAuthorizer
from application.gameplay_context import GameplayContextCoordinator
from application.narrative_publication import (
    CommittedNarrativeService,
    CommittedNarrativeSource,
    NarrativeCandidate,
    NarrativePublicationError,
    turn_scene_roster,
)
from application.post_commit_expression import PostCommitExpressionService
from application.scenario_policy import TurnWorkerFactory
from application.speech_unit import SpeechUnitSealingService
from application.story_disclosure import (
    disclosed_castable_roster,
    disclosed_turn_facts,
)
from application.story_expression import StoryExpressionQueryService
from application.story_initialization import (
    GOLDEN_SCENARIO_ID,
    StoryInitializationService,
    TrustedScenarioBundle,
)
from application.story_session_facade import (
    PublicStorySessionView,
    SegmentDeliveryView,
    StorySessionSnapshotRecord,
    StorySessionFacade,
    SubmitAdviceCommand,
    TurnDeliveryView,
)
from application.story_session_open import StorySessionOpenService
from application.story_turn_commit import StoryTurnCommitResult
from application.turn_context_binding import (
    AuthorizedContextSource,
    AuthorizedTurnContextBinding,
    TurnContextBindingError,
    TurnContextBindingPort,
    TurnContextStage,
)
from application.turn_orchestrator import TurnOrchestrator
from application.voice_evidence import load_evidence_record, render_execution
from application.voice_foundry import VoiceFoundryWorker
from application.voice_foundry_commands import VoiceFoundryCommandService
from application.voice_foundry_service import VoiceSupplyService
from application.voice_supply_trigger import VoiceSupplyTrigger

from .audio.config import AudioProviderConfig
from .audio.voice_delivery import (
    TurnDeliveryError,
    TurnDeliveryOutcome,
    TurnDeliveryPipeline,
)
from .audio.foundry_policy import DEFAULT_VARIANT, execution_policy
from .audio.voice_foundry_adapter import SpeechRailVoiceFoundryAdapter
from .audio.voice_runtime import SealedSpeechUnitRegistry, VoiceRenderRuntime
from .beat_plan_repository import SQLiteBeatPlanRepository
from .database_manager import DatabaseManager, DatabasePaths
from .episode_finalization_repository import SQLiteEpisodeFinalizationRepository
from .episode_settlement import (
    ScenarioSettlement,
    SettlingCommitPort,
    _SettlementBeatPlanPort,
)
from .gameplay_context_repository import SQLiteGameplayContextRepository
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
from .turn_context_repository import (
    SQLiteTurnContextRepository,
    TurnContextBinding,
    TurnContextStorageConflict,
)
from .turn_intake_repository import SQLiteTurnInputCommandPort
from .voice_binding_repository import SQLiteVoiceBindingRepository
from .voice_design_catalog import (
    VoiceDesignCatalog,
    VoiceDesignError,
    load_voice_design_catalog,
)
from .voice_binding_resolver import (
    VoiceBindingResolutionError,
    resolve_voice_runtime,
)
from domain.voice_identity import VoiceBindingScope

from .voice_binding_resolver import binding_scope_for, speaker_scope_for
from .voice_foundry_control import (
    VoiceScopeResolver,
    ControlHandler as VoiceFoundryControlHandler,
    voice_foundry_control_handlers,
)
from .voice_foundry_driver import VoiceFoundryDriver
from .voice_foundry_repository import SQLiteVoiceFoundryRepository

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


class _SQLiteTurnContextBindingPort(TurnContextBindingPort):
    """Adapt the application-only binding DTO to the frozen SQLite model."""

    def __init__(self, repository: SQLiteTurnContextRepository) -> None:
        self._repository = repository

    @staticmethod
    def _storage_binding(
        binding: AuthorizedTurnContextBinding,
    ) -> TurnContextBinding:
        stored = TurnContextBinding.from_manifest(
            turn_id=binding.turn_id,
            stage=binding.stage,
            input_turn_id=binding.input_turn_id,
            source_store_revision=binding.source_store_revision,
            source_story_revision=binding.source_story_revision,
            policy_revision=binding.policy_revision,
            content_digest=binding.content_digest,
            lineage_digest=binding.lineage_digest,
            manifest=[
                {
                    "source_id": source.source_id,
                    "source_revision": source.source_revision,
                    "fingerprint": source.fingerprint,
                }
                for source in binding.manifest
            ],
        )
        if (
            stored.context_revision != binding.context_revision
            or stored.manifest_digest != binding.manifest_digest
        ):
            raise TurnContextBindingError("revision_conflict")
        return stored

    @staticmethod
    def _application_binding(
        binding: TurnContextBinding,
    ) -> AuthorizedTurnContextBinding:
        value = AuthorizedTurnContextBinding(
            turn_id=binding.turn_id,
            stage=binding.stage,  # type: ignore[arg-type]
            input_turn_id=binding.input_turn_id,
            source_store_revision=binding.source_store_revision,
            source_story_revision=binding.source_story_revision,
            policy_revision=binding.policy_revision,
            content_digest=binding.content_digest,
            lineage_digest=binding.lineage_digest,
            manifest=tuple(
                AuthorizedContextSource(
                    source_id=source.source_id,
                    source_revision=source.source_revision,
                    fingerprint=source.fingerprint,
                )
                for source in binding.manifest
            ),
        )
        if (
            value.context_revision != binding.context_revision
            or value.manifest_digest != binding.manifest_digest
        ):
            raise TurnContextBindingError("revision_conflict")
        return value

    async def save(
        self,
        binding: AuthorizedTurnContextBinding,
    ) -> AuthorizedTurnContextBinding:
        if not isinstance(binding, AuthorizedTurnContextBinding):
            raise TurnContextBindingError("turn_identity_conflict")
        try:
            stored = await self._repository.save(self._storage_binding(binding))
        except TurnContextStorageConflict as exc:
            raise TurnContextBindingError(exc.code) from None
        return self._application_binding(stored)

    async def load(
        self,
        *,
        turn_id: str,
        stage: TurnContextStage,
    ) -> AuthorizedTurnContextBinding | None:
        try:
            stored = await self._repository.load(turn_id=turn_id, stage=stage)
        except TurnContextStorageConflict as exc:
            raise TurnContextBindingError(exc.code) from None
        return None if stored is None else self._application_binding(stored)


class _BoundSQLitePlayerAdviceRepository:
    """Keep infrastructure binding types behind this runtime adapter."""

    def __init__(
        self,
        repository: SQLitePlayerAdviceRepository,
        contexts: _SQLiteTurnContextBindingPort,
    ) -> None:
        self._repository = repository
        self._contexts = contexts

    async def load_input(self, input_turn_id: str):
        return await self._repository.load_input(input_turn_id)

    async def load_advice(self, input_turn_id: str):
        return await self._repository.load_advice(input_turn_id)

    async def publish(
        self,
        input_turn_id: str,
        advice,
        *,
        interpreter_revision: str,
        context_binding: AuthorizedTurnContextBinding | None = None,
    ):
        storage_binding = (
            None
            if context_binding is None
            else self._contexts._storage_binding(context_binding)
        )
        try:
            return await self._repository.publish(
                input_turn_id,
                advice,
                interpreter_revision=interpreter_revision,
                context_binding=storage_binding,
            )
        except TurnContextStorageConflict as exc:
            raise TurnContextBindingError(exc.code) from None


async def _live_worker_factory(
    database: DatabaseManager,
    endpoint: ModelEndpointConfig,
) -> LiveFirstTurnFactory:
    repository = SQLiteGameplayContextRepository(database)
    coordinator = GameplayContextCoordinator(
        snapshot=repository,
        authorization=repository,
        profiles=LiveTurnWorkerProfiles(),
        lore=repository.lore_port,
        world=repository.world_port,
        character=repository.character_port,
        story=repository.story_port,
        memory=repository.memory_port,
    )
    transport = OpenAICompatibleChatTransport(endpoint)
    try:
        execution = AuthorizedLiveExecution(
            coordinator=coordinator,
            renderer=PromptRenderer(secrets.token_bytes(32)),
            transport=transport,
            validate_proposal=lambda proposal, _request: isinstance(proposal, dict),
        )
    except BaseException:
        await transport.aclose()
        raise
    return LiveFirstTurnFactory(execution)


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


class _SupervisedLoop(Protocol):
    """The lifecycle three words every background loop in this runtime shares."""

    @property
    def is_running(self) -> bool: ...

    def request_stop(self) -> None: ...

    async def stop(self) -> None: ...


async def _close_runtime_resources(
    *,
    post_commit_worker: PostCommitWorker | None,
    foundry_driver: VoiceFoundryDriver | None = None,
    workers: TurnWorkerFactory | None,
    voice: VoiceRenderRuntime | None,
    database: DatabaseManager,
) -> None:
    """Release runtime resources once, continuing after independent failures."""

    errors: list[BaseException] = []
    if post_commit_worker is not None:
        errors.extend(
            await _stop_supervised(post_commit_worker),
        )

    # Before the database, and on the same terms as the post-commit worker:
    # both loops read and write through this handle, so a driver still
    # polling while the world closes is the same hazard as a worker still
    # settling.
    if foundry_driver is not None:
        errors.extend(await _stop_supervised(foundry_driver))

    close_workers = getattr(workers, "aclose", None)
    if callable(close_workers):
        try:
            await close_workers()
        except BaseException as error:  # noqa: BLE001 - keep releasing independent resources.
            errors.append(error)

    if voice is not None:
        try:
            await voice.aclose()
        except BaseException as error:  # noqa: BLE001 - keep releasing independent resources.
            errors.append(error)

    try:
        await database.close()
    except BaseException as error:  # noqa: BLE001 - keep releasing independent resources.
        errors.append(error)

    if errors:
        _raise_cleanup_errors(errors)


async def _stop_supervised(loop: _SupervisedLoop) -> list[BaseException]:
    """Stop a background loop, retrying once if the first attempt failed.

    The only thing that makes a failed stop worth reporting is the loop still
    running afterwards: that is the case where continuing would close the
    database out from under it. A stop that raised *and* left nothing running
    did what it was asked to, so its error is dropped rather than raised —
    which is what keeps a cancelled post-COMMIT job from turning a clean
    shutdown into a failed one.
    """
    errors: list[BaseException] = []
    for _ in range(2):
        try:
            await loop.stop()
            return errors
        except asyncio.CancelledError as error:
            if not loop.is_running:
                return errors
            errors.append(error)
        except BaseException as error:  # noqa: BLE001 - keep releasing independent resources.
            if not loop.is_running:
                return errors
            errors.append(error)
        loop.request_stop()
    if loop.is_running:
        _raise_cleanup_errors(errors)
    return errors


def _raise_cleanup_errors(errors: list[BaseException]) -> None:
    primary = errors[0]
    for extra in errors[1:]:
        primary.add_note(f"additional shutdown failure: {extra!r}")
    raise primary


class _NoDesigns:
    """Stands in for an unreadable catalog without disabling composition."""

    def __contains__(self, _identity: object) -> bool:
        return False

    def get(self, _identity: str) -> object:
        raise VoiceDesignError("voice_design_catalog_unreadable")


def _load_catalog_or_none() -> VoiceDesignCatalog | None:
    """Read the casting briefs, or report that this process has none.

    Content that will not load is not a reason to refuse to start. The
    engine's job is to run a world; losing the catalog costs the automatic
    path and the picker, which are visible and actionable, against an engine
    that refuses to open because a JSON file is malformed.
    """
    try:
        return load_voice_design_catalog()
    except VoiceDesignError:
        return None


@dataclass(frozen=True, slots=True)
class FoundryRuntime:
    """The supply chain, assembled and alive for as long as the world is.

    Holding the control handlers alone was enough to answer a client's calls
    and not enough to move any of them: registering eight methods made the
    surface look alive while a registered task sat at ``requested`` forever,
    because the thing that advances it was never given a lifetime. The driver
    is what turns a request into progress, so it starts with the runtime and
    stops with it.

    ``supply`` is carried for the callers that need to ask what an identity
    still needs without going through IPC — the pre-warm path, and the audio
    job that quietly requests a voice the first time somebody speaks.
    """

    supply: VoiceSupplyService
    driver: VoiceFoundryDriver
    designs: VoiceDesignCatalog | None
    handlers: dict[str, VoiceFoundryControlHandler]

    async def start(self) -> None:
        await self.driver.start()


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
        workers: TurnWorkerFactory,
        beat_plans: SQLiteBeatPlanRepository,
        episodes: SQLiteEpisodeFinalizationRepository,
        projector: OutboxProjector,
        handlers: dict[str, StoryRequestHandler],
        foundry: FoundryRuntime | None = None,
    ) -> None:
        self._database = database
        self._facade = facade
        self._content = content
        self._model_ready = model_ready
        self._voice = voice
        self._post_commit_worker = post_commit_worker
        self._workers = workers
        self._beat_plans = beat_plans
        self._episodes = episodes
        self._projector = projector
        self._handlers = dict(handlers)
        self._foundry = foundry
        self._close_task: asyncio.Task[None] | None = None

    @property
    def _foundry_driver(self) -> VoiceFoundryDriver | None:
        return None if self._foundry is None else self._foundry.driver

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
        workers: TurnWorkerFactory | None = None
        runtime: StoryRuntime | None = None
        try:
            voice = cls._open_voice(audio_config)
            workers = (
                await _live_worker_factory(database, model_endpoint)
                if model_endpoint is not None
                else GoldenScenarioWorkers(GoldenFiveTurnFactory(catalog))
            )
            runtime = cls._compose_runtime(
                database,
                content_repository,
                content,
                catalog,
                config.content_path,
                config=config,
                model_endpoint=model_endpoint,
                voice=voice,
                audio_config=audio_config,
                workers=workers,
                fetch_json=fetch_json,
                durable_post_commit=durable_post_commit,
            )
            if durable_post_commit:
                await PostCommitReconciler(database).reconcile()
            if runtime._post_commit_worker is not None:
                await runtime._post_commit_worker.start()
            # The supply driver only now has something to advance: any task
            # registered before this point was, by construction, a request
            # nobody had made yet.
            if runtime._foundry is not None:
                await runtime._foundry.start()
            return runtime
        except BaseException as failure:
            try:
                if runtime is not None:
                    await runtime.close()
                else:
                    await _close_runtime_resources(
                        post_commit_worker=None,
                        workers=workers,
                        voice=voice,
                        database=database,
                    )
            except BaseException as cleanup_error:  # noqa: BLE001 - preserve startup failure after cleanup.
                failure.add_note(
                    f"runtime cleanup also failed: {cleanup_error!r}"
                )
            raise

    @staticmethod
    def _open_voice(audio_config: AudioProviderConfig | None) -> VoiceRenderRuntime | None:
        """Build the render runtime only for a named SpeechRail provider."""
        if audio_config is None:
            return None
        if audio_config.provider_name.casefold() != "speechrail":
            return None
        return VoiceRenderRuntime(provider_instance=audio_config.provider_name)

    @staticmethod
    def _open_foundry(
        database: DatabaseManager,
        audio_config: AudioProviderConfig | None,
        scopes: VoiceScopeResolver | None = None,
    ) -> "FoundryRuntime | None":
        """Wire the supply chain to a real provider, or to nothing at all.

        Every component here had a test and no production caller, which is why
        a casting could be driven from a test and from nowhere else. They are
        built together and torn down together: a repository with no port, or a
        port with no repository, would each be a supply chain that cannot
        finish.

        The surface is registered only when a port can actually be built.
        Advertising eight methods whose every write ends in
        ``service_unavailable`` would be a handshake promising a capability
        the process does not have.
        """
        if audio_config is None:
            return None
        if audio_config.provider_name.casefold() != "speechrail":
            return None
        # Declared, not inferred. A deployment that has not said which model
        # catalog key it casts with, or under what rights scope, gets no
        # foundry: the adapter would refuse every publish anyway, and a
        # surface advertised in the handshake is a promise the process cannot
        # keep.
        policy = execution_policy(
            audio_config, dictionary_revision=DICTIONARY_REVISION
        )
        if policy is None:
            return None
        repository = SQLiteVoiceFoundryRepository(database)
        supply = VoiceSupplyService(
            repository=repository,
            bindings=SQLiteVoiceBindingRepository(database),
        )
        # The audition is rendered by the model the game will speak with. A
        # preview rendered by anything else yields evidence about a
        # configuration no player will ever hear, and the whole point of
        # binding evidence to a model artifact is lost.
        port = SpeechRailVoiceFoundryAdapter(
            audio_config,
            preview_model=audio_config.tts_model,
            execution_policy=policy,
        )
        worker = VoiceFoundryWorker(repository, port)
        commands = VoiceFoundryCommandService(
            repository=repository, supply=supply, driver=worker
        )
        # One catalog, loaded once and shared: the picker the App renders and
        # the brief the trigger casts from have to be the same words, or a
        # button and an automatic first appearance would produce different
        # voices for the same character.
        designs = _load_catalog_or_none()
        return FoundryRuntime(
            supply=supply,
            driver=VoiceFoundryDriver(repository=repository, worker=worker),
            designs=designs,
            handlers=voice_foundry_control_handlers(
                repository=repository,
                supply=supply,
                commands=commands,
                worker=worker,
                designs=designs,
                scopes=scopes,
                provider_instance=(
                    "" if audio_config is None else audio_config.provider_name
                ),
            ),
        )

    @staticmethod
    def _open_supply_trigger(
        foundry: "FoundryRuntime | None",
        audio_config: AudioProviderConfig | None,
    ) -> VoiceSupplyTrigger | None:
        """Build the silent first-appearance trigger, or nothing at all.

        Shares the catalog the control surface publishes rather than reading
        it again, so the brief a person picks in the App and the brief cast
        without asking are the same object.
        """
        if foundry is None or audio_config is None:
            return None
        return VoiceSupplyTrigger(
            supply=foundry.supply,
            # A catalog that failed to load costs the handful of briefs a
            # person already ruled on — not the automatic path. Composing a
            # brief from what a character has said needs no catalog at all,
            # and tying the two together would mean one malformed file
            # silences every new speaker in the world.
            designs=foundry.designs or _NoDesigns(),
            provider_instance=audio_config.provider_name,
        )

    @classmethod
    def _compose_runtime(
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
        workers: TurnWorkerFactory,
        fetch_json,
        durable_post_commit: bool = False,
    ) -> StoryRuntime:
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
        context_bindings = _SQLiteTurnContextBindingPort(
            SQLiteTurnContextRepository(database)
        )
        live_context_bindings = (
            context_bindings if model_endpoint is not None else None
        )
        advice_repository = SQLitePlayerAdviceRepository(database)
        advice = (
            _BoundSQLitePlayerAdviceRepository(
                advice_repository,
                context_bindings,
            )
            if model_endpoint is not None
            else advice_repository
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
        # Read-only half of the foundry, wired independently of the control
        # surface. ``_open_foundry`` returns nothing when a deployment has not
        # declared a casting policy, but a voice published under an earlier
        # configuration still has evidence that a render must be admitted
        # against — and evidence outlives the switch that minted it.
        evidence_store = SQLiteVoiceFoundryRepository(database)
        foundry = cls._open_foundry(
            database, audio_config, scopes=_SessionScopeResolver(query)
        )
        supply_trigger = cls._open_supply_trigger(foundry, audio_config)
        delivery = _DeliveryCoordinator(
            query=query,
            narratives=narrative_port,
            bindings=bindings,
            voice=voice,
            audio_config=audio_config,
            voice_id=config.voice_id,
            workers=workers,
            context_bindings=live_context_bindings,
            fetch_json=fetch_json,
            evidence_store=evidence_store,
        )
        story_port = SQLiteStorySessionCommitPort(database, planner=planner)
        story = (
            story_port
            if durable_post_commit
            else SettlingCommitPort(story_port, settlement)
        )
        initialization = StoryInitializationService(content_repository)
        open_sessions = StorySessionOpenService(
            SQLiteStorySessionOpenPort(database)
        )
        intake = SQLiteTurnInputCommandPort(database)
        turns = TurnOrchestrator(
            sessions=query,
            intake=intake,
            advice=advice,
            story=story,
            scenario=scenario,
            workers=workers,
            context=live_context_bindings,
            work=None if durable_post_commit else delivery.after_commit,
        )
        facade = StorySessionFacade(
            initialization=initialization,
            open_sessions=open_sessions,
            query=query,
            scenario=scenario,
            turns=turns,
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
                    advice=advice_repository,
                    narratives=narratives,
                    beat_plans=SQLiteBeatPlanRepository(database),
                    expression=expression,
                    workers=workers,
                    frozen_expression=model_endpoint is None,
                    context_bindings=live_context_bindings,
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
                    evidence_store=evidence_store,
                    supply_trigger=supply_trigger,
                ),
                supported_recipes=planner.supported_recipes,
            )

        beat_plans = SQLiteBeatPlanRepository(database)
        episodes = SQLiteEpisodeFinalizationRepository(database)
        projector = OutboxProjector(database)
        public_narratives = SQLiteNarrativeBlockRepository(database)
        expression_query = StoryExpressionQueryService(
            reads=public_narratives,
            disclosure=AudioDisclosureAuthorizer(public_narratives),
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
                expression=expression_query,
                registry=(
                    voice.sealed_units
                    if voice is not None
                    else SealedSpeechUnitRegistry()
                ),
            )
            story_handlers.update(
                _post_commit_control_handlers(post_commit_control)
            )
        handlers = {
            **story_handlers,
            **story_expression_control_handlers(expression_query),
        }
        return cls(
            database=database,
            facade=facade,
            content=content,
            model_ready=model_endpoint is not None,
            voice=voice,
            post_commit_worker=post_commit_worker,
            workers=workers,
            beat_plans=beat_plans,
            episodes=episodes,
            projector=projector,
            handlers=handlers,
            foundry=foundry,
        )

    @property
    def request_handlers(self) -> dict[str, StoryRequestHandler]:
        return dict(self._handlers)

    @property
    def control_handlers(self) -> dict[str, Callable[[Mapping[str, object]], Awaitable[tuple[dict[str, object] | None, str | None]]]]:
        # The supply surface does not depend on the render runtime: a voice has
        # to be cast long before there is anything to render it with. Gating
        # the whole registry on ``_voice`` would hide eight working methods
        # from every engine that has no renderer configured yet.
        handlers: dict[
            str,
            Callable[
                [Mapping[str, object]],
                Awaitable[tuple[dict[str, object] | None, str | None]],
            ],
        ] = dict(self._foundry.handlers) if self._foundry is not None else {}
        if self._voice is not None:
            handlers["voice.render"] = self._voice.handle_control
        return handlers

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
        task = self._close_task
        if task is None:
            task = asyncio.create_task(
                _close_runtime_resources(
                    post_commit_worker=self._post_commit_worker,
                    foundry_driver=self._foundry_driver,
                    workers=self._workers,
                    voice=self._voice,
                    database=self._database,
                ),
                name="story-runtime-close",
            )
            self._close_task = task
        await asyncio.shield(task)


class _SessionScopeResolver:
    """Answer "whose world is this" from a session the engine already owns.

    The App is never told the world id, the worldline id or the owner, and it
    has no business being: a scope it could name is a scope it could forge.
    So the button sends a session it is already in, and the engine derives the
    rest from the session it already has. The identity and the phase come from
    the design rather than the caller — the design is content this engine
    published, and that is what makes the swap safe.
    """

    def __init__(self, query: SQLiteStorySessionQuery) -> None:
        self._query = query

    async def scope_for(
        self,
        session_id: str,
        presentation_identity: str,
        phase: str,
    ) -> VoiceBindingScope | None:
        try:
            session = await self._query.load_session(session_id)
        except Exception:  # noqa: BLE001 - an unknown session is not a crash
            return None
        return binding_scope_for(
            session,
            presentation_identity=presentation_identity,
            phase=phase,
        )


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
        context_bindings: TurnContextBindingPort | None,
        fetch_json,
        evidence_store: SQLiteVoiceFoundryRepository,
    ) -> None:
        self._query = query
        self._narratives = narratives
        self._bindings = bindings
        self._voice = voice
        self._audio = audio_config
        self._voice_id = voice_id
        self._workers = workers
        self._context_bindings = context_bindings
        self._fetch_json = fetch_json
        self._evidence_store = evidence_store

    async def after_commit(
        self,
        command: SubmitAdviceCommand,
        result: StoryTurnCommitResult,
        view: PublicStorySessionView | None = None,
    ) -> TurnDeliveryView:
        """Post-COMMIT expression.  A failure here never touches Domain state."""
        del view
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
                scene_roster = turn_scene_roster(
                    story_state=result.session.story_state,
                    committed_story_revision=story_revision,
                )
                source = CommittedNarrativeSource(
                    turn_id=result.turn.id,
                    session_id=result.turn.session_id,
                    story_revision=story_revision,
                    state_delta_id=result.delta.id,
                    state_delta=result.delta,
                    scene_id=result.delta.story_delta.scene_id,
                    protagonist_id=result.session.protagonist_id,
                    disclosed_facts=disclosed_turn_facts(
                        delta=result.delta,
                        bootstrap=snapshot.bootstrap,
                    ),
                    input_turn_id=command.input_turn_id,
                    source_store_revision=result.store_revision,
                    # The commit result carries the session as this turn left it,
                    # so the roster is read from state that cannot have moved on.
                    present_character_ids=scene_roster,
                    # Narrowed from the world roster by D5, using the same
                    # public-name allowlist the model's roster evidence was
                    # built from — one table, two consumers, no second source
                    # of who is called what.
                    castable_character_labels=disclosed_castable_roster(
                        active_character_ids=scene_roster,
                        protagonist_id=result.session.protagonist_id,
                        character_display_names=(
                            snapshot.bootstrap.presentation.character_display_names
                        ),
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
            context_bindings=self._context_bindings,
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

        units = await self._deliver_character_segments(
            snapshot=snapshot,
            narrative=narrative,
            result=result,
        )
        ready_units = [unit for unit in units if unit.state == "ready"]
        if not ready_units:
            # Nothing could be voiced, so the turn has no audio to announce.
            # The reason is the first segment's, because a turn-wide code would
            # name a failure that belongs to one line.
            return TurnDeliveryView(
                state="unavailable",
                reason=(
                    units[0].reason
                    if units and units[0].reason
                    else "narrative_has_no_character_segment"
                ),
            )
        return TurnDeliveryView(
            state="ready",
            narrative_block_id=narrative.id,
            speech_units=tuple(units),
        )

    async def _deliver_character_segments(
        self,
        *,
        snapshot: StorySessionSnapshotRecord,
        narrative: NarrativeBlock,
        result: StoryTurnCommitResult,
    ) -> list[SegmentDeliveryView]:
        """Voice every speakable segment of a block, and report on each one.

        The scope follows the segment rather than the session: a turn's audio
        belongs to whoever is speaking, and a resolver handed only the session
        would go looking for the protagonist's voice and report the wrong
        speaker as missing.

        Only character segments are candidates. The sealing boundary refuses a
        speakerless narration deliberately: until a NarrativeBlock carries an
        explicit narrator identity, a caller must not get to choose who
        narrates.

        One segment failing does not stop the block. A speaker whose voice was
        never bound, whose evidence was never admitted, or whose provider
        refused costs *that* line its audio; the lines around it still play.
        That is the difference between a turn with a gap and a turn with no
        voice at all.
        """
        units: list[SegmentDeliveryView] = []
        resolved_by_scope: dict[VoiceBindingScope, object] = {}

        for segment_index, item in enumerate(narrative.segments):
            if item.type != "character":
                continue
            scope = speaker_scope_for(snapshot.session, item)
            if scope is None:
                units.append(
                    SegmentDeliveryView(
                        segment_index=segment_index,
                        state="unavailable",
                        reason="segment_speaker_unresolved",
                    )
                )
                continue

            # Two lines from the same speaker are the same binding; resolving
            # it twice would ask the provider catalog the same question twice
            # and risk two revisions for one voice.
            resolved = resolved_by_scope.get(scope)
            if resolved is None:
                try:
                    resolved = await resolve_voice_runtime(
                        repository=self._bindings,
                        session=snapshot.session,
                        config=self._audio,
                        voice_id=self._voice_id,
                        scope=scope,
                        fetch_json=self._fetch_json,
                    )
                except VoiceBindingResolutionError as exc:
                    units.append(
                        SegmentDeliveryView(
                            segment_index=segment_index,
                            state="unavailable",
                            reason=exc.code,
                        )
                    )
                    continue
                except Exception:  # noqa: BLE001 - hide provider details after text publication
                    units.append(
                        SegmentDeliveryView(
                            segment_index=segment_index,
                            state="unavailable",
                            reason="voice_runtime_unavailable",
                        )
                    )
                    continue
                resolved_by_scope[scope] = resolved

            unit = await self._deliver_one_segment(
                resolved=resolved,
                result=result,
                narrative=narrative,
                segment_index=segment_index,
            )
            units.append(unit)
        return units

    async def _deliver_one_segment(
        self,
        *,
        resolved,
        result: StoryTurnCommitResult,
        narrative: NarrativeBlock,
        segment_index: int,
    ) -> SegmentDeliveryView:
        """Seal and hand one segment over, turning any refusal into a report."""
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
        evidence = (
            None
            if execution is None
            else await load_evidence_record(
                self._evidence_store,
                resolved.provider_instance,
                resolved.binding.evidence.evidence_id,
            )
        )
        if execution is None or evidence is None:
            # Text is already published; a voice without admitted evidence
            # costs this segment its audio and nothing else.
            return SegmentDeliveryView(
                segment_index=segment_index,
                state="unavailable",
                reason="voice_evidence_not_admitted",
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
                "execution": execution,
                "evidence": evidence,
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
                    session_id=result.turn.session_id,
                    story_revision=result.turn.committed_story_revision,
                    state_delta_id=result.delta.id,
                    narrative=narrative,
                    segment_index=segment_index,
                )
            )
        except TurnDeliveryError as exc:
            return SegmentDeliveryView(
                segment_index=segment_index,
                state="unavailable",
                reason=exc.code,
            )
        except Exception:  # noqa: BLE001 - audio failures cannot unwind COMMIT
            return SegmentDeliveryView(
                segment_index=segment_index,
                state="unavailable",
                reason="voice_delivery_unavailable",
            )
        if receipt is None:
            return SegmentDeliveryView(
                segment_index=segment_index,
                state="unavailable",
                reason="narrative_has_no_character_segment",
            )
        return SegmentDeliveryView(
            segment_index=segment_index,
            state="ready",
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


__all__ = [
    "DICTIONARY_REVISION",
    "ENGINEERING_WORLD_ID",
    "ModelTransportError",
    "StoryRuntime",
    "StoryRuntimeConfig",
    "default_content_path",
]
