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
        "voice_design.schema.json",
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

#: Mirrors ``MAX_FRAME_BYTES`` in engine/infrastructure/ipc_framing.py. It is
#: restated rather than imported: contracts do not depend on the engine, and a
#: frame limit that quietly drifts from the transport is exactly the kind of
#: drift this assertion exists to catch.
MAX_FRAME_BYTES = 1024 * 1024

#: The base this protocol's relative cross-file ``$ref``s resolve against.
PROTOCOL_BASE = FOUNDRY["$id"].rsplit("/", 1)[0] + "/"

EXPECTED_METHODS = {
    "voice.foundry.request",
    "voice.foundry.get",
    "voice.foundry.list",
    "voice.foundry.list_designs",
    "voice.foundry.cast_design",
    "voice.foundry.select",
    "voice.foundry.confirm_reference",
    "voice.foundry.validate",
    "voice.foundry.review",
    "voice.foundry.publish",
    "voice.foundry.asset.get",
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
    """Register schemas under every URI a cross-file ``$ref`` may resolve to.

    The product schemas carry ``mysterious.world`` ids while this protocol
    lives on ``worldofmysteries.io``, so a relative ``$ref`` like
    ``voice_cast_request.schema.json`` resolves against the protocol's own
    base and lands on a URI no schema claims. Registering only the declared
    ``$id`` hides that: nothing ever resolved these refs, because nothing ever
    validated a whole response.
    """
    resources = []
    for schema in schemas:
        resource = Resource.from_contents(schema)
        name = schema["$id"].rsplit("/", 1)[-1]
        resources.append((schema["$id"], resource))
        resources.append((f"{PROTOCOL_BASE}{name}", resource))
    return Registry().with_resources(resources)


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
            "model_catalog_revision": "catalog-rev-1",
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


def test_intake_carries_the_whole_cast_request_and_nothing_else():
    """The method advertised by the IPC schema finally has a shape.

    ``voice.foundry.request`` has been in the transport's capability enum
    since the protocol was written, so a client could ask for it and there
    was nothing to validate the answer against. Intake is the one write here
    that is not a command: it acts on no existing task, so it has no
    expected revision and no command id to replay under.
    """
    validator = _validator(FOUNDRY, "foundry_request_request")
    assert validator.is_valid({"schema_version": "1.0", "request": _cast_request()})
    assert not validator.is_valid({"schema_version": "1.0"})
    assert not validator.is_valid(
        {"schema_version": "1.0", "request": _cast_request(), "force": True}
    )


def test_an_already_bound_identity_answers_ready_without_inventing_a_task():
    """A voice that already exists is an answer, not an empty casting.

    Returning a task alongside ``ready`` would put a phantom casting in
    front of a listener: there was nothing to cast, and a task id would
    invite someone to go and look for candidates that were never minted.
    """
    validator = _validator(FOUNDRY, "foundry_request_response")
    assert validator.is_valid(
        {"schema_version": "1.0", "outcome": "ready", "binding_id": "bind_01"}
    )
    assert not validator.is_valid(
        {"schema_version": "1.0", "outcome": "ready", "task_id": "task-01"}
    )
    assert validator.is_valid(
        {"schema_version": "1.0", "outcome": "supply_required", "task_id": "task-01"}
    )
    assert not validator.is_valid({"schema_version": "1.0", "outcome": "ready_ish"})


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


def test_evidence_execution_carries_the_catalogue_revision_the_gate_compares():
    """The catalogue revision is an execution fact, not an extra.

    ``VoiceEvidenceGate`` refuses a render whose
    ``model_catalog_revision`` differs from the snapshot's, and
    ``voice_render_control`` already requires the caller to declare
    ``expected_model_catalog_revision``. The evidence document was the only
    one of the three that left it out — and because ``execution`` is closed to
    additional properties, a bundle carrying it was rejected by the contract
    written to describe it. A stale catalogue entry silently passing as the
    current one is exactly what that check exists to prevent, so the field is
    required rather than permitted.
    """
    schema = SCHEMAS["voice_identity_evidence.schema.json"]
    execution = schema["$defs"]["execution"]
    assert execution["additionalProperties"] is False
    assert "model_catalog_revision" in execution["required"]
    assert execution["properties"]["model_catalog_revision"] == {
        "$ref": "#/$defs/identifier"
    }

    validator = Draft202012Validator(
        schema, registry=_registry(*SCHEMAS.values())
    )
    assert validator.is_valid(_evidence())

    missing = copy.deepcopy(_evidence())
    del missing["execution"]["model_catalog_revision"]
    assert not validator.is_valid(missing)

    blank = copy.deepcopy(_evidence())
    blank["execution"]["model_catalog_revision"] = ""
    assert not validator.is_valid(blank)

    # The two contracts have to be naming the same fact, or a caller could
    # declare one revision while the evidence is pinned to another.
    render = json.loads(
        (ROOT / "contracts/protocol/voice_render_control.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert "expected_model_catalog_revision" in render["$defs"]["request_v2"][
        "required"
    ]


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
        "foundry_request_request",
        "foundry_list_request",
        "foundry_designs_request",
        "foundry_cast_design_request",
        "foundry_asset_request",
        "foundry_command",
        "foundry_get_response",
        "foundry_request_response",
        "foundry_designs_response",
        "foundry_asset_response",
        "foundry_command_response",
    ],
)
def test_control_shapes_are_closed_and_cannot_carry_domain_or_worker_inventory(shape):
    assert set(FOUNDRY["$defs"][shape]["properties"]).isdisjoint(FORBIDDEN_FIELDS)
    assert FOUNDRY["$defs"][shape]["additionalProperties"] is False


