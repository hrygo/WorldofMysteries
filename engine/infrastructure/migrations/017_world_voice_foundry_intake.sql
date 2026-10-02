-- W-V01 declared the execution scope and the budget on every cast request.
-- Neither had anywhere to land: the task row could not hold them, so an
-- intake handler had either to drop them silently or refuse every request.
-- Dropping a declared budget is the same defect class as the empty
-- validation digest — the caller is told a limit was honoured when nothing
-- ever read it.
--
-- execution_model_id / execution_model_artifact_revision stay nullable
-- because the contract makes them nullable: "whatever this provider serves"
-- is an expressible request, and it is the honest answer for a deployment
-- that has not pinned a model. execution_variant is not nullable, so a row
-- always says which rendering path was asked for.
--
-- Defaults match what the engine was already doing unasked
-- (MAX_CANDIDATES, the 120s retry deadline, MAX_ASSET_BYTES), so every row
-- written before this rollout keeps describing itself truthfully.
ALTER TABLE voice_foundry_tasks ADD COLUMN execution_model_id TEXT
    CHECK(execution_model_id IS NULL OR length(execution_model_id)<=256);

ALTER TABLE voice_foundry_tasks ADD COLUMN execution_model_artifact_revision TEXT
    CHECK(execution_model_artifact_revision IS NULL
          OR length(execution_model_artifact_revision)<=256);

ALTER TABLE voice_foundry_tasks ADD COLUMN execution_variant TEXT NOT NULL
    DEFAULT 'default'
    CHECK(length(execution_variant)>0 AND length(execution_variant)<=256);

ALTER TABLE voice_foundry_tasks ADD COLUMN budget_candidate_count INTEGER NOT NULL
    DEFAULT 4 CHECK(budget_candidate_count BETWEEN 1 AND 4);

ALTER TABLE voice_foundry_tasks ADD COLUMN budget_timeout_ms INTEGER NOT NULL
    DEFAULT 120000 CHECK(budget_timeout_ms BETWEEN 1000 AND 3600000);

ALTER TABLE voice_foundry_tasks ADD COLUMN budget_max_audio_bytes INTEGER NOT NULL
    DEFAULT 16777216 CHECK(budget_max_audio_bytes BETWEEN 1 AND 134217728);
