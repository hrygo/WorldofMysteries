"""Trusted Golden 001 initializer and bootstrap freezing tests."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from application.story_initialization import (
    ENGINEERING_NAMESPACE,
    GOLDEN_SCENARIO_ID,
    SUPPORTED_ADVICE,
    StoryInitializationError,
    StoryInitializationService,
    TrustedScenarioBundle,
)
from application.story_session_open import (
    OpenStorySessionCommand,
    StorySessionOpenResult,
    StorySessionOpenService,
    StorySessionSnapshot,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "golden_001"
RUNTIME = ROOT / "docs" / "07_工程启动" / "golden_001_runtime"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_digest(payload: dict) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "content_digest"}
    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    def __init__(self, bundle: TrustedScenarioBundle) -> None:
        self.bundle = bundle
        self.requests: list[str] = []

    async def load(self, scenario_id: str) -> TrustedScenarioBundle:
        self.requests.append(scenario_id)
        return self.bundle


class OpenPort:
    def __init__(self) -> None:
        self.commands: list[OpenStorySessionCommand] = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def open_session(
        self, command: OpenStorySessionCommand
    ) -> StorySessionOpenResult:
        self.commands.append(command)
        self.entered.set()
        await self.release.wait()
        return StorySessionOpenResult(
            snapshot=StorySessionSnapshot(
                session=command.initial_session,
                observed_store_revision=command.store_expected_revision + 1,
            ),
            opened_store_revision=command.store_expected_revision + 1,
            replayed=False,
        )

    async def load_snapshot(self, session_id: str) -> StorySessionSnapshot:
        raise AssertionError("not used")


@pytest.mark.asyncio
async def test_initializer_builds_turn_zero_from_trusted_bundle():
    source = Source(TrustedScenarioBundle.model_validate(_bundle_payload()))
    initialized = await StoryInitializationService(source).initialize(
        scenario_id=GOLDEN_SCENARIO_ID,
        open_request_id="open_first_001",
    )

    expected_id = "session_" + hashlib.sha256(
        (
            "story-open/v1\0"
            f"{ENGINEERING_NAMESPACE}\0"
            f"{GOLDEN_SCENARIO_ID}\0"
            "open_first_001"
        ).encode("utf-8")
    ).hexdigest()[:32]
    session = initialized.initial_session

    assert source.requests == [GOLDEN_SCENARIO_ID]
    assert session.id == expected_id
    assert session.world_id == "world_001"
    assert session.worldline_id == "wl_main"
    assert session.protagonist_id == "char_evelyn_gray"
    assert session.story_seed_id == "seed_golden_001"
    assert session.base_revisions.world == 103
    assert session.base_revisions.character == 27
    assert session.base_revisions.story == 0
    assert session.story_state.revision == 0
    assert session.story_state.turn == 0
    assert session.story_state.phase.value == "discovery"
    assert session.story_state.scene.id == "consultation_room"
    assert session.story_state.scene.location_id == "loc_morris_clinic"
    assert session.story_state.scene.active_character_ids == [
        "char_evelyn_gray",
        "npc_doctor_morris",
    ]
    assert session.story_state.world_time == "1349-06-12T21:40:00"
    assert session.story_state.protagonist_goal == "find_missing_patient"
    assert session.story_state.active_conflicts == ["find_jonathan"]
    assert session.story_state.discovered_clue_ids == []
    assert session.story_state.commitments.hard_ids == []
    assert session.story_state.commitments.soft_ids == []
    assert session.story_state.local_state == {}
    assert session.story_state.last_state_delta_id is None
    assert {
        key: value.value for key, value in session.story_state.secret_states.items()
    } == {
        "secret_01": "hidden",
        "secret_02": "hidden",
        "secret_03": "hidden",
        "secret_04": "hidden",
    }
    assert session.story_state.pressure == {
        "clinic_closing": 0,
        "doctor_suspicion": 0,
    }
    assert initialized.bootstrap.content_digest == _bundle_payload()["content_digest"]
    assert initialized.bootstrap.initial_session == session
    assert initialized.bootstrap.advice_template["raw_input"] == SUPPORTED_ADVICE


@pytest.mark.asyncio
async def test_initializer_rejects_content_digest_mismatch():
    payload = _bundle_payload()
    payload["content_digest"] = "0" * 64

    with pytest.raises(StoryInitializationError) as raised:
        await StoryInitializationService(
            Source(TrustedScenarioBundle.model_validate(payload))
        ).initialize(
            scenario_id=GOLDEN_SCENARIO_ID,
            open_request_id="open_first_001",
        )

    assert raised.value.code == "content_digest_mismatch"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda payload: payload["seed"].update({"protagonist_id": "other"}),
            "protagonist_mismatch",
        ),
        (
            lambda payload: payload["seed"]["setting"].update(
                {"location_id": "other_location"}
            ),
            "location_mismatch",
        ),
        (
            lambda payload: payload["knowledge"][0].update(
                {"character_id": "npc_doctor_morris"}
            ),
            "knowledge_owner_mismatch",
        ),
        (
            lambda payload: payload["knowledge"][0].update(
                {"worldline_id": "other_worldline"}
            ),
            "knowledge_worldline_mismatch",
        ),
        (
            lambda payload: payload["knowledge"][0].update(
                {"acquired_world_time": "1349-06-12T22:00:00"}
            ),
            "knowledge_after_opening",
        ),
        (
            lambda payload: payload["presentation"]["clue_display_names"].update(
                {"clue_doctor_pause": "错误文案"}
            ),
            "unsupported_presentation",
        ),
        (
            lambda payload: payload["advice_template"].update(
                {"raw_input": "other advice"}
            ),
            "unsupported_advice",
        ),
        (
            lambda payload: payload["advice_template"].update(
                {"input_mode": "voice"}
            ),
            "unsupported_input_mode",
        ),
    ],
)
async def test_initializer_fails_closed_on_untrusted_content(mutate, expected_code):
    payload = _bundle_payload()
    mutate(payload)
    payload["content_digest"] = _canonical_digest(payload)

    with pytest.raises(StoryInitializationError) as raised:
        await StoryInitializationService(
            Source(TrustedScenarioBundle.model_validate(payload))
        ).initialize(
            scenario_id=GOLDEN_SCENARIO_ID,
            open_request_id="open_first_001",
        )

    assert raised.value.code == expected_code


@pytest.mark.asyncio
async def test_initializer_rejects_unknown_scenario_without_loading_source():
    source = Source(TrustedScenarioBundle.model_validate(_bundle_payload()))

    with pytest.raises(StoryInitializationError) as raised:
        await StoryInitializationService(source).initialize(
            scenario_id="golden_002",
            open_request_id="open_first_001",
        )

    assert raised.value.code == "unsupported_scenario"
    assert source.requests == []


@pytest.mark.asyncio
async def test_open_freezes_optional_bootstrap_before_first_await():
    initialized = await StoryInitializationService(
        Source(TrustedScenarioBundle.model_validate(_bundle_payload()))
    ).initialize(
        scenario_id=GOLDEN_SCENARIO_ID,
        open_request_id="open_first_001",
    )
    port = OpenPort()
    service = StorySessionOpenService(port)
    task = asyncio.create_task(
        service.open(
            OpenStorySessionCommand(
                initial_session=initialized.initial_session,
                open_request_id="open_first_001",
                store_expected_revision=0,
                request_id="request_open_first_001",
                trace_id="trace_open_first_001",
                bootstrap=initialized.bootstrap,
            )
        )
    )

    await port.entered.wait()
    initialized.bootstrap.seed["id"] = "tampered_seed"
    initialized.initial_session.story_state.scene.id = "tampered_scene"
    port.release.set()
    await task

    captured = port.commands[0]
    assert captured.bootstrap is not None
    assert captured.bootstrap.seed["id"] == "seed_golden_001"
    assert captured.bootstrap.initial_session.story_state.scene.id == "consultation_room"
    assert captured.bootstrap is not initialized.bootstrap
