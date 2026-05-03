-- Tables backing the new max-doc system.
-- Run after the existing rag_documents/pgvector setup is in place.

-- 1) task_catalog: atomic, scheduler-pickable tasks per max.
--    The schedule generator chooses task IDs from this table; never invents tasks.
CREATE TABLE IF NOT EXISTS task_catalog (
    id                  TEXT PRIMARY KEY,                -- e.g. "skin.cleanse_am"
    maxx_id             TEXT NOT NULL,                   -- skinmax/hairmax/heightmax/...
    title               TEXT NOT NULL,                   -- ≤28 chars (validator enforces)
    description         TEXT NOT NULL,
    duration_min        INTEGER NOT NULL DEFAULT 5,
    default_window      TEXT NOT NULL,                   -- am_open|am_active|midday|pm_active|pm_close|flexible
    tags                JSONB NOT NULL DEFAULT '[]'::jsonb,
    applies_when        JSONB NOT NULL DEFAULT '[]'::jsonb,    -- list of expressions
    contraindicated_when JSONB NOT NULL DEFAULT '[]'::jsonb,
    intensity           REAL NOT NULL DEFAULT 0.3,       -- 0..1
    evidence_section    TEXT,                            -- citation for retrieval
    cooldown_hours      INTEGER NOT NULL DEFAULT 0,
    frequency           JSONB NOT NULL DEFAULT '{"type":"daily","n":1}'::jsonb,
    source_doc          TEXT NOT NULL,                   -- "data/maxes/skinmax.md"
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS task_catalog_maxx_idx ON task_catalog(maxx_id);

-- 2) max_doc_meta: per-max front-matter (schedule_design + required_fields + modifiers).
--    Stored as JSONB for fast load + zero schema churn when content evolves.
CREATE TABLE IF NOT EXISTS max_doc_meta (
    maxx_id             TEXT PRIMARY KEY,
    display_name        TEXT NOT NULL,
    short_description   TEXT,
    schedule_design     JSONB NOT NULL DEFAULT '{}'::jsonb,
    required_fields     JSONB NOT NULL DEFAULT '[]'::jsonb,
    optional_context    JSONB NOT NULL DEFAULT '[]'::jsonb,
    prompt_modifiers    JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_doc          TEXT NOT NULL,
    content_hash        TEXT NOT NULL,                   -- sha256 of source — used for skip-on-unchanged ingest
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3) user_schedule_context: persistent per-user facts that influence future generations.
--    Single row per user; the value is a JSONB blob the chat agent updates
--    via the update_schedule_context tool whenever it learns something
--    relevant (product preferences, frictions, equipment owned, dislikes).
CREATE TABLE IF NOT EXISTS user_schedule_context (
    user_id             UUID PRIMARY KEY,
    context             JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Helper for atomic JSONB merges from Python.
-- Usage: INSERT ... ON CONFLICT (user_id) DO UPDATE SET context = user_schedule_context.context || EXCLUDED.context.

-- 4) schedule_generation_log: lightweight audit trail of generations + tweaks.
--    Used to compute "user immediately re-tweaks" signal for prompt evals.
CREATE TABLE IF NOT EXISTS schedule_generation_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    schedule_id         UUID,
    maxx_id             TEXT NOT NULL,
    op                  TEXT NOT NULL,                   -- "generate" | "adapt"
    elapsed_ms          INTEGER NOT NULL,
    task_count          INTEGER,
    validator_retries   INTEGER NOT NULL DEFAULT 0,
    feedback            TEXT,                            -- adapter input
    diff_ops            JSONB,                           -- adapter output (if op=adapt)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS schedule_gen_log_user_idx ON schedule_generation_log(user_id, created_at DESC);
