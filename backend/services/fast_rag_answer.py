"""Direct retrieval + answer path for straightforward knowledge questions.

This path is intentionally lighter than the tool-calling agent:
- no agent executor
- no tool schema overhead
- small prompt with cited evidence only
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from config import settings
from services.lc_providers import get_chat_llm_with_fallback
from services.rag_service import retrieve_chunks

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


async def answer_from_rag(
    *,
    message: str,
    maxx_hints: list[str],
    active_maxx: Optional[str] = None,
    max_chunks: Optional[int] = None,
) -> tuple[str, list[dict]]:
    """Return a direct RAG answer and the retrieved evidence used."""
    hints = [h for h in (maxx_hints or []) if h]
    if not hints and active_maxx:
        hints = [active_maxx]
    if not hints:
        return "", []

    k_total = int(max_chunks or getattr(settings, "rag_top_k", 4) or 4)
    k_per_maxx = max(2, k_total // max(1, len(hints)) + 1)

    async def _one(maxx: str) -> list[dict]:
        rows = await retrieve_chunks(None, maxx, message, k=k_per_maxx, min_similarity=0.45)
        return [{**row, "_maxx": maxx} for row in rows]

    gathered = await asyncio.gather(*[_one(h) for h in hints])
    retrieved = [row for rows in gathered for row in rows]
    retrieved.sort(key=lambda c: c.get("similarity", 0.0), reverse=True)
    retrieved = retrieved[:k_total]
    if not retrieved:
        return "", []

    evidence_lines: list[str] = []
    for i, chunk in enumerate(retrieved, 1):
        meta = chunk.get("metadata") or {}
        source = meta.get("source") or f"{chunk.get('_maxx')}/{chunk.get('doc_title')}.md"
        section = meta.get("section") or chunk.get("doc_title") or "section"
        evidence_lines.append(
            f"[{i}] source={source} | section={section}\n{chunk.get('content', '').strip()}"
        )

    llm = get_chat_llm_with_fallback(max_tokens=420).bind(temperature=0.2)
    human = (
        f"User question:\n{message.strip()}\n\n"
        f"Evidence:\n{chr(10).join(evidence_lines)}"
    )
    try:
        resp = await llm.ainvoke([SystemMessage(content=_SYSTEM), HumanMessage(content=human)])
        text = getattr(resp, "content", resp)
        if isinstance(text, list):
            text = "\n".join(str(x) for x in text)
        return str(text or "").strip(), retrieved
    except Exception as e:
        logger.warning("fast rag answer failed: %s", e)
        return "", retrieved
