"""Composition root for the trusted Golden 001 product runtime.

The runtime binds the frozen content artifact (read-only canon role), the
engineering world database under an explicit persistent data root, the existing
application services and the public story control handlers. It never creates an
empty canon database and never learns storage paths from IPC payloads.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai.golden_first_turn import GoldenFirstTurnFactory
from application.story_initialization import (
    GOLDEN_SCENARIO_ID,
    StoryInitializationService,
    TrustedScenarioBundle,
)
from application.story_session_facade import StorySessionFacade
from application.story_session_open import StorySessionOpenService

from .database_manager import DatabaseManager, DatabasePaths
from .player_advice_repository import SQLitePlayerAdviceRepository
from .story_content_repository import SQLiteStoryContentRepository
from .story_control import StoryRequestHandler, story_control_handlers
from .story_session_open_repository import SQLiteStorySessionOpenPort
from .story_session_query import SQLiteStorySessionQuery
from .story_session_repository import SQLiteStorySessionCommitPort
from .turn_intake_repository import SQLiteTurnInputCommandPort

ENGINEERING_WORLD_ID = "engineering-golden001"
CONTENT_ARTIFACT_NAME = "canon.db"


def default_content_path() -> Path:
    """Locate the packaged content artifact relative to the installed module."""
    return Path(__file__).resolve().parent / "story_content" / CONTENT_ARTIFACT_NAME


@dataclass(frozen=True, slots=True)
class StoryRuntimeConfig:
    """Explicit storage configuration; never inferred from cwd or environment."""

    data_root: Path
    content_path: Path
    world_id: str = ENGINEERING_WORLD_ID

    @classmethod
    def for_data_root(
        cls,
        data_root: Path,
        *,
        content_path: Path | None = None,
        world_id: str = ENGINEERING_WORLD_ID,
    ) -> StoryRuntimeConfig:
        return cls(
            data_root=Path(data_root),
            content_path=Path(content_path) if content_path else default_content_path(),
            world_id=world_id,
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
    ) -> None:
        self._database = database
        self._facade = facade
        self._content = content
        self._handlers = story_control_handlers(facade)

    @classmethod
    async def open(
        cls,
        config: StoryRuntimeConfig,
        *,
        expected_sqlite_version: str | None = None,
        fault_hook: Callable[[str], None] | None = None,
    ) -> StoryRuntime:
        content_repository = SQLiteStoryContentRepository(config.content_path)
        content = await content_repository.load(GOLDEN_SCENARIO_ID)
        database = await DatabaseManager.open(
            config.paths(),
            expected_sqlite_version=expected_sqlite_version,
            fault_hook=fault_hook,
        )
        try:
            facade = cls._build_facade(database, content_repository, content)
        except BaseException:
            await database.close()
            raise
        return cls(database=database, facade=facade, content=content)

    @staticmethod
    def _build_facade(
        database: DatabaseManager,
        content_repository: SQLiteStoryContentRepository,
        content: TrustedScenarioBundle,
    ) -> StorySessionFacade:
        return StorySessionFacade(
            initialization=StoryInitializationService(content_repository),
            open_sessions=StorySessionOpenService(SQLiteStorySessionOpenPort(database)),
            query=SQLiteStorySessionQuery(
                database,
                supported_advice=(content.advice_template.raw_input,),
            ),
            intake=SQLiteTurnInputCommandPort(database),
            advice=SQLitePlayerAdviceRepository(database),
            story=SQLiteStorySessionCommitPort(database),
            first_turn=GoldenFirstTurnFactory(),
        )

    @property
    def request_handlers(self) -> dict[str, StoryRequestHandler]:
        return dict(self._handlers)

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    @property
    def scenario_id(self) -> str:
        return self._content.scenario_id

    def health(self) -> dict[str, bool]:
        # The fixed first-turn proposer is not a live model or voice service.
        return {
            "transport_ready": True,
            "world_ready": True,
            "model_ready": False,
            "voice_ready": False,
        }

    async def close(self) -> None:
        await self._database.close()
