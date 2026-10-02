-- W-V05 the listening review that authorises a voice binding.
-- evidence_id / evidence_digest arrived with 015; model_artifact_revision
-- completes the triple, because the artifact a human heard is a different
-- fact from the catalogue entry that merely offers it.
--
-- All three stay nullable. A binding may be reserved before it is reviewed,
-- and every row written before the evidence rollout must keep loading.
ALTER TABLE voice_bindings ADD COLUMN model_artifact_revision TEXT
    CHECK(model_artifact_revision IS NULL OR length(model_artifact_revision)<=256);
