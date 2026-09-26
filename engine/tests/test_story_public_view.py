"""Allowlist projection tests for the trusted first-turn UI."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from application.story_initialization import (
    GOLDEN_SCENARIO_ID,
    SUPPORTED_ADVICE,
    StoryInitializationService,
    TrustedScenarioBundle,
)
from application.story_public_view import (
    StoryPublicViewError,
    StoryPublicViewProjector,
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


class Source:
    async def load(self, scenario_id: str) -> TrustedScenarioBundle:
        return TrustedScenarioBundle.model_validate(_bundle_payload())


async def _initialized():
    return await StoryInitializationService(Source()).initialize(
        scenario_id=GOLDEN_SCENARIO_ID,
        open_request_id="open_first_001",
    )


@pytest.mark.asyncio
async def test_projector_returns_only_public_allowlisted_fields():
    initialized = await _initialized()
    session = initialized.initial_session
    session.story_state.discovered_clue_ids = ["clue_doctor_pause"]
    session.story_state.turn = 1
    session.story_state.revision = 1

    view = StoryPublicViewProjector().project(
        session=session,
        bootstrap=initialized.bootstrap,
        observed_store_revision=2,
        last_committed_turn_id="turn_001",
    )

    assert view.model_dump(exclude_none=True) == {
        "schema_version": "1.0",
        "scenario_id": "golden_001",
        "session_id": session.id,
        "mode": "golden_deterministic",
        "status": "active",
        "story_revision": 1,
        "turn": 1,
        "observed_store_revision": 2,
        "world_time": "1349-06-12T21:40:00",
        "protagonist": {
            "id": "char_evelyn_gray",
            "display_name": "伊芙琳·格雷",
        },
        "scene": {
            "id": "consultation_room",
            "location_id": "loc_morris_clinic",
            "display_name": "哈维诊所 · 诊室",
        },
        "discovered_clues": [
            {"id": "clue_doctor_pause", "display_name": "医生的停顿"}
        ],
        "can_submit": False,
        "last_committed_turn_id": "turn_001",
    }
    assert "secret_states" not in view.model_dump()
    assert "pressure" not in view.model_dump()


@pytest.mark.asyncio
async def test_unknown_discovered_clue_fails_closed_without_leaking_identity():
    initialized = await _initialized()
    session = initialized.initial_session
    session.story_state.discovered_clue_ids = ["clue_hidden_unknown"]

    with pytest.raises(StoryPublicViewError, match="recovery_required"):
        StoryPublicViewProjector().project(
            session=session,
            bootstrap=initialized.bootstrap,
            observed_store_revision=1,
        )
