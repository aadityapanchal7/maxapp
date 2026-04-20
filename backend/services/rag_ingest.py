"""Local document validation helpers for the live file-based BM25 RAG.

No vectors or database writes live here anymore. The canonical source of truth
is the markdown content in ``rag_docs/`` plus the legacy fallback docs in
``backend/rag_content/``. These helpers let scripts verify that the docs parse
into usable chunks and refresh the in-memory index.
"""

from __future__ import annotations

import logging
from pathlib import Path

from services.rag_service import VALID_MAXX_IDS, _split_markdown_with_headings, reload_indexes

logger = logging.getLogger(__name__)


def preview_doc_chunks(
    *,
    content: str,
    maxx_id: str,
    doc_title: str,
    source_file: str = "",
) -> list[dict]:
    """Return the chunk structure that the live retriever would index."""
    if maxx_id not in VALID_MAXX_IDS:
        raise ValueError(f"Unknown maxx_id '{maxx_id}'. Must be one of: {sorted(VALID_MAXX_IDS)}")
    if not content or not content.strip():
        raise ValueError(f"Document '{doc_title}' has empty content")

    chunks = _split_markdown_with_headings(content)
    source_name = Path(source_file).name if source_file else ""
    return [
        {
            "doc_title": doc_title,
            "chunk_index": int(chunk["chunk_index"]),
            "section": chunk["section"] or doc_title,
            "content": chunk["content"],
            "source_file": source_name,
        }
        for chunk in chunks
        if str(chunk.get("content") or "").strip()
    ]


def ingest_doc(
    *,
    content: str,
    maxx_id: str,
    doc_title: str,
    source_file: str = "",
    reload_index: bool = False,
) -> int:
    """Validate a doc against the live chunker and optionally clear cached indexes."""
    chunks = preview_doc_chunks(
        content=content,
        maxx_id=maxx_id,
        doc_title=doc_title,
        source_file=source_file,
    )
    if reload_index:
        reload_indexes()
    logger.info("Validated %d file-based RAG chunks for %s/%s", len(chunks), maxx_id, doc_title)
    return len(chunks)
