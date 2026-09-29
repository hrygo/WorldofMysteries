"""Voice Foundry control wire contract tests (VF-01)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = {
    path.name: json.loads(path.read_text(encoding="utf-8"))
    for path in (ROOT / "contracts/schemas").glob("*.schema.json")
    if path.name
    in {
        "voice_cast_request.schema.json",
        "voice_identity_evidence.schema.json",
        "voice_foundry_state.schema.json",
    }
}
FOUNDRY = json.loads(
    (ROOT / "contracts/protocol/voice_foundry_control.schema.json").read_text(
        encoding="utf-8"
    )
)
AUDIO_BATCH = json.loads(
    (ROOT / "contracts/protocol/voice_audio_batch_control.schema.json").read_text(
        encoding="utf-8"
    )
)
IPC = json.loads(
    (ROOT / "contracts/protocol/engine_ipc.schema.json").read_text(encoding="utf-8")
)

EXPECTED_METHODS = {
    "voice.foundry.request",
    "voice.foundry.get",
    "voice.foundry.list",
    "voice.foundry.select",
    "voice.foundry.confirm_reference",
    "voice.foundry.validate",
    "voice.foundry.review",
    "voice.foundry.publish",
    "voice.foundry.retry",
    "voice.foundry.cancel",
    "voice.binding.replace",
    "voice.audio.batch.get",
    "voice.audio.segment.prepare",
}

FORBIDDEN_FIELDS = {
    "state_delta",
    "world_revision",
    "domain_transaction",
    "raw_input",
    "resolver_input",
    "lease_owner",
    "lease_generation",
    "sql",
    "token",
    "secret",
    "hidden_identity",
    "future_plot",
}


def _registry(*schemas: dict) -> Registry:
    return Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )


def _validator(schema: dict, shape: str) -> Draft202012Validator:
    wrapper = {
        "$schema": schema["$schema"],
        "$id": schema["$id"],
        "$ref": f"#/$defs/{shape}",
        "$defs": schema["$defs"],
    }
    return Draft202012Validator(
        wrapper,
        registry=_registry(schema, *SCHEMAS.values()),
    )


def _scope() -> dict:
    return {
        "owner_id": "owner_01",
        "world_id": "world_01",
        "worldline_id": "worldline_01",
        "presentation_identity": "character_klain",
        "phase": "narrative",
        "locale": "zh-CN",
    }


def _cast_request() -> dict:
    return {
        "schema_version": "1.0",
        "request_id": "vfr_01",
        "request_digest": "a" * 64,
        "authorization_ref": "authz_public_voice_01",
        "scope": _scope(),
        "persona_revision": "persona-1",
        "usage": "dialogue",
        "locale": "zh-CN",
        "public_traits": ["低沉", "克制"],
        "voice_description": "克制而警觉的年轻男性声音。",
        "reference_text": "这是用于确认音色参考的完整句子，必须足够长以通过校验。",
        "validation_text": "这是用于跨文本复验的另一句完整文本，不能与参考文本相同。",
        "provider_instance": "speechrail-local",
        "requested_execution_scope": {
            "model_id": None,
            "model_artifact_revision": None,
            "variant": "custom_voice",
        },
        "budget": {
            "candidate_count": 4,
            "timeout_ms": 120000,
            "max_audio_bytes": 8388608,
        },
        "origin": {
            "kind": "content",
            "source_ref": "content:narrator-and-main-cast",
            "source_revision": 1,
        },
    }


def _evidence() -> dict:
    return {
        "schema_version": "1.0",
        "evidence_id": "evidence_01",
        "evidence_digest": "b" * 64,
        "provider_instance": "speechrail-local",
        "voice_id": "voice_klain_01",
        "voice_revision": "vr_0123456789abcdef0123456789abcdef",
        "execution": {
            "model_id": "tts-model",
            "model_artifact_revision": "model-rev-1",
            "variant": "custom_voice",
            "locale": "zh-CN",
            "validation_policy_revision": "policy-1",
            "processing_fingerprint": "c" * 64,
        },
        "reference": {
            "status": "pass",
            "audio_digest": "d" * 64,
            "text_digest": "e" * 64,
        },
        "output": {
            "status": "pass",
            "validation_id": "vv_0123456789abcdef01234567",
            "audio_digest": "f" * 64,
            "text_digest": "0" * 64,
        },
        "human": {
            "identity_status": "pass",
            "naturalness_status": "pass",
            "review_id": "review_01",
            "reference_audio_digest": "d" * 64,
            "validation_audio_digest": "f" * 64,
        },
        "publication": {
            "state": "published",
            "published_revision": "vr_0123456789abcdef0123456789abcdef",
        },
        "rights": {
            "allowed_usages": ["dialogue", "narration"],
            "scope_ref": "rights_01",
        },
        "created_at": "2026-09-29T00:00:00Z",
        "expires_at": None,
        "revoked": False,
        "cached_playback_policy": "revocation_aware",
    }


def _state() -> dict:
    return {
        "schema_version": "1.0",
        "task_id": "vft_01",
        "request_id": "vfr_01",
        "request_digest": "a" * 64,
        "scope": _scope(),
        "stage": "awaiting_review",
        "task_revision": 4,
        "cancel_requested": False,
        "operation_status": "confirmed",
        "required_actions": ["listen_reference", "listen_validation", "review"],
        "reason_code": None,
        "candidates": [
            {
                "candidate_id": "candidate_01",
                "slot": 1,
                "seed": 101,
                "state": "reviewing",
                "preview_audio_digest": "1" * 64,
                "provider_candidate_id": "voice_design_01",
                "provider_candidate_revision": "vr_candidate_01",
            }
        ],
    }


def test_all_new_contracts_are_valid_draft_2020_12():
    for schema in (*SCHEMAS.values(), FOUNDRY, AUDIO_BATCH):
        Draft202012Validator.check_schema(schema)


def test_voice_methods_are_registered_as_explicit_handshake_capabilities():
    capability = IPC["$defs"]["voice_foundry_method_capability"]
    assert set(capability["enum"]) == EXPECTED_METHODS
    validator = Draft202012Validator(capability)
    assert all(validator.is_valid(method) for method in EXPECTED_METHODS)
    assert not validator.is_valid("voice.foundry.debug")


def test_cast_request_is_authorized_public_presentation_only():
    validator = Draft202012Validator(
        SCHEMAS["voice_cast_request.schema.json"],
        registry=_registry(*SCHEMAS.values()),
    )
    request = _cast_request()
    assert validator.is_valid(request)
    assert FORBIDDEN_FIELDS.isdisjoint(request)

    for field in FORBIDDEN_FIELDS:
        invalid = copy.deepcopy(request)
        invalid[field] = "leaked"
        assert not validator.is_valid(invalid)


def test_reference_and_validation_text_are_both_bounded_and_distinct_fields():
    request = _cast_request()
    assert (
        request["reference_text"]
        and request["validation_text"]
        and request["reference_text"] != request["validation_text"]
    )
    schema = SCHEMAS["voice_cast_request.schema.json"]
    for field in ("reference_text", "validation_text"):
        assert schema["properties"][field] == {"$ref": "#/$defs/review_text"}
    assert schema["$defs"]["review_text"]["minLength"] == 20
    assert schema["$defs"]["review_text"]["maxLength"] == 240
    assert schema["properties"]["budget"] == {"$ref": "#/$defs/budget"}
    budget = schema["$defs"]["budget"]["properties"]
    assert 1 <= budget["candidate_count"]["minimum"]
    assert (
        budget["candidate_count"]["maximum"] == 4
    )


def test_evidence_binds_voice_model_reference_output_and_human_assets():
    validator = Draft202012Validator(
        SCHEMAS["voice_identity_evidence.schema.json"],
        registry=_registry(*SCHEMAS.values()),
    )
    evidence = _evidence()
    assert validator.is_valid(evidence)
    assert evidence["execution"]["model_artifact_revision"] != evidence[
        "publication"
    ]["published_revision"]

    wrong_model = copy.deepcopy(evidence)
    wrong_model["execution"]["model_artifact_revision"] = None
    assert not validator.is_valid(wrong_model)

    wrong_review_asset = copy.deepcopy(evidence)
    wrong_review_asset["human"]["validation_audio_digest"] = "2" * 64
    assert validator.is_valid(wrong_review_asset)
    assert wrong_review_asset["human"][
        "validation_audio_digest"
    ] != wrong_review_asset["output"]["audio_digest"]


def test_foundry_state_vocabulary_is_single_and_explicit():
    assert SCHEMAS["voice_foundry_state.schema.json"]["properties"]["stage"][
        "enum"
    ] == [
        "requested",
        "previewing",
        "awaiting_selection",
        "provisioning",
        "validating",
        "awaiting_review",
        "published",
        "binding",
        "ready",
        "failed",
        "cancelled",
    ]
    validator = Draft202012Validator(
        SCHEMAS["voice_foundry_state.schema.json"],
        registry=_registry(*SCHEMAS.values()),
    )
    state = _state()
    assert validator.is_valid(state)
    state["stage"] = "casting"
    assert not validator.is_valid(state)


@pytest.mark.parametrize(
    "shape",
    [
        "foundry_get_request",
        "foundry_list_request",
        "foundry_command",
        "foundry_get_response",
        "foundry_command_response",
    ],
)
def test_control_shapes_are_closed_and_cannot_carry_domain_or_worker_inventory(shape):
    assert set(FOUNDRY["$defs"][shape]["properties"]).isdisjoint(FORBIDDEN_FIELDS)
    assert FOUNDRY["$defs"][shape]["additionalProperties"] is False


def test_get_and_list_are_documented_pure_reads():
    for shape in ("foundry_get_request", "foundry_list_request"):
        description = FOUNDRY["$defs"][shape]["description"].lower()
        assert "pure read" in description
        assert "provider" in description
        assert "never" in description


@pytest.mark.parametrize(
    "action",
    [
        "select",
        "confirm_reference",
        "validate",
        "review",
        "publish",
        "retry",
        "cancel",
    ],
)
def test_every_write_action_uses_command_id_digest_and_expected_revision(action):
    command = FOUNDRY["$defs"]["foundry_command"]
    assert action in command["properties"]["action"]["enum"]
    for field in (
        "command_id",
        "payload_digest",
        "expected_task_revision",
        "action",
    ):
        assert field in command["required"]
    response = FOUNDRY["$defs"]["foundry_command_response"]
    assert {"accepted", "replayed"} <= set(response["required"])
    assert response["properties"]["accepted"]["const"] is True


def test_binding_replacement_is_an_explicit_cas_command():
    replace = FOUNDRY["$defs"]["binding_replace_request"]
    assert {
        "command_id",
        "payload_digest",
        "scope",
        "expected_binding_revision",
        "provider_instance",
        "voice_id",
        "voice_revision",
        "evidence_id",
        "evidence_digest",
    } <= set(replace["required"])
    assert replace["additionalProperties"] is False
    response = FOUNDRY["$defs"]["binding_replace_response"]
    assert {"accepted", "replayed", "binding_id", "binding_revision"} <= set(
        response["required"]
    )


def test_review_binds_actual_reference_and_validation_audio_digests():
    review = FOUNDRY["$defs"]["human_review"]
    assert set(review["required"]) == {
        "validation_id",
        "reference_audio_digest",
        "validation_audio_digest",
        "identity",
        "naturalness",
    }
    assert review["properties"]["identity"]["enum"] == ["pass", "reject"]
    assert review["properties"]["naturalness"]["enum"] == ["pass", "reject"]


def test_audio_batch_is_per_segment_and_does_not_reuse_single_delivery_contract():
    assert "voice_audio_batches" not in AUDIO_BATCH["$defs"]
    segment = AUDIO_BATCH["$defs"]["audio_segment_view"]
    assert {"segment_index", "presentation_identity", "state"} <= set(
        segment["required"]
    )
    assert segment["properties"]["state"]["enum"] == [
        "waiting_voice",
        "sealed",
        "handoff_ready",
        "unavailable",
        "skipped",
    ]
    get_request = AUDIO_BATCH["$defs"]["audio_batch_get_request"]
    assert set(get_request["properties"]) == {
        "schema_version",
        "session_id",
        "turn_id",
    }
    prepare = AUDIO_BATCH["$defs"]["audio_segment_prepare_request"]
    assert {"command_id", "payload_digest", "expected_generation"} <= set(
        prepare["required"]
    )
