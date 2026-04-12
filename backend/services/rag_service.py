"""
RAG retrieval service — semantic search over rag_documents (Supabase pgvector).

Retrieval uses raw async SQL with asyncpg-safe string embedding format:
  embedding <=> CAST(:embedding AS vector)
This avoids asyncpg OID registration issues and works with the existing
async session pool without any additional codec setup.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import text

logger = logging.getLogger(__name__)

VALID_MAXX_IDS = frozenset({"skinmax", "fitmax", "hairmax", "heightmax", "bonemax"})

_embedder = None


def get_embedder():
    """Return a singleton OpenAIEmbeddings instance (lazy init)."""
    global _embedder
    if _embedder is None:
        try:
            from langchain_openai import OpenAIEmbeddings
            from config import settings
            if not getattr(settings, "openai_api_key", None):
                raise ValueError("OPENAI_API_KEY not configured — RAG embeddings unavailable")
            _embedder = OpenAIEmbeddings(
                model="text-embedding-3-small",
                openai_api_key=settings.openai_api_key,
            )
        except Exception as e:
            logger.warning("RAG embedder init failed: %s", e)
            raise
    return _embedder


async def embed_text(text_input: str) -> list[float]:
    """Embed a single string. Wraps the sync OpenAI call in a thread."""
    embedder = get_embedder()
    result = await asyncio.to_thread(embedder.embed_query, text_input)
    return result


def _vec_to_pg_str(vec: list[float]) -> str:
    """Convert a float list to pgvector's '[0.1,0.2,...]' literal format."""
    return "[" + ",".join(str(v) for v in vec) + "]"


async def retrieve_chunks(
    db: "AsyncSession",
    maxx_id: str,
    query: str,
    k: int = 4,
    min_similarity: float = 0.35,
) -> list[dict]:
    """
    Retrieve top-k semantically similar chunks for the given maxx_id namespace.

    Only returns chunks with cosine similarity >= min_similarity (default 0.35).
    This prevents injecting low-relevance content for greetings like "hi" even
    when a maxx_id is inferred from an active schedule.

    Returns a list of dicts: [{content, doc_title, chunk_index, similarity}, ...]
    Returns [] if maxx_id is unknown, query is blank, or no docs have been ingested.
    Falls back to [] (not raises) on any error so callers can degrade gracefully.
    """
    if not query or not query.strip():
        return []
    if maxx_id not in VALID_MAXX_IDS:
        return []

    try:
        query_vec = await embed_text(query.strip())
        vec_str = _vec_to_pg_str(query_vec)

        sql = text("""
            SELECT
                content,
                doc_title,
                chunk_index,
                metadata,
                1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM rag_documents
            WHERE maxx_id = :maxx_id
              AND 1 - (embedding <=> CAST(:embedding AS vector)) >= :min_sim
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :k
        """)
        rows = await db.execute(sql, {
            "embedding": vec_str,
            "maxx_id": maxx_id,
            "k": k,
            "min_sim": min_similarity,
        })
        results = rows.mappings().all()
        return [dict(r) for r in results]

    except Exception as e:
        logger.warning("RAG retrieve_chunks failed (maxx=%s): %s", maxx_id, e)
        return []
