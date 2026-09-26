#!/usr/bin/env python3
"""Build the trusted Golden 001 content artifact (build-time only).

The Local Engine never reads the repository at run time. This script freezes the
trusted engineering fixtures into a single read-only SQLite artifact that the
engine loads in the ``canon`` role, and it refuses to build anything that the
trusted initializer cannot turn into a turn=0 session.

Expected outcomes are deliberately unreadable here: ``expected_episode.json``,
``turns/*_expected.json`` and any ``expected/`` directory live outside the
allowlist, so a build cannot smuggle a pre-computed result into the runtime.

Run with an interpreter that has the engine dependencies installed::

    uv run --project engine python scripts/build_story_content.py --out <path>

``scripts/bundle_engine.py`` calls this module with the staged runtime
interpreter, so the packaged artifact is produced by the same code path.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from jsonschema import Draft202012Validator  # noqa: E402

from application.story_initialization import (  # noqa: E402
    GOLDEN_CONTENT_VERSION,
    GOLDEN_POLICY_VERSION,
    GOLDEN_SCENARIO_ID,
    SCENARIO_TITLE,
    SCENE_DISPLAY_NAME,
    SUPPORTED_ADVICE,
    ScenarioPresentation,
    StoryInitializationService,
    TrustedScenarioBundle,
)

CONTENT_ARTIFACT_RELATIVE = Path("infrastructure/story_content/canon.db")
CLUE_DISPLAY_NAMES = {"clue_doctor_pause": "医生的停顿"}
BUILD_OPEN_REQUEST_ID = "build-verification"

FIXTURE_DIR = ROOT / "fixtures" / "golden_001"
RUNTIME_FIXTURE_DIR = ROOT / "docs" / "07_工程启动" / "golden_001_runtime"
SCHEMA_DIR = ROOT / "contracts" / "schemas"


class StoryContentBuildError(RuntimeError):
    """Bounded build failure without repository paths in the code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise StoryContentBuildError("invalid_source_json") from None
    if not isinstance(payload, dict):
        raise StoryContentBuildError("invalid_source_json")
    return payload


def validate_schema(schema_name: str, payload: dict) -> None:
    schema = read_json(SCHEMA_DIR / schema_name)
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
    except Exception:
        raise StoryContentBuildError(f"schema_rejected:{schema_name}") from None


def canonical_digest(payload: dict) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "content_digest"}
    canonical = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _knowledge_paths() -> list[Path]:
    return sorted((FIXTURE_DIR / "knowledge").glob("*.json"))


def build_payload() -> dict:
    """Assemble and fully validate the frozen engineering bundle."""

    seed = read_json(FIXTURE_DIR / "seed.json")
    world = read_json(FIXTURE_DIR / "world.json")
    character = read_json(FIXTURE_DIR / "character.json")
    knowledge = [read_json(path) for path in _knowledge_paths()]
    advice = read_json(FIXTURE_DIR / "turns" / "01_advice.json")
    action_intent = read_json(RUNTIME_FIXTURE_DIR / "mock" / "01_action_intent.json")
    if not knowledge:
        raise StoryContentBuildError("missing_knowledge")

    validate_schema("story_seed.schema.json", seed)
    validate_schema("world_snapshot.schema.json", world)
    validate_schema("character.schema.json", character)
    for item in knowledge:
        validate_schema("character_knowledge.schema.json", item)
    validate_schema("action_intent.schema.json", action_intent)

    # The product first turn is fixed text; the fixture keeps the original voice
    # sample for the five-turn scenario and must not leak a second input mode.
    advice = dict(advice)
    advice["input_mode"] = "text"
    advice["raw_input"] = SUPPORTED_ADVICE
    validate_schema("player_advice.schema.json", advice)

    payload = {
        "scenario_id": GOLDEN_SCENARIO_ID,
        "content_version": GOLDEN_CONTENT_VERSION,
        "policy_version": GOLDEN_POLICY_VERSION,
        "seed": seed,
        "world": world,
        "character": character,
        "knowledge": knowledge,
        "presentation": ScenarioPresentation(
            scenario_title=SCENARIO_TITLE,
            scene_display_name=SCENE_DISPLAY_NAME,
            clue_display_names=CLUE_DISPLAY_NAMES,
        ).model_dump(mode="json", exclude_none=False, exclude_unset=True),
        "advice_template": advice,
        "action_intent_template": action_intent,
    }
    payload["content_digest"] = canonical_digest(payload)

    try:
        TrustedScenarioBundle.model_validate(payload)
    except Exception:
        raise StoryContentBuildError("invalid_trusted_bundle") from None
    # Cross-file identity, opening time, knowledge owner and turn=0 construction
    # are owned by the trusted initializer; a build that cannot open is invalid.
    asyncio.run(_verify_initializable(payload))
    return payload


async def _verify_initializable(payload: dict) -> None:
    bundle = TrustedScenarioBundle.model_validate(payload)

    class _Source:
        async def load(self, scenario_id: str) -> TrustedScenarioBundle:
            return bundle

    try:
        await StoryInitializationService(_Source()).initialize(
            scenario_id=GOLDEN_SCENARIO_ID, open_request_id=BUILD_OPEN_REQUEST_ID
        )
    except StoryContentBuildError:
        raise
    except Exception:
        raise StoryContentBuildError("initializer_rejected_bundle") from None


def serialize_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_artifact(path: Path, payload: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            "CREATE TABLE scenario_bundles("
            "scenario_id TEXT PRIMARY KEY, content_version TEXT NOT NULL, "
            "content_digest TEXT NOT NULL, payload_json TEXT NOT NULL"
            " CHECK(json_valid(payload_json)))"
        )
        connection.execute(
            "INSERT INTO scenario_bundles VALUES (?,?,?,?)",
            (
                payload["scenario_id"],
                payload["content_version"],
                payload["content_digest"],
                serialize_payload(payload),
            ),
        )
        connection.commit()
    _verify_artifact(path, payload)
    return path


def _verify_artifact(path: Path, payload: dict) -> None:
    uri = f"file:{path}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        rows = connection.execute(
            "SELECT scenario_id, content_version, content_digest, payload_json "
            "FROM scenario_bundles"
        ).fetchall()
    if len(rows) != 1:
        raise StoryContentBuildError("artifact_row_count")
    scenario_id, content_version, digest, encoded = rows[0]
    if (scenario_id, content_version, digest) != (
        payload["scenario_id"],
        payload["content_version"],
        payload["content_digest"],
    ):
        raise StoryContentBuildError("artifact_binding_mismatch")
    if json.loads(encoded) != payload:
        raise StoryContentBuildError("artifact_payload_mismatch")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=ENGINE / CONTENT_ARTIFACT_RELATIVE,
        help="输出内容制品路径（默认 engine/infrastructure/story_content/canon.db）",
    )
    parser.add_argument(
        "--print-digest",
        action="store_true",
        help="只打印构建摘要，便于包清单比对",
    )
    args = parser.parse_args(argv)
    payload = build_payload()
    artifact = write_artifact(args.out, payload)
    summary = {
        "scenario_id": payload["scenario_id"],
        "content_version": payload["content_version"],
        "policy_version": payload["policy_version"],
        "content_digest": payload["content_digest"],
        "artifact_bytes": artifact.stat().st_size,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
