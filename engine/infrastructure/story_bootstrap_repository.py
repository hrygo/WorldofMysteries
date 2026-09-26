"""Durable read/write helpers for the frozen Story Session bootstrap."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from application.story_initialization import StorySessionBootstrap
from pydantic import ValidationError

from .database_manager import DatabaseManager
from .database_schema import StorageError


class StoryBootstrapError(RuntimeError):
    """Stable bootstrap persistence/recovery failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class StoryBootstrapRecord:
    bootstrap: StorySessionBootstrap
    opened_store_revision: int


class BootstrapTransaction(Protocol):
    revision: int

    def execute(self, sql: str, parameters: tuple = ()) -> list[dict]: ...


def canonical_bootstrap_json(bootstrap: StorySessionBootstrap) -> str:
    try:
        return json.dumps(
            bootstrap.model_dump(mode="json", exclude_none=False),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise StoryBootstrapError("invalid_bootstrap") from None


def bootstrap_digest(bootstrap: StorySessionBootstrap) -> str:
    import hashlib

    return hashlib.sha256(canonical_bootstrap_json(bootstrap).encode("utf-8")).hexdigest()


def insert_bootstrap(
    tx: BootstrapTransaction,
    bootstrap: StorySessionBootstrap,
    *,
    opened_store_revision: int,
) -> None:
    if not isinstance(bootstrap, StorySessionBootstrap):
        raise StoryBootstrapError("invalid_bootstrap")
    if (
        isinstance(opened_store_revision, bool)
        or not isinstance(opened_store_revision, int)
        or opened_store_revision < 0
    ):
        raise StoryBootstrapError("invalid_opened_store_revision")
    try:
        bootstrap_json = canonical_bootstrap_json(bootstrap)
    except StoryBootstrapError:
        raise
    tx.execute(
        "INSERT INTO story_session_bootstraps("
        "session_id,scenario_id,content_version,content_digest,bootstrap_json,"
        "opened_store_revision) VALUES (?,?,?,?,?,?)",
        (
            bootstrap.initial_session.id,
            bootstrap.scenario_id,
            bootstrap.content_version,
            bootstrap.content_digest,
            bootstrap_json,
            opened_store_revision,
        ),
    )


class SQLiteStoryBootstrapRepository:
    def __init__(self, database: DatabaseManager) -> None:
        self._database = database

    async def load(self, session_id: str) -> StorySessionBootstrap | None:
        record = await self.load_record(session_id)
        return None if record is None else record.bootstrap

    async def load_record(self, session_id: str) -> StoryBootstrapRecord | None:
        _session_id(session_id)
        rows = await self._database.read_world(
            "SELECT * FROM story_session_bootstraps WHERE session_id=?",
            (session_id,),
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise StoryBootstrapError("bootstrap_identity_ambiguous")
        return StoryBootstrapRecord(
            bootstrap=_decode_row(rows[0]),
            opened_store_revision=rows[0]["opened_store_revision"],
        )

    async def require(self, session_id: str) -> StorySessionBootstrap:
        bootstrap = await self.load(session_id)
        if bootstrap is None:
            raise StoryBootstrapError("recovery_required")
        return bootstrap

    async def require_record(self, session_id: str) -> StoryBootstrapRecord:
        record = await self.load_record(session_id)
        if record is None:
            raise StoryBootstrapError("recovery_required")
        return record


def _decode_row(row: dict[str, Any]) -> StorySessionBootstrap:
    try:
        bootstrap = StorySessionBootstrap.model_validate(
            json.loads(row["bootstrap_json"])
        )
    except (TypeError, ValueError, ValidationError, json.JSONDecodeError):
        raise StoryBootstrapError("invalid_bootstrap") from None
    if (
        bootstrap.initial_session.id != row["session_id"]
        or bootstrap.scenario_id != row["scenario_id"]
        or bootstrap.content_version != row["content_version"]
        or bootstrap.content_digest != row["content_digest"]
    ):
        raise StoryBootstrapError("bootstrap_identity_mismatch")
    revision = row["opened_store_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise StoryBootstrapError("invalid_opened_store_revision")
    return bootstrap


def _session_id(session_id: object) -> str:
    if (
        not isinstance(session_id, str)
        or not session_id.strip()
        or len(session_id) > 256
        or "\x00" in session_id
    ):
        raise StoryBootstrapError("invalid_session_id")
    return session_id
