"""File-based RAG — no embeddings, no pgvector, no DB magic.

Architecture
============
Course content lives as markdown files under `backend/rag_content/<maxx_id>/*.md`:

    backend/rag_content/
      ├── skinmax/
      │   ├── debloat.md
      │   ├── acne.md
      │   └── sunscreen.md
      ├── hairmax/
      │   └── minoxidil.md
      ├── bonemax/
      │   └── mewing.md
      ├── heightmax/
      └── fitmax/

Each file is split on `\\n\\n` into chunks. A BM25 index is built per maxx_id at
import time and cached in memory. On each chat turn, `retrieve_chunks()` scores
the query against the relevant maxx_id's chunks and returns the top-k.

Why BM25 and not embeddings
---------------------------
- Zero setup: no API key needed for retrieval, no pgvector, no embed cost per turn
- Deterministic: same query always returns the same chunks
- Fast: scoring against a few hundred chunks is <10ms
- Good enough: for keyword-heavy questions ("how do i debloat", "what is mewing")
  BM25 matches or beats embeddings on precision

The public API matches what api/chat.py expects, so swapping back to embeddings
later is a drop-in replacement.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession  # for type hint parity

logger = logging.getLogger(__name__)

VALID_MAXX_IDS = frozenset({"skinmax", "fitmax", "hairmax", "heightmax", "bonemax"})

_CONTENT_DIR = Path(__file__).resolve().parent.parent / "rag_content"

# In-memory index built at first access. Keyed by maxx_id.
_INDEX: dict[str, "_Bm25Index"] = {}


# ---------------------------------------------------------------------------
# Tiny BM25 implementation — vendored so we don't need rank_bm25 dependency.
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for", "from",
    "how", "i", "in", "is", "it", "its", "my", "of", "on", "or", "should", "that",
    "the", "this", "to", "was", "were", "what", "when", "where", "which", "who",
    "why", "with", "you", "your",
})


def _tokenize(s: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((s or "").lower()) if t not in _STOP and len(t) > 1]


class _Bm25Index:
    """Minimal BM25Okapi. Enough for a few hundred chunks per maxx_id."""

    def __init__(self, chunks: list[dict], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.tokens = [_tokenize(c["content"]) for c in chunks]
        self.N = len(chunks) or 1
        self.avgdl = sum(len(t) for t in self.tokens) / self.N if self.tokens else 0.0
        self.k1 = k1
        self.b = b
        # Document frequency per term
        df: dict[str, int] = {}
        for toks in self.tokens:
            for term in set(toks):
                df[term] = df.get(term, 0) + 1
        # idf with BM25+ smoothing
        import math
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
            for t in doc_tokens:
                tf_map[t] = tf_map.get(t, 0) + 1
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
        ranked = sorted(
            range(self.N), key=lambda i: scores[i], reverse=True
        )
        out: list[dict] = []
        for idx in ranked[:k]:
            s = scores[idx]
            if s < min_score:
                continue
            c = self.chunks[idx]
            out.append({
                "content": c["content"],
                "doc_title": c["doc_title"],
                "chunk_index": c["chunk_index"],
                "metadata": c.get("metadata") or {},
                "similarity": round(float(s), 3),  # BM25 score, not cosine — same field name for compat
            })
        return out


# ---------------------------------------------------------------------------
# Index builder
# ---------------------------------------------------------------------------

def _split_markdown(body: str) -> list[str]:
    """Chunk a markdown file on blank lines; keep chunks under ~1600 chars."""
    raw_paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body or "") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in raw_paragraphs:
        if len(buf) + len(para) + 2 > 1600 and buf:
            chunks.append(buf.strip())
            buf = para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


def _load_maxx_index(maxx_id: str) -> _Bm25Index:
    folder = _CONTENT_DIR / maxx_id
    chunks: list[dict] = []
    if not folder.exists():
        logger.info("RAG: no content folder for %s at %s — retrieval will return []", maxx_id, folder)
        return _Bm25Index([])

    for md in sorted(folder.glob("*.md")):
        try:
            body = md.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("RAG: couldn't read %s: %s", md, e)
            continue
        doc_title = md.stem
        for i, chunk in enumerate(_split_markdown(body)):
            chunks.append({
                "content": chunk,
                "doc_title": doc_title,
                "chunk_index": i,
                "metadata": {"source": str(md.relative_to(_CONTENT_DIR.parent))},
            })

    logger.info("RAG: indexed %s (%d chunks across %d files)", maxx_id, len(chunks), len(list(folder.glob("*.md"))))
    return _Bm25Index(chunks)


def _get_index(maxx_id: str) -> _Bm25Index:
    idx = _INDEX.get(maxx_id)
    if idx is None:
        idx = _load_maxx_index(maxx_id)
        _INDEX[maxx_id] = idx
    return idx


def reload_indexes() -> None:
    """Clear the in-memory cache. Call after editing files in rag_content/."""
    _INDEX.clear()


# ---------------------------------------------------------------------------
# Public API — same signature the chat code already imports.
# ---------------------------------------------------------------------------

async def retrieve_chunks(
    db: "AsyncSession",  # kept for API compatibility; unused
    maxx_id: str,
    query: str,
    k: int = 4,
    min_similarity: float = 0.5,
) -> list[dict]:
    """Return top-k BM25-scored chunks from the maxx_id content folder.

    `db` is accepted for signature compatibility with the old pgvector version.
    `min_similarity` here maps to a minimum BM25 score, not cosine similarity.
    BM25 scores typically range 0–20; 0.5 is a permissive threshold that still
    filters out totally off-topic queries.

    Returns [] for invalid maxx_id, blank query, or when no chunks clear the bar.
    """
    if not query or not query.strip():
        return []
    if maxx_id not in VALID_MAXX_IDS:
        return []
    try:
        idx = _get_index(maxx_id)
        return idx.top_k(query, k=k, min_score=min_similarity)
    except Exception as e:
        logger.warning("RAG retrieve_chunks failed (maxx=%s): %s", maxx_id, e)
        return []


# Back-compat stubs — old ingest script imported these. File-based RAG doesn't
# need embeddings, so these raise helpful errors if something still calls them.

def embed_text(*_args, **_kwargs):  # pragma: no cover
    raise RuntimeError(
        "embed_text is no longer used — file-based RAG reads from backend/rag_content/. "
        "Drop markdown files into the maxx_id folder instead of ingesting."
    )


def _vec_to_pg_str(*_args, **_kwargs):  # pragma: no cover
    raise RuntimeError("pgvector helpers are gone — file-based RAG doesn't use vectors.")
