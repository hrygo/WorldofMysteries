"""Golden 001 fixed interpreter/proposer template tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ai.golden_first_turn import GoldenFirstTurnFactory
from application.advice_interpretation import (
    AdviceInterpretationError,
    FrozenTurnInput,
)
from application.story_initialization import (
    GOLDEN_SCENARIO_ID,
    SUPPORTED_ADVICE,
    StoryInitializationService,
    TrustedScenarioBundle,
)
from application.turn_input import TurnInputStatus
from contracts import BaseRevisions, InputMode, PlayerAdvice

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


async def _bootstrap():
    initialized = await StoryInitializationService(Source()).initialize(
        scenario_id=GOLDEN_SCENARIO_ID,
        open_request_id="open_first_001",
    )
    return initialized.bootstrap


def _frozen(text: str = SUPPORTED_ADVICE) -> FrozenTurnInput:
    return FrozenTurnInput(
        input_turn_id="input_first_001",
        session_id="session_first_001",
        turn_id="turn_first_001",
        idempotency_key="turn-input:first",
        input_mode=InputMode.TEXT,
        raw_input=text,
        input_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        base_revisions=BaseRevisions(world=103, character=27, story=0),
        status=TurnInputStatus.RECEIVED,
        committed_world_revision=None,
    )


@pytest.mark.asyncio
async def test_interpreter_uses_only_frozen_semantic_template():
    bootstrap = await _bootstrap()
    candidate = await GoldenFirstTurnFactory().interpreter_for(
        bootstrap
    ).interpret(_frozen())

    assert candidate.primary_intent == "observe"
    assert candidate.secondary_intents == ("delay_confrontation",)
    assert candidate.proposed_actions == ("observe_morris",)
    assert candidate.risk_preference == "cautious"
    assert candidate.confidence == 0.97


@pytest.mark.asyncio
async def test_interpreter_rejects_any_other_text():
    bootstrap = await _bootstrap()

    with pytest.raises(
        AdviceInterpretationError,
        match="deterministic_input_unsupported",
    ):
        await GoldenFirstTurnFactory().interpreter_for(bootstrap).interpret(
            _frozen("另一句话")
        )


@pytest.mark.asyncio
async def test_proposer_rebinds_identity_and_evidence_later():
    bootstrap = await _bootstrap()
    frozen = _frozen()
    advice = PlayerAdvice.model_validate(
        {
            "schema_version": "1.0",
            "id": "advice_first_001",
            "turn_id": frozen.turn_id,
            "raw_input": frozen.raw_input,
            "input_mode": "text",
            "primary_intent": "observe",
            "proposed_actions": ["observe_morris"],
            "confidence": 0.97,
        }
    )
    candidate = await GoldenFirstTurnFactory().proposer_for(
        bootstrap
    ).propose(frozen=frozen, advice=advice, scope=None)

    assert candidate.intent == "observe_subject"
    assert candidate.actions[0].type == "continue_conversation"
    assert not hasattr(candidate, "evidence_ids")
    assert candidate.proposer_revision == "golden001-action-intent-template-v1"
