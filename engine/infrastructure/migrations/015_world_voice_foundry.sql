-- Durable presentation-side voice supply tasks, operation recovery, and
-- immutable verification/binding history. These rows never advance world_meta.
CREATE TABLE voice_foundry_tasks(
    task_id TEXT PRIMARY KEY CHECK(length(task_id)>0 AND length(task_id)<=256),
    request_id TEXT NOT NULL UNIQUE CHECK(length(request_id)>0 AND length(request_id)<=256),
    request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
    authorization_ref TEXT NOT NULL CHECK(length(authorization_ref)>0 AND length(authorization_ref)<=256),
    owner_id TEXT NOT NULL CHECK(length(owner_id)>0 AND length(owner_id)<=256),
    world_id TEXT NOT NULL CHECK(length(world_id)>0 AND length(world_id)<=256),
    worldline_id TEXT NOT NULL CHECK(length(worldline_id)>0 AND length(worldline_id)<=256),
    presentation_identity TEXT NOT NULL CHECK(length(presentation_identity)>0 AND length(presentation_identity)<=256),
    phase TEXT NOT NULL CHECK(length(phase)>0 AND length(phase)<=256),
    locale TEXT NOT NULL CHECK(length(locale)>0 AND length(locale)<=35),
    persona_revision TEXT NOT NULL CHECK(length(persona_revision)>0 AND length(persona_revision)<=256),
    usage TEXT NOT NULL CHECK(usage IN ('dialogue','narration')),
    provider_instance TEXT NOT NULL CHECK(length(provider_instance)>0 AND length(provider_instance)<=256),
    public_traits_json TEXT NOT NULL CHECK(length(public_traits_json)<=65536),
    voice_description TEXT NOT NULL CHECK(length(voice_description)>0 AND length(voice_description)<=1000),
    reference_text TEXT NOT NULL CHECK(length(reference_text) BETWEEN 20 AND 240),
    validation_text TEXT NOT NULL CHECK(length(validation_text) BETWEEN 20 AND 240),
    origin_kind TEXT NOT NULL CHECK(origin_kind IN ('content','scene')),
    origin_ref TEXT NOT NULL CHECK(length(origin_ref)>0 AND length(origin_ref)<=256),
    origin_revision INTEGER NOT NULL CHECK(origin_revision>=0),
    stage TEXT NOT NULL CHECK(stage IN (
        'requested','previewing','awaiting_selection','provisioning',
        'validating','awaiting_review','published','binding','ready',
        'failed','cancelled'
    )),
    task_revision INTEGER NOT NULL CHECK(task_revision>=1),
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0,1)),
    operation_status TEXT NOT NULL CHECK(operation_status IN (
        'prepared','unknown','confirmed','rejected'
    )),
    required_actions_json TEXT NOT NULL CHECK(length(required_actions_json)<=65536),
    reason_code TEXT CHECK(reason_code IS NULL OR length(reason_code)<=128),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK(reference_text<>validation_text)
) STRICT;

CREATE UNIQUE INDEX ux_voice_foundry_active_scope_digest
ON voice_foundry_tasks(
    owner_id,world_id,worldline_id,presentation_identity,phase,locale,
    persona_revision,request_digest,provider_instance
)
WHERE stage NOT IN ('failed','cancelled');

CREATE INDEX ix_voice_foundry_scope_stage
ON voice_foundry_tasks(owner_id,world_id,worldline_id,stage,updated_at);

CREATE TABLE voice_foundry_candidates(
    task_id TEXT NOT NULL REFERENCES voice_foundry_tasks(task_id) ON DELETE RESTRICT,
    candidate_id TEXT NOT NULL CHECK(length(candidate_id)>0 AND length(candidate_id)<=256),
    slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 4),
    seed INTEGER NOT NULL CHECK(seed BETWEEN 0 AND 4294967295),
    state TEXT NOT NULL CHECK(state IN (
        'previewing','ready','selected','provisioning','validating',
        'reviewing','published','failed','cancelled'
    )),
    preview_audio_digest TEXT NOT NULL CHECK(length(preview_audio_digest)=64),
    recipe_json TEXT NOT NULL CHECK(length(recipe_json)>0 AND length(recipe_json)<=65536),
    recipe_digest TEXT NOT NULL CHECK(length(recipe_digest)=64),
    provider_candidate_id TEXT CHECK(
        provider_candidate_id IS NULL OR length(provider_candidate_id)<=256
    ),
    provider_candidate_revision TEXT CHECK(
        provider_candidate_revision IS NULL OR length(provider_candidate_revision)<=256
    ),
    reference_audio_digest TEXT CHECK(
        reference_audio_digest IS NULL OR length(reference_audio_digest)=64
    ),
    reference_text_digest TEXT CHECK(
        reference_text_digest IS NULL OR length(reference_text_digest)=64
    ),
    validation_audio_digest TEXT CHECK(
        validation_audio_digest IS NULL OR length(validation_audio_digest)=64
    ),
    validation_text_digest TEXT CHECK(
        validation_text_digest IS NULL OR length(validation_text_digest)=64
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(task_id,candidate_id),
    UNIQUE(task_id,slot)
) STRICT;

