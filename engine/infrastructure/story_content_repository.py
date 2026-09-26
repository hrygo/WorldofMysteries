"""Read-only loader for build-time trusted story content artifacts."""
from __future__ import annotations

import asyncio
from contextlib import closing
import json
from pathlib import Path

from application.story_initialization import (
    GOLDEN_SCENARIO_ID,
    TrustedScenarioBundle,
)
from pydantic import ValidationError

from .database_schema import StorageError, connect


class StoryContentError(RuntimeError):
    """Stable content-artifact failure without path or payload disclosure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SQLiteStoryContentRepository:
    """Load one validated bundle from a read-only ``scenario_bundles`` table."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    async def load(self, scenario_id: str) -> TrustedScenarioBundle:
        if scenario_id != GOLDEN_SCENARIO_ID:
            raise StoryContentError("unsupported_scenario")
        return await asyncio.to_thread(self._load_sync, scenario_id)

    def _load_sync(self, scenario_id: str) -> TrustedScenarioBundle:
        try:
            with closing(connect(self._path, readonly=True)) as connection:
                rows = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT scenario_id, content_version, content_digest, payload_json "
                        "FROM scenario_bundles WHERE scenario_id=?",
                        (scenario_id,),
                    )
                ]
        except (OSError, StorageError):
            raise StoryContentError("invalid_story_content") from None
        if not rows:
            raise StoryContentError("story_content_not_found")
        if len(rows) != 1:
            raise StoryContentError("invalid_story_content")

        row = rows[0]
        try:
            payload = json.loads(row["payload_json"])
            if not isinstance(payload, dict):
                raise ValueError("bundle payload must be an object")
            if payload.get("content_digest") != row["content_digest"]:
                raise StoryContentError("content_digest_mismatch")
            if (
                payload.get("scenario_id") != row["scenario_id"]
                or payload.get("content_version") != row["content_version"]
            ):
                raise ValueError("artifact columns do not match payload")
            bundle = TrustedScenarioBundle.model_validate(payload)
        except StoryContentError:
            raise
        except (TypeError, ValueError, ValidationError, json.JSONDecodeError):
            raise StoryContentError("invalid_story_content") from None
        return bundle
