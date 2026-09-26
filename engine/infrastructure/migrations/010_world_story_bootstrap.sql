-- Trusted Golden opening bootstrap and public intake CAS provenance.
-- Bootstrap content is immutable command provenance bound to the same domain
-- commit that created the Story Session; it never mutates Canon or world facts.
ALTER TABLE turn_intake_commands
ADD COLUMN public_expected_store_revision INTEGER
    CHECK(
        public_expected_store_revision IS NULL
        OR public_expected_store_revision>=0
    );

CREATE TABLE story_session_bootstraps(
    session_id TEXT PRIMARY KEY
        REFERENCES story_sessions(id) DEFERRABLE INITIALLY DEFERRED,
    scenario_id TEXT NOT NULL CHECK(length(scenario_id)>0),
    content_version TEXT NOT NULL CHECK(length(content_version)>0),
    content_digest TEXT NOT NULL
        CHECK(
            length(content_digest)=64
            AND content_digest NOT GLOB '*[^0-9a-f]*'
        ),
    bootstrap_json TEXT NOT NULL
        CHECK(
            json_valid(bootstrap_json)
            AND length(bootstrap_json)>0
            AND length(bootstrap_json)<=1048576
        ),
    opened_store_revision INTEGER NOT NULL
        REFERENCES domain_commits(revision) DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE INDEX ix_story_session_bootstraps_scenario
ON story_session_bootstraps(scenario_id, content_version);