def test_get_and_list_are_documented_pure_reads():
    for shape in (
        "foundry_get_request",
        "foundry_list_request",
        "foundry_designs_request",
    ):
        description = FOUNDRY["$defs"][shape]["description"].lower()
        assert "pure read" in description
        assert "provider" in description
        assert "never" in description


def _design(**overrides) -> dict:
    design = {
        "schema_version": "1.0",
        "design_id": "tingen.victor-osborn",
        "display_name": "维克多·奥斯本",
        "presentation_identity": "victor-osborn",
        "usage": "dialogue",
        "locale": "zh-CN",
        "design_revision": 2,
        "public_traits": ["低沉", "粗粝"],
        "voice_description": "一位五十岁上下的男性。音色粗粝、沙哑，常年被机器声磨过。",
        "reference_text": "机器老了才最要紧，人老了还能修，机器散了可没人赔得起。",
        "validation_text": "我修过贝克兰德运来的新锅炉，都比不上咱们这台老伙计懂事。",
    }
    design.update(overrides)
    return design


def test_a_casting_brief_carries_a_voice_and_nothing_else():
    """The record a preview, a prompt and a log all read cannot be a dossier.

    A hidden identity or an unplayed plot beat added here would reach a voice
    actor, a provider and a log file in the same breath. Closing the shape is
    the only control that does not depend on somebody remembering.
    """
    validator = Draft202012Validator(
        SCHEMAS["voice_design.schema.json"],
        registry=_registry(*SCHEMAS.values()),
    )
    assert validator.is_valid(_design())
    for leaked in (
        {"canon_anchor": "lotm:kleins"},
        {"hidden_identity": "audrey"},
        {"secret": "he is the seer"},
        {"future_arc": "the war in the east"},
    ):
        assert not validator.is_valid(_design(**leaked)), leaked


def test_a_brief_that_cannot_be_cast_is_refused_by_the_contract_too():
    """The loader refuses these; the contract is what a second client reads."""
    validator = Draft202012Validator(
        SCHEMAS["voice_design.schema.json"],
        registry=_registry(*SCHEMAS.values()),
    )
    assert not validator.is_valid(_design(usage="narration", presentation_identity=""))
    assert not validator.is_valid(_design(design_revision=0))
    assert not validator.is_valid(_design(reference_text="短"))
    assert not validator.is_valid(_design(public_traits=["a", "a"]))


