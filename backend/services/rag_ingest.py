"""
RAG ingestion pipeline — chunks, embeds, and upserts documents into rag_documents.

Used exclusively by the local ingestion script (scripts/ingest_rag_docs.py).
Each call is idempotent: old chunks for (maxx_id, doc_title) are deleted before insert.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import delete, text

from services.rag_service import VALID_MAXX_IDS, get_embedder, _vec_to_pg_str

logger = logging.getLogger(__name__)


async def ingest_doc(
    db: "AsyncSession",
    content: str,
    maxx_id: str,
    doc_title: str,
    source_file: str = "",
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> int:
    """
    Chunk, embed, and upsert a document into rag_documents.

    Returns the number of chunks inserted.
    Raises ValueError for invalid maxx_id.
    Raises on embedding or DB errors so the caller can surface them.
    """
    if maxx_id not in VALID_MAXX_IDS:
        raise ValueError(f"Unknown maxx_id '{maxx_id}'. Must be one of: {sorted(VALID_MAXX_IDS)}")
    if not content or not content.strip():
        raise ValueError(f"Document '{doc_title}' has empty content")

    # --- Split into chunks ---
    from langchain_text_splitters import MarkdownTextSplitter
    splitter = MarkdownTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    docs = splitter.create_documents([content])
    chunks = [d.page_content for d in docs if d.page_content.strip()]

    if not chunks:
        logger.warning("No chunks produced for %s/%s", maxx_id, doc_title)
        return 0

    # --- Embed (batch — one API call for the whole doc) ---
    embedder = get_embedder()
    vectors: list[list[float]] = await asyncio.to_thread(embedder.embed_documents, chunks)

    # --- Delete old chunks (idempotent re-ingest) ---
    await db.execute(
        text("DELETE FROM rag_documents WHERE maxx_id = :mid AND doc_title = :dt"),
        {"mid": maxx_id, "dt": doc_title},
    )

    # --- Bulk insert ---
    now = datetime.utcnow().isoformat()
    file_size = len(content.encode("utf-8"))
    rows = [
        {
            "maxx_id": maxx_id,
            "doc_title": doc_title,
            "chunk_index": i,
            "content": chunk,
            "embedding": _vec_to_pg_str(vec),
            "metadata": json.dumps({
                "source_file": os.path.basename(source_file) if source_file else "",
                "file_size": file_size,
                "ingested_at": now,
            }),
        }
        for i, (chunk, vec) in enumerate(zip(chunks, vectors))
    ]

    await db.execute(
        text("""
            INSERT INTO rag_documents (maxx_id, doc_title, chunk_index, content, embedding, metadata)
            VALUES (:maxx_id, :doc_title, :chunk_index, :content, CAST(:embedding AS vector), CAST(:metadata AS jsonb))
        """),
        rows,
    )
    await db.commit()

    logger.info("Ingested %d chunks for %s/%s", len(rows), maxx_id, doc_title)
    return len(rows)
