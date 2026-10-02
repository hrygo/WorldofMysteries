"""Post-COMMIT Story work status and retry wire contract tests (AO-03)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (ROOT / "contracts/protocol/story_post_commit_control.schema.json").read_text(
        encoding="utf-8"
    )
)
IPC_SCHEMA = json.loads(
    (ROOT / "contracts/protocol/engine_ipc.schema.json").read_text(encoding="utf-8")
)
SESSION_SCHEMA = json.loads(
    (ROOT / "contracts/protocol/story_session_control.schema.json").read_text(
        encoding="utf-8"
    )
)
EXPRESSION_SCHEMA = json.loads(
    (ROOT / "contracts/protocol/story_expression_control.schema.json").read_text(
        encoding="utf-8"
    )
)
SESSION_FIXTURE = json.loads(
    (ROOT / "contracts/fixtures/ipc/story_session_control.json").read_text(
        encoding="utf-8"
    )
)

SESSION_ID = "session_0123456789abcdef0123456789abcdef"
TURN_ID = "turn_0123456789abcdef0123456789abcdef"
POST_COMMIT_METHODS = {
    "story.advice.submit.v2",
    "story.turn.submit.v2",
    "story.turn.work.get",
    "story.turn.work.retry",
}


def _registry(schema: dict) -> Registry:
    return Registry().with_resources(
        (
            resource["$id"],
            Resource.from_contents(resource),
        )
        for resource in (schema, SESSION_SCHEMA, EXPRESSION_SCHEMA)
    )


def _validator_for(shape: str) -> Draft202012Validator:
    schema = {
        "$schema": SCHEMA["$schema"],
        "$id": SCHEMA["$id"],
        "$ref": f"#/$defs/{shape}",
        "$defs": SCHEMA["$defs"],
    }
    return Draft202012Validator(schema, registry=_registry(SCHEMA))


def _session_validator_for(shape: str) -> Draft202012Validator:
    schema = {
        "$schema": SESSION_SCHEMA["$schema"],
        "$id": SESSION_SCHEMA["$id"],
        "$ref": f"#/$defs/{shape}",
        "$defs": SESSION_SCHEMA["$defs"],
    }
    return Draft202012Validator(schema, registry=_registry(SESSION_SCHEMA))


def _delivery() -> dict:
    recipe = {
        "speech_unit_id": "speech_unit_01",
        "turn_id": TURN_ID,
        "story_revision": 1,
        "narrative_block_id": "narrative_01",
        "segment_index": 0,
        "performance_plan_id": "performance_01",
        "spoken_text": "蒸汽管在墙后低鸣。",
        "voice_id": "voice_01",
        "expected_voice_revision": "voice_revision_01",
        "expected_model_revision": None,
        "speed": 1.0,
        "language": "zh-CN",
        # Same four pins as the Engine seals: the reviewed evidence and the
        # exact artifact it was reviewed against.
        "evidence_id": "evidence_01",
        "evidence_digest": "b" * 64,
        "expected_model_artifact_revision": "model_artifact_01",
        "expected_model_catalog_revision": "qwen3-tts-20260929",
    }
    return {
        "state": "ready",
        "narrative_block_id": "narrative_01",
        "speech_units": [
            {
                "segment_index": 0,
                "state": "ready",
                "speech_unit_id": "speech_unit_01",
                "spoken_text": "蒸汽管在墙后低鸣。",
                "render_recipe": recipe,
            }
        ],
    }


def _work_response(
    *,
    settlement_state: str = "succeeded",
    narrative_state: str = "ready",
    audio_state: str = "ready",
) -> dict:
    response = {
        "schema_version": "1.0",
        "session_id": SESSION_ID,
        "turn_id": TURN_ID,
        "settlement_state": settlement_state,
        "narrative_state": narrative_state,
        "narrative_segments": (
            [{"type": "narration", "text": "蒸汽管在墙后低鸣。"}]
            if narrative_state == "ready"
            else []
        ),
        "audio_state": audio_state,
    }
    if settlement_state == "blocked":
        response["settlement_reason"] = "settlement_conflict"
    if narrative_state == "blocked":
        response["narrative_reason"] = "narrative_unavailable"
    if audio_state == "unavailable":
        response["audio_reason"] = "handoff_expired"
    if audio_state == "ready":
        response["delivery"] = _delivery()
    return response


def _fixture_case(case_id: str) -> dict:
    return next(case["value"] for case in SESSION_FIXTURE["cases"] if case["id"] == case_id)


def test_post_commit_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(SCHEMA)


def test_work_get_and_retry_method_capabilities_are_registered_in_ipc():
    capability = IPC_SCHEMA["$defs"]["story_post_commit_method_capability"]
    assert set(capability["enum"]) == POST_COMMIT_METHODS
    validator = Draft202012Validator(capability)
    assert all(validator.is_valid(method) for method in POST_COMMIT_METHODS)
    assert not validator.is_valid("story.turn.work.debug")


def test_work_get_is_a_pure_read_and_retry_only_accepts_idempotent_work_identity():
    get_request = SCHEMA["$defs"]["work_get_request"]
    retry_request = SCHEMA["$defs"]["work_retry_request"]
    assert "pure read" in get_request["description"].lower()
    assert "provider" in get_request["description"].lower()
    assert "idempotent" in retry_request["description"].lower()
    assert "domain" in retry_request["description"].lower()

    assert set(get_request["properties"]) == {
        "schema_version",
        "session_id",
        "turn_id",
    }
    assert set(retry_request["properties"]) == {
        "schema_version",
        "session_id",
        "turn_id",
        "kind",
        "retry_request_id",
    }
    domain_rewrite_fields = {
        "raw_input",
        "input_mode",
        "input_turn_id",
        "expected_story_revision",
        "expected_store_revision",
        "proposal",
        "state_delta",
        "resolver_input",
    }
    get_response = SCHEMA["$defs"]["work_get_response"]
    retry_response = SCHEMA["$defs"]["work_retry_response"]
    domain_write_fields = domain_rewrite_fields | {
        "receipt",
        "state_delta",
        "story_revision",
        "committed_store_revision",
        "world_revision",
        "domain_transaction",
    }
    for shape in (get_request, retry_request, get_response, retry_response):
        assert domain_write_fields.isdisjoint(shape["properties"])
        assert shape["additionalProperties"] is False


@pytest.mark.parametrize("identity_field", ["session_id", "turn_id"])
@pytest.mark.parametrize(
    "internal_inventory",
    [
        {"lease": "lease_01", "owner": "engine_01"},
        {"internal_error": "sqlite3.OperationalError", "generation": 4},
    ],
)
def test_requests_cannot_embed_internal_identity_inventory(identity_field, internal_inventory):
    request = {
        "schema_version": "1.0",
        "session_id": SESSION_ID,
        "turn_id": TURN_ID,
    }
    request[identity_field] = {
        "id": request[identity_field],
        **internal_inventory,
    }
    assert not _validator_for("work_get_request").is_valid(request)
    assert SCHEMA["$defs"]["identifier"]["type"] == "string"


def test_request_identity_fields_are_scalar_allowlisted_values():
    for shape, expected in [
        ("work_get_request", {"schema_version", "session_id", "turn_id"}),
        (
            "work_retry_request",
            {"schema_version", "session_id", "turn_id", "kind", "retry_request_id"},
        ),
    ]:
        request = SCHEMA["$defs"][shape]
        assert set(request["properties"]) == expected
        assert request["properties"]["session_id"] == {"$ref": "#/$defs/identifier"}
        assert request["properties"]["turn_id"] == {"$ref": "#/$defs/identifier"}
        assert request["additionalProperties"] is False


def test_work_get_request_and_idempotent_retry_acknowledgment_shapes():
    get_request = {
        "schema_version": "1.0",
        "session_id": SESSION_ID,
        "turn_id": TURN_ID,
    }
    assert _validator_for("work_get_request").is_valid(get_request)

    retry_response = {
        "schema_version": "1.0",
        "session_id": SESSION_ID,
        "turn_id": TURN_ID,
        "kind": "audio_prepare",
        "retry_request_id": "retry_01",
        "accepted": True,
        "replayed": False,
    }
    validator = _validator_for("work_retry_response")
    assert validator.is_valid(retry_response)

    rejected_ack = copy.deepcopy(retry_response)
    rejected_ack["accepted"] = False
    assert not validator.is_valid(rejected_ack)
    domain_mutation = copy.deepcopy(retry_response)
    domain_mutation["state_delta"] = {}
    assert not validator.is_valid(domain_mutation)


def test_retry_kind_is_exactly_the_post_commit_work_task_vocabulary():
    kind = SCHEMA["$defs"]["work_kind"]
    assert kind["enum"] == [
        "episode_finalize",
        "narrative_publish",
        "audio_prepare",
    ]
    request = {
        "schema_version": "1.0",
        "session_id": SESSION_ID,
        "turn_id": TURN_ID,
        "kind": "audio_prepare",
        "retry_request_id": "retry_01",
    }
    assert _validator_for("work_retry_request").is_valid(request)
    request["kind"] = "story_turn_submit"
    assert not _validator_for("work_retry_request").is_valid(request)


@pytest.mark.parametrize(
    ("state", "needs_reason"),
    [
        ("not_required", False),
        ("pending", False),
        ("running", False),
        ("blocked", True),
        ("succeeded", False),
    ],
)
def test_each_settlement_state_has_its_own_reason_binding(state, needs_reason):
    response = _work_response(settlement_state=state)
    validator = _validator_for("work_get_response")
    assert validator.is_valid(response)

    invalid = copy.deepcopy(response)
    if needs_reason:
        invalid.pop("settlement_reason")
    else:
        invalid["settlement_reason"] = "unexpected_reason"
    assert not validator.is_valid(invalid)


def test_settlement_state_vocabulary_is_exact():
    assert SCHEMA["$defs"]["settlement_state"]["enum"] == [
        "not_required",
        "pending",
        "running",
        "blocked",
        "succeeded",
    ]
    response = _work_response()
    response["settlement_state"] = "unavailable"
    assert not _validator_for("work_get_response").is_valid(response)


@pytest.mark.parametrize(
    ("state", "valid_mutation", "invalid_mutation"),
    [
        (
            "pending",
            lambda response: None,
            lambda response: response.update(
                narrative_segments=[{"type": "narration", "text": "尚未发布"}]
            ),
        ),
        (
            "running",
            lambda response: None,
            lambda response: response.update(narrative_reason="should_not_be_present"),
        ),
        (
            "blocked",
            lambda response: None,
            lambda response: response.pop("narrative_reason"),
        ),
        (
            "ready",
            lambda response: None,
            lambda response: response.update(narrative_segments=[]),
        ),
    ],
)
def test_each_narrative_state_has_its_own_artifact_and_reason_binding(
    state, valid_mutation, invalid_mutation
):
    validator = _validator_for("work_get_response")
    valid = _work_response(narrative_state=state)
    valid_mutation(valid)
    assert validator.is_valid(valid)

    invalid = _work_response(narrative_state=state)
    invalid_mutation(invalid)
    assert not validator.is_valid(invalid)


def test_ready_narrative_rejects_reason_and_non_ready_narrative_rejects_artifacts():
    validator = _validator_for("work_get_response")
    ready_with_reason = _work_response(narrative_state="ready")
    ready_with_reason["narrative_reason"] = "narrative_error"
    assert not validator.is_valid(ready_with_reason)

    for state in ("pending", "running", "blocked"):
        with_artifact = _work_response(narrative_state=state)
        with_artifact["narrative_segments"] = [
            {"type": "narration", "text": "不得提前显示"}
        ]
        assert not validator.is_valid(with_artifact)


def test_narrative_state_vocabulary_is_exact_and_segments_use_expression_view():
    assert SCHEMA["$defs"]["narrative_state"]["enum"] == [
        "pending",
        "running",
        "blocked",
        "ready",
    ]
    assert SCHEMA["$defs"]["narrative_segment"] == {
        "$ref": "story_expression_control.schema.json#/$defs/expression_segment"
    }


@pytest.mark.parametrize(
    ("state", "needs_reason", "needs_delivery"),
    [
        ("pending", False, False),
        ("running", False, False),
        ("unavailable", True, False),
        ("ready", False, True),
    ],
)
def test_each_audio_state_has_its_own_handoff_binding(
    state, needs_reason, needs_delivery
):
    validator = _validator_for("work_get_response")
    valid = _work_response(audio_state=state)
    assert validator.is_valid(valid)

    invalid = copy.deepcopy(valid)
    if needs_delivery:
        invalid["delivery"]["speech_units"][0].pop("render_recipe")
    elif needs_reason:
        invalid.pop("audio_reason")
    else:
        invalid["audio_reason"] = "unexpected_reason"
    assert not validator.is_valid(invalid)

    if state == "unavailable":
        missing_reason = copy.deepcopy(valid)
        missing_reason.pop("audio_reason")
        assert not validator.is_valid(missing_reason)


def test_audio_ready_requires_complete_turn_delivery_view():
    response = _work_response(audio_state="ready")
    assert SCHEMA["$defs"]["turn_delivery_view"] == {
        "$ref": "story_session_control.schema.json#/$defs/turn_delivery"
    }
    assert _validator_for("work_get_response").is_valid(response)
    assert response["delivery"]["state"] == "ready"
    segment = response["delivery"]["speech_units"][0]
    assert segment["state"] == "ready"
    assert set(segment["render_recipe"]) == {
        "speech_unit_id",
        "turn_id",
        "story_revision",
        "narrative_block_id",
        "segment_index",
        "performance_plan_id",
        "spoken_text",
        "voice_id",
        "expected_voice_revision",
        "expected_model_revision",
        "evidence_id",
        "evidence_digest",
        "expected_model_artifact_revision",
        "expected_model_catalog_revision",
        "speed",
        "language",
    }

    missing_delivery = copy.deepcopy(response)
    missing_delivery.pop("delivery")
    assert not _validator_for("work_get_response").is_valid(missing_delivery)
    unavailable_delivery = copy.deepcopy(response)
    unavailable_delivery["delivery"]["state"] = "unavailable"
    assert not _validator_for("work_get_response").is_valid(unavailable_delivery)


def test_handoff_expiry_requires_unavailable_without_delivery():
    response = _work_response(audio_state="unavailable")
    response["audio_reason"] = "handoff_expired"
    validator = _validator_for("work_get_response")
    assert validator.is_valid(response)

    response_with_expired_delivery = copy.deepcopy(response)
    response_with_expired_delivery["delivery"] = _delivery()
    assert not validator.is_valid(response_with_expired_delivery)

    ready_with_expiry_reason = _work_response(audio_state="ready")
    ready_with_expiry_reason["audio_reason"] = "handoff_expired"
    assert not validator.is_valid(ready_with_expiry_reason)


def test_audio_ready_documents_sealed_result_and_current_registry_semantics():
    description = SCHEMA["$defs"]["audio_state"]["description"].lower()
    assert "sealed result" in description
    assert "current engine registry" in description
    assert "handoff_expired" in description


def test_audio_failure_does_not_derive_or_rewrite_other_work_states():
    response = _work_response(
        settlement_state="succeeded",
        narrative_state="ready",
        audio_state="unavailable",
    )
    response["audio_reason"] = "handoff_expired"
    assert _validator_for("work_get_response").is_valid(response)
    assert response["settlement_state"] == "succeeded"
    assert response["narrative_state"] == "ready"
    assert response["audio_state"] == "unavailable"
    assert "delivery" not in response

    invalid_reversed_projection = copy.deepcopy(response)
    invalid_reversed_projection["delivery"] = _delivery()
    assert not _validator_for("work_get_response").is_valid(invalid_reversed_projection)


def test_v2_submit_requests_reuse_v1_input_shapes_and_live_input_mode():
    advice_request = _fixture_case("advice_submit_request_valid")
    turn_request = {
        "schema_version": "1.0",
        "session_id": SESSION_ID,
        "input_turn_id": "input_turn_live_001",
        "raw_input": "我想问问他的反应。",
        "input_mode": "voice",
        "expected_story_revision": 1,
        "expected_store_revision": 2,
    }
    for shape, value, legacy_shape in [
        ("advice_submit_v2_request", advice_request, "advice_submit_request"),
        ("turn_submit_v2_request", turn_request, "turn_submit_request"),
    ]:
        assert _validator_for(shape).is_valid(value)
        assert SCHEMA["$defs"][shape] == {
            "$ref": f"story_session_control.schema.json#/$defs/{legacy_shape}"
        }
    assert turn_request["input_mode"] == "voice"


@pytest.mark.parametrize(
    ("shape", "legacy_case"),
    [
        ("advice_submit_v2_response", "advice_submit_response_valid"),
        ("turn_submit_v2_response", "advice_submit_response_valid"),
    ],
)
def test_v2_submit_responses_are_commit_receipt_public_session_and_replay_flag(
    shape, legacy_case
):
    legacy = _fixture_case(legacy_case)
    response = {
        "schema_version": "1.0",
        "receipt": legacy["receipt"],
        "session": legacy["session"],
        "replayed": legacy["replayed"],
    }
    validator = _validator_for(shape)
    assert validator.is_valid(response)

    no_receipt = copy.deepcopy(response)
    no_receipt.pop("receipt")
    assert not validator.is_valid(no_receipt)
    no_session = copy.deepcopy(response)
    no_session.pop("session")
    assert not validator.is_valid(no_session)
    no_replayed = copy.deepcopy(response)
    no_replayed.pop("replayed")
    assert not validator.is_valid(no_replayed)

    synchronous_delivery = copy.deepcopy(response)
    synchronous_delivery["delivery"] = _delivery()
    assert not validator.is_valid(synchronous_delivery)


def test_v2_submit_schema_explicitly_reuses_domain_receipt_and_public_session():
    response = SCHEMA["$defs"]["v2_submit_response"]
    assert response["properties"]["receipt"]["$ref"] == (
        "story_session_control.schema.json#/$defs/committed_receipt"
    )
    assert response["properties"]["session"]["$ref"] == (
        "story_session_control.schema.json#/$defs/public_story_session_view"
    )
    assert response["additionalProperties"] is False
    assert "delivery" not in response["properties"]


def test_v1_submit_response_shape_stays_compatible_with_optional_delivery():
    legacy = _fixture_case("advice_submit_response_valid")
    validator = _session_validator_for("advice_submit_response")
    assert validator.is_valid(legacy)
    assert "delivery" in SESSION_SCHEMA["$defs"]["advice_submit_response"]["properties"]

    with_delivery = copy.deepcopy(legacy)
    with_delivery["delivery"] = _delivery()
    assert validator.is_valid(with_delivery)


def test_v1_session_control_methods_remain_present_and_unmodified_by_ao03():
    assert {
        "advice_submit_request",
        "turn_submit_request",
        "advice_submit_response",
        "turn_submit_response",
    } <= set(SESSION_SCHEMA["$defs"])
    assert "input_mode" in SESSION_SCHEMA["$defs"]["turn_submit_request"]["properties"]