def test_the_catalog_response_points_at_the_published_design_schema():
    response = FOUNDRY["$defs"]["foundry_designs_response"]
    assert (
        response["properties"]["designs"]["items"]["$ref"]
        == "voice_design.schema.json"
    )
    assert response["additionalProperties"] is False
    assert set(response["required"]) == {"schema_version", "catalog_version", "designs"}


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


def test_audition_asset_is_a_read_naming_one_candidate_and_one_kind():
    """A client asks for one asset of one parked candidate.

    It is a read, not a command: it moves nothing, so there is no command id
    and no expected revision to lie about. The candidate is named because a
    task can hold several, and only one of them was ever put in front of a
    listener — the others are previews nobody judged.
    """
    request = FOUNDRY["$defs"]["foundry_asset_request"]
    assert set(request["required"]) == {
        "schema_version",
        "task_id",
        "candidate_id",
        "kind",
    }
    assert request["properties"]["kind"]["enum"] == ["reference", "validation"]
    validator = _validator(FOUNDRY, "foundry_asset_request")
    assert validator.is_valid(
        {
            "schema_version": "1.0",
            "task_id": "vf-task-1",
            "candidate_id": "vf-task-1:candidate:0",
            "kind": "validation",
        }
    )
    assert not validator.is_valid(
        {
            "schema_version": "1.0",
            "task_id": "vf-task-1",
            "candidate_id": "vf-task-1:candidate:0",
            "kind": "preview",
        }
    )


def test_audition_asset_travels_with_the_facts_that_identify_it():
    """The bytes are worth nothing without the revision and the digest beside them.

    ``voice.foundry.review`` demands a validation id and two digests, and this
    response is the only place a client can learn any of them — the task
    projection carries neither. Sending the audio alone would leave a reviewer
    unable to say what they heard; sending the digest alone would prove nothing
    about whether it is the same audio.
    """
    response = FOUNDRY["$defs"]["foundry_asset_response"]
    assert {
        "candidate_revision",
        "validation_id",
        "audio_digest",
        "audio_bytes",
        "audio_base64",
    } <= set(response["required"])
    validator = _validator(FOUNDRY, "foundry_asset_response")
    body = {
        "schema_version": "1.0",
        "task_id": "vf-task-1",
        "candidate_id": "vf-task-1:candidate:0",
        "kind": "validation",
        "candidate_revision": "vr_" + "c" * 32,
        "validation_id": "vv_" + "e" * 24,
        "audio_digest": "9" * 64,
        "audio_bytes": 4096,
        "audio_base64": "UklGRg==",
    }
    assert validator.is_valid(body)
    # The reference asset belongs to no validation and says so outright, rather
    # than carrying an empty id a client could echo into a review.
    assert validator.is_valid({**body, "kind": "reference", "validation_id": None})
    assert not validator.is_valid({**body, "validation_id": None})


