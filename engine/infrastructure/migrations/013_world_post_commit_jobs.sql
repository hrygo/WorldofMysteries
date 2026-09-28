-- Durable post-COMMIT work scheduling and immutable result records.
-- This migration only creates schema; historical reconciliation is performed separately.
CREATE TABLE post_commit_jobs (
    job_id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES turn_transactions(id),
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN (
        'episode_finalize','narrative_publish','audio_prepare'
    )),
    recipe_revision TEXT NOT NULL,
    source_story_revision INTEGER NOT NULL,
    source_world_revision INTEGER NOT NULL,
    input_digest TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'pending','running','retry_wait','blocked','succeeded'
    )),
    attempt INTEGER NOT NULL DEFAULT 0,
    lease_owner TEXT,
    lease_generation INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    last_error_code TEXT,
    result_ref TEXT,
    UNIQUE(turn_id, kind, recipe_revision)
) STRICT;

CREATE TABLE post_commit_retry_requests (
    request_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES post_commit_jobs(job_id)
) STRICT;

CREATE TABLE post_commit_job_results (
    job_id TEXT PRIMARY KEY REFERENCES post_commit_jobs(job_id),
    format_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_digest TEXT NOT NULL
) STRICT;
