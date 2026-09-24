CREATE TABLE delivery_cursors(
    track_id TEXT NOT NULL,
    consumer_id TEXT NOT NULL,
    unit_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK(generation >= 0),
    source_offset_frames INTEGER NOT NULL CHECK(source_offset_frames >= 0),
    total_source_frames INTEGER CHECK(total_source_frames IS NULL OR total_source_frames > 0),
    evidence TEXT NOT NULL CHECK(evidence IN ('queued','scheduled','rendered_estimate','measured_loopback')),
    stop_reason TEXT CHECK(stop_reason IS NULL OR stop_reason IN (
        'user_stop','superseded','device_route_change','suspend',
        'provider_error','media_error','completed'
    )),
    cursor_revision INTEGER NOT NULL CHECK(cursor_revision >= 1),
    PRIMARY KEY(track_id, consumer_id),
    CHECK(total_source_frames IS NULL OR source_offset_frames <= total_source_frames)
) STRICT;

CREATE INDEX idx_delivery_cursors_unit
ON delivery_cursors(unit_id);
