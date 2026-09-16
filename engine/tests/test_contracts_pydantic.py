"""Test suite for Contract Pydantic Models Validation (T-CON-002)."""

import json
from pathlib import Path
import pytest
from contracts import (
    ActionIntent,
    BeatPlan,
    Character,
    CharacterKnowledge,
    EngineIPCEnvelope,
    Episode,
    NarrativeBlock,
    PlayerAdvice,
    StateDelta,
    WorldSnapshot,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures" / "golden_001"


def test_character_pydantic_parsing():
    with open(FIXTURES_DIR / "character.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    char = Character.model_validate(data)
    assert char.id == "char_evelyn_gray"
    assert char.identity.display_name == "伊芙琳·格雷"
    assert char.identity.sequence == 9
    assert char.identity.pathway_id == "pathway.fool"
    assert char.revision == 27


def test_world_snapshot_pydantic_parsing():
    with open(FIXTURES_DIR / "world.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    world = WorldSnapshot.model_validate(data)
    assert world.world_id == "world_001"
    assert world.worldline_id == "wl_main"
    assert world.location is not None
    assert world.location.id == "loc_morris_clinic"
    assert world.revision == 103


def test_episode_pydantic_parsing():
    with open(FIXTURES_DIR / "expected_episode.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    ep = Episode.model_validate(data)
    assert ep.id == "ep_golden_001"
    assert ep.ending.type == "partial_truth"
    assert ep.secret_states["secret_04"] == "hidden"
    assert len(ep.discovered_clue_ids) == 5


def test_player_advice_pydantic_parsing():
    advice_files = list((FIXTURES_DIR / "turns").glob("*_advice.json"))
    assert len(advice_files) == 5

    for a_file in advice_files:
        with open(a_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        advice = PlayerAdvice.model_validate(data)
        assert advice.schema_version == "1.0"
        assert len(advice.raw_input) > 0


def test_character_knowledge_pydantic_parsing():
    k_files = list((FIXTURES_DIR / "knowledge").glob("*.json"))
    assert len(k_files) >= 4

    for k_file in k_files:
        with open(k_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        k = CharacterKnowledge.model_validate(data)
        assert k.schema_version == "1.0"
        assert k.character_id == "char_evelyn_gray"


def test_envelope_request_response_cycle():
    # Request
    req = EngineIPCEnvelope(
        kind="request",
        protocol_version="1.0",
        trace_id="trace_test_001",
        request_id="req_001",
        method="world.open",
        payload={"world_id": "world_001"},
    )
    req_json = req.model_dump_json()

    parsed_req = EngineIPCEnvelope.model_validate_json(req_json)
    assert parsed_req.kind == "request"
    assert parsed_req.method == "world.open"

    # Response
    resp = EngineIPCEnvelope(
        kind="response",
        protocol_version="1.0",
        trace_id="trace_test_001",
        request_id="req_001",
        status="ok",
        payload={"world_id": "world_001", "status": "opened"},
    )
    resp_json = resp.model_dump_json()
    parsed_resp = EngineIPCEnvelope.model_validate_json(resp_json)
    assert parsed_resp.status == "ok"
    assert parsed_resp.payload["status"] == "opened"


def test_strenum_contract_validation():
    from contracts import CharacterKind, EndingType, InputMode, KnowledgeStatus

    assert CharacterKind.ORIGINAL == "original"
    assert EndingType.PARTIAL_TRUTH == "partial_truth"
    assert InputMode.VOICE == "voice"
    assert KnowledgeStatus.CONFIRMED == "confirmed"

    # Verify that invalid enum value raises ValidationError
    with pytest.raises(Exception):
        from contracts import PlayerAdvice

        PlayerAdvice.model_validate(
            {
                "id": "adv_err",
                "raw_input": "test",
                "input_mode": "invalid_mode",
                "primary_intent": "test",
            }
        )

