-- Immutable pre-COMMIT PlayerAdvice interpretation for W-V09.
-- The first durable interpretation for an input_turn wins. This is command/evidence
-- state only and never advances world_meta or creates Domain events.
CREATE TABLE turn_advice_interpretations(
    input_turn_id TEXT PRIMARY KEY
        REFERENCES turn_intake_commands(input_turn_id) ON DELETE RESTRICT,
    advice_id TEXT NOT NULL UNIQUE CHECK(length(advice_id)>0),
    turn_id TEXT NOT NULL UNIQUE CHECK(length(turn_id)>0),
    input_sha256 TEXT NOT NULL CHECK(length(input_sha256)=64),
    interpreter_revision TEXT NOT NULL CHECK(length(interpreter_revision)>0),
    advice_sha256 TEXT NOT NULL CHECK(length(advice_sha256)=64),
    advice_json TEXT NOT NULL CHECK(length(advice_json)>0 AND length(advice_json)<=65536)
) STRICT;

CREATE INDEX ix_turn_advice_turn_id
ON turn_advice_interpretations(turn_id);
