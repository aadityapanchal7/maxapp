"""Fast file-based RAG over the current markdown knowledge base.

Sources, in priority order:
1. repo-root ``rag_docs/<maxx_id>``            -- preferred, current canonical docs
2. ``backend/rag_content/<maxx_id>``           -- legacy fallback content

Retrieval stays cheap and deterministic:
- heading-aware markdown chunking
- in-memory BM25 per module
- title / section text included in the search index
- current-base docs get a small score boost over legacy content
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession  # kept for signature parity

logger = logging.getLogger(__name__)

VALID_MAXX_IDS = frozenset({"skinmax", "fitmax", "hairmax", "heightmax", "bonemax"})

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
_PRIMARY_CONTENT_DIR = _REPO_ROOT / "rag_docs"
_LEGACY_CONTENT_DIR = _BACKEND_DIR / "rag_content"

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


@dataclass(frozen=True)
class _DocSource:
    root: Path
    label: str
    priority_boost: float


_DOC_SOURCES = (
    _DocSource(_PRIMARY_CONTENT_DIR, "rag_docs", 1.2),
    _DocSource(_LEGACY_CONTENT_DIR, "rag_content", 1.0),
)


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


def _iter_markdown_files(maxx_id: str) -> list[tuple[_DocSource, Path]]:
    picked: list[tuple[_DocSource, Path]] = []
    seen_keys: set[str] = set()
    for source in _DOC_SOURCES:
        folder = source.root / maxx_id
        if not folder.exists():
            continue
        for md in sorted(folder.glob("*.md")):
            dedupe_key = md.stem.lower()
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            picked.append((source, md))
    return picked


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


def _load_maxx_index(maxx_id: str) -> _Bm25Index:
    chunks: list[dict] = []
    files = _iter_markdown_files(maxx_id)
    if not files:
        logger.info("RAG: no docs found for %s under %s or %s", maxx_id, _PRIMARY_CONTENT_DIR, _LEGACY_CONTENT_DIR)
        return _Bm25Index([])

    for source, md in files:
        try:
            body = md.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("RAG: couldn't read %s: %s", md, e)
            continue
        doc_title = md.stem
        rel_source = str(md.relative_to(_REPO_ROOT if source.root == _PRIMARY_CONTENT_DIR else _BACKEND_DIR))
        for block in _split_markdown_with_headings(body):
            section = block["section"] or doc_title
            content = block["content"]
            search_text = "\n".join(part for part in (doc_title, section, content) if part)
            chunks.append({
                "content": content,
                "search_text": search_text,
                "doc_title": doc_title,
                "chunk_index": int(block["chunk_index"]),
                "priority_boost": source.priority_boost,
                "metadata": {
                    "source": rel_source,
                    "section": section,
                    "source_set": source.label,
                },
            })

    logger.info("RAG: indexed %s (%d chunks across %d files)", maxx_id, len(chunks), len(files))
    return _Bm25Index(chunks)


def _get_index(maxx_id: str) -> _Bm25Index:
    idx = _INDEX.get(maxx_id)
    if idx is None:
        idx = _load_maxx_index(maxx_id)
        _INDEX[maxx_id] = idx
    return idx


def reload_indexes() -> None:
    """Clear the in-memory cache. Call after editing rag docs."""
    _INDEX.clear()


async def retrieve_chunks(
    db: "AsyncSession",  # kept for API compatibility; unused
    maxx_id: str,
    query: str,
    k: int = 4,
    min_similarity: float = 0.5,
) -> list[dict]:
    """Return top-k BM25-scored chunks for the requested module."""
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


def embed_text(*_args, **_kwargs):  # pragma: no cover
    raise RuntimeError(
        "embed_text is no longer used — file-based RAG reads from rag_docs/ and backend/rag_content/."
    )


def _vec_to_pg_str(*_args, **_kwargs):  # pragma: no cover
    raise RuntimeError("pgvector helpers are gone — file-based RAG doesn't use vectors.")
