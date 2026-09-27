-- Durable post-COMMIT BeatPlan publication, bound to the committed turn.
-- Mirrors narrative_blocks: written only after authoritative COMMIT, unique per
-- turn, and replay-idempotent. Part of world.db authority, never retrieval.db.
CREATE TABLE beat_plans(
    id TEXT PRIMARY KEY CHECK(length(id)>0),
    turn_id TEXT NOT NULL UNIQUE REFERENCES turn_transactions(id),
    session_id TEXT NOT NULL REFERENCES story_sessions(id),
    source_story_revision INTEGER NOT NULL CHECK(source_story_revision>0),
    source_world_revision INTEGER NOT NULL CHECK(source_world_revision>0),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json))
) STRICT;
CREATE INDEX ix_beat_plans_session
ON beat_plans(session_id, source_story_revision);
