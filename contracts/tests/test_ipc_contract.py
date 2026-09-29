"""One fixture corpus must produce the same result in Schema, Python and Swift."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from contracts import EngineIPCEnvelope

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/protocol/engine_ipc.schema.json").read_text())
CASES = [case for name in ("envelopes", "numeric_wire")
         for case in json.loads((ROOT / f"contracts/fixtures/ipc/{name}.json").read_text())]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_schema_and_python_agree(case):
    value = json.loads(case["rawWire"]) if "rawWire" in case else case["envelope"]
    assert value == case["envelope"]
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


@pytest.mark.parametrize("field,value", [("protocol_version", "2.0"), ("capabilities", ["x", "x"]),
                                          ("capabilities", [""]), ("capabilities", [1])])
def test_invalid_handshake_response_parity(field, value):
    from contracts.envelope import HandshakeResponse
    data = dict(engine_version="0.1.0", engine_build="1", python_version="3.14.7",
                protocol_version="1.0", capabilities=["system.health"])
    data[field] = value
    assert not Draft202012Validator(SCHEMA["$defs"]["handshake_response"]).is_valid(data)
    with pytest.raises(ValidationError):
        HandshakeResponse.model_validate(data)


@pytest.mark.parametrize("token", ["a" * 64 + "\n", "a" * 63, "G" * 64])
def test_invalid_handshake_token_parity(token):
    from contracts.envelope import HandshakeRequest
    data = dict(app_version="1", app_build="1", supported_protocols=["1.0"], session_token=token)
    assert not Draft202012Validator(SCHEMA["$defs"]["handshake_request"]).is_valid(data)
    with pytest.raises(ValidationError):
        HandshakeRequest.model_validate(data)


def test_voice_render_control_protocol_fixture():
    schema = json.loads(
        (ROOT / "contracts" / "protocol" / "voice_render_control.schema.json")
        .read_text(encoding="utf-8")
    )
    fixture = json.loads(
        (ROOT / "contracts" / "fixtures" / "ipc" / "voice_render_control.json")
        .read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    validator.validate(fixture["request"])
    validator.validate(fixture["request_v2"])
    validator.validate(fixture["accepted"])

    invalid = dict(fixture["request"])
    invalid["display_text"] = "must not cross the render control boundary"
    assert not validator.is_valid(invalid)


@pytest.mark.parametrize(
    "pin",
    [
        "evidence_id",
        "evidence_digest",
        "expected_model_artifact_revision",
        "expected_model_catalog_revision",
    ],
)
def test_voice_render_control_v2_refuses_an_unpinned_render(pin):
    """Each of the four pins is load-bearing on its own. A render that cannot
    name the review that authorised it, or the exact artifact that review
    heard, is not a weaker v2 — it is an unattributable one."""
    schema = json.loads(
        (ROOT / "contracts" / "protocol" / "voice_render_control.schema.json")
        .read_text(encoding="utf-8")
    )
    fixture = json.loads(
        (ROOT / "contracts" / "fixtures" / "ipc" / "voice_render_control.json")
        .read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)

    unpinned = dict(fixture["request_v2"])
    unpinned.pop(pin)
    assert not validator.is_valid(unpinned)


def test_voice_render_control_v2_cannot_be_downgraded_to_v1():
    """v1 is kept only so units sealed before v2 can be replayed. A peer must
    not be able to present a fully pinned render as the unpinned version and
    have the evidence pins silently dropped by a lenient reader."""
    schema = json.loads(
        (ROOT / "contracts" / "protocol" / "voice_render_control.schema.json")
        .read_text(encoding="utf-8")
    )
    fixture = json.loads(
        (ROOT / "contracts" / "fixtures" / "ipc" / "voice_render_control.json")
        .read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)

    downgraded = dict(fixture["request_v2"])
    downgraded["schema_version"] = "1.0"
    assert not validator.is_valid(downgraded)
