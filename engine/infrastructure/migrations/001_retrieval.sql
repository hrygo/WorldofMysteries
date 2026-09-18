-- Disposable event projection. Not an authorization engine or a fact source.
CREATE TABLE projection_meta (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    store_id TEXT NOT NULL,
    last_indexed_revision INTEGER NOT NULL CHECK (last_indexed_revision >= 0)
) STRICT;
CREATE TABLE projected_events (
    event_id TEXT PRIMARY KEY,
    source_revision INTEGER NOT NULL CHECK (source_revision > 0),
    worldline_id TEXT NOT NULL,
    world_time TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    cause_id TEXT,
    episode_id TEXT,
    turn_id TEXT,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
) STRICT;
CREATE INDEX ix_projected_events_scope ON projected_events(worldline_id, source_revision);
