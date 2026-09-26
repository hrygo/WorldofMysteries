"""Read-only SQLite query adapter for the public trusted first-turn facade.

Every session read is one statement so session, bootstrap, observed store
revision and pending input come from a single SQLite snapshot. Missing or
ambiguous durable state fails closed instead of guessing.
"""
from __future__ import annotations

from application.story_initialization import GOLDEN_SCENARIO_ID
from application.story_session_facade import (
    StoredInputRecord,
    StoryEntrySnapshot,
    StorySessionSnapshotRecord,
)
from application.turn_input import TurnInputStatus

from .database_manager import DatabaseManager, StorageError
from .story_bootstrap_repository import StoryBootstrapError, _decode_row
from .story_session_repository import (
    SQLiteStorySessionCommitPort,
    _decode_story_session_row,
)
from .turn_intake_repository import SQLiteTurnInputCommandPort

_MAX_REVISION = 2**63 - 1

_ENTRY_SQL = (
    "SELECT "
    "(SELECT revision FROM world_meta WHERE singleton=1) AS observed_store_revision, "
    "(SELECT session_id FROM story_session_bootstraps WHERE scenario_id=? "
    "ORDER BY opened_store_revision DESC, session_id DESC LIMIT 1) AS session_id, "
    "(SELECT count(*) FROM story_session_bootstraps WHERE scenario_id=?) "
    "AS bootstrap_count, "
    "(SELECT count(*) FROM story_sessions) AS session_count"
)

_SESSION_SQL = (
    "SELECT "
    "s.id, s.world_id, s.worldline_id, s.protagonist_id, s.story_seed_id, "
    "s.base_world_revision, s.base_character_revision, s.base_story_revision, "
    "s.story_revision, s.status, s.story_state_json, s.committed_world_revision, "
    "b.session_id, b.scenario_id, b.content_version, b.content_digest, "
    "b.bootstrap_json, b.opened_store_revision, "
    "(SELECT revision FROM world_meta WHERE singleton=1) AS observed_store_revision, "
    "(SELECT count(*) FROM turn_intake_commands c "
    "WHERE c.session_id=s.id AND c.status='received') AS pending_count, "
    "(SELECT min(c.input_turn_id) FROM turn_intake_commands c "
    "WHERE c.session_id=s.id AND c.status='received') AS pending_input_turn_id "
    "FROM story_sessions s "
    "LEFT JOIN story_session_bootstraps b ON b.session_id = s.id "
    "WHERE s.id=?"
)


class StoryQueryError(RuntimeError):
    """Stable query failure; the message never carries durable payloads."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _identifier(value: object, code: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 256
        or "\x00" in value
    ):
        raise StoryQueryError(code)
    return value


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise StoryQueryError("story_session_corrupt")
    return value


def _revision(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_REVISION:
        raise StoryQueryError("story_session_corrupt")
    return value


class SQLiteStorySessionQuery:
    """Authorized reads for one engineering scenario namespace."""

    def __init__(
        self,
        database: DatabaseManager,
        *,
        supported_advice: tuple[str, ...],
    ) -> None:
        self._database = database
        self._supported_advice = tuple(supported_advice)
        self._inputs = SQLiteTurnInputCommandPort(database)
        self._story = SQLiteStorySessionCommitPort(database)

    async def entry(self, scenario_id: str) -> StoryEntrySnapshot:
        if scenario_id != GOLDEN_SCENARIO_ID:
            raise StoryQueryError("unsupported_scenario")
        rows = await self._database.read_world(
            _ENTRY_SQL, (scenario_id, scenario_id)
        )
        if len(rows) != 1:
            raise StoryQueryError("story_session_corrupt")
        row = rows[0]
        observed = _revision(row["observed_store_revision"])
        bootstraps = _count(row["bootstrap_count"])
        sessions = _count(row["session_count"])
        if bootstraps > 1:
            raise StoryQueryError("recovery_required")
        session_id = row["session_id"]
        if bootstraps == 0:
            # A durable session without its frozen bootstrap can never be
            # silently re-initialized from current content.
            if sessions:
                raise StoryQueryError("recovery_required")
            return StoryEntrySnapshot(
                supported_advice=self._supported_advice,
                observed_store_revision=observed,
            )
        snapshot = await self.session(_identifier(session_id, "story_session_corrupt"))
        return StoryEntrySnapshot(
            supported_advice=self._supported_advice,
            observed_store_revision=observed,
            session=snapshot,
            pending_input_turn_id=snapshot.pending_input_turn_id,
        )

    async def session(self, session_id: str) -> StorySessionSnapshotRecord:
        identifier = _identifier(session_id, "invalid_session_id")
        rows = await self._database.read_world(_SESSION_SQL, (identifier,))
        if not rows:
            raise StoryQueryError("story_session_not_found")
        if len(rows) != 1:
            raise StoryQueryError("story_session_corrupt")
        row = rows[0]
        observed = _revision(row["observed_store_revision"])
        if row.get("bootstrap_json") is None:
            raise StoryQueryError("recovery_required")
        try:
            session = _decode_story_session_row(row)
            bootstrap = _decode_row(row)
        except StoryBootstrapError:
            raise StoryQueryError("recovery_required") from None
        except (KeyError, TypeError, ValueError):
            raise StoryQueryError("story_session_corrupt") from None
        pending_count = _count(row["pending_count"])
        if pending_count > 1:
            raise StoryQueryError("recovery_required")
        pending_input_turn_id: str | None = None
        if pending_count == 1:
            pending_input_turn_id = _identifier(
                row["pending_input_turn_id"], "story_session_corrupt"
            )
        return StorySessionSnapshotRecord(
            session=session,
            bootstrap=bootstrap,
            observed_store_revision=observed,
            pending_input_turn_id=pending_input_turn_id,
        )

    async def input(
        self, session_id: str, input_turn_id: str
    ) -> StoredInputRecord | None:
        _identifier(session_id, "invalid_session_id")
        identifier = _identifier(input_turn_id, "invalid_input_turn_id")
        try:
            receipt = await self._inputs.load(identifier)
            if receipt is None or receipt.session_id != session_id:
                return None
            committed_story_revision = None
            if receipt.status is TurnInputStatus.COMMITTED:
                turn = await self._story.load_turn(receipt.turn_id)
                committed_story_revision = turn.committed_story_revision
        except StorageError:
            raise StoryQueryError("recovery_required") from None
        return StoredInputRecord(
            receipt=receipt,
            committed_story_revision=committed_story_revision,
        )
