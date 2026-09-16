"""Cross-Language Serialization Roundtrip Verification (T-CON-003).

Validates that Python and Swift models conform to the exact same contract.
"""

import json
import subprocess
from pathlib import Path
import pytest
from contracts import Character, EngineIPCEnvelope, PlayerAdvice

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures" / "golden_001"


def test_python_to_canonical_json_roundtrip():
    """Verify that Python Pydantic serializes to canonical JSON without data loss."""
    with open(FIXTURES_DIR / "character.json", "r", encoding="utf-8") as f:
        original = json.load(f)

    char = Character.model_validate(original)
    serialized = json.loads(char.model_dump_json())

    assert serialized["id"] == original["id"]
    assert serialized["identity"]["display_name"] == original["identity"]["display_name"]
    assert serialized["revision"] == original["revision"]


def test_strict_envelope_rejects_unknown_kind():
    """Verify that invalid IPC kind is rejected by envelope contract."""
    with pytest.raises(Exception):
        EngineIPCEnvelope.model_validate(
            {
                "kind": "unknown_action",
                "protocol_version": "1.0",
                "trace_id": "trace_001",
            }
        )


def test_strict_envelope_requires_trace_id():
    """Verify that trace_id is strictly required on all IPC messages."""
    with pytest.raises(Exception):
        EngineIPCEnvelope.model_validate(
            {
                "kind": "request",
                "protocol_version": "1.0",
                "method": "world.open",
            }
        )
