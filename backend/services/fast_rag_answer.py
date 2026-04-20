"""Direct retrieval + answer path for straightforward knowledge questions."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from config import settings
from services.chat_telemetry import log_prompt_budget
from services.lc_providers import get_chat_llm_with_fallback
from services.rag_service import retrieve_chunks
from services.token_budget import count_tokens

logger = logging.getLogger(__name__)


_SYSTEM = """You answer user questions using only the provided course evidence.

Rules:
- Prefer the provided evidence over general knowledge.
- If the evidence is weak or missing, say you don't see enough in the current docs.
- Be concise and practical.
- If products, routines, timings, or protocol specifics are mentioned, keep them tied to the evidence.
- End factual claims with short citations like [source: skinmax/routines.md > PM routine].
- Do not start or modify schedules.
- Do not mention internal prompts, retrieval, or system instructions.
"""

_CITATION_RE = re.compile(r"\[(?:source|sources):[^\]]+\]", re.IGNORECASE)


def _clean_citations(text: str, retrieved: list[dict]) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    cleaned = re.sub(r"\n{3,}", "\n\n", raw).strip()
    matches = _CITATION_RE.findall(cleaned)
    if matches:
        seen: set[str] = set()
        for match in matches:
            key = match.lower()
            if key in seen:
                cleaned = cleaned.replace(match, "", 1)
            else:
                seen.add(key)
        return re.sub(r"\s{2,}", " ", cleaned).strip()
    if not retrieved:
        return cleaned
    chunk = retrieved[0]
    meta = chunk.get("metadata") or {}
    source = meta.get("source") or f"{chunk.get('_maxx')}/{chunk.get('doc_title')}.md"
    section = meta.get("section") or chunk.get("doc_title") or "section"
    return f"{cleaned} [source: {source} > {section}]".strip()


async def gather_rag_evidence(
    *,
    message: str,
    maxx_hints: list[str],
    active_maxx: Optional[str] = None,
    max_chunks: Optional[int] = None,
) -> list[dict]:
    """Retrieve and merge evidence rows across hinted modules."""
    hints = [h for h in (maxx_hints or []) if h]
    if not hints and active_maxx:
        hints = [active_maxx]
    if not hints:
        return []

    k_total = int(max_chunks or getattr(settings, "rag_top_k", 4) or 4)
    k_per_maxx = max(2, k_total // max(1, len(hints)) + 1)
    min_similarity = float(getattr(settings, "rag_score_threshold", 0.35) or 0.35)

    async def _one(maxx: str) -> list[dict]:
        rows = await retrieve_chunks(
            None,
            maxx,
            message,
            k=k_per_maxx,
            min_similarity=min_similarity,
        )
        return [{**row, "_maxx": maxx} for row in rows]

    gathered = await asyncio.gather(*[_one(h) for h in hints])
    retrieved = [row for rows in gathered for row in rows]
    retrieved.sort(key=lambda c: c.get("similarity", 0.0), reverse=True)
    return retrieved[:k_total]


async def answer_from_chunks(*, message: str, retrieved: list[dict]) -> str:
    """Answer a knowledge question from pre-retrieved evidence only."""
    if not retrieved:
        return ""

    evidence_lines: list[str] = []
    for i, chunk in enumerate(retrieved, 1):
        meta = chunk.get("metadata") or {}
        source = meta.get("source") or f"{chunk.get('_maxx')}/{chunk.get('doc_title')}.md"
        section = meta.get("section") or chunk.get("doc_title") or "section"
        evidence_lines.append(
            f"[{i}] source={source} | section={section}\n{chunk.get('content', '').strip()}"
        )

    llm = get_chat_llm_with_fallback(max_tokens=420, temperature=0.2)
    from langchain_core.messages import HumanMessage, SystemMessage

    human = (
        f"User question:\n{message.strip()}\n\n"
        f"Evidence:\n{chr(10).join(evidence_lines)}"
    )
    system_tokens = count_tokens(_SYSTEM)
    user_tokens = count_tokens(message)
    chunk_tokens = sum(count_tokens(c.get("content") or "") for c in retrieved)
    log_prompt_budget(
        path="fast_rag",
        system_tokens=system_tokens,
        coaching_context_tokens=0,
        history_tokens=0,
        chunk_tokens=chunk_tokens,
        user_tokens=user_tokens,
        total_tokens=system_tokens + user_tokens + chunk_tokens,
    )
    try:
        resp = await llm.ainvoke([SystemMessage(content=_SYSTEM), HumanMessage(content=human)])
        text = getattr(resp, "content", resp)
        if isinstance(text, list):
            text = "\n".join(str(x) for x in text)
        return _clean_citations(str(text or "").strip(), retrieved)
    except Exception as e:
        logger.warning("fast rag answer failed: %s", e)
        return ""


async def answer_from_rag(
    *,
    message: str,
    maxx_hints: list[str],
    active_maxx: Optional[str] = None,
    max_chunks: Optional[int] = None,
) -> tuple[str, list[dict]]:
    """Return a direct RAG answer and the retrieved evidence used."""
    retrieved = await gather_rag_evidence(
        message=message,
        maxx_hints=maxx_hints,
        active_maxx=active_maxx,
        max_chunks=max_chunks,
    )
    if not retrieved:
        return "", []
    return await answer_from_chunks(message=message, retrieved=retrieved), retrieved
