-- Supabase migration — RAG split-path refactor
-- Run once against production. Idempotent; safe to replay.
--
-- Changes:
--   1. chat_history.retrieved_chunk_ids  → JSONB (was BIGINT[] under legacy pgvector path)
--   2. Drop stale pgvector tables if they exist (kb_chunks, rag_documents)
--   3. No new tables are required — file-based BM25 lives in-process and reads
--      from rag_docs/*.md on disk, not the DB.
--
-- There is NOTHING to persist for retrieval other than the audit column above.

BEGIN;

-- 1) Convert retrieved_chunk_ids to JSONB only if the existing type is wrong.
--    Keeps existing JSONB rows (and their content) intact once migrated.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'chat_history'
          AND column_name = 'retrieved_chunk_ids'
          AND data_type <> 'jsonb'
    ) THEN
        ALTER TABLE chat_history DROP COLUMN retrieved_chunk_ids;
    END IF;
END $$;

ALTER TABLE chat_history
    ADD COLUMN IF NOT EXISTS retrieved_chunk_ids JSONB;

-- Optional: document the format. Values are JSON arrays of file-based chunk refs,
-- e.g. ["routines:0:abc123def456", "rag_docs/skinmax/routines.md::PM routine"].
COMMENT ON COLUMN chat_history.retrieved_chunk_ids IS
    'RAG audit trail. JSON array of file-based chunk IDs (doc_title:chunk_index:sha1) '
    'or fallback source::section refs. NULL when no retrieval ran for the turn.';

-- 2) Purge legacy pgvector tables — no code references them after the refactor.
DROP TABLE IF EXISTS kb_chunks CASCADE;
DROP TABLE IF EXISTS rag_documents CASCADE;

COMMIT;
