-- Immutable cross-domain turn evidence and atomic Episode finalization.
-- Every row remains in world.db and is committed with its Domain revision.
CREATE TABLE turn_character_changes(
    id TEXT PRIMARY KEY CHECK(length(id)>0),
    session_id TEXT NOT NULL REFERENCES story_sessions(id),
    turn_id TEXT NOT NULL REFERENCES turn_transactions(id),
    state_delta_id TEXT NOT NULL REFERENCES story_state_deltas(id),
    ordinal INTEGER NOT NULL CHECK(ordinal>=0),
    character_id TEXT NOT NULL CHECK(length(character_id)>0),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    committed_world_revision INTEGER NOT NULL
        REFERENCES domain_commits(revision) DEFERRABLE INITIALLY DEFERRED,
    UNIQUE(state_delta_id, ordinal)
) STRICT;
CREATE INDEX ix_turn_character_changes_character
ON turn_character_changes(session_id, character_id, committed_world_revision);

CREATE TABLE turn_relationship_changes(
    id TEXT PRIMARY KEY CHECK(length(id)>0),
    session_id TEXT NOT NULL REFERENCES story_sessions(id),
    turn_id TEXT NOT NULL REFERENCES turn_transactions(id),
    state_delta_id TEXT NOT NULL REFERENCES story_state_deltas(id),
    ordinal INTEGER NOT NULL CHECK(ordinal>=0),
    from_character_id TEXT NOT NULL CHECK(length(from_character_id)>0),
    to_character_id TEXT NOT NULL CHECK(length(to_character_id)>0),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    committed_world_revision INTEGER NOT NULL
        REFERENCES domain_commits(revision) DEFERRABLE INITIALLY DEFERRED,
    UNIQUE(state_delta_id, ordinal)
) STRICT;
CREATE INDEX ix_turn_relationship_changes_pair
ON turn_relationship_changes(session_id, from_character_id, to_character_id, committed_world_revision);

CREATE TABLE turn_knowledge_changes(
    id TEXT PRIMARY KEY CHECK(length(id)>0),
    session_id TEXT NOT NULL REFERENCES story_sessions(id),
    turn_id TEXT NOT NULL REFERENCES turn_transactions(id),
    state_delta_id TEXT NOT NULL REFERENCES story_state_deltas(id),
    ordinal INTEGER NOT NULL CHECK(ordinal>=0),
    character_id TEXT NOT NULL CHECK(length(character_id)>0),
    proposition_id TEXT NOT NULL CHECK(length(proposition_id)>0),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    committed_world_revision INTEGER NOT NULL
        REFERENCES domain_commits(revision) DEFERRABLE INITIALLY DEFERRED,
    UNIQUE(state_delta_id, ordinal)
) STRICT;
CREATE INDEX ix_turn_knowledge_changes_subject
ON turn_knowledge_changes(session_id, character_id, proposition_id, committed_world_revision);

CREATE TABLE turn_world_events(
    id TEXT PRIMARY KEY CHECK(length(id)>0),
    session_id TEXT NOT NULL REFERENCES story_sessions(id),
    turn_id TEXT NOT NULL REFERENCES turn_transactions(id),
    state_delta_id TEXT NOT NULL REFERENCES story_state_deltas(id),
    ordinal INTEGER NOT NULL CHECK(ordinal>=0),
    event_type TEXT NOT NULL CHECK(length(event_type)>0),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    committed_world_revision INTEGER NOT NULL
        REFERENCES domain_commits(revision) DEFERRABLE INITIALLY DEFERRED,
    UNIQUE(state_delta_id, ordinal)
) STRICT;
CREATE INDEX ix_turn_world_events_type
ON turn_world_events(session_id, event_type, committed_world_revision);

CREATE TABLE episodes(
    id TEXT PRIMARY KEY CHECK(length(id)>0),
    world_id TEXT NOT NULL CHECK(length(world_id)>0),
    worldline_id TEXT NOT NULL CHECK(length(worldline_id)>0),
    session_id TEXT NOT NULL UNIQUE REFERENCES story_sessions(id),
    story_seed_id TEXT,
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    committed_world_revision INTEGER NOT NULL
        REFERENCES domain_commits(revision) DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE INDEX ix_episodes_worldline
ON episodes(worldline_id, committed_world_revision);

CREATE TABLE episode_character_events(
    episode_id TEXT NOT NULL REFERENCES episodes(id),
    artifact_id TEXT NOT NULL CHECK(length(artifact_id)>0),
    ordinal INTEGER NOT NULL CHECK(ordinal>=0),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    committed_world_revision INTEGER NOT NULL
        REFERENCES domain_commits(revision) DEFERRABLE INITIALLY DEFERRED,
    PRIMARY KEY(episode_id, artifact_id)
) STRICT;

CREATE TABLE episode_relationship_events(
    episode_id TEXT NOT NULL REFERENCES episodes(id),
    artifact_id TEXT NOT NULL CHECK(length(artifact_id)>0),
    ordinal INTEGER NOT NULL CHECK(ordinal>=0),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    committed_world_revision INTEGER NOT NULL
        REFERENCES domain_commits(revision) DEFERRABLE INITIALLY DEFERRED,
    PRIMARY KEY(episode_id, artifact_id)
) STRICT;

CREATE TABLE episode_knowledge_changes(
    episode_id TEXT NOT NULL REFERENCES episodes(id),
    artifact_id TEXT NOT NULL CHECK(length(artifact_id)>0),
    ordinal INTEGER NOT NULL CHECK(ordinal>=0),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    committed_world_revision INTEGER NOT NULL
        REFERENCES domain_commits(revision) DEFERRABLE INITIALLY DEFERRED,
    PRIMARY KEY(episode_id, artifact_id)
) STRICT;

CREATE TABLE character_episode_memories(
    episode_id TEXT NOT NULL REFERENCES episodes(id),
    artifact_id TEXT NOT NULL CHECK(length(artifact_id)>0),
    ordinal INTEGER NOT NULL CHECK(ordinal>=0),
    character_id TEXT NOT NULL CHECK(length(character_id)>0),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    committed_world_revision INTEGER NOT NULL
        REFERENCES domain_commits(revision) DEFERRABLE INITIALLY DEFERRED,
    PRIMARY KEY(episode_id, artifact_id)
) STRICT;
CREATE INDEX ix_character_episode_memories_character
ON character_episode_memories(character_id, episode_id);

CREATE TABLE episode_world_events(
    episode_id TEXT NOT NULL REFERENCES episodes(id),
    artifact_id TEXT NOT NULL CHECK(length(artifact_id)>0),
    ordinal INTEGER NOT NULL CHECK(ordinal>=0),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    committed_world_revision INTEGER NOT NULL
        REFERENCES domain_commits(revision) DEFERRABLE INITIALLY DEFERRED,
    PRIMARY KEY(episode_id, artifact_id)
) STRICT;

CREATE TABLE episode_finalizations(
    episode_id TEXT PRIMARY KEY REFERENCES episodes(id),
    idempotency_key TEXT NOT NULL UNIQUE CHECK(length(idempotency_key)>0),
    request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
    committed_world_revision INTEGER NOT NULL UNIQUE
        REFERENCES domain_commits(revision) DEFERRABLE INITIALLY DEFERRED
) STRICT;
