-- Hybrid RAG: pgvector enablement + ANN index
-- Safe to run multiple times.

CREATE EXTENSION IF NOT EXISTS vector;

-- If embedding was created as TEXT previously, convert it to vector(1536).
-- Existing NULL / empty values stay NULL.
ALTER TABLE rag_documents
ALTER COLUMN embedding TYPE vector(1536)
USING CASE
  WHEN embedding IS NULL THEN NULL
  WHEN trim(embedding::text) = '' THEN NULL
  ELSE embedding::vector(1536)
END;

CREATE INDEX IF NOT EXISTS rag_documents_embedding_hnsw_idx
ON rag_documents
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 200);

-- Query-time default can be tuned per session/workload.
-- Larger ef_search -> better recall, higher latency.
SET hnsw.ef_search = 100;
