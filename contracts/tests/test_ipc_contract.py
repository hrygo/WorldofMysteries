"""One fixture corpus must produce the same result in Schema, Python and Swift."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from contracts import EngineIPCEnvelope

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/protocol/engine_ipc.schema.json").read_text())
CASES = json.loads((ROOT / "contracts/fixtures/ipc/envelopes.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_schema_and_python_agree(case):
    value = case["envelope"]
    assert Draft202012Validator(SCHEMA).is_valid(value) == case["valid"]
    if not case["valid"]:
        with pytest.raises(ValidationError):
            EngineIPCEnvelope.model_validate(value)
        return
    model = EngineIPCEnvelope.model_validate(value)
    wire = json.loads(model.model_dump_json())
    Draft202012Validator(SCHEMA).validate(wire)
    assert EngineIPCEnvelope.model_validate(wire) == model
    assert all(v is not None for v in wire.values())


def test_documentation_schema_is_only_a_local_reference():
    path = ROOT / "docs/07_工程启动/protocol/engine_ipc.schema.json"
    alias = json.loads(path.read_text())
    assert set(alias) == {"$schema", "$ref", "$comment"}
    assert (path.parent / alias["$ref"]).resolve() == (ROOT / "contracts/protocol/engine_ipc.schema.json").resolve()


def test_handshake_definitions_match_python():
    from contracts.envelope import HandshakeRequest, HandshakeResponse
    request = dict(app_version="0.1.0", app_build="1", supported_protocols=["1.0"], session_token="a" * 64)
    response = dict(engine_version="0.1.0", engine_build="1", python_version="3.14.7", protocol_version="1.0", capabilities=["system.health"])
    for name, data, model in [("handshake_request", request, HandshakeRequest), ("handshake_response", response, HandshakeResponse)]:
        validator = Draft202012Validator(SCHEMA["$defs"][name])
        validator.validate(data)
        assert model.model_validate(data).model_dump() == data
    assert request["session_token"] not in repr(HandshakeRequest.model_validate(request))