def test_one_audition_asset_always_fits_a_single_ipc_frame():
    """An asset too large to cross the wire is refused, not truncated.

    Truncation would be the worse outcome by far: a WAV cut short still plays,
    still sounds like a voice, and a listener would judge it — while the digest
    in the evidence describes bytes that are not what they heard. The bound is
    therefore a contract fact a client can rely on, not an implementation
    detail it has to discover by getting a frame error.
    """
    cap = FOUNDRY["$defs"]["foundry_asset_response"]["properties"]["audio_bytes"][
        "maximum"
    ]
    # Standard base64 emits four characters per three bytes, rounded up.
    encoded = 4 * -(-cap // 3)
    assert encoded + 1024 < MAX_FRAME_BYTES


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


def _binding_replace() -> dict:
    return {
        "schema_version": "1.0",
        "command_id": "cmd_replace_1",
        "payload_digest": "a" * 64,
        "scope": _scope(),
        "expected_binding_revision": 3,
        "binding_id": "vb_klein",
        "logical_voice_id": "voice_klein",
        "persona_revision": "persona_2",
        "provider_instance": "speechrail_local",
        "voice_id": "klein_approved_v2",
        "voice_revision": "wvr_2",
        "model_artifact_revision": "qwen3_tts_2026_09_30",
        "evidence_id": "ev_klein_2",
        "evidence_digest": "b" * 64,
    }


def test_a_replacement_names_the_binding_and_the_voice_being_installed():
    """The command cannot be carried out without all of these.

    A replacement that omitted the binding it re-points, the game-side voice
    identity, the persona revision, or the artifact the approval was heard on
    would leave the implementation inventing one of them. Naming them here
    keeps the wire and the domain from disagreeing about what is being
    installed.
    """
    replace = FOUNDRY["$defs"]["binding_replace_request"]
    assert {
        "binding_id",
        "logical_voice_id",
        "persona_revision",
        "model_artifact_revision",
    } <= set(replace["required"])
    assert replace["additionalProperties"] is False

    validator = _validator(FOUNDRY, "binding_replace_request")
    assert validator.is_valid(_binding_replace())


@pytest.mark.parametrize(
    "missing",
    [
        "binding_id",
        "logical_voice_id",
        "persona_revision",
        "model_artifact_revision",
    ],
)
def test_a_replacement_without_its_identity_or_evidence_is_refused(missing):
    request = _binding_replace()
    del request[missing]
    assert not _validator(FOUNDRY, "binding_replace_request").is_valid(request)


def test_the_catalogue_revision_is_optional_and_the_artifact_revision_is_not():
    """A catalogue entry may be absent; the artifact a person heard may not.

    Folding the catalogue revision into the artifact revision is how an old
    catalogue row ends up standing in for a voice nobody listened to, so the
    artifact revision is required on its own.
    """
    validator = _validator(FOUNDRY, "binding_replace_request")

    without_catalogue = _binding_replace()
    assert validator.is_valid(without_catalogue)

    null_catalogue = {**_binding_replace(), "model_catalog_revision": None}
    assert validator.is_valid(null_catalogue)

    assert not validator.is_valid({**_binding_replace(), "model_catalog_revision": 7})


def test_a_replacement_cannot_smuggle_in_an_assurance_the_revision_contradicts():
    """There is no separate assurance field to disagree with voice_revision.

    ADR-005 D2 admits only voices with an immutable artifact revision; a
    legacy provider voice is a UI hint, not a renderable identity. Encoding
    that as a required non-nullable ``voice_revision`` means a caller cannot
    assert an assurance the revision does not support, and the closed shape
    means it cannot smuggle one in either.
    """
    replace = FOUNDRY["$defs"]["binding_replace_request"]
    assert "assurance" not in replace["properties"]
    assert "assurance" not in replace["required"]
    assert "voice_revision" in replace["required"]
    assert replace["properties"]["voice_revision"] == {"$ref": "#/$defs/identifier"}

    validator = _validator(FOUNDRY, "binding_replace_request")
    assert not validator.is_valid({**_binding_replace(), "assurance": "legacy"})
    legacy = _binding_replace()
    del legacy["voice_revision"]
    assert not validator.is_valid(legacy)


def test_casting_a_design_does_not_ask_the_client_to_name_a_world():
    """The client is never told the world, so it must not be asked for it.

    A scope the caller could supply is a scope it could forge; a scope it
    cannot supply is a request it has no honest way to make. The engine
    resolves owner, world and worldline from a session it already owns, and
    takes the identity from the design it published.
    """
    shape = FOUNDRY["$defs"]["foundry_cast_design_request"]
    assert set(shape["required"]) == {"schema_version", "session_id", "design_id"}
    assert set(shape["properties"]) == {"schema_version", "session_id", "design_id"}
    assert shape["additionalProperties"] is False
    assert FORBIDDEN_FIELDS.isdisjoint(shape["properties"])
    for forged in ("world_id", "worldline_id", "owner_id", "scope"):
        assert forged not in shape["properties"]
