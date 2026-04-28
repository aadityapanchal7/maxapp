"""Direct retrieval + answer path for straightforward knowledge questions."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from config import settings
from services.chat_telemetry import log_prompt_budget
from services.lc_providers import get_chat_llm_with_fallback
from services.rag_prompt_selector import _LEXICONS, select_rag_system_prompt
from services.rag_service import retrieve_chunks
from services.token_budget import count_tokens

logger = logging.getLogger(__name__)


# Per-module fallback expansion terms. Only the highest-weight (3) lexicon
# entries — they push BM25 toward canonical doc content when the user's
# unexpanded query produces zero hits. Stripped to single-word tokens; multi-
# word phrases dilute the tokenizer with no extra recall.
_EXPANSION_TERMS: dict[str, list[str]] = {
    maxx: [t for t, w in lex.items() if w >= 3 and " " not in t]
    for maxx, lex in _LEXICONS.items()
}


def _expand_query(query: str, maxx: str) -> str:
    """Append module-anchor terms to a short query that needs help.

    Only used as a SECOND-PASS retrieval fallback when the unexpanded query
    returns nothing — running expansion on every query was empirically worse
    (long-tail queries got dragged into the most-anchor-heavy doc, e.g. all
    bonemax queries pulled toward the Bonesmashing doc).
    """
    if len(query.split()) >= 8:
        return query
    expansion = _EXPANSION_TERMS.get(maxx, [])
    if not expansion:
        return query
    q_lower = query.lower()
    extras = [t for t in expansion[:6] if t not in q_lower]
    if not extras:
        return query
    return f"{query} {' '.join(extras)}"

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
        # Pass 1: original query — this is what works for ~95% of turns.
        rows = await retrieve_chunks(
            None,
            maxx,
            message,
            k=k_per_maxx,
            min_similarity=min_similarity,
        )
        if rows:
            return [{**row, "_maxx": maxx} for row in rows]
        # Pass 2 (fallback): query expansion. Only fires when the original
        # query produced zero hits — typical case is a 1-2 word slang query
        # whose tokens don't match any indexed doc title verbatim.
        expanded = _expand_query(message, maxx)
        if expanded == message:
            return []
        rows = await retrieve_chunks(
            None,
            maxx,
            expanded,
            k=k_per_maxx,
            min_similarity=min_similarity,
        )
        return [{**row, "_maxx": maxx} for row in rows]

    gathered = await asyncio.gather(*[_one(h) for h in hints])
    retrieved = [row for rows in gathered for row in rows]
    retrieved.sort(key=lambda c: c.get("similarity", 0.0), reverse=True)
    return retrieved[:k_total]


_RESPONSE_LENGTH_BLOCKS: dict[str, str] = {
    "concise": (
        "\n\n## USER RESPONSE LENGTH PREFERENCE: CONCISE  (overrides any other length rule above)\n"
        "- Hard cap: 1 sentence. 2 only if the question literally has two parts.\n"
        "- No bullets, no headers, no lists, no lead-ins.\n"
        "- One inline citation is fine; skip others. Pick the single most useful specific."
    ),
    "medium": (
        "\n\n## USER RESPONSE LENGTH PREFERENCE: MEDIUM  (default)\n"
        "- 2-3 sentences. Or up to 4 short bullets if a list genuinely helps.\n"
        "- Answer first, then one concrete specific (product, dose, timing, or timeframe) with inline citation."
    ),
    "detailed": (
        "\n\n## USER RESPONSE LENGTH PREFERENCE: DETAILED  (overrides any other length rule above)\n"
        "- Up to ~8 sentences, or a tight bulleted structure. Still lowercase, still Max's voice — length is not license to pad.\n"
        "- Every specific you name (ingredient %, minutes, reps, macros) needs an inline citation.\n"
        "- Structure: direct answer → specifics with citations → one sentence on why. No intros, no end-summaries."
    ),
}


def _length_suffix(response_length: Optional[str]) -> str:
    key = (response_length or "").strip().lower()
    return _RESPONSE_LENGTH_BLOCKS.get(key, _RESPONSE_LENGTH_BLOCKS["medium"])


async def answer_from_chunks(
    *,
    message: str,
    retrieved: list[dict],
    maxx_hints: Optional[list[str]] = None,
    active_maxx: Optional[str] = None,
    user_context_str: Optional[str] = None,
    response_length: Optional[str] = None,
) -> str:
    """Answer a knowledge question from pre-retrieved evidence only.

    The system prompt is composed by `select_rag_system_prompt()` — it pulls
    `rag_answer_system` from the Supabase `system_prompts` cache and appends
    the best-matching `{maxx_id}_coaching_reference` based on the query.

    If `user_context_str` is provided (schedule / profile / onboarding summary)
    it is injected into the user message so grounded answers can reference the
    caller's live state without pulling the full coaching context hot path.
    """
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

    # Fall back to chunk-origin maxx when caller didn't pass hints (e.g. graph
    # retrieval already tagged each chunk with _maxx).
    if not maxx_hints:
        chunk_maxxes = [c.get("_maxx") for c in retrieved if c.get("_maxx")]
        maxx_hints = list(dict.fromkeys(m for m in chunk_maxxes if isinstance(m, str)))

    selection = select_rag_system_prompt(
        message, maxx_hints=maxx_hints, active_maxx=active_maxx
    )
    system_prompt = selection.system_prompt + _length_suffix(response_length)
    logger.info(
        "[fast_rag] selector chosen_maxx=%s score=%d runner_up=%d reason=%s length=%s",
        selection.chosen_maxx, selection.score, selection.runner_up_score, selection.reason,
        (response_length or "medium"),
    )

    length_key = (response_length or "").strip().lower()
    max_tokens = 120 if length_key == "concise" else 640 if length_key == "detailed" else 420
    llm = get_chat_llm_with_fallback(max_tokens=max_tokens, temperature=0.2)
    from langchain_core.messages import HumanMessage, SystemMessage

    context_block = ""
    if user_context_str:
        context_block = f"User context (schedule, profile, onboarding):\n{user_context_str.strip()}\n\n"

    human = (
        f"{context_block}"
        f"User question:\n{message.strip()}\n\n"
        f"Evidence from module docs:\n{chr(10).join(evidence_lines)}"
    )
    system_tokens = count_tokens(system_prompt)
    user_tokens = count_tokens(message)
    chunk_tokens = sum(count_tokens(c.get("content") or "") for c in retrieved)
    log_prompt_budget(
        path="fast_rag",
        system_tokens=system_tokens,
        coaching_context_tokens=count_tokens(user_context_str or ""),
        history_tokens=0,
        chunk_tokens=chunk_tokens,
        user_tokens=user_tokens,
        total_tokens=system_tokens + user_tokens + chunk_tokens + count_tokens(user_context_str or ""),
    )
    try:
        resp = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=human)])
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
    user_context_str: Optional[str] = None,
    response_length: Optional[str] = None,
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
    answer = await answer_from_chunks(
        message=message,
        retrieved=retrieved,
        maxx_hints=maxx_hints,
        active_maxx=active_maxx,
        user_context_str=user_context_str,
        response_length=response_length,
    )
    return answer, retrieved
