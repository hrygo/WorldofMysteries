CREATE TABLE audio_takes(
    take_id TEXT PRIMARY KEY,
    render_key TEXT NOT NULL UNIQUE CHECK(length(render_key)=64),
    relative_path TEXT NOT NULL UNIQUE,
    file_sha256 TEXT NOT NULL CHECK(length(file_sha256)=64),
    codec TEXT NOT NULL CHECK(codec='pcm_s16le'),
    sample_rate INTEGER NOT NULL CHECK(sample_rate=24000),
    channels INTEGER NOT NULL CHECK(channels=1),
    sample_count INTEGER NOT NULL CHECK(sample_count>0),
    byte_count INTEGER NOT NULL CHECK(byte_count=sample_count*2),
    duration_ms INTEGER NOT NULL CHECK(duration_ms>=0),
    manifest_json TEXT NOT NULL,
    manifest_hmac TEXT NOT NULL CHECK(length(manifest_hmac)=64),
    status TEXT NOT NULL CHECK(status='complete')
) STRICT;
