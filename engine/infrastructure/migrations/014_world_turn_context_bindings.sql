-- Minimal, immutable provenance for each authorized turn-context stage.
-- Context bodies and credentials stay outside world.db.
CREATE TABLE turn_context_bindings(
    turn_id TEXT NOT NULL CHECK(length(turn_id)>0 AND length(turn_id)<=256),
    stage TEXT NOT NULL CHECK(stage IN ('interpretation','action','narrative')),
    context_revision TEXT NOT NULL CHECK(length(context_revision)=64),
    input_turn_id TEXT NOT NULL
        REFERENCES turn_intake_commands(input_turn_id) ON DELETE RESTRICT,
    source_store_revision INTEGER NOT NULL CHECK(source_store_revision>=0),
    source_story_revision INTEGER NOT NULL CHECK(source_story_revision>=0),
    policy_revision TEXT NOT NULL CHECK(length(policy_revision)>0 AND length(policy_revision)<=256),
    content_digest TEXT NOT NULL CHECK(length(content_digest)>0 AND length(content_digest)<=256),
    lineage_digest TEXT NOT NULL CHECK(length(lineage_digest)>0 AND length(lineage_digest)<=256),
    manifest_json TEXT NOT NULL CHECK(length(manifest_json)>0 AND length(manifest_json)<=1048576),
    manifest_digest TEXT NOT NULL CHECK(length(manifest_digest)=64),
    PRIMARY KEY(turn_id,stage,context_revision),
    FOREIGN KEY(turn_id)
        REFERENCES turn_advice_interpretations(turn_id) ON DELETE RESTRICT
) STRICT;

CREATE INDEX ix_turn_context_bindings_input_stage
ON turn_context_bindings(input_turn_id,stage);
