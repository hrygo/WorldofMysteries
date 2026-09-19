"""Canonical Engine media header and framing contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/protocol/engine_media.schema.json").read_text())
CASES = json.loads((ROOT / "contracts/fixtures/media/headers.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)

MAX_HEADER_BYTES = 16 * 1024
MAX_PAYLOAD_BYTES = 256 * 1024
PCM16_MONO_BYTES_PER_FRAME = 2
CONTROL_KINDS = {"open", "credit", "end", "cancel", "error"}


def _semantic_frame_valid(header: object, payload_length: object) -> bool:
    if not isinstance(header, dict) or not isinstance(payload_length, int):
        return False
    if payload_length < 0 or payload_length > MAX_PAYLOAD_BYTES:
        return False
    try:
        header_bytes = json.dumps(
            header, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    except (TypeError, ValueError):
        return False
    if not header_bytes or len(header_bytes) > MAX_HEADER_BYTES:
        return False

    kind = header.get("kind")
    if kind in CONTROL_KINDS:
        return payload_length == 0
    if kind != "chunk":
        return False
    return (
        payload_length == header.get("payload_bytes")
        and payload_length == header.get("frame_count", 0) * PCM16_MONO_BYTES_PER_FRAME
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_media_header_and_framing_fixture(case):
    schema_valid = VALIDATOR.is_valid(case["header"])
    semantic_valid = _semantic_frame_valid(case["header"], case["payload_length"])
    assert schema_valid and semantic_valid == case["valid"] if schema_valid else not case["valid"]


def test_media_header_schema_is_strict_and_versioned():
    valid_open = next(case["header"] for case in CASES if case["id"] == "open_tts_valid")
    VALIDATOR.validate(valid_open)
    assert valid_open["protocol_version"] == "1.0"
    assert valid_open["format"] == {
        "codec": "pcm_s16le",
        "sample_rate": 24000,
        "channels": 1,
    }


def test_wire_limits_are_bounded():
    assert MAX_HEADER_BYTES == 16 * 1024
    assert MAX_PAYLOAD_BYTES == 256 * 1024
    assert SCHEMA["$defs"]["open"]["properties"]["max_payload_bytes"]["maximum"] == MAX_PAYLOAD_BYTES
    assert SCHEMA["$defs"]["chunk"]["properties"]["payload_bytes"]["maximum"] == MAX_PAYLOAD_BYTES


CONTROL_SCHEMA = json.loads(
    (ROOT / "contracts/protocol/engine_media_control.schema.json").read_text()
)
CONTROL_CASES = json.loads(
    (ROOT / "contracts/fixtures/media/control_open.json").read_text()
)


@pytest.mark.parametrize("case", CONTROL_CASES, ids=lambda case: case["id"])
def test_media_open_control_payload_fixtures(case):
    shape = case["shape"]
    validator = Draft202012Validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": f"#/$defs/{shape}",
            "$defs": CONTROL_SCHEMA["$defs"],
        }
    )
    assert validator.is_valid(case["payload"]) is case["valid"]


def test_media_open_control_contract_is_strict_and_versioned():
    request = CONTROL_SCHEMA["$defs"]["request"]
    grant = CONTROL_SCHEMA["$defs"]["grant"]
    assert request["additionalProperties"] is False
    assert grant["additionalProperties"] is False
    assert grant["properties"]["protocol_version"] == {"const": "1.0"}
    assert grant["properties"]["ticket"]["pattern"] == "^[0-9a-f]{64}$"
    assert grant["properties"]["expires_in_ms"]["maximum"] == 30_000
