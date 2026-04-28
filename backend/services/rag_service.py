"""Fast DB-backed RAG over the rag_documents table in Supabase.

Content is stored in the ``rag_documents`` table (one row per document or chunk,
grouped by ``maxx_id`` + ``doc_title``).  On first query for a module the rows
are fetched, reassembled into full markdown per doc, chunked with a heading-aware
splitter, and indexed with in-memory BM25.  Subsequent queries hit the cache.

Call ``reload_indexes()`` (or hit the admin endpoint) after editing content in
the Supabase dashboard to rebuild the cache.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession  # kept for signature parity

from config import settings
from services.chat_telemetry import log_retrieval

logger = logging.getLogger(__name__)

VALID_MAXX_IDS = frozenset({"skinmax", "fitmax", "hairmax", "heightmax", "bonemax", "general"})

_INDEX: dict[str, "_Bm25Index"] = {}

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for", "from",
    "how", "i", "in", "is", "it", "its", "my", "of", "on", "or", "should", "that",
    "the", "this", "to", "was", "were", "what", "when", "where", "which", "who",
    "why", "with", "you", "your",
})


def _tokenize(s: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((s or "").lower()) if t not in _STOP and len(t) > 1]


def _chunk_id(*, source: str, doc_title: str, section: str, chunk_index: int) -> str:
    """Stable, human-readable chunk identifier for the audit trail.

    Format: {doc_title}:{chunk_index}:{sha1_of_source+title+section+index[:12]}.
    The hash lets the same (title, index) coexist across doc variants without
    collision; the prefix keeps logs scannable.
    """
    raw = f"{source}|{doc_title}|{section}|{chunk_index}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{doc_title}:{chunk_index}:{digest}"


class _Bm25Index:
    """Minimal BM25Okapi over already-built chunks."""

    def __init__(self, chunks: list[dict], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.tokens = [_tokenize(c["search_text"]) for c in chunks]
        self.N = len(chunks) or 1
        self.avgdl = sum(len(t) for t in self.tokens) / self.N if self.tokens else 0.0
        self.k1 = k1
        self.b = b
        df: dict[str, int] = {}
        for toks in self.tokens:
            for term in set(toks):
                df[term] = df.get(term, 0) + 1
        self.idf = {
            term: math.log((self.N - n + 0.5) / (n + 0.5) + 1.0)
            for term, n in df.items()
        }

    def score(self, query_tokens: list[str]) -> list[float]:
        scores = [0.0] * self.N
        for i, doc_tokens in enumerate(self.tokens):
            if not doc_tokens:
                continue
            dl = len(doc_tokens)
            tf_map: dict[str, int] = {}
            for token in doc_tokens:
                tf_map[token] = tf_map.get(token, 0) + 1
            score = 0.0
            for q in query_tokens:
                tf = tf_map.get(q, 0)
                if tf == 0:
                    continue
                idf = self.idf.get(q, 0.0)
                denom = tf + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                score += idf * (tf * (self.k1 + 1)) / (denom or 1)
            scores[i] = score
        return scores

    def top_k(self, query: str, k: int, min_score: float) -> list[dict]:
        q_toks = _tokenize(query)
        if not q_toks:
            return []
        scores = self.score(q_toks)
        ranked = sorted(range(self.N), key=lambda i: scores[i], reverse=True)
        out: list[dict] = []
        for idx in ranked[: max(k * 3, k)]:
            base_score = scores[idx]
            chunk = self.chunks[idx]
            boosted = base_score * float(chunk.get("priority_boost", 1.0))
            if boosted < min_score:
                continue
            out.append({
                "id": chunk["id"],
                "content": chunk["content"],
                "doc_title": chunk["doc_title"],
                "chunk_index": chunk["chunk_index"],
                "metadata": chunk.get("metadata") or {},
                "similarity": round(float(boosted), 3),
            })
        out.sort(key=lambda c: c.get("similarity", 0.0), reverse=True)
        return out[:k]


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", (line or "").strip())


def _split_markdown_with_headings(body: str) -> list[dict]:
    """Chunk markdown by heading path first, then by paragraph budget."""
    lines = (body or "").splitlines()
    heading_path: list[str] = []
    blocks: list[dict] = []
    current_lines: list[str] = []

    def _flush() -> None:
        text = "\n".join(current_lines).strip()
        if not text:
            return
        section = " > ".join(heading_path)
        blocks.append({"section": section, "text": text})

    for raw in lines:
        line = raw.rstrip()
        m = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if m:
            _flush()
            current_lines = []
            level = len(m.group(1))
            title = _clean_line(m.group(2))
            if not title:
                continue
            heading_path[:] = heading_path[: level - 1]
            heading_path.append(title)
            continue
        current_lines.append(line)
    _flush()

    chunks: list[dict] = []
    for block in blocks:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", block["text"]) if p.strip()]
        buf = ""
        chunk_index = 0
        for para in paragraphs:
            candidate = f"{buf}\n\n{para}".strip() if buf else para
            if len(candidate) > 1400 and buf:
                chunks.append({
                    "section": block["section"],
                    "chunk_index": chunk_index,
                    "content": buf.strip(),
                })
                chunk_index += 1
                buf = para
            else:
                buf = candidate
        if buf.strip():
            chunks.append({
                "section": block["section"],
                "chunk_index": chunk_index,
                "content": buf.strip(),
            })
    return chunks


async def _fetch_docs_from_db(maxx_id: str) -> list[tuple[str, str]]:
    """Fetch (doc_title, full_body) pairs from rag_documents for a module.

    Rows sharing the same doc_title are concatenated in chunk_index order to
    reassemble the full markdown body.
    """
    from db.sqlalchemy import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT doc_title, chunk_index, content "
                "FROM rag_documents "
                "WHERE maxx_id = :mid "
                "ORDER BY doc_title, chunk_index"
            ),
            {"mid": maxx_id},
        )
        rows = result.fetchall()

    if not rows:
        return []

    grouped: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for doc_title, chunk_index, content in rows:
        grouped[doc_title].append((chunk_index, content))

    docs: list[tuple[str, str]] = []
    for doc_title, parts in grouped.items():
        parts.sort(key=lambda t: t[0])
        full_body = "\n\n".join(content for _, content in parts)
        docs.append((doc_title, full_body))
    return docs


async def _load_maxx_index(maxx_id: str) -> _Bm25Index:
    docs = await _fetch_docs_from_db(maxx_id)
    if not docs:
        logger.info("RAG: no docs found for %s in rag_documents table", maxx_id)
        return _Bm25Index([])

    chunks: list[dict] = []
    # DB-backed provenance: every chunk's `source` is the synthetic path
    # `rag_documents/<maxx>/<doc_title>` so audit logs and _chunk_id stay
    # stable across the file-vs-DB RAG variants.
    for doc_title, body in docs:
        source_path = f"rag_documents/{maxx_id}/{doc_title}"
        for block in _split_markdown_with_headings(body):
            section = block["section"] or doc_title
            content = block["content"]
            search_text = "\n".join(part for part in (doc_title, section, content) if part)
            chunks.append({
                "id": _chunk_id(
                    source=source_path,
                    doc_title=doc_title,
                    section=section,
                    chunk_index=int(block["chunk_index"]),
                ),
                "content": content,
                "search_text": search_text,
                "doc_title": doc_title,
                "chunk_index": int(block["chunk_index"]),
                "priority_boost": 1.0,
                "metadata": {
                    "source": source_path,
                    "section": section,
                },
            })

    logger.info("RAG: indexed %s (%d chunks across %d docs)", maxx_id, len(chunks), len(docs))
    return _Bm25Index(chunks)


async def _get_index(maxx_id: str) -> _Bm25Index:
    idx = _INDEX.get(maxx_id)
    if idx is None:
        idx = await _load_maxx_index(maxx_id)
        _INDEX[maxx_id] = idx
    return idx


def reload_indexes() -> None:
    """Clear the in-memory cache. Call after editing rag docs in Supabase."""
    _INDEX.clear()


async def warm_indexes() -> None:
    """Pre-load every module's BM25 index into the cache.

    Called on app startup so the very first KNOWLEDGE turn doesn't pay the
    ~150-300ms cold-load DB round-trip. Failures are logged but never raise —
    the cache will lazy-load on first query if warmup couldn't reach the DB.
    """
    for maxx in VALID_MAXX_IDS:
        try:
            await _get_index(maxx)
        except Exception as e:
            logger.warning("RAG warmup skipped for %s: %s", maxx, e)
    logger.info("RAG: warmed %d indexes", len(_INDEX))


async def retrieve_chunks(
    db: "AsyncSession",  # kept for API compatibility; unused
    maxx_id: str,
    query: str,
    k: int = 4,
    min_similarity: float = float(getattr(settings, "rag_score_threshold", 0.35) or 0.35),
) -> list[dict]:
    """Return top-k BM25-scored chunks for the requested module.

    Also searches the 'general' index (cross-cutting knowledge like sleep,
    debloat, eyes, stress) and merges results so every answer can draw on
    both module-specific and general content.
    """
    if not query or not query.strip():
        return []
    if maxx_id not in VALID_MAXX_IDS:
        return []
    t0 = time.perf_counter()
    try:
        idx = await _get_index(maxx_id)
        results = idx.top_k(query, k=k, min_score=min_similarity)

        if maxx_id != "general":
            try:
                gen_idx = await _get_index("general")
                gen_results = gen_idx.top_k(query, k=max(k // 2, 2), min_score=min_similarity)
                results.extend(gen_results)
                results.sort(key=lambda c: c.get("similarity", 0.0), reverse=True)
                results = results[:k]
            except Exception:
                pass  # general index may be empty; non-fatal

        log_retrieval(
            maxx_id=maxx_id,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            hits=len(results),
            threshold=min_similarity,
            query_tokens=len(_tokenize(query)),
        )
        return results
    except Exception as e:
        logger.warning("RAG retrieve_chunks failed (maxx=%s): %s", maxx_id, e)
        return []


def embed_text(*_args, **_kwargs):  # pragma: no cover
    raise RuntimeError(
        "embed_text is no longer used — DB-backed RAG reads from rag_documents table."
    )


def _vec_to_pg_str(*_args, **_kwargs):  # pragma: no cover
    raise RuntimeError("pgvector helpers are gone — DB-backed RAG doesn't use vectors.")
