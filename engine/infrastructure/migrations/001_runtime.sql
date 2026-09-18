-- Diagnostics remain in a separate file, never the authoritative commit store.
CREATE TABLE runtime_metadata (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL CHECK (json_valid(value_json))
) STRICT;
