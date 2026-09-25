-- Durable pre-COMMIT input identity for W-V09 real-turn orchestration.
-- This table is command/recovery state, not world fact state. RECEIVED/CANCELLED
-- do not advance world_meta; COMMITTED is linked to the Domain commit that won.
CREATE TABLE turn_intake_commands(
    input_turn_id TEXT PRIMARY KEY CHECK(length(input_turn_id)>0),
    session_id TEXT NOT NULL CHECK(length(session_id)>0),
    turn_id TEXT NOT NULL UNIQUE CHECK(length(turn_id)>0),
    idempotency_key TEXT NOT NULL UNIQUE CHECK(length(idempotency_key)>0),
    input_mode TEXT NOT NULL CHECK(input_mode IN ('voice','text','suggestion')),
    raw_input TEXT NOT NULL CHECK(length(raw_input)>0 AND length(raw_input)<=16384),
    input_sha256 TEXT NOT NULL CHECK(length(input_sha256)=64),
    base_world_revision INTEGER NOT NULL CHECK(base_world_revision>=0),
    base_character_revision INTEGER NOT NULL CHECK(base_character_revision>=0),
    base_story_revision INTEGER NOT NULL CHECK(base_story_revision>=0),
    status TEXT NOT NULL CHECK(status IN ('received','cancelled','committed')),
    committed_world_revision INTEGER
        REFERENCES domain_commits(revision) DEFERRABLE INITIALLY DEFERRED,
    CHECK(
        (status='committed' AND committed_world_revision IS NOT NULL)
        OR
        (status IN ('received','cancelled') AND committed_world_revision IS NULL)
    )
) STRICT;

CREATE INDEX ix_turn_intake_session_status
ON turn_intake_commands(session_id,status);
