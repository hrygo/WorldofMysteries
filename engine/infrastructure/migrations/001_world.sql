-- Infrastructure journal only. Typed domain repositories own their own tables.
CREATE TABLE world_meta (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    store_id TEXT NOT NULL UNIQUE,
    revision INTEGER NOT NULL CHECK (revision >= 0)
) STRICT;
CREATE TABLE domain_commits (
    revision INTEGER PRIMARY KEY CHECK (revision > 0),
    worldline_id TEXT NOT NULL CHECK (length(worldline_id) > 0),
    idempotency_key TEXT NOT NULL UNIQUE,
    request_digest TEXT NOT NULL,
    request_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    world_time TEXT NOT NULL,
    commit_time TEXT NOT NULL,
    operation_json TEXT NOT NULL CHECK (json_valid(operation_json)),
    result_json TEXT NOT NULL CHECK (json_valid(result_json))
) STRICT;
CREATE TABLE domain_events (
    event_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL REFERENCES domain_commits(revision),
    worldline_id TEXT NOT NULL,
    world_time TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    cause_id TEXT,
    episode_id TEXT,
    turn_id TEXT,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;
CREATE INDEX ix_domain_events_lineage ON domain_events(worldline_id, revision, event_id);
CREATE TABLE projection_outbox (
    revision INTEGER PRIMARY KEY REFERENCES domain_commits(revision),
    processed INTEGER NOT NULL DEFAULT 0 CHECK (processed IN (0, 1))
) STRICT;
CREATE INDEX ix_projection_outbox_pending ON projection_outbox(revision) WHERE processed = 0;
