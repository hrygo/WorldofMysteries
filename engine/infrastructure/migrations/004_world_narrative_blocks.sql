-- Post-COMMIT NarrativeBlock expression persistence for W-V05 audio disclosure.
-- Narrative output is durable but is not a new world fact revision.
CREATE TABLE narrative_blocks (
    id TEXT PRIMARY KEY CHECK (length(id) > 0),
    turn_id TEXT NOT NULL UNIQUE
        REFERENCES turn_transactions(id) DEFERRABLE INITIALLY DEFERRED,
    session_id TEXT NOT NULL
        REFERENCES story_sessions(id) DEFERRABLE INITIALLY DEFERRED,
    source_story_revision INTEGER NOT NULL CHECK (source_story_revision >= 0),
    source_state_delta_id TEXT NOT NULL
        REFERENCES story_state_deltas(id) DEFERRABLE INITIALLY DEFERRED,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;

CREATE INDEX ix_narrative_blocks_session_revision
ON narrative_blocks(session_id, source_story_revision);
