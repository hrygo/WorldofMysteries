"""Read-only trusted story content artifact tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from application.story_initialization import (
    GOLDEN_SCENARIO_ID,
    SUPPORTED_ADVICE,
    StoryInitializationError,
    TrustedScenarioBundle,
)
from infrastructure.story_content_repository import (
    SQLiteStoryContentRepository,
    StoryContentError,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "golden_001"
RUNTIME = ROOT / "docs" / "07_工程启动" / "golden_001_runtime"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_digest(payload: dict) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "content_digest"}
    return hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _bundle_payload() -> dict:
    advice = _read(FIXTURES / "turns" / "01_advice.json")
    advice["input_mode"] = "text"
    advice["raw_input"] = SUPPORTED_ADVICE
    payload = {
        "scenario_id": GOLDEN_SCENARIO_ID,
        "content_version": "1",
        "policy_version": "golden001-opening-policy",
        "seed": _read(FIXTURES / "seed.json"),
        "world": _read(FIXTURES / "world.json"),
        "character": _read(FIXTURES / "character.json"),
        "knowledge": [
            _read(path)
            for path in sorted((FIXTURES / "knowledge").glob("*.json"))
        ],
        "presentation": {
            "scenario_title": "不存在的预约",
            "scene_display_name": "哈维诊所 · 诊室",
            "clue_display_names": {"clue_doctor_pause": "医生的停顿"},
        },
        "advice_template": advice,
        "action_intent_template": _read(
            RUNTIME / "mock" / "01_action_intent.json"
        ),
    }
    payload["content_digest"] = _canonical_digest(payload)
    return payload


def _write_artifact(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE scenario_bundles("
            "scenario_id TEXT PRIMARY KEY,"
            "content_version TEXT NOT NULL,"
            "content_digest TEXT NOT NULL,"
            "payload_json TEXT NOT NULL"
            ") STRICT"
        )
        connection.execute(
            "INSERT INTO scenario_bundles VALUES (?,?,?,?)",
            (
                payload["scenario_id"],
                payload["content_version"],
                payload["content_digest"],
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            ),
        )


@pytest.mark.asyncio
async def test_loads_trusted_bundle_from_readonly_content_artifact(tmp_path):
    payload = _bundle_payload()
    artifact = tmp_path / "canon.db"
    _write_artifact(artifact, payload)
    repository = SQLiteStoryContentRepository(artifact)

    loaded = await repository.load(GOLDEN_SCENARIO_ID)

    assert isinstance(loaded, TrustedScenarioBundle)
    assert loaded.scenario_id == GOLDEN_SCENARIO_ID
    assert loaded.content_digest == payload["content_digest"]
    assert loaded.world.revision == 103
    assert loaded.character.revision == 27


@pytest.mark.asyncio
async def test_content_artifact_column_digest_mismatch_fails_closed(tmp_path):
    payload = _bundle_payload()
    artifact = tmp_path / "canon.db"
    _write_artifact(artifact, payload)
    with sqlite3.connect(artifact) as connection:
        connection.execute(
            "UPDATE scenario_bundles SET content_digest=?",
            ("0" * 64,),
        )

    with pytest.raises(StoryContentError) as raised:
        await SQLiteStoryContentRepository(artifact).load(GOLDEN_SCENARIO_ID)

    assert raised.value.code == "content_digest_mismatch"


@pytest.mark.asyncio
async def test_missing_scenario_fails_closed(tmp_path):
    artifact = tmp_path / "canon.db"
    _write_artifact(artifact, _bundle_payload())

    with pytest.raises(StoryContentError) as raised:
        await SQLiteStoryContentRepository(artifact).load("golden_missing")

    assert raised.value.code == "unsupported_scenario"


@pytest.mark.asyncio
async def test_invalid_bundle_payload_is_not_returned(tmp_path):
    payload = _bundle_payload()
    payload["world"]["revision"] = -1
    payload["content_digest"] = _canonical_digest(payload)
    artifact = tmp_path / "canon.db"
    _write_artifact(artifact, payload)

    with pytest.raises(StoryContentError) as raised:
        await SQLiteStoryContentRepository(artifact).load(GOLDEN_SCENARIO_ID)

    assert raised.value.code == "invalid_story_content"
