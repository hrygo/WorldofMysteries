-- W-V04 durable presentation voice bindings.
-- Presentation revisions are stored in world.db but do not advance world_meta.revision.
CREATE TABLE voice_bindings (
    binding_id TEXT PRIMARY KEY CHECK (length(binding_id) > 0),
    owner_id TEXT NOT NULL CHECK (length(owner_id) > 0),
    world_id TEXT NOT NULL CHECK (length(world_id) > 0),
    worldline_id TEXT NOT NULL CHECK (length(worldline_id) > 0),
    presentation_identity TEXT NOT NULL CHECK (length(presentation_identity) > 0),
    phase TEXT NOT NULL CHECK (length(phase) > 0),
    locale TEXT NOT NULL CHECK (length(locale) > 0),
    logical_voice_id TEXT NOT NULL CHECK (length(logical_voice_id) > 0),
    persona_revision TEXT NOT NULL CHECK (length(persona_revision) > 0),
    provider_instance TEXT NOT NULL CHECK (length(provider_instance) > 0),
    provider_voice_id TEXT NOT NULL CHECK (length(provider_voice_id) > 0),
    assurance TEXT NOT NULL CHECK (assurance IN ('legacy','content_addressed')),
    voice_revision TEXT,
    model_catalog_revision TEXT,
    provider_revoked INTEGER NOT NULL DEFAULT 0 CHECK (provider_revoked IN (0,1)),
    binding_revision INTEGER NOT NULL CHECK (binding_revision > 0),
    status TEXT NOT NULL CHECK (status IN ('reserved','active','revoked')),
    reserved_at_world_revision INTEGER NOT NULL CHECK (reserved_at_world_revision >= 0),
    CHECK (
        (assurance='legacy' AND voice_revision IS NULL)
        OR
        (assurance='content_addressed' AND voice_revision IS NOT NULL AND length(voice_revision) > 0)
    ),
    UNIQUE(owner_id, world_id, worldline_id, presentation_identity, phase, locale)
) STRICT;

CREATE INDEX ix_voice_bindings_worldline_status
ON voice_bindings(worldline_id, status, presentation_identity);