CREATE TABLE voice_foundry_operations(
    operation_id TEXT PRIMARY KEY CHECK(length(operation_id)>0 AND length(operation_id)<=256),
    task_id TEXT NOT NULL REFERENCES voice_foundry_tasks(task_id) ON DELETE RESTRICT,
    stage TEXT NOT NULL CHECK(length(stage)>0 AND length(stage)<=64),
    attempt_identity TEXT NOT NULL CHECK(length(attempt_identity)>0 AND length(attempt_identity)<=256),
    idempotency_key TEXT NOT NULL UNIQUE CHECK(length(idempotency_key)>0 AND length(idempotency_key)<=256),
    payload_json TEXT NOT NULL CHECK(length(payload_json)<=1048576),
    payload_digest TEXT NOT NULL CHECK(length(payload_digest)=64),
    status TEXT NOT NULL CHECK(status IN ('prepared','unknown','confirmed','rejected')),
    provider_result_ref TEXT CHECK(
        provider_result_ref IS NULL OR length(provider_result_ref)<=256
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(task_id,stage,attempt_identity)
) STRICT;

CREATE INDEX ix_voice_foundry_operations_task_status
ON voice_foundry_operations(task_id,status,updated_at);

CREATE TABLE voice_foundry_commands(
    command_id TEXT PRIMARY KEY CHECK(length(command_id)>0 AND length(command_id)<=256),
    task_id TEXT NOT NULL REFERENCES voice_foundry_tasks(task_id) ON DELETE RESTRICT,
    payload_digest TEXT NOT NULL CHECK(length(payload_digest)=64),
    accepted_result_json TEXT NOT NULL CHECK(length(accepted_result_json)<=1048576),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE voice_evidence_snapshots(
    provider_instance TEXT NOT NULL CHECK(length(provider_instance)>0 AND length(provider_instance)<=256),
    evidence_id TEXT NOT NULL CHECK(length(evidence_id)>0 AND length(evidence_id)<=256),
    evidence_digest TEXT NOT NULL CHECK(length(evidence_digest)=64),
    voice_id TEXT NOT NULL CHECK(length(voice_id)>0 AND length(voice_id)<=256),
    voice_revision TEXT NOT NULL CHECK(length(voice_revision)>0 AND length(voice_revision)<=256),
    snapshot_json TEXT NOT NULL CHECK(length(snapshot_json)>0 AND length(snapshot_json)<=1048576),
    created_at TEXT NOT NULL,
    PRIMARY KEY(provider_instance,evidence_id,evidence_digest)
) STRICT;

ALTER TABLE voice_bindings ADD COLUMN evidence_id TEXT
    CHECK(evidence_id IS NULL OR length(evidence_id)<=256);
ALTER TABLE voice_bindings ADD COLUMN evidence_digest TEXT
    CHECK(evidence_digest IS NULL OR length(evidence_digest)=64);

CREATE TABLE voice_binding_revisions(
    binding_id TEXT NOT NULL CHECK(length(binding_id)>0 AND length(binding_id)<=256),
    binding_revision INTEGER NOT NULL CHECK(binding_revision>=1),
    owner_id TEXT NOT NULL CHECK(length(owner_id)>0 AND length(owner_id)<=256),
    world_id TEXT NOT NULL CHECK(length(world_id)>0 AND length(world_id)<=256),
    worldline_id TEXT NOT NULL CHECK(length(worldline_id)>0 AND length(worldline_id)<=256),
    presentation_identity TEXT NOT NULL CHECK(length(presentation_identity)>0 AND length(presentation_identity)<=256),
    phase TEXT NOT NULL CHECK(length(phase)>0 AND length(phase)<=256),
    locale TEXT NOT NULL CHECK(length(locale)>0 AND length(locale)<=35),
    logical_voice_id TEXT NOT NULL CHECK(length(logical_voice_id)>0 AND length(logical_voice_id)<=256),
    persona_revision TEXT NOT NULL CHECK(length(persona_revision)>0 AND length(persona_revision)<=256),
    provider_instance TEXT NOT NULL CHECK(length(provider_instance)>0 AND length(provider_instance)<=256),
    provider_voice_id TEXT NOT NULL CHECK(length(provider_voice_id)>0 AND length(provider_voice_id)<=256),
    voice_revision TEXT NOT NULL CHECK(length(voice_revision)>0 AND length(voice_revision)<=256),
    model_catalog_revision TEXT CHECK(
        model_catalog_revision IS NULL OR length(model_catalog_revision)<=256
    ),
    evidence_id TEXT CHECK(evidence_id IS NULL OR length(evidence_id)<=256),
    evidence_digest TEXT CHECK(evidence_digest IS NULL OR length(evidence_digest)=64),
    qualification TEXT NOT NULL CHECK(qualification IN ('qualified','unevaluated')),
    status TEXT NOT NULL CHECK(status IN ('reserved','active','revoked')),
    reserved_at_world_revision INTEGER NOT NULL CHECK(reserved_at_world_revision>=0),
    recorded_at TEXT NOT NULL,
    PRIMARY KEY(binding_id,binding_revision),
    CHECK(
        (qualification='qualified' AND evidence_id IS NOT NULL AND evidence_digest IS NOT NULL)
        OR
        (qualification='unevaluated' AND evidence_id IS NULL AND evidence_digest IS NULL)
    )
) STRICT;

INSERT OR IGNORE INTO voice_binding_revisions(
    binding_id,binding_revision,owner_id,world_id,worldline_id,
    presentation_identity,phase,locale,logical_voice_id,persona_revision,
    provider_instance,provider_voice_id,voice_revision,model_catalog_revision,
    evidence_id,evidence_digest,qualification,status,
    reserved_at_world_revision,recorded_at
)
SELECT
    binding_id,binding_revision,owner_id,world_id,worldline_id,
    presentation_identity,phase,locale,logical_voice_id,persona_revision,
    provider_instance,provider_voice_id,voice_revision,model_catalog_revision,
    NULL,NULL,'unevaluated',status,reserved_at_world_revision,
    strftime('%Y-%m-%dT%H:%M:%fZ','now')
FROM voice_bindings;
