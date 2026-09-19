-- Story Session durable overlay tables. Specialized Story Domain storage, not generic facts.
CREATE TABLE story_sessions (
    id TEXT PRIMARY KEY CHECK (length(id) > 0),
    world_id TEXT NOT NULL CHECK (length(world_id) > 0),
    worldline_id TEXT NOT NULL CHECK (length(worldline_id) > 0),
    protagonist_id TEXT NOT NULL CHECK (length(protagonist_id) > 0),
    story_seed_id TEXT NOT NULL CHECK (length(story_seed_id) > 0),
    base_world_revision INTEGER NOT NULL CHECK (base_world_revision >= 0),
    base_character_revision INTEGER NOT NULL CHECK (base_character_revision >= 0),
    base_story_revision INTEGER NOT NULL CHECK (base_story_revision >= 0),
    story_revision INTEGER NOT NULL CHECK (story_revision >= 0),
    status TEXT NOT NULL CHECK (status IN (
        'active','suspended','closing','finalized','cancelled','recovery_required'
    )),
    story_state_json TEXT NOT NULL CHECK (json_valid(story_state_json)),
    committed_world_revision INTEGER NOT NULL
        REFERENCES domain_commits(revision) DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE UNIQUE INDEX ux_story_sessions_open_worldline
ON story_sessions(worldline_id)
WHERE status IN ('active','suspended','closing','recovery_required');

CREATE TABLE story_state_deltas (
    id TEXT PRIMARY KEY CHECK (length(id) > 0),
    session_id TEXT NOT NULL REFERENCES story_sessions(id),
    turn_id TEXT NOT NULL CHECK (length(turn_id) > 0),
    story_revision INTEGER NOT NULL CHECK (story_revision > 0),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    committed_world_revision INTEGER NOT NULL
        REFERENCES domain_commits(revision) DEFERRABLE INITIALLY DEFERRED,
    UNIQUE(session_id, turn_id),
    UNIQUE(session_id, story_revision)
) STRICT;

CREATE TABLE turn_transactions (
    id TEXT PRIMARY KEY CHECK (length(id) > 0),
    session_id TEXT NOT NULL REFERENCES story_sessions(id),
    idempotency_key TEXT NOT NULL UNIQUE CHECK (length(idempotency_key) > 0),
    status TEXT NOT NULL CHECK (status IN (
        'received','interpreted','decided','resolved','validated','committed',
        'beat_ready','narrative_ready','audio_ready','delivered',
        'failed_retryable','failed_fatal','cancelled','reconcile_required'
    )),
    base_world_revision INTEGER NOT NULL CHECK (base_world_revision >= 0),
    base_character_revision INTEGER NOT NULL CHECK (base_character_revision >= 0),
    base_story_revision INTEGER NOT NULL CHECK (base_story_revision >= 0),
    player_advice_id TEXT,
    action_intent_id TEXT,
    state_delta_id TEXT REFERENCES story_state_deltas(id) DEFERRABLE INITIALLY DEFERRED,
    committed_story_revision INTEGER CHECK (committed_story_revision >= 0),
    narrative_block_id TEXT,
    transaction_json TEXT NOT NULL CHECK (json_valid(transaction_json)),
    committed_world_revision INTEGER
        REFERENCES domain_commits(revision) DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE INDEX ix_turn_transactions_session_status
ON turn_transactions(session_id, status, committed_story_revision);
