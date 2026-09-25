-- W-V08 immutable StoryBook audio track revisions and take pins.
CREATE TABLE audio_tracks(
    track_id TEXT PRIMARY KEY CHECK(length(track_id)>0),
    track_family_id TEXT NOT NULL CHECK(length(track_family_id)>0),
    story_session_id TEXT NOT NULL
        REFERENCES story_sessions(id) DEFERRABLE INITIALLY DEFERRED,
    revision INTEGER NOT NULL CHECK(revision>=1),
    kind TEXT NOT NULL CHECK(kind IN ('original','redub')),
    supersedes_track_id TEXT
        REFERENCES audio_tracks(track_id) DEFERRABLE INITIALLY DEFERRED,
    UNIQUE(track_family_id, revision),
    UNIQUE(supersedes_track_id),
    CHECK(
        (revision=1 AND kind='original' AND supersedes_track_id IS NULL)
        OR
        (revision>1 AND kind='redub' AND supersedes_track_id IS NOT NULL)
    )
) STRICT;

CREATE TABLE audio_track_units(
    track_id TEXT NOT NULL
        REFERENCES audio_tracks(track_id) DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal>=0),
    unit_id TEXT NOT NULL CHECK(length(unit_id)>0),
    turn_id TEXT NOT NULL
        REFERENCES turn_transactions(id) DEFERRABLE INITIALLY DEFERRED,
    narrative_block_id TEXT NOT NULL
        REFERENCES narrative_blocks(id) DEFERRABLE INITIALLY DEFERRED,
    segment_index INTEGER NOT NULL CHECK(segment_index>=0),
    story_revision INTEGER NOT NULL CHECK(story_revision>=0),
    take_id TEXT NOT NULL
        REFERENCES audio_takes(take_id) DEFERRABLE INITIALLY DEFERRED,
    PRIMARY KEY(track_id, ordinal),
    UNIQUE(track_id, unit_id),
    UNIQUE(track_id, narrative_block_id, segment_index)
) STRICT;

CREATE INDEX ix_audio_track_units_take
ON audio_track_units(take_id);

CREATE INDEX ix_audio_tracks_story_session
ON audio_tracks(story_session_id, track_family_id, revision);
